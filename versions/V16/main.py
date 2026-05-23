"""
main.py - V16 澶氬洜瀛愯嚜閫傚簲鍧囧€煎洖褰掔瓥鐣?

================================================================================
绛栫暐鏍稿績鐞嗗康
================================================================================
涓嶆槸绠€鍗曠殑 "RSI < 32 灏变拱"锛岃€屾槸涓€涓畬鏁寸殑閲忓寲鍐崇瓥绯荤粺:

  1. 甯傚満鐘舵€佸垽鏂?  鈫?鍒ゆ柇鐜板湪鏄墰/鐔?闇囪崱锛岃嚜閫傚簲璋冩暣鍙傛暟
  2. 澶氬洜瀛愰€夎偂     鈫?鍏洜瀛愮患鍚堣瘎鍒嗭紝鑷姩鍒嗚鲸"鏈夋満浼?鍜?璇ユ矇娣€"
  3. ATR 鍔ㄦ€侀鎺?  鈫?姣忓彧鑲＄エ浣跨敤鑷韩娉㈠姩鐜囪绠楁鎹燂紝鑰岄潪鍥哄畾 5%
  4. 琛屼笟鍒嗘暎       鈫?鍚岃涓氭渶澶?1 鍙紝浼橀€夊己鍔胯涓氫腑鐨勮秴鍗栬偂
  5. 娉㈠姩鐜囦粨浣?    鈫?浣庢尝鍔ㄨ偂绁ㄤ粨浣嶅姞鎴愶紝楂樻尝鍔ㄨ偂绁ㄤ粨浣嶆墦鎶?

================================================================================
绛栫暐娴佺▼锛堟瘡鏃?14:50锛?
================================================================================
  Step 1: 鏍囪甯傚満鐘舵€侊紙鐗?鐔?闇囪崱锛夛紝搴旂敤鑷€傚簲鍙傛暟
  Step 2: 棰勫姞杞芥墍鏈夎偂绁ㄦ暟鎹埌缂撳瓨
  Step 3: 妫€鏌ユ墍鏈夋寔浠撶殑鍑哄満鏉′欢锛圓TR姝㈡崯/璺熻釜姝㈢泩/RSI杩囩儹/鏃堕棿姝㈡崯锛?
  Step 4: 璁＄畻琛屼笟鍔ㄩ噺
  Step 5: 澶氬洜瀛愮瓫閫?+ 璇勫垎鎺掑簭
  Step 6: 鎸夎瘎鍒嗕粠楂樺埌浣庝拱鍏ワ紝琛屼笟鍒嗘暎锛屼粨浣嶈嚜閫傚簲

================================================================================
妯″潡鏋舵瀯
================================================================================
  config.py      鈫?鎵€鏈夊彲璋冨弬鏁帮紙澶氬洜瀛愭潈閲嶃€丄TR鍊嶆暟銆佸競鍦虹姸鎬佸弬鏁扮瓑锛?
  indicators.py  鈫?绾嚱鏁版妧鏈寚鏍囷紙RSI銆丄TR銆丮A銆侀噺姣斻€佸舰鎬佽瘑鍒€佸競鍦哄垎绫伙級
  stock_pool.py  鈫?35 鍙簿閫夎偂绁ㄥ€欓€夋睜锛?2 涓涓氾級
  screener.py    鈫?鍏洜瀛愰€夎偂鎵撳垎寮曟搸
  main.py        鈫?绛栫暐涓荤▼搴忥紙鐘舵€佺鐞嗐€佷氦鏄撴墽琛屻€佹棩蹇楄緭鍑猴級
================================================================================
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gm.api import *

import config
import indicators
import stock_pool
import screener

# =============================================================================
# 鍏ㄥ眬鍒濆鍖?
# =============================================================================

set_token(config.GM_TOKEN)

# 鑲＄エ姹?
SYMBOLS       = stock_pool.get_all_symbols()
SYMBOL_SECTOR = stock_pool.get_symbol_sector_map()

# 澶х洏鎸囨暟绗﹀彿
MARKET_INDEX = config.MARKET_INDEX

print('鈺? + '鈺? * 58 + '鈺?)
print('鈺? V16 澶氬洜瀛愯嚜閫傚簲鍧囧€煎洖褰掔瓥鐣?)
print('鈺? 鑲＄エ姹? %d 鍙?/ %d 涓涓? % (len(SYMBOLS), len(stock_pool.get_sector_list())))
print('鈺? 鍏洜瀛愰€夎偂 + ATR鍔ㄦ€侀鎺?+ 甯傚満鐘舵€佽嚜閫傚簲 + 琛屼笟娉㈠姩鐜囦粨浣?)
print('鈺? + '鈺? * 58 + '鈺?)


# =============================================================================
# init() 鈥?GM 妗嗘灦鍒濆鍖?
# =============================================================================

def init(context):
    """
    绛栫暐鍒濆鍖?
      - 鍒涘缓鎸佷粨璺熻釜缁撴瀯
      - 璁㈤槄鑲＄エ + 澶х洏鎸囨暟鏁版嵁
      - 娉ㄥ唽姣忔棩 14:50 璋冨害
    """
    # ---- 鎸佷粨璺熻釜 ----
    # pos_info: {symbol: {'cost': 鎴愭湰浠? 'peak': 鏈€楂樹环,
    #                     'entry_date': 鍏ュ満鏃ユ湡, 'sector': 琛屼笟}}
    context.pos_info = {}

    # sector_pos: {sector: symbol} 鈥?琛屼笟鍗犵敤鎯呭喌
    context.sector_pos = {}

    # data_cache: 鍚?bar 鏁版嵁缂撳瓨
    context.data_cache = {}

    # regime: 褰撳墠甯傚満鐘舵€?'bull' / 'range' / 'bear'
    context.regime = 'range'

    # ---- 缁熻 ----
    context.stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0.0}

    # ---- 璁㈤槄鏁版嵁 ----
    # 鍏ㄩ儴鑲＄エ + 澶х洏鎸囨暟
    all_symbols = list(SYMBOLS) + [MARKET_INDEX]
    subscribe(symbols=all_symbols, frequency='1d', count=config.DATA_COUNT)

    # ---- 璋冨害 ----
    schedule(schedule_func=on_bar, date_rule='1d', time_rule='14:50:00')

    # ---- 鍥炴祴瀹屾垚鍥炶皟 ----
    context.on_backtest_finished = on_backtest_finished


# =============================================================================
# on_bar() 鈥?姣忔棩浜ゆ槗涓婚€昏緫
# =============================================================================

def on_bar(context, bars=None):
    try:
        _on_bar_impl(context, bars)
    except Exception as e:
        import traceback
        print('[寮傚父] on_bar 鍑洪敊: %s' % e)
        traceback.print_exc()


def _on_bar_impl(context, bars=None):
    """
    姣忔棩 14:50 瑙﹀彂涓€娆★紙schedule 鍥炶皟锛夈€?
    GM 妗嗘灦鏈夋椂浼氶澶栦紶鍏?bars 鍙傛暟锛屽洜姝や繚鐣?bars 浠ュ吋瀹逛袱绉嶈皟鐢ㄦ柟寮忋€?

    瀹屾暣娴佺▼锛?
      甯傚満鐘舵€?鈫?鏁版嵁棰勫姞杞?鈫?鍑哄満妫€鏌?鈫?琛屼笟鍔ㄩ噺 鈫?閫夎偂鎵撳垎 鈫?鍏ュ満鎵ц
    """
    # ---- Step 0: 娓呯紦瀛?----
    context.data_cache = {}

    # ---- Step 1: 甯傚満鐘舵€佸垽鏂?----
    context.regime = _detect_regime(context)
    regime_cfg = config.REGIME_PARAMS.get(context.regime, config.REGIME_PARAMS['range'])

    # ---- Step 2: 棰勫姞杞藉叏閮ㄨ偂绁ㄦ暟鎹?----
    loaded_count = _preload_data(context)

    # ---- Step 3: 妫€鏌ュ嚭鍦?----
    _check_exits(context, regime_cfg)

    # ---- Step 4: 琛屼笟鍔ㄩ噺璁＄畻 ----
    sector_momentum = screener.calc_sector_momentum(context)

    # ---- Step 5: 澶氬洜瀛愰€夎偂鎵撳垎 ----
    candidates = screener.screen_all(context, sector_momentum)

    # ---- Step 6: 鎵ц鍏ュ満 ----
    taken = 0
    if len(context.pos_info) < regime_cfg['max_positions']:
        taken = _execute_entries(context, candidates, regime_cfg)

    # ---- 姣忔棩鐘舵€佹棩蹇楋紙濮嬬粓杈撳嚭锛屾柟渚跨洃鎺э級----
    pos_count = len(context.pos_info)
    # 灏濊瘯鑾峰彇褰撳墠鏃ユ湡
    try:
        if bars and len(bars) > 0:
            date_str = bars[0].bob.strftime('%Y-%m-%d')
        else:
            date_str = str(context.now.strftime('%Y-%m-%d'))
    except Exception:
        date_str = '--'
    print('[鐘舵€乚 %s | %s | 鏁版嵁:%d鍙?| 鍊欓€?%d鍙?| 涔板叆:%d | 鎸佷粨:%d/%d | RSI闃堝€?%d'
          % (date_str, context.regime, loaded_count, len(candidates), taken,
             pos_count, regime_cfg['max_positions'], regime_cfg.get('rsi_buy', config.RSI_BUY)))


# =============================================================================
# 鏁版嵁鑾峰彇锛堝甫缂撳瓨锛?
# =============================================================================

def _preload_data(context):
    """棰勫姞杞芥墍鏈夎偂绁?+ 澶х洏鎸囨暟鐨勫巻鍙叉暟鎹埌缂撳瓨銆傝繑鍥炴垚鍔熷姞杞界殑鑲＄エ鏁般€?""
    all_symbols = list(SYMBOLS) + [MARKET_INDEX]
    loaded = 0
    for sym in all_symbols:
        df = _get_bar_data(context, sym)
        if df is not None:
            loaded += 1
    return loaded


