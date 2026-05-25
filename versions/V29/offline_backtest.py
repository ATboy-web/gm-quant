"""
offline_backtest.py - V29.4 绂荤嚎鍥炴祴鑴氭湰

V29.4 鏀硅繘锛堝叏绛栫暐婵€娲?+ 绛栫暐閰嶉鍒讹級:
  鏍瑰洜: sector_config.py 鏈悓姝?鈫?MR/BK/DV/RT 鏈惎鐢?鈫?VP 鍨勬柇
  淇: 鍏ㄩ潰鍚屾鎵€鏈?.py 鏂囦欢 + executor 绛栫暐閰嶉鍒?(姣忕瓥鐣モ墹2鍙?
  config: RSI_BUY 29鈫?3, ENTRY_THRESHOLD 0.42鈫?.36 (閫傞厤2024-2026鐗涘競)
  VP: 淇濈暀 V29.2 瓒嬪娍纭棬绉婚櫎

V29.2 鏀硅繘锛堜慨澶嶅绛栫暐绔炰簤涓殑鍗曠瓥鐣ユ瑙嗭級:
  executor: 缃俊搴︽敼鐢?max(confidences)脳(1+鍏辫瘑鍔犳垚), 涓嶅啀鐢?avg
            浠撲綅姣斾緥涓嬮檺鎻愬崌: 鍙岀‘璁?.60鈫?.75, 鍗?.40鈫?.55
  VP: 绉婚櫎 V29.1 瓒嬪娍纭棬(鍗曠瓥鐣ユ祴璇曡瘉瀹炴湁瀹?+8.29%鈫?0.75%)
  鏍瑰洜: VP鐙珛杩愯 +8.29%, 澶氱瓥鐣?-27.7%, 宸窛鏉ヨ嚜鎶曠エ鏈哄埗鑰岄潪绛栫暐閫昏緫

V29 鏀硅繘锛圡OM/DV 绛栫暐浼樺寲锛?
  MOM: 鍏ュ満闂ㄦ0.35鈫?.55, 閲忚兘纭棬1.1鈫?.3, RSI涓嬮檺45, 鍧囩嚎鍒嗙>1.5%
  DV: 浣庝綅 AND(鍘烵R), 60d<0%, 20d<-4%, RSI 33-52, 闂ㄦ0.72, 浠?MA60
  MOM鏉冮噸: 8琛屼笟绂佺敤, 4琛屼笟闄嶆潈40-60%, BK琛ュ伩鎻愭潈
  DV鏉冮噸: 鍏ㄨ涓氶檷鏉儈30%
  1. 鍏ュ満閫備腑: ENTRY_THRESHOLD 0.42, RSI_BUY 29
  2. 姝㈡崯閫備腑: ATR_STOP_MULT 1.4, STOP_LOSS_CAP 0.07
  3. 浠撲綅閫備腑: POSITION_PCT 0.14, MAX_TRADES 10
  4. 鐔旀柇鍥為€€: 杩炰簭3绗?鍐峰嵈5澶? cooldown 2澶?
  5. 鍚勮涓?entry_threshold 闄嶄綆 ~0.02
  6. Bug淇: record_buy 缂哄け(MAX_TRADES澶辨晥), 鐔旀柇鐘舵€佹寔涔呭寲淇

V27 鏀硅繘:
  1. 鏀剁揣鍙傛暟: RSI涔板叆28, 鍏ュ満闃堝€?.45, 姝㈡崯1.3鍊岮TR/6%纭鎹?
  2. 寤堕暱鍐峰嵈鏈? 1澶┾啋3澶? 鍑忓皯Whipsaw
  3. 鎻愰珮涔板叆闂ㄦ: 鎶曠エ鈮?.8(鍘?.5), 鍑忓皯鍗曠瓥鐣ュ急淇″彿
  4. 闄嶄綆浜ゆ槗棰戠巼: 鍗曡偂鏈€澶?娆?鍘?2), 杩炰簭2绗旂啍鏂?
  5. 鎬ц兘浼樺寲: 寤惰繜鏋勫缓data_cache, 琛屼笟鍔ㄩ噺缂撳瓨鍖? 鍑忓皯鍒囩墖

V20 鏀硅繘:
  1. 鏂板鍙嶈浆纭绛栫暐(RT)
  2. 6绛栫暐浣撶郴: MR + MOM + VP + BK + DV + RT
  3. 鍖栧伐/鏂拌兘婧?鐓ょ偔琛屼笟閽堝鎬т紭鍖?

V19.2 鏀硅繘:
  1. 鏂板绐佺牬绛栫暐(BK)鍜岀孩鍒╃瓥鐣?DV)
  2. 鏂拌兘婧?鍏敤浜嬩笟鍙傛暟浼樺寲
  3. 绛栫暐宸ュ巶鏀寔5绛栫暐

V19 鏀硅繘:
  1. 琛屼笟宸紓鍖栫瓥鐣ュ弬鏁?
  2. 绛栫暐宸ュ巶鍔ㄦ€佸垱寤?
  3. executor 鎵ц鍣ㄥ鐢?
  4. 涓?GM 缁堢瑙ｈ€︼紝绾?Python 鍥炴祴
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import time
from datetime import datetime, timedelta
from gm.api import *

import config
import indicators
import stock_pool
import screener
import sector_config
import executor
import trace
import gm_logger as logger
import strategy_mr
import strategy_momentum
import strategy_vp
import strategy_breakout
import strategy_dividend
import strategy_reversal
import fusion
import visualizer

# =============================================================================
# 鍏ㄥ眬璁剧疆
# =============================================================================

set_token(config.GM_TOKEN)

SYMBOLS = stock_pool.get_all_symbols()
MARKET_INDEX = config.MARKET_INDEX
SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()

logger.setup_logger(name='offline_backtest')
log = logger.log

log.info('=' * 56)
log.info('  V28 \u79bb\u7ebf\u56de\u6d4b \u2014 \u516d\u7b56\u7565\u884c\u4e1a\u5dee\u5f02\u5316\u878d\u5408\u6846\u67b6')
log.info('  绛栫暐: MR + MOM + VP + BK + DV + RT')
log.info('  鑲＄エ姹? %d 鍙?/ %d 琛屼笟', len(SYMBOLS), len(stock_pool.get_sector_list()))
log.info('=' * 56)
sector_config.print_summary()


# =============================================================================
# 鏁版嵁鑾峰彇
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
    log.info('[鏁版嵁] 姝ｅ湪涓嬭浇鍘嗗彶鏁版嵁...')
    data = {}
    all_syms = list(SYMBOLS) + [MARKET_INDEX]

    for i, sym in enumerate(all_syms):
        df = fetch_history(sym, start, end)
        if df is not None and len(df) >= config.MIN_DATA_BARS:
            data[sym] = df
        if (i + 1) % 10 == 0 or (i + 1) == len(all_syms):
            log.info('  杩涘害: %d/%d', i + 1, len(all_syms))

    log.info('[鏁版嵁] 瀹屾垚: 鎴愬姛 %d/%d', len(data), len(all_syms))
    return data


# =============================================================================
# V19 鍥炴祴寮曟搸
# =============================================================================

class V19BacktestEngine:

    def __init__(self, data, start_cash=25000):
        self.data = data
        self.cash = float(start_cash)
        self.initial_cash = float(start_cash)
        self.positions = {}
        self.trades = []
        self.daily_values = []

        # V19 鎵ц鍣?
        self.exec_engine = executor.TradeExecutor()

        if MARKET_INDEX in data:
            self.bar_dates = list(data[MARKET_INDEX]['bob'].dt.strftime('%Y-%m-%d'))

        log.info('[寮曟搸] 浜ゆ槗鏃ユ暟: %d | 鍒濆璧勯噾: %.0f',
                 len(self.bar_dates), start_cash)

        # V27: 鎬ц兘浼樺寲 鈥?棰勮绠楁瘡涓猙ar_idx鐨剆lice杈圭晫锛岄伩鍏嶉噸澶峣loc
        self._slices_cache = {}
        self._sector_momentum_cache = {}

        # 绛栫暐缁熻
        self.strategy_stats = {
            'MR':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'MOM': {'wins': 0, 'total': 0, 'pnl': 0.0},
            'VP':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'BK':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'DV':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'RT':  {'wins': 0, 'total': 0, 'pnl': 0.0},
        }
        # 琛屼笟缁熻
        self.sector_stats = {}

    def run(self):
        log.info('[寮曟搸] 寮€濮嬪洖娴?(V29 浼樺寲)...')
        for i, date_str in enumerate(self.bar_dates):
            self._daily_bar(date_str, i)
            self._record_daily_value(date_str, i)

            if (i + 1) % 50 == 0:
                total_val = self.daily_values[-1]['total'] if self.daily_values else 0
                pos_count = len(self.positions)
                ret = (total_val - self.initial_cash) / self.initial_cash * 100
                log.info('  [%s] 杩涘害 %d/%d | 鍑€鍊?%.0f (%+.1f%%) | 鎸佷粨 %d',
                         date_str, i + 1, len(self.bar_dates), total_val, ret, pos_count)

        self._print_summary()

    def _daily_bar(self, date_str, bar_idx):
        if bar_idx < config.DATA_COUNT:
            return

        # V19.2: 娓呯悊杩囨湡鍐峰嵈鏈?
        self.exec_engine.cleanup_cooldowns(date_str)

        regime = self._detect_regime(bar_idx)
        regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

        # V27: 鍙瀯寤烘寔浠撴暟鎹敤浜庡嚭鍦烘鏌?
        pos_info_copy = {sym: dict(pos) for sym, pos in self.positions.items()}
        data_cache = {}
        for sym in self.positions:
            df = self._get_df_slice(sym, bar_idx)
            if df is not None:
                data_cache[sym] = df

        sells = self.exec_engine.check_exits(
            pos_info_copy, data_cache, regime, today_str=date_str
        )

        for sym, price, vote, info in sells:
            if sym in self.positions:
                self._execute_sell(sym, price, vote['reason'], date_str)
                self.exec_engine.record_sell(sym, date_str)

        # 琛屼笟鍔ㄩ噺 (V27: 缂撳瓨鍖?
        sector_momentum = self._calc_sector_momentum_cached(bar_idx)
        sentiment = {}
        for sec, mom in sector_momentum.items():
            sentiment[sec] = max(-1.0, min(1.0, mom * 5))
        self.exec_engine._sentiment = sentiment

        # 鍏ュ満: 妫€鏌ユ槸鍚﹁繕鏈夌┖闂?
        max_pos = regime_cfg['max_positions']
        if len(self.positions) < max_pos:
            # V27: 琛ュ厖鏋勫缓鍊欓€夎偂鏁版嵁
            for sym in SYMBOLS:
                if sym not in data_cache:
                    df = self._get_df_slice(sym, bar_idx)
                    if df is not None:
                        data_cache[sym] = df

            occupied = set(p.get('sector') for p in self.positions.values())
            candidates = self.exec_engine.find_buy_candidates(
                SYMBOLS, occupied, self.positions,
                data_cache, sector_momentum, regime, today_str=date_str
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

            # V28: 杩借釜鍗曞彧鑲＄エ浜ゆ槗娆℃暟锛圴27閬楁紡锛屽鑷碝AX_TRADES_PER_SYMBOL鍦ㄧ绾垮洖娴嬩腑澶辨晥锛?
            self.exec_engine.record_buy(sym)

            rsi_str = ' RSI=%.0f' % c['rsi'] if c.get('rsi') else ''
            log.info('[涔板叆] %s | %s | %s | 绛栫暐:%s | %.2f脳%d%s',
                     date_str, sym, c['reason'],
                     c['best_strategy'], price, qty, rsi_str)

            # V27: 璁板綍涔板叆浜ゆ槗
            self.trades.append({
                'date': date_str, 'symbol': sym, 'side': 'BUY',
                'price': price, 'vol': qty, 'pnl_pct': 0,
                'reason': c['reason'], 'sector': sector,
                'strategy': c['best_strategy'],
            })

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
        cost_price = pos['cost']
        pnl_pct = (price - cost_price) / cost_price * 100
        sector = pos.get('sector', '鏈煡')
        strat = pos.get('strategy', '?')
        entry_date = pos.get('entry_date', '')

        # 绠楁寔浠撳ぉ鏁?
        hold_days = 0
        if entry_date:
            try:
                from datetime import datetime as dt
                hold_days = (dt.strptime(date_str, '%Y-%m-%d') -
                             dt.strptime(entry_date, '%Y-%m-%d')).days
            except Exception:
                pass

        self.cash += price * vol

        self.trades.append({
            'date': date_str, 'symbol': sym, 'side': 'SELL',
            'price': price, 'vol': vol, 'pnl_pct': pnl_pct,
            'reason': reason, 'sector': sector, 'strategy': strat,
            'cost_price': cost_price, 'hold_days': hold_days,
            'entry_date': entry_date,
        })

        # 琛屼笟缁熻
        if sector not in self.sector_stats:
            self.sector_stats[sector] = {'wins': 0, 'total': 0, 'pnl': 0.0}
        self.sector_stats[sector]['total'] += 1
        self.sector_stats[sector]['pnl'] += pnl_pct
        if pnl_pct > 0:
            self.sector_stats[sector]['wins'] += 1

        del self.positions[sym]

        # 绛栫暐缁熻
        if strat in self.strategy_stats:
            self.strategy_stats[strat]['total'] += 1
            self.strategy_stats[strat]['pnl'] += pnl_pct
            if pnl_pct > 0:
                self.strategy_stats[strat]['wins'] += 1

        log.info('[鍗栧嚭] %s | %s | %s | 浠?.2f | %+.2f%% | %s',
                 date_str, sym, reason, price, pnl_pct, strat)

        # V27: 閫氱煡鎵ц鍣ㄨ褰曚氦鏄撶粨鏋滐紝瑙﹀彂杩炰簭鐔旀柇
        self.exec_engine.note_trade_result(pnl_pct / 100, date_str)

    def _calc_sector_momentum_cached(self, bar_idx):
        """V27: 缂撳瓨鍖栬涓氬姩閲忚绠椼€傛瘡10涓猙ar鎵嶉噸绠椾竴娆℃彁楂橀€熷害銆?""
        cache_key = bar_idx // 10
        if cache_key in self._sector_momentum_cache:
            return self._sector_momentum_cache[cache_key]
        result = self._calc_sector_momentum(bar_idx)
        self._sector_momentum_cache[cache_key] = result
        return result

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
        """V27: 浼樺寲 鈥?鐩存帴璁＄畻鍚粨甯傚€硷紝鍑忓皯閲嶅鍒囩墖銆?""
        market_value = 0.0
        for sym, pos in self.positions.items():
            df = self.data.get(sym)
            if df is not None and bar_idx < len(df):
                cur_price = float(df['close'].values[bar_idx])
                market_value += cur_price * pos['vol']

        total_value = self.cash + market_value
        self.daily_values.append({
            'date': date_str, 'cash': self.cash,
            'market': market_value, 'total': total_value,
        })

    def _print_summary(self):
        if not self.daily_values:
            log.info('[缁撴灉] 鏃犱氦鏄撹褰?)
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

        log.info('=' * 56)
        log.info('  V20 鍏瓥鐣ヨ涓氬樊寮傚寲鍥炴祴缁撴灉鎽樿')
        log.info('=' * 56)
        log.info('  鍒濆璧勯噾:   %.0f', initial)
        log.info('  鏈€缁堝噣鍊?   %.0f', final_value)
        log.info('  鎬绘敹鐩婄巼:   %+.2f%%', total_return)
        log.info('  鏈€澶у洖鎾?   %.2f%%', max_dd)
        log.info('  浜ゆ槗娆℃暟:   %d (鍗栧嚭%d)', len(self.trades), len(sell_trades))
        log.info('  鑳滅巼:       %.1f%% (%d/%d)',
                 win_rate, len(win_trades), len(sell_trades))
        if sell_trades:
            log.info('  骞冲潎鐩堜簭:   %+.2f%%',
                     np.mean([t['pnl_pct'] for t in sell_trades]))

        # ---- 绛栫暐鍒嗛」 ----
        log.info('  ---- 绛栫暐鍒嗛」 ----')
        for name in ['MR', 'MOM', 'VP', 'BK', 'DV', 'RT']:
            ss = self.strategy_stats[name]
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                log.info('  %s: 浜ゆ槗%d 鑳滅巼%.1f%% 绱鐩堜簭%+.1f%%',
                         name, ss['total'], wr, ss['pnl'])

        # ---- 琛屼笟鍒嗛」 ----
        log.info('  ---- 琛屼笟鍒嗛」 ----')
        for sector in sorted(self.sector_stats.keys()):
            ss = self.sector_stats[sector]
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                log.info('  %-6s: 浜ゆ槗%d 鑳滅巼%.1f%% 绱%+.1f%%',
                         sector, ss['total'], wr, ss['pnl'])

        log.info('=' * 56)

        # 鏈€杩?10 绗斾氦鏄?
        if sell_trades:
            log.info('  鏈€杩?10 绗斿崠鍑?')
            for t in sell_trades[-10:]:
                log.info('  %s %s %-6s %+.2f%% %s %s',
                         t['date'], t['symbol'], t.get('strategy', '?'),
                         t['pnl_pct'], t.get('reason', ''), t.get('sector', ''))


# =============================================================================
# 涓荤▼搴?
# =============================================================================

if __name__ == '__main__':
    # V29.3: 娉ㄩ噴鎺夊彲瑙嗗寲浜や簰鎻愮ず锛岄伩鍏嶅悗鍙拌繍琛屾椂闃诲
    # visualizer.prompt_visual()
    # 濡傞渶鍙鍖栵紝鎵嬪姩鍙栨秷娉ㄩ噴涓婁竴琛岋紝鎴栧湪缁堢鐩存帴杩愯
    print('  [璺宠繃] 鍙鍖栫獥鍙ｏ紙浠呭懡浠よ杈撳嚭锛塡n')

    start_date = config.BACKTEST_START[:10]
    end_date   = config.BACKTEST_END[:10]

    all_data = preload_all_data(start_date, end_date)

    if MARKET_INDEX not in all_data:
        log.error('[閿欒] 鏃犳硶鑾峰彇澶х洏鎸囨暟鏁版嵁锛岄€€鍑?)
        sys.exit(1)

    if len(all_data) < 5:
        log.error('[閿欒] 鏈夋晥鑲＄エ鏁版嵁涓嶈冻锛岄€€鍑?)
        sys.exit(1)

    _t0 = time.time()
    engine = V19BacktestEngine(all_data, start_cash=config.BACKTEST_CASH)
    engine.run()
    _elapsed = time.time() - _t0

    log.info('[鑰楁椂] 鍥炴祴鎬昏€楁椂: %.1f 鍒嗛挓 (%.1f 绉?', _elapsed / 60, _elapsed)

    # V27: 杞崲涓哄彲瑙嗗寲鏁版嵁骞跺惎鍔?
    if visualizer.VISUAL_ENABLED:
        viz_data = visualizer.from_backtest_engine(engine)
        visualizer.launch_visualizer(viz_data, _elapsed)
