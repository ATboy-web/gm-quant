"""
offline_backtest.py - V20 离线回测脚本

V20 改进:
  1. 新增反转确认策略(RT)
  2. 6策略体系: MR + MOM + VP + BK + DV + RT
  3. 化工/新能源/煤炭行业针对性优化

V19.2 改进:
  1. 新增突破策略(BK)和红利策略(DV)
  2. 新能源/公用事业参数优化
  3. 策略工厂支持5策略

V19 改进:
  1. 行业差异化策略参数
  2. 策略工厂动态创建
  3. executor 执行器复用
  4. 与 GM 终端解耦，纯 Python 回测
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from gm.api import *

import config
import indicators
import stock_pool
import screener
import sector_config
import executor
import strategy_mr
import strategy_momentum
import strategy_vp
import strategy_breakout
import strategy_dividend
import strategy_reversal
import fusion

# =============================================================================
# 全局设置
# =============================================================================

set_token(config.GM_TOKEN)

SYMBOLS = stock_pool.get_all_symbols()
MARKET_INDEX = config.MARKET_INDEX
SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()

print('=' * 60)
print('  V20 离线回测 — 六策略行业差异化融合框架')
print('  策略: MR + MOM + VP + BK + DV + RT')
print('  V20: RT反转确认 + 弱势行业优化')
print('  股票池: %d 只 / %d 行业' % (len(SYMBOLS), len(stock_pool.get_sector_list())))
print('=' * 60)
sector_config.print_summary()


# =============================================================================
# 数据获取
# =============================================================================

def fetch_history(symbol, start, end, freq='1d'):
    try:
        df = history(
            symbol=symbol, frequency=freq,
            start_time=start, end_time=end,
            adjust=ADJUST_PREV, df=True
        )
        if df is not None and len(df) > 0:
            df = df.sort_values('bob').reset_index(drop=True)
            return df
    except Exception:
        pass
    return None


def preload_all_data(start, end):
    print('[数据] 正在下载历史数据...')
    data = {}
    all_syms = list(SYMBOLS) + [MARKET_INDEX]

    for i, sym in enumerate(all_syms):
        df = fetch_history(sym, start, end)
        if df is not None and len(df) >= config.MIN_DATA_BARS:
            data[sym] = df
        if (i + 1) % 10 == 0 or (i + 1) == len(all_syms):
            print('  进度: %d/%d' % (i + 1, len(all_syms)))

    print('[数据] 完成: 成功 %d/%d' % (len(data), len(all_syms)))
    return data


# =============================================================================
# V19 回测引擎
# =============================================================================

class V19BacktestEngine:

    def __init__(self, data, start_cash=25000):
        self.data = data
        self.cash = float(start_cash)
        self.initial_cash = float(start_cash)
        self.positions = {}
        self.trades = []
        self.daily_values = []

        # V19 执行器
        self.exec_engine = executor.TradeExecutor()

        if MARKET_INDEX in data:
            self.bar_dates = list(data[MARKET_INDEX]['bob'].dt.strftime('%Y-%m-%d'))

        print('[引擎] 交易日数: %d | 初始资金: %.0f'
              % (len(self.bar_dates), start_cash))

        # 策略统计
        self.strategy_stats = {
            'MR':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'MOM': {'wins': 0, 'total': 0, 'pnl': 0.0},
            'VP':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'BK':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'DV':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'RT':  {'wins': 0, 'total': 0, 'pnl': 0.0},
        }
        # 行业统计
        self.sector_stats = {}

    def run(self):
        print('[引擎] 开始回测...')
        for i, date_str in enumerate(self.bar_dates):
            self._daily_bar(date_str, i)
            self._record_daily_value(date_str, i)

            if (i + 1) % 50 == 0:
                total_val = self.daily_values[-1]['total'] if self.daily_values else 0
                pos_count = len(self.positions)
                ret = (total_val - self.initial_cash) / self.initial_cash * 100
                print('  [%s] 进度 %d/%d | 净值 %.0f (%+.1f%%) | 持仓 %d'
                      % (date_str, i + 1, len(self.bar_dates), total_val, ret, pos_count))

        self._print_summary()

    def _daily_bar(self, date_str, bar_idx):
        if bar_idx < config.DATA_COUNT:
            return

        # V19.2: 清理过期冷却期
        self.exec_engine.cleanup_cooldowns(date_str)

        regime = self._detect_regime(bar_idx)
        regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

        # 出场检查（使用 executor）
        pos_info_copy = {sym: dict(pos) for sym, pos in self.positions.items()}
        data_cache = {}
        for sym in list(self.positions.keys()) + SYMBOLS:
            df = self._get_df_slice(sym, bar_idx)
            if df is not None:
                data_cache[sym] = df

        sells = self.exec_engine.check_exits(
            pos_info_copy, data_cache, regime, today_str=date_str
        )

        for sym, price, vote, info in sells:
            if sym in self.positions:
                self._execute_sell(sym, price, vote['reason'], date_str)
                # V19.2: 记录卖出，启动冷却期
                self.exec_engine.record_sell(sym, date_str)

        # 行业动量
        sector_momentum = self._calc_sector_momentum(bar_idx)

        # 入场
        max_pos = regime_cfg['max_positions']
        occupied = set(p.get('sector') for p in self.positions.values())
        if len(self.positions) < max_pos:
            candidates = self.exec_engine.find_buy_candidates(
                SYMBOLS, occupied, self.positions,
                data_cache, sector_momentum, regime
            )
            self._do_buys(candidates, max_pos, date_str)

    def _do_buys(self, candidates, max_pos, date_str):
        remaining = max_pos - len(self.positions)
        if remaining <= 0:
            return

        taken_sectors = set(p.get('sector') for p in self.positions.values())
        taken_count = 0

        for c in candidates:
            if taken_count >= remaining:
                break
            sector = c['sector']
            if sector in taken_sectors:
                continue

            sym = c['symbol']
            price = c['price']

            qty = self.exec_engine.calc_position_size(
                c, self.cash, remaining - taken_count
            )
            if qty < 100:
                continue

            self.cash -= price * qty
            self.positions[sym] = {
                'vol': qty, 'cost': price, 'peak': price,
                'entry_date': date_str, 'sector': sector,
                'strategy': c['best_strategy'],
                'voters': c.get('voters', []),
                'confidence': c['confidence'],
            }
            taken_sectors.add(sector)
            taken_count += 1

            rsi_str = ' RSI=%.0f' % c['rsi'] if c.get('rsi') else ''
            print('[买入] %s | %s | %s | 策略:%s | %.2f×%d%s'
                  % (date_str, sym, c['reason'],
                     c['best_strategy'], price, qty, rsi_str))

    def _get_df_slice(self, symbol, bar_idx):
        if symbol not in self.data:
            return None
        df = self.data[symbol]
        if bar_idx >= len(df):
            return None
        return df.iloc[:bar_idx + 1]

    def _detect_regime(self, bar_idx):
        df = self._get_df_slice(MARKET_INDEX, bar_idx)
        if df is None:
            return 'range'
        closes = df['close'].values
        return indicators.classify_regime(
            closes,
            ma_period=config.REGIME_MA_PERIOD,
            bear_threshold=config.REGIME_BEAR_THRESHOLD
        )

    def _execute_sell(self, sym, price, reason, date_str):
        if sym not in self.positions:
            return
        pos = self.positions[sym]
        vol = pos['vol']
        pnl_pct = (price - pos['cost']) / pos['cost'] * 100
        sector = pos.get('sector', '未知')
        strat = pos.get('strategy', '?')

        self.cash += price * vol

        self.trades.append({
            'date': date_str, 'symbol': sym, 'side': 'SELL',
            'price': price, 'vol': vol, 'pnl_pct': pnl_pct,
            'reason': reason, 'sector': sector, 'strategy': strat,
        })

        # 行业统计
        if sector not in self.sector_stats:
            self.sector_stats[sector] = {'wins': 0, 'total': 0, 'pnl': 0.0}
        self.sector_stats[sector]['total'] += 1
        self.sector_stats[sector]['pnl'] += pnl_pct
        if pnl_pct > 0:
            self.sector_stats[sector]['wins'] += 1

        del self.positions[sym]

        # 策略统计
        if strat in self.strategy_stats:
            self.strategy_stats[strat]['total'] += 1
            self.strategy_stats[strat]['pnl'] += pnl_pct
            if pnl_pct > 0:
                self.strategy_stats[strat]['wins'] += 1

        print('[卖出] %s | %s | %s | 价%.2f | %+.2f%% | %s'
              % (date_str, sym, reason, price, pnl_pct, strat))

    def _calc_sector_momentum(self, bar_idx):
        momentum = {}
        for sector in stock_pool.get_sector_list():
            stocks = stock_pool.filter_by_sector(sector)
            rets = []
            for sym in stocks:
                df = self._get_df_slice(sym, bar_idx)
                if df is None or len(df) < 12:
                    continue
                closes = df['close'].values
                if closes[-12] > 0:
                    ret = (closes[-1] / closes[-12] - 1)
                    rets.append(ret)
            if rets:
                momentum[sector] = float(np.mean(rets))
            else:
                momentum[sector] = 0.0
        return momentum

    def _record_daily_value(self, date_str, bar_idx):
        market_value = 0.0
        for sym, pos in self.positions.items():
            df = self._get_df_slice(sym, bar_idx)
            if df is not None and len(df) > 0:
                cur_price = float(df['close'].values[-1])
                market_value += cur_price * pos['vol']

        total_value = self.cash + market_value
        self.daily_values.append({
            'date': date_str, 'cash': self.cash,
            'market': market_value, 'total': total_value,
        })

    def _print_summary(self):
        if not self.daily_values:
            print('[结果] 无交易记录')
            return

        df = pd.DataFrame(self.daily_values)
        final_value = df['total'].iloc[-1]
        initial = self.initial_cash
        total_return = (final_value - initial) / initial * 100

        df['cummax'] = df['total'].cummax()
        df['drawdown'] = (df['total'] - df['cummax']) / df['cummax']
        max_dd = df['drawdown'].min() * 100

        sell_trades = [t for t in self.trades if t['side'] == 'SELL']
        win_trades = [t for t in sell_trades if t['pnl_pct'] > 0]
        win_rate = len(win_trades) / len(sell_trades) * 100 if sell_trades else 0

        print()
        print('=' * 60)
        print('  V20 六策略行业差异化回测结果摘要')
        print('=' * 60)
        print('  初始资金:   %.0f' % initial)
        print('  最终净值:   %.0f' % final_value)
        print('  总收益率:   %+.2f%%' % total_return)
        print('  最大回撤:   %.2f%%' % max_dd)
        print('  交易次数:   %d (卖出%d)' % (len(self.trades), len(sell_trades)))
        print('  胜率:       %.1f%% (%d/%d)'
              % (win_rate, len(win_trades), len(sell_trades)))
        print('  平均盈亏:   %+.2f%%' %
              (np.mean([t['pnl_pct'] for t in sell_trades]) if sell_trades else 0))

        # ---- 策略分项 ----
        print('  ---- 策略分项 ----')
        for name in ['MR', 'MOM', 'VP', 'BK', 'DV', 'RT']:
            ss = self.strategy_stats[name]
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                print('  %s: 交易%d 胜率%.1f%% 累计盈亏%+.1f%%'
                      % (name, ss['total'], wr, ss['pnl']))

        # ---- 行业分项 ----
        print('  ---- 行业分项 ----')
        for sector in sorted(self.sector_stats.keys()):
            ss = self.sector_stats[sector]
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                print('  %-6s: 交易%d 胜率%.1f%% 累计%+.1f%%'
                      % (sector, ss['total'], wr, ss['pnl']))

        print('=' * 60)

        # 最近 10 笔交易
        if sell_trades:
            print()
            print('  最近 10 笔卖出:')
            for t in sell_trades[-10:]:
                print('  %s %s %-6s %+.2f%% %s %s'
                      % (t['date'], t['symbol'], t.get('strategy', '?'),
                         t['pnl_pct'], t.get('reason', ''), t.get('sector', '')))


# =============================================================================
# 主程序
# =============================================================================

if __name__ == '__main__':
    start_date = config.BACKTEST_START[:10]
    end_date   = config.BACKTEST_END[:10]

    all_data = preload_all_data(start_date, end_date)

    if MARKET_INDEX not in all_data:
        print('[错误] 无法获取大盘指数数据，退出')
        sys.exit(1)

    if len(all_data) < 5:
        print('[错误] 有效股票数据不足，退出')
        sys.exit(1)

    engine = V19BacktestEngine(all_data, start_cash=config.BACKTEST_CASH)
    engine.run()
