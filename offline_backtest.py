"""
offline_backtest.py - V16 离线回测脚本

不依赖掘金终端，直接用 history() API 拉取数据并模拟回测。
用法: python offline_backtest.py
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

# =============================================================================
# 全局设置
# =============================================================================

set_token(config.GM_TOKEN)

SYMBOLS = stock_pool.get_all_symbols()
MARKET_INDEX = config.MARKET_INDEX

print('╔' + '═' * 58 + '╗')
print('║   V16 离线回测 (不依赖掘金终端)')
print('║   股票池: %d 只 / %d 行业' % (len(SYMBOLS), len(stock_pool.get_sector_list())))
print('╚' + '═' * 58 + '╝')


# =============================================================================
# 数据获取
# =============================================================================

def fetch_history(symbol, start, end, freq='1d'):
    """用 GM history() API 拉取历史数据。"""
    try:
        df = history(
            symbol=symbol,
            frequency=freq,
            start_time=start,
            end_time=end,
            adjust=ADJUST_PREV,
            df=True
        )
        if df is not None and len(df) > 0:
            df = df.sort_values('bob').reset_index(drop=True)
            return df
    except Exception as e:
        pass
    return None


def preload_all_data(start, end):
    """
    预加载所有股票 + 大盘指数的历史数据。
    返回: {symbol: DataFrame}
    """
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
# 回测引擎
# =============================================================================

class BacktestEngine:
    """
    简化的回测引擎，模拟每日调仓。
    不考虑手续费、滑点（与 GM 回测保持一致）。
    """

    def __init__(self, data, start_cash=25000):
        self.data = data
        self.cash = float(start_cash)
        self.initial_cash = float(start_cash)
        self.positions = {}   # {symbol: {'vol': int, 'cost': float, 'peak': float, 'entry_date': str, 'sector': str}}
        self.trades = []       # 交易记录
        self.daily_values = [] # 每日净值
        self.bar_dates = []    # 所有交易日

        # 构建统一的交易日历
        if MARKET_INDEX in data:
            self.bar_dates = list(data[MARKET_INDEX]['bob'].dt.strftime('%Y-%m-%d'))

        print('[引擎] 交易日数: %d | 初始资金: %.0f' % (len(self.bar_dates), start_cash))

    def run(self):
        """运行回测。"""
        print('[引擎] 开始回测...')

        for i, date_str in enumerate(self.bar_dates):
            # 每日 14:50 执行（这里简化为用当日收盘价）
            self._daily_bar(date_str, i)
            self._record_daily_value(date_str, i)

        self._print_summary()

    def _daily_bar(self, date_str, bar_idx):
        """
        每日交易逻辑（对应 GM 的 on_bar）。
        """
        # 跳过前 80 根 bar（数据不足无法计算指标）
        if bar_idx < config.DATA_COUNT:
            return

        # Step 1: 市场状态判断
        regime = self._detect_regime(bar_idx)
        regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

        # Step 2: 出场检查
        self._check_exits(date_str, bar_idx, regime_cfg)

        # Step 3: 行业动量
        sector_momentum = self._calc_sector_momentum(bar_idx)

        # Step 4: 选股打分
        candidates = self._screen_all(date_str, bar_idx, sector_momentum)

        # Step 5: 入场
        remaining = regime_cfg['max_positions'] - len(self.positions)
        if remaining > 0 and candidates:
            self._execute_entries(date_str, bar_idx, candidates, remaining, regime_cfg)

    def _get_df_slice(self, symbol, bar_idx):
        """获取截止到 bar_idx 的数据切片。"""
        if symbol not in self.data:
            return None
        df = self.data[symbol]
        if bar_idx >= len(df):
            return None
        return df.iloc[:bar_idx + 1]

    def _detect_regime(self, bar_idx):
        """判断市场状态。"""
        df = self._get_df_slice(MARKET_INDEX, bar_idx)
        if df is None:
            return 'range'
        closes = df['close'].values
        return indicators.classify_regime(
            closes,
            ma_period=config.REGIME_MA_PERIOD,
            bear_threshold=config.REGIME_BEAR_THRESHOLD
        )

    def _check_exits(self, date_str, bar_idx, regime_cfg):
        """检查所有持仓的出场条件。"""
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

            # 更新最高价
            if cur_price > pos['peak']:
                pos['peak'] = cur_price

            # 计算 ATR
            atr = indicators.calc_atr(highs, lows, closes, config.ATR_PERIOD)
            if atr is None:
                atr = cur_price * 0.03

            pnl = (cur_price - pos['cost']) / pos['cost']
            reason = None

            # 条件 1: ATR 止损
            stop_mult = regime_cfg.get('atr_stop_mult', config.ATR_STOP_MULT)
            stop_loss_pct = atr / cur_price * stop_mult
            stop_loss_pct = min(stop_loss_pct, config.STOP_LOSS_CAP)
            stop_loss_pct = max(stop_loss_pct, 0.03)

            if pnl <= -stop_loss_pct:
                reason = 'ATR止损(%.1f%%)' % (stop_loss_pct * 100)

            # 条件 2: ATR 跟踪止盈
            elif pos['peak'] > pos['cost']:
                trail_pct = atr / cur_price * config.ATR_TRAIL_MULT
                trail_pct = max(trail_pct, 0.04)
                if cur_price <= pos['peak'] * (1.0 - trail_pct):
                    reason = 'ATR跟踪(%.1f%%)' % (trail_pct * 100)

            # 条件 3: RSI 过热
            if reason is None:
                rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
                if rsi is not None and rsi > config.RSI_EXIT:
                    reason = 'RSI过热(%.0f)' % rsi

            # 条件 4: 时间止损
            if reason is None:
                entry_date = pos.get('entry_date', date_str)
                held_days = self._count_trading_days(entry_date, date_str)
                if held_days >= config.TIME_STOP_DAYS and pnl < 0.02:
                    reason = '时间止损(%dd)' % held_days

            # 执行卖出
            if reason:
                self._execute_sell(sym, cur_price, reason, pos, date_str, atr / cur_price)

    def _execute_sell(self, sym, price, reason, pos, date_str, vol_pct):
        """执行卖出。"""
        vol = pos['vol']
        pnl_pct = (price - pos['cost']) / pos['cost'] * 100
        sector = pos.get('sector', '未知')

        # 更新资金
        self.cash += price * vol

        # 记录交易
        self.trades.append({
            'date':   date_str,
            'symbol': sym,
            'side':   'SELL',
            'price':  price,
            'vol':    vol,
            'pnl_pct': pnl_pct,
            'reason': reason,
            'sector': sector,
        })

        # 清理持仓
        del self.positions[sym]

        print('[卖出] %s | %s | %s | 价%.2f | %+.2f%% | 现金%.0f'
              % (date_str, sym, reason, price, pnl_pct, self.cash))

    def _screen_all(self, date_str, bar_idx, sector_momentum):
        """对候选股票打分。"""
        candidates = []
        SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()

        for sym in SYMBOLS:
            if sym in self.positions:
                continue  # 已持仓

            df = self._get_df_slice(sym, bar_idx)
            if df is None:
                continue

            sector = SYMBOL_SECTOR_MAP.get(sym, '未知')

            # 快速初筛
            closes = df['close'].values
            if len(closes) < config.RSI_PERIOD + 1:
                continue

            # 条件 0: RSI 硬性超卖检查（核心 —— 均值回归策略的基础）
            rsi_quick = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
            if rsi_quick is None or rsi_quick >= config.RSI_BUY:
                continue

            cur  = float(closes[-1])
            if cur < config.PRICE_MIN or cur > config.PRICE_MAX:
                continue
            chg = abs(cur - float(closes[-2])) / float(closes[-2]) if float(closes[-2]) > 0 else 0
            if chg > config.PRICE_CHG_LIMIT:
                continue

            # 多因子打分（直接调用 screener 模块，避免重复实现）
            result = screener._score_stock(df, sym, sector, sector_momentum)
            if result is None:
                continue
            if result['total'] >= config.ENTRY_THRESHOLD:
                candidates.append(result)

        candidates.sort(key=lambda x: x['total'], reverse=True)
        return candidates

    def _calc_sector_momentum(self, bar_idx):
        """计算行业动量。"""
        momentum = {}
        sector_map = stock_pool.get_symbol_sector_map()

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

    def _execute_entries(self, date_str, bar_idx, candidates, remaining, regime_cfg):
        """执行买入。"""
        occupied_sectors = set(p.get('sector') for p in self.positions.values())
        taken_sectors = set(occupied_sectors)
        taken_count = 0

        for c in candidates:
            if taken_count >= remaining:
                break

            sym    = c['symbol']
            sector = c['sector']
            price  = c['price']

            if sym in self.positions:
                continue
            if sector in taken_sectors:
                continue

            # 波动率仓位调整
            vol_group = stock_pool.get_sector_volatility_group(sector)
            if vol_group == 'high':
                pos_pct = config.POSITION_PCT * config.VOL_ADJ_HIGH
            elif vol_group == 'low':
                pos_pct = config.POSITION_PCT * config.VOL_ADJ_LOW
            else:
                pos_pct = config.POSITION_PCT

            # 计算买入数量
            allocated = self.cash * pos_pct / max(remaining - taken_count, 1)
            if allocated < price * 100:
                continue

            qty = int(allocated / (price * 100)) * 100
            if qty < 100:
                continue

            # 执行买入
            self.cash -= price * qty
            self.positions[sym] = {
                'vol':      qty,
                'cost':     price,
                'peak':     price,
                'entry_date': date_str,
                'sector':   sector,
            }
            taken_sectors.add(sector)
            taken_count += 1

            print('[买入] %s | %s(%s) | 评分%.3f | RSI%.1f | %.2f×%d | 余资%.0f'
                  % (date_str, sector, vol_group, c['total'], c['rsi'], price, qty, self.cash))

    def _record_daily_value(self, date_str, bar_idx):
        """记录每日净值。"""
        # 计算持仓市值
        market_value = 0.0
        for sym, pos in self.positions.items():
            df = self._get_df_slice(sym, bar_idx)
            if df is not None and len(df) > 0:
                cur_price = float(df['close'].values[-1])
                market_value += cur_price * pos['vol']

        total_value = self.cash + market_value
        self.daily_values.append({
            'date':  date_str,
            'cash':  self.cash,
            'market': market_value,
            'total': total_value,
        })

    def _count_trading_days(self, entry_date, current_date):
        """估算持仓交易日数。"""
        try:
            d0 = datetime.strptime(entry_date, '%Y-%m-%d')
            d1 = datetime.strptime(current_date, '%Y-%m-%d')
            return max(1, (d1 - d0).days)
        except Exception:
            return 1

    def _print_summary(self):
        """输出回测结果摘要。"""
        if not self.daily_values:
            print('[结果] 无交易记录')
            return

        df = pd.DataFrame(self.daily_values)
        final_value = df['total'].iloc[-1]
        initial = self.initial_cash
        total_return = (final_value - initial) / initial * 100

        # 最大回撤
        df['cummax'] = df['total'].cummax()
        df['drawdown'] = (df['total'] - df['cummax']) / df['cummax']
        max_dd = df['drawdown'].min() * 100

        # 交易统计
        sell_trades = [t for t in self.trades if t['side'] == 'SELL']
        win_trades = [t for t in sell_trades if t['pnl_pct'] > 0]
        win_rate = len(win_trades) / len(sell_trades) * 100 if sell_trades else 0

        print('\n' + '=' * 60)
        print('  回测结果摘要')
        print('=' * 60)
        print('  初始资金:   %.0f' % initial)
        print('  最终净值:   %.0f' % final_value)
        print('  总收益率:   %+.2f%%' % total_return)
        print('  最大回撤:   %.2f%%' % max_dd)
        print('  交易次数:   %d' % len(self.trades))
        print('  胜率:       %.1f%%' % win_rate)
        print('=' * 60)

        # 输出交易明细
        if self.trades:
            print('\n  交易明细:')
            for t in self.trades:
                side_mark = '+' if t['pnl_pct'] > 0 else ''
                print('  %s %s %s %.2f%% %s'
                      % (t['date'], t['side'], t['symbol'],
                         t['pnl_pct'], t.get('reason', '')))


# =============================================================================
# 主程序
# =============================================================================

if __name__ == '__main__':
    start_date = config.BACKTEST_START[:10]  # '2024-01-01'
    end_date   = config.BACKTEST_END[:10]    # '2026-05-22'

    # 预加载数据
    all_data = preload_all_data(start_date, end_date)

    if MARKET_INDEX not in all_data:
        print('[错误] 无法获取大盘指数数据，退出')
        sys.exit(1)

    if len(all_data) < 5:
        print('[错误] 有效股票数据不足，退出')
        sys.exit(1)

    # 运行回测
    engine = BacktestEngine(all_data, start_cash=config.BACKTEST_CASH)
    engine.run()
