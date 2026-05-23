"""
offline_backtest.py - V18 离线回测脚本

三策略并行 + 投票融合 + KNN 历史匹配。
不依赖掘金终端，直接用 history() API 拉数据模拟回测。
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
import strategy_mr
import strategy_momentum
import strategy_vp
import fusion
import knn_matcher

# =============================================================================
# 全局设置
# =============================================================================

set_token(config.GM_TOKEN)

SYMBOLS = stock_pool.get_all_symbols()
MARKET_INDEX = config.MARKET_INDEX
SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()

print('=' * 60)
print('  V18 离线回测 — 多策略融合框架')
print('  策略: 均值回归 + 动量趋势 + 量价背离')
print('  融合: 投票制 + KNN历史匹配')
print('  股票池: %d 只 / %d 行业' % (len(SYMBOLS), len(stock_pool.get_sector_list())))
print('=' * 60)


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
# V18 回测引擎
# =============================================================================

class V18BacktestEngine:

    def __init__(self, data, start_cash=25000, use_knn=False):
        self.data = data
        self.cash = float(start_cash)
        self.initial_cash = float(start_cash)
        self.positions = {}  # {sym: {vol, cost, peak, entry_date, sector, strategy, voters}}
        self.trades = []
        self.daily_values = []
        self.use_knn = use_knn

        # KNN 匹配器
        self.knn = knn_matcher.KNNMatcher() if use_knn else None

        if MARKET_INDEX in data:
            self.bar_dates = list(data[MARKET_INDEX]['bob'].dt.strftime('%Y-%m-%d'))

        print('[引擎] 交易日数: %d | 初始资金: %.0f | KNN: %s'
              % (len(self.bar_dates), start_cash, '启用' if use_knn else '关闭'))

        # 策略统计
        self.strategy_stats = {
            'MR':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'MOM': {'wins': 0, 'total': 0, 'pnl': 0.0},
            'VP':  {'wins': 0, 'total': 0, 'pnl': 0.0},
        }

    def run(self):
        # ---- KNN 特征库构建 ----
        if self.use_knn:
            self.knn.build_from_data(self.data, self.bar_dates)

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

        regime = self._detect_regime(bar_idx)
        regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

        self._check_exits(date_str, bar_idx, regime_cfg)

        sector_momentum = self._calc_sector_momentum(bar_idx)

        max_pos = regime_cfg['max_positions']
        if len(self.positions) < max_pos:
            self._execute_entries(date_str, bar_idx, sector_momentum, regime_cfg)

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

    # =====================================================================
    # 入场: 三策略打分 + 投票融合
    # =====================================================================

    def _execute_entries(self, date_str, bar_idx, sector_momentum, regime_cfg):
        occupied_sectors = set(p.get('sector') for p in self.positions.values())
        remaining = regime_cfg['max_positions'] - len(self.positions)
        if remaining <= 0:
            return

        regime = self._detect_regime(bar_idx)
        buy_candidates = []

        for sym in SYMBOLS:
            if sym in self.positions:
                continue
            sector = SYMBOL_SECTOR_MAP.get(sym, '未知')
            if sector in occupied_sectors:
                continue

            df = self._get_df_slice(sym, bar_idx)
            if df is None:
                continue

            # 三个策略打分
            mr_sig  = strategy_mr.get_signal(df, sector, sector_momentum, regime) \
                      if config.STRATEGY_MR_ENABLED else None
            mom_sig = strategy_momentum.get_signal(df, sector, sector_momentum, regime) \
                      if config.STRATEGY_MOM_ENABLED else None
            vp_sig  = strategy_vp.get_signal(df, sector, sector_momentum, regime) \
                      if config.STRATEGY_VP_ENABLED else None

            # 融合投票
            vote_result = fusion.vote_entry(mr_sig, mom_sig, vp_sig, regime)

            # KNN 增强（如果启用且投票分歧）
            if self.use_knn and vote_result['position_pct'] < 0.6:
                knn_rec = self.knn.recommend_strategy(df)
                if knn_rec['recommend'] != 'voting' and knn_rec['confidence'] > 0.4:
                    # KNN 推荐某个策略 → 给该策略的信号加权
                    # 简化: 如果 KNN 说应该用某个策略，提高该策略在投票中的权重
                    pass  # 后续实现 KNN 加权投票

            if vote_result['action'] == 'BUY':
                cur_price = float(df['close'].values[-1])
                # 确定主导策略
                highest_score = 0
                best_strategy = 'MR'
                for sig, name in [(mr_sig, 'MR'), (mom_sig, 'MOM'), (vp_sig, 'VP')]:
                    if sig and sig.get('action') == 'BUY':
                        if sig.get('score', 0) > highest_score:
                            highest_score = sig['score']
                            best_strategy = name

                buy_candidates.append({
                    'symbol': sym, 'sector': sector, 'price': cur_price,
                    'confidence': vote_result['confidence'],
                    'position_pct': vote_result['position_pct'],
                    'reason': vote_result['reason'],
                    'best_strategy': best_strategy,
                    'rsi': mr_sig['rsi'] if mr_sig and 'rsi' in mr_sig else 0,
                })

        buy_candidates.sort(key=lambda x: x['confidence'], reverse=True)

        taken_sectors = set(occupied_sectors)
        taken_count = 0

        for c in buy_candidates:
            if taken_count >= remaining:
                break
            if c['sector'] in taken_sectors:
                continue

            sym    = c['symbol']
            sector = c['sector']
            price  = c['price']

            vol_group = stock_pool.get_sector_volatility_group(sector)
            if vol_group == 'high':
                base_pct = config.POSITION_PCT * config.VOL_ADJ_HIGH
            elif vol_group == 'low':
                base_pct = config.POSITION_PCT * config.VOL_ADJ_LOW
            else:
                base_pct = config.POSITION_PCT

            pos_pct = base_pct * c['position_pct']

            allocated = self.cash * pos_pct / max(remaining - taken_count, 1)
            if allocated < price * 100:
                continue

            qty = int(allocated / (price * 100)) * 100
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

            print('[买入] %s | %s(%s) | %s | 策略:%s | %.2f×%d | RSI=%.0f'
                  % (date_str, sector, vol_group, c['reason'],
                     c['best_strategy'], price, qty, c['rsi']))

    # =====================================================================
    # 出场: 各策略独立检查 + 融合投票
    # =====================================================================

    def _check_exits(self, date_str, bar_idx, regime_cfg):
        regime = self._detect_regime(bar_idx)

        for sym in list(self.positions.keys()):
            pos = self.positions[sym]
            df = self._get_df_slice(sym, bar_idx)
            if df is None:
                continue

            closes = df['close'].values
            highs  = df['high'].values
            lows   = df['low'].values
            if len(closes) < 2:
                continue

            cur_price = float(closes[-1])
            if cur_price > pos['peak']:
                pos['peak'] = cur_price

            # 三个策略各自检查出场
            mr_exit  = strategy_mr.check_exit(df, pos, regime, today_str=date_str) \
                       if config.STRATEGY_MR_ENABLED else None
            mom_exit = strategy_momentum.check_exit(df, pos, regime) \
                       if config.STRATEGY_MOM_ENABLED else None
            vp_exit  = strategy_vp.check_exit(df, pos, regime, today_str=date_str) \
                       if config.STRATEGY_VP_ENABLED else None

            # 融合投票（传入归属策略）
            owner_strategy = pos.get('strategy', 'MR')
            vote_result = fusion.vote_exit(mr_exit, mom_exit, vp_exit, regime,
                                           owner_strategy=owner_strategy)

            if vote_result['action'] == 'SELL':
                self._execute_sell(sym, cur_price, vote_result['reason'],
                                   pos, date_str)

    def _execute_sell(self, sym, price, reason, pos, date_str):
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

        del self.positions[sym]

        # 策略统计
        if strat in self.strategy_stats:
            self.strategy_stats[strat]['total'] += 1
            self.strategy_stats[strat]['pnl'] += pnl_pct
            if pnl_pct > 0:
                self.strategy_stats[strat]['wins'] += 1

        print('[卖出] %s | %s | %s | 价%.2f | %+.2f%% | %s'
              % (date_str, sym, reason, price, pnl_pct, strat))

    # =====================================================================
    # 辅助方法
    # =====================================================================

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
        print('  V18 回测结果摘要')
        print('=' * 60)
        print('  初始资金:   %.0f' % initial)
        print('  最终净值:   %.0f' % final_value)
        print('  总收益率:   %+.2f%%' % total_return)
        print('  最大回撤:   %.2f%%' % max_dd)
        print('  交易次数:   %d (买入%d 卖出%d)'
              % (len(self.trades),
                 sum(1 for t in self.trades if t['side'] == 'BUY'),
                 len(sell_trades)))
        print('  胜率:       %.1f%% (%d/%d)'
              % (win_rate, len(win_trades), len(sell_trades)))
        print('  平均盈亏:   %+.2f%%' %
              (np.mean([t['pnl_pct'] for t in sell_trades]) if sell_trades else 0))
        print('  ---- 策略分项 ----')
        for name in ['MR', 'MOM', 'VP']:
            ss = self.strategy_stats[name]
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                print('  %s: 交易%d 胜率%.1f%% 累计盈亏%+.1f%%'
                      % (name, ss['total'], wr, ss['pnl']))
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

    print('[KNN] 模式: %s' % ('启用' if config.FUSION_MODE == 'knn' else '关闭'))
    print()

    all_data = preload_all_data(start_date, end_date)

    if MARKET_INDEX not in all_data:
        print('[错误] 无法获取大盘指数数据，退出')
        sys.exit(1)

    if len(all_data) < 5:
        print('[错误] 有效股票数据不足，退出')
        sys.exit(1)

    use_knn = (config.FUSION_MODE == 'knn')
    engine = V18BacktestEngine(all_data, start_cash=config.BACKTEST_CASH,
                               use_knn=use_knn)
    engine.run()