def _get_bar_data(context, sym):
    """鑾峰彇鑲＄エ鏃ョ嚎 DataFrame锛屽悓 bar 鍐呯紦瀛樸€?""
    if sym in context.data_cache:
        return context.data_cache[sym]

    try:
        # 鈿狅笍 context.data() 鍙湁 4 涓弬鏁? symbol, frequency, count, fields
        # skip_suspended/fill_missing 鏄?history() 鐨勫弬鏁帮紝context.data() 涓嶆敮鎸侊紒
        df = context.data(
            symbol=sym,
            frequency='1d',
            count=config.DATA_COUNT,
        )
        if df is not None and len(df) >= config.MIN_DATA_BARS:
            context.data_cache[sym] = df
            return df
        elif df is not None:
            context.data_cache[sym] = None  # 鏁版嵁鏉℃暟涓嶈冻
        else:
            context.data_cache[sym] = None
    except Exception as e:
        # 绗竴涓け璐ョ殑鏍囩殑鎵撳嵃寮傚父淇℃伅鐢ㄤ簬鎺掓煡
        if not hasattr(context, '_data_error_printed'):
            context._data_error_printed = True
            import traceback
            print('[閿欒] context.data(%s) 寮傚父: %s' % (sym, e))
            traceback.print_exc()
        context.data_cache[sym] = None

    return None


# =============================================================================
# 甯傚満鐘舵€佸垽鏂?
# =============================================================================

def _detect_regime(context):
    """
    鍩轰簬澶х洏鎸囨暟锛堜笂璇佺患鎸囷級鍒ゆ柇褰撳墠甯傚満鐘舵€併€?

    浣跨敤 indicators.classify_regime():
      - bull:  浠锋牸 > MA60 涓旇繎 20 鏃ヨ穼骞?< 8%
      - bear:  杩?20 鏃ヨ穼骞?> 8%锛堜弗閲嶄笅璺岋級
      - range: 鍏朵綑鎯呭喌

    杩斿洖:
        str: 'bull' | 'range' | 'bear'
    """
    df = _get_bar_data(context, MARKET_INDEX)
    if df is None:
        return 'range'

    closes = df['close'].values
    regime = indicators.classify_regime(
        closes,
        ma_period=config.REGIME_MA_PERIOD,
        bear_threshold=config.REGIME_BEAR_THRESHOLD
    )
    return regime


# =============================================================================
# 鍑哄満閫昏緫
# =============================================================================

def _check_exits(context, regime_cfg):
    """
    閬嶅巻鎵€鏈夋寔浠擄紝鎸変紭鍏堢骇妫€鏌ュ嚭鍦烘潯浠躲€?

    鍑哄満鏉′欢:
      1. ATR 鍥哄畾姝㈡崯: 浜忔崯 > min(STOP_LOSS_CAP, ATR_STOP_MULT 脳 ATR)
      2. ATR 璺熻釜姝㈢泩: 浠庨珮鐐瑰洖鎾?> ATR_TRAIL_MULT 脳 ATR
      3. RSI 杩囩儹: RSI > RSI_EXIT
      4. 鏃堕棿姝㈡崯: 鎸佷粨 > TIME_STOP_DAYS 涓旀湭鐩堝埄
    """
    for sym in list(context.pos_info.keys()):
        info = context.pos_info[sym]
        df    = _get_bar_data(context, sym)
        if df is None:
            continue

        closes = df['close'].values
        highs  = df['high'].values
        lows   = df['low'].values
        opens  = df['open'].values

        if len(closes) < 2:
            continue

        cur_price = float(closes[-1])

        # ---- 鏇存柊鏈€楂樹环 ----
        if cur_price > info['peak']:
            info['peak'] = cur_price

        # ---- 璁＄畻 ATR 鍜屾尝鍔ㄧ巼 ----
        atr = indicators.calc_atr(highs, lows, closes, config.ATR_PERIOD)
        if atr is None:
            atr = cur_price * 0.03  # 榛樿 3% 娉㈠姩鐜?

        # ---- 鐩堜簭 ----
        pnl = (cur_price - info['cost']) / info['cost']

        # ---- 鍑哄満鍒ゅ畾 ----
        reason = None

        # 鏉′欢 1: ATR 鍥哄畾姝㈡崯
        stop_mult = regime_cfg.get('atr_stop_mult', config.ATR_STOP_MULT)
        stop_loss_pct = atr / cur_price * stop_mult
        stop_loss_pct = min(stop_loss_pct, config.STOP_LOSS_CAP)  # 涓婇檺淇濇姢
        stop_loss_pct = max(stop_loss_pct, 0.03)                   # 涓嬮檺 3%

        if pnl <= -stop_loss_pct:
            reason = 'ATR姝㈡崯(%.1f%%)' % (stop_loss_pct * 100)

        # 鏉′欢 2: ATR 璺熻釜姝㈢泩锛堜粎鐩堝埄鐘舵€侊級
        elif info['peak'] > info['cost']:
            trail_pct = atr / cur_price * config.ATR_TRAIL_MULT
            trail_pct = max(trail_pct, 0.04)  # 鑷冲皯 4% 鍥炴挙鎵嶈Е鍙?
            if cur_price <= info['peak'] * (1.0 - trail_pct):
                reason = 'ATR璺熻釜(%.1f%%)' % (trail_pct * 100)

        # 鏉′欢 3: RSI 杩囩儹
        if reason is None:
            rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
            if rsi is not None and rsi > config.RSI_EXIT:
                reason = 'RSI杩囩儹(%.0f)' % rsi

        # 鏉′欢 4: 鏃堕棿姝㈡崯
        if reason is None:
            days_held = _count_holding_days(info)
            if days_held >= config.TIME_STOP_DAYS and pnl < 0.02:
                reason = '鏃堕棿姝㈡崯(%dd)' % days_held

        # ---- 鎵ц鍗栧嚭 ----
        if reason:
            _execute_sell(context, sym, cur_price, reason, info, atr / cur_price)


def _count_holding_days(info):
    """浼扮畻鎸佷粨澶╂暟锛堝熀浜?bar 璁℃暟锛夈€?""
    if 'bar_count' not in info:
        info['bar_count'] = 0
    info['bar_count'] += 1
    return info['bar_count']


