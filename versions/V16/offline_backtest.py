"""
offline_backtest.py - V16 绂荤嚎鍥炴祴鑴氭湰

涓嶄緷璧栨帢閲戠粓绔紝鐩存帴鐢?history() API 鎷夊彇鏁版嵁骞舵ā鎷熷洖娴嬨€?鐢ㄦ硶: python offline_backtest.py
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
# 鍏ㄥ眬璁剧疆
# =============================================================================

set_token(config.GM_TOKEN)

SYMBOLS = stock_pool.get_all_symbols()
MARKET_INDEX = config.MARKET_INDEX

print('鈺? + '鈺? * 58 + '鈺?)
print('鈺?  V16 绂荤嚎鍥炴祴 (涓嶄緷璧栨帢閲戠粓绔?')
print('鈺?  鑲＄エ姹? %d 鍙?/ %d 琛屼笟' % (len(SYMBOLS), len(stock_pool.get_sector_list())))
print('鈺? + '鈺? * 58 + '鈺?)


# =============================================================================
# 鏁版嵁鑾峰彇
# =============================================================================

def fetch_history(symbol, start, end, freq='1d'):
    """鐢?GM history() API 鎷夊彇鍘嗗彶鏁版嵁銆?""
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
    棰勫姞杞芥墍鏈夎偂绁?+ 澶х洏鎸囨暟鐨勫巻鍙叉暟鎹€?    杩斿洖: {symbol: DataFrame}
    """
    print('[鏁版嵁] 姝ｅ湪涓嬭浇鍘嗗彶鏁版嵁...')
    data = {}
    all_syms = list(SYMBOLS) + [MARKET_INDEX]

    for i, sym in enumerate(all_syms):
        df = fetch_history(sym, start, end)
        if df is not None and len(df) >= config.MIN_DATA_BARS:
            data[sym] = df
        if (i + 1) % 10 == 0 or (i + 1) == len(all_syms):
            print('  杩涘害: %d/%d' % (i + 1, len(all_syms)))

    print('[鏁版嵁] 瀹屾垚: 鎴愬姛 %d/%d' % (len(data), len(all_syms)))
    return data


# =============================================================================
# 鍥炴祴寮曟搸
# =============================================================================

class BacktestEngine:
    """
    绠€鍖栫殑鍥炴祴寮曟搸锛屾ā鎷熸瘡鏃ヨ皟浠撱€?    涓嶈€冭檻鎵嬬画璐广€佹粦鐐癸紙涓?GM 鍥炴祴淇濇寔涓€鑷达級銆?    """

    def __init__(self, data, start_cash=25000):
        self.data = data
        self.cash = float(start_cash)
        self.initial_cash = float(start_cash)
        self.positions = {}   # {symbol: {'vol': int, 'cost': float, 'peak': float, 'entry_date': str, 'sector': str}}
        self.trades = []       # 浜ゆ槗璁板綍
        self.daily_values = [] # 姣忔棩鍑€鍊?        self.bar_dates = []    # 鎵€鏈変氦鏄撴棩

        # 鏋勫缓缁熶竴鐨勪氦鏄撴棩鍘?        if MARKET_INDEX in data:
            self.bar_dates = list(data[MARKET_INDEX]['bob'].dt.strftime('%Y-%m-%d'))

        print('[寮曟搸] 浜ゆ槗鏃ユ暟: %d | 鍒濆璧勯噾: %.0f' % (len(self.bar_dates), start_cash))

    def run(self):
        """杩愯鍥炴祴銆?""
        print('[寮曟搸] 寮€濮嬪洖娴?..')

        for i, date_str in enumerate(self.bar_dates):
            # 姣忔棩 14:50 鎵ц锛堣繖閲岀畝鍖栦负鐢ㄥ綋鏃ユ敹鐩樹环锛?            self._daily_bar(date_str, i)
            self._record_daily_value(date_str, i)

        self._print_summary()

    def _daily_bar(self, date_str, bar_idx):
        """
        姣忔棩浜ゆ槗閫昏緫锛堝搴?GM 鐨?on_bar锛夈€?        """
        # 璺宠繃鍓?80 鏍?bar锛堟暟鎹笉瓒虫棤娉曡绠楁寚鏍囷級
        if bar_idx < config.DATA_COUNT:
            return

        # Step 1: 甯傚満鐘舵€佸垽鏂?        regime = self._detect_regime(bar_idx)
        regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

        # Step 2: 鍑哄満妫€鏌?        self._check_exits(date_str, bar_idx, regime_cfg)

        # Step 3: 琛屼笟鍔ㄩ噺
        sector_momentum = self._calc_sector_momentum(bar_idx)

        # Step 4: 閫夎偂鎵撳垎
        candidates = self._screen_all(date_str, bar_idx, sector_momentum)

        # Step 5: 鍏ュ満
        remaining = regime_cfg['max_positions'] - len(self.positions)
        if remaining > 0 and candidates:
            self._execute_entries(date_str, bar_idx, candidates, remaining, regime_cfg)

    def _get_df_slice(self, symbol, bar_idx):
        """鑾峰彇鎴鍒?bar_idx 鐨勬暟鎹垏鐗囥€?""
        if symbol not in self.data:
            return None
        df = self.data[symbol]
        if bar_idx >= len(df):
            return None
        return df.iloc[:bar_idx + 1]

    def _detect_regime(self, bar_idx):
        """鍒ゆ柇甯傚満鐘舵€併€?""
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
        """妫€鏌ユ墍鏈夋寔浠撶殑鍑哄満鏉′欢銆?""
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

            # 鏇存柊鏈€楂樹环
            if cur_price > pos['peak']:
                pos['peak'] = cur_price

            # 璁＄畻 ATR
            atr = indicators.calc_atr(highs, lows, closes, config.ATR_PERIOD)
            if atr is None:
                atr = cur_price * 0.03

            pnl = (cur_price - pos['cost']) / pos['cost']
            reason = None

            # 鏉′欢 1: ATR 姝㈡崯
            stop_mult = regime_cfg.get('atr_stop_mult', config.ATR_STOP_MULT)
            stop_loss_pct = atr / cur_price * stop_mult
            stop_loss_pct = min(stop_loss_pct, config.STOP_LOSS_CAP)
            stop_loss_pct = max(stop_loss_pct, 0.03)

            if pnl <= -stop_loss_pct:
                reason = 'ATR姝㈡崯(%.1f%%)' % (stop_loss_pct * 100)

            # 鏉′欢 2: ATR 璺熻釜姝㈢泩
            elif pos['peak'] > pos['cost']:
                trail_pct = atr / cur_price * config.ATR_TRAIL_MULT
                trail_pct = max(trail_pct, 0.04)
                if cur_price <= pos['peak'] * (1.0 - trail_pct):
                    reason = 'ATR璺熻釜(%.1f%%)' % (trail_pct * 100)

            # 鏉′欢 3: RSI 杩囩儹
            if reason is None:
                rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
                if rsi is not None and rsi > config.RSI_EXIT:
                    reason = 'RSI杩囩儹(%.0f)' % rsi

            # 鏉′欢 4: 鏃堕棿姝㈡崯
            if reason is None:
                entry_date = pos.get('entry_date', date_str)
                held_days = self._count_trading_days(entry_date, date_str)
                if held_days >= config.TIME_STOP_DAYS and pnl < 0.02:
                    reason = '鏃堕棿姝㈡崯(%dd)' % held_days

            # 鎵ц鍗栧嚭
            if reason:
                self._execute_sell(sym, cur_price, reason, pos, date_str, atr / cur_price)

    def _execute_sell(self, sym, price, reason, pos, date_str, vol_pct):
        """鎵ц鍗栧嚭銆?""
        vol = pos['vol']
        pnl_pct = (price - pos['cost']) / pos['cost'] * 100
        sector = pos.get('sector', '鏈煡')

        # 鏇存柊璧勯噾
        self.cash += price * vol

        # 璁板綍浜ゆ槗
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

        # 娓呯悊鎸佷粨
        del self.positions[sym]

        print('[鍗栧嚭] %s | %s | %s | 浠?.2f | %+.2f%% | 鐜伴噾%.0f'
              % (date_str, sym, reason, price, pnl_pct, self.cash))

    def _screen_all(self, date_str, bar_idx, sector_momentum):
        """瀵瑰€欓€夎偂绁ㄦ墦鍒嗐€?""
        candidates = []
        SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()

        for sym in SYMBOLS:
            if sym in self.positions:
                continue  # 宸叉寔浠?
            df = self._get_df_slice(sym, bar_idx)
            if df is None:
                continue

            sector = SYMBOL_SECTOR_MAP.get(sym, '鏈煡')

            # 蹇€熷垵绛?            closes = df['close'].values
            if len(closes) < config.RSI_PERIOD + 1:
                continue

            # 鏉′欢 0: RSI 纭€ц秴鍗栨鏌ワ紙鏍稿績 鈥斺€?鍧囧€煎洖褰掔瓥鐣ョ殑鍩虹锛?            rsi_quick = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
            if rsi_quick is None or rsi_quick >= config.RSI_BUY:
                continue

            cur  = float(closes[-1])
            if cur < config.PRICE_MIN or cur > config.PRICE_MAX:
                continue
            chg = abs(cur - float(closes[-2])) / float(closes[-2]) if float(closes[-2]) > 0 else 0
            if chg > config.PRICE_CHG_LIMIT:
                continue

            # 澶氬洜瀛愭墦鍒嗭紙鐩存帴璋冪敤 screener 妯″潡锛岄伩鍏嶉噸澶嶅疄鐜帮級
            result = screener._score_stock(df, sym, sector, sector_momentum)
            if result is None:
                continue
            if result['total'] >= config.ENTRY_THRESHOLD:
                candidates.append(result)

        candidates.sort(key=lambda x: x['total'], reverse=True)
        return candidates

    def _calc_sector_momentum(self, bar_idx):
        """璁＄畻琛屼笟鍔ㄩ噺銆?""
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
        """鎵ц涔板叆銆?""
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

            # 娉㈠姩鐜囦粨浣嶈皟鏁?            vol_group = stock_pool.get_sector_volatility_group(sector)
            if vol_group == 'high':
                pos_pct = config.POSITION_PCT * config.VOL_ADJ_HIGH
            elif vol_group == 'low':
                pos_pct = config.POSITION_PCT * config.VOL_ADJ_LOW
            else:
                pos_pct = config.POSITION_PCT

            # 璁＄畻涔板叆鏁伴噺
            allocated = self.cash * pos_pct / max(remaining - taken_count, 1)
            if allocated < price * 100:
                continue

            qty = int(allocated / (price * 100)) * 100
            if qty < 100:
                continue

            # 鎵ц涔板叆
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

            print('[涔板叆] %s | %s(%s) | 璇勫垎%.3f | RSI%.1f | %.2f脳%d | 浣欒祫%.0f'
                  % (date_str, sector, vol_group, c['total'], c['rsi'], price, qty, self.cash))

    def _record_daily_value(self, date_str, bar_idx):
        """璁板綍姣忔棩鍑€鍊笺€?""
        # 璁＄畻鎸佷粨甯傚€?        market_value = 0.0
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
        """浼扮畻鎸佷粨浜ゆ槗鏃ユ暟銆?""
        try:
            d0 = datetime.strptime(entry_date, '%Y-%m-%d')
            d1 = datetime.strptime(current_date, '%Y-%m-%d')
            return max(1, (d1 - d0).days)
        except Exception:
            return 1

    def _print_summary(self):
        """杈撳嚭鍥炴祴缁撴灉鎽樿銆?""
        if not self.daily_values:
            print('[缁撴灉] 鏃犱氦鏄撹褰?)
            return

        df = pd.DataFrame(self.daily_values)
        final_value = df['total'].iloc[-1]
        initial = self.initial_cash
        total_return = (final_value - initial) / initial * 100

        # 鏈€澶у洖鎾?        df['cummax'] = df['total'].cummax()
        df['drawdown'] = (df['total'] - df['cummax']) / df['cummax']
        max_dd = df['drawdown'].min() * 100

        # 浜ゆ槗缁熻
        sell_trades = [t for t in self.trades if t['side'] == 'SELL']
        win_trades = [t for t in sell_trades if t['pnl_pct'] > 0]
        win_rate = len(win_trades) / len(sell_trades) * 100 if sell_trades else 0

        print('\n' + '=' * 60)
        print('  鍥炴祴缁撴灉鎽樿')
        print('=' * 60)
        print('  鍒濆璧勯噾:   %.0f' % initial)
        print('  鏈€缁堝噣鍊?   %.0f' % final_value)
        print('  鎬绘敹鐩婄巼:   %+.2f%%' % total_return)
        print('  鏈€澶у洖鎾?   %.2f%%' % max_dd)
        print('  浜ゆ槗娆℃暟:   %d' % len(self.trades))
        print('  鑳滅巼:       %.1f%%' % win_rate)
        print('=' * 60)

        # 杈撳嚭浜ゆ槗鏄庣粏
        if self.trades:
            print('\n  浜ゆ槗鏄庣粏:')
            for t in self.trades:
                side_mark = '+' if t['pnl_pct'] > 0 else ''
                print('  %s %s %s %.2f%% %s'
                      % (t['date'], t['side'], t['symbol'],
                         t['pnl_pct'], t.get('reason', '')))


# =============================================================================
# 涓荤▼搴?# =============================================================================

if __name__ == '__main__':
    start_date = config.BACKTEST_START[:10]  # '2024-01-01'
    end_date   = config.BACKTEST_END[:10]    # '2026-05-22'

    # 棰勫姞杞芥暟鎹?    all_data = preload_all_data(start_date, end_date)

    if MARKET_INDEX not in all_data:
        print('[閿欒] 鏃犳硶鑾峰彇澶х洏鎸囨暟鏁版嵁锛岄€€鍑?)
        sys.exit(1)

    if len(all_data) < 5:
        print('[閿欒] 鏈夋晥鑲＄エ鏁版嵁涓嶈冻锛岄€€鍑?)
        sys.exit(1)

    # 杩愯鍥炴祴
    engine = BacktestEngine(all_data, start_cash=config.BACKTEST_CASH)
    engine.run()