def _execute_sell(context, sym, price, reason, info, vol_pct):
    """鎵ц鍗栧嚭鎿嶄綔銆?""
    # 鏌ヨ瀹為檯鎸佷粨
    vol = 0
    all_positions = get_position()
    if all_positions:
        for pos in all_positions:
            if pos.symbol == sym:
                vol = int(pos.volume)
                break

    # 娓呯悊璁板綍
    context.pos_info.pop(sym, None)
    sector = info.get('sector', SYMBOL_SECTOR.get(sym, '鏈煡'))
    if sector in context.sector_pos:
        del context.sector_pos[sector]

    # 璁＄畻鐩堜簭
    pnl_pct = (price - info['cost']) / info['cost'] * 100
    days = info.get('bar_count', 0)

    # 涓嬪崟
    if vol > 0:
        order_volume(
            symbol=sym,
            volume=vol,
            side=OrderSide_Sell,
            order_type=OrderType_Market,
            position_effect=PositionEffect_Close
        )

    # 鏃ュ織
    print('[鍗栧嚭] %s | %s | %s | 浠?.2f | %+.2f%% | %dd | 娉㈠姩%.1f%%'
          % (sym, sector, reason, price, pnl_pct, days, vol_pct * 100))

    # 鏇存柊缁熻
    context.stats['total_trades'] += 1
    context.stats['total_pnl'] += pnl_pct
    if pnl_pct > 0:
        context.stats['wins'] += 1
    else:
        context.stats['losses'] += 1


# =============================================================================
# 鍏ュ満閫昏緫
# =============================================================================

def _execute_entries(context, candidates, regime_cfg):
    """
    鎸夎瘎鍒嗕粠楂樺埌浣庢墽琛屼拱鍏ャ€?

    瑙勫垯:
      - 姣忚涓氭渶澶氫拱鍏?1 鍙?
      - 鎬讳拱鍏ユ暟 鈮?max_positions - 褰撳墠鎸佷粨鏁?
      - 楂樻尝鍔ㄨ涓氫粨浣嶆墦鎶橈紝浣庢尝鍔ㄨ涓氫粨浣嶅姞鎴?
      - ATR 鍔ㄦ€佹鎹熷湪鍏ュ満鏃惰褰?

    杩斿洖:
        int: 瀹為檯涔板叆鐨勮偂绁ㄦ暟閲?
    """
    occupied_sectors = set(context.sector_pos.keys())
    remaining = regime_cfg['max_positions'] - len(context.pos_info)
    if remaining <= 0:
        return 0

    taken_sectors = set(occupied_sectors)
    taken_count   = 0

    # 鏌ヨ鍙敤璧勯噾锛圙M 涓嬪崟鏄紓姝ョ殑锛岃繖閲岀敤 snapshot锛?
    cash_info = get_cash()
    available_cash = float(cash_info.available)
    initial_cash = available_cash  # 璁板綍鍒濆璧勯噾锛岀敤浜庤绠楁瘡绗斿垎閰?

    for c in candidates:
        if taken_count >= remaining:
            break

        sym    = c['symbol']
        sector = c['sector']
        price  = c['price']
        rsi    = c['rsi']
        score  = c['total']

        # 宸叉寔浠?
        if sym in context.pos_info:
            continue

        # 璇ヨ涓氭湰杞凡涔板叆
        if sector in taken_sectors:
            continue

        # ---- 娉㈠姩鐜囦粨浣嶈皟鏁?----
        vol_group = stock_pool.get_sector_volatility_group(sector)
        if vol_group == 'high':
            pos_pct = config.POSITION_PCT * config.VOL_ADJ_HIGH
        elif vol_group == 'low':
            pos_pct = config.POSITION_PCT * config.VOL_ADJ_LOW
        else:
            pos_pct = config.POSITION_PCT

        # ---- 璁＄畻涔板叆鏁伴噺锛堝熀浜庡綋鍓嶅彲鐢ㄨ祫閲戯紝涓嶅仛閫掑噺鍋囪锛?---
        # GM 寮傛涓嬪崟锛宑ash.available 鍦ㄦ湰 bar 鍐呬笉浼氬彉
        # 鐢?remaining 璁℃暟闄愬埗锛屽疄闄呬粨浣嶇敱 POSITION_PCT 鎺у埗
        allocated = initial_cash * pos_pct / max(remaining - taken_count, 1)
        if allocated < price * 100:
            continue  # 璧勯噾涓嶈冻 1 鎵?

        qty = int(allocated / (price * 100)) * 100
        if qty < 100:
            continue

        # ---- 涓嬪崟 ----
        order_volume(
            symbol=sym,
            volume=qty,
            side=OrderSide_Buy,
            order_type=OrderType_Market,
            position_effect=PositionEffect_Open
        )

        # ---- 璁板綍鎸佷粨 ----
        context.pos_info[sym] = {
            'cost':       price,
            'peak':       price,
            'bar_count':  0,
            'sector':     sector,
            'entry_rsi':  rsi,
            'vol_group':  vol_group,
            'score':      score,
        }
        context.sector_pos[sector] = sym
        taken_sectors.add(sector)
        taken_count += 1
        # 涓嶅啀閫掑噺 available_cash锛孏M 寮傛涓嬪崟 cash 涓嶄細绔嬪嵆鏇存柊

        # 璇︾粏鏃ュ織
        details = c['details']
        print('[涔板叆] %s | %s(%s) | 璇勫垎%.3f | RSI%.1f | %.2f脳%d | 浣欒祫%.0f'
              % (sym, sector, vol_group, score, rsi, price, qty, available_cash))
        print('       鍥犲瓙: RSI=%.2f 瓒嬪娍=%.2f 閲?%.2f 璺屽箙=%.2f 褰㈡€?%.2f 琛屼笟=%.2f'
              % (details['rsi_score'], details['trend_score'],
                 details['vol_score'], details['dd_score'],
                 details['reversal_score'], details['sector_score']))

    return taken_count


# =============================================================================
# 鍥炴祴瀹屾垚鍥炶皟
# =============================================================================

def on_backtest_finished(context, indicator):
    """鍥炴祴缁撴潫鏃剁殑鎬荤粨鏃ュ織銆?""
    s = context.stats
    pos_count = len(context.pos_info)

    print()
    print('=' * 56)
    print('  鍥炴祴缁撴潫 鈥?V16 澶氬洜瀛愯嚜閫傚簲鍧囧€煎洖褰掔瓥鐣?)
    print('=' * 56)
    print('  鎬讳氦鏄撴鏁? %d  |  鑳? %d  |  璐? %d  |  鑳滅巼: %.1f%%'
          % (s['total_trades'], s['wins'], s['losses'],
             (s['wins'] / s['total_trades'] * 100) if s['total_trades'] > 0 else 0))
    print('  绱鐩堜簭 : %+.2f%%' % s['total_pnl'])
    print('  鍓╀綑鎸佷粨 : %d 鍙? % pos_count)
    try:
        nav = context.account().nav
        print('  鏈€缁堝噣鍊?: %.2f  |  璧勯噾: %.0f'
              % (nav, float(get_cash().nav)))
    except Exception:
        pass
    print('=' * 56)


# =============================================================================
# 閿欒澶勭悊
# =============================================================================

def handle_error(context, error_code, error_msg, **kwargs):
    print('[閿欒] code=%s msg=%s' % (error_code, error_msg))


# =============================================================================
# 鍥炴祴鍏ュ彛
# =============================================================================

if __name__ == '__main__':
    run(
        filename='main.py',
        backtest_start_time=config.BACKTEST_START,
        backtest_end_time=config.BACKTEST_END,
        backtest_initial_cash=config.BACKTEST_CASH,
        backtest_adjust=ADJUST_PREV,
    )
