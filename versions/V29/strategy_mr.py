"""
strategy_mr.py - 鍧囧€煎洖褰掔瓥鐣?(V18)

缁ф壙 V17 鍏洜瀛愭墦鍒嗘牳蹇冿紝鍘绘帀 MA60 瓒嬪娍鍑哄満銆?
浣滀负 V18 澶氱瓥鐣ヨ瀺鍚堜腑鐨勩€屾妱搴曢€夋墜銆嶃€?

淇″彿鏍煎紡:
  get_signal(df, sector, sector_momentum, regime) -> {
      'action': 'BUY' | 'HOLD',
      'confidence': 0.0 ~ 1.0,
      'score': float,
      'rsi': float,
      'reason': str,
  }

  check_exit(df, pos_info, regime, context=None) -> {
      'action': 'SELL' | 'HOLD',
      'confidence': 0.0 ~ 1.0,
      'reason': str,
  }
"""

import numpy as np
import config
import indicators
import stock_pool

SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    鍧囧€煎洖褰掍拱鍏ヤ俊鍙枫€?

    浣跨敤鍏洜瀛愮患鍚堣瘎鍒?
      RSI瓒呭崠(35%) + 瓒嬪娍瀵归綈(20%) + 閲忚兘纭(15%)
      + 璺屽箙(15%) + 鍙嶈浆褰㈡€?8%) + 琛屼笟鍔ㄩ噺(7%)

    鍙傛暟:
        df: DataFrame with columns [open, high, low, close, volume]
        sector: 琛屼笟鍚嶇О
        sector_momentum: 琛屼笟鍔ㄩ噺瀛楀吀 {sector: momentum}
        regime: 'bull' | 'range' | 'bear'

    杩斿洖:
        dict: {'action', 'confidence', 'score', 'rsi', 'reason'} 鎴?None
    """
    closes = df['close'].values
    opens  = df['open'].values
    highs  = df['high'].values
    lows   = df['low'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < config.MIN_DATA_BARS:
        return None

    cur_price = float(closes[-1])

    # ---- 蹇€熻繃婊?----
    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])
    rsi_buy_threshold = regime_cfg.get('rsi_buy', config.RSI_BUY)
    entry_threshold = regime_cfg.get('entry_threshold', config.ENTRY_THRESHOLD)

    # ---- RSI ----
    rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
    if rsi is None:
        return None

    if rsi >= rsi_buy_threshold:
        return {'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
                'rsi': round(rsi, 1), 'reason': 'RSI=%.0f >= %d' % (rsi, rsi_buy_threshold)}

    # ---- 鏋佸害瓒呭崠蹇€熻矾寰?----
    if rsi < 18:
        return {'action': 'BUY', 'confidence': 0.95, 'score': 0.99,
                'rsi': round(rsi, 1), 'reason': '鏋佸害瓒呭崠 RSI=%.0f' % rsi}

    # ---- 鍏洜瀛愭墦鍒?----
    w = config.SCORING_WEIGHTS

    # 鍥犲瓙1: RSI瓒呭崠娣卞害
    if rsi < rsi_buy_threshold:
        rsi_score = (rsi_buy_threshold - rsi) / (rsi_buy_threshold - config.RSI_DEEP_OVERSOLD)
        rsi_score = min(1.0, max(0.0, rsi_score))
    else:
        rsi_score = 0.0

    # 鍥犲瓙2: 瓒嬪娍瀵归綈
    trend_score = 0.0
    ma20 = indicators.calc_sma(closes, config.MA_SHORT)
    ma60 = indicators.calc_sma(closes, config.MA_LONG)
    if ma20 and cur_price > ma20:
        trend_score += 0.5
    if ma60 and cur_price > ma60:
        trend_score += 0.5

    # 鍥犲瓙3: 閲忚兘纭
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0
    if vol_ratio >= config.VOL_SURGE_MIN:
        vol_score = min(1.0, (vol_ratio - config.VOL_SURGE_MIN) / (2.0 - config.VOL_SURGE_MIN))
    else:
        vol_score = 0.0

    # 鍥犲瓙4: 璺屽箙
    dd = indicators.calc_drawdown(closes, 20)
    if dd is None:
        dd_score = 0.0
    elif dd > 0.20:
        dd_score = 0.5
    elif dd > 0.05:
        dd_score = min(1.0, dd / 0.15)
    else:
        dd_score = dd / 0.05 * 0.5

    # 鍥犲瓙5: 鍙嶈浆褰㈡€?
    reversal = indicators.detect_reversal(opens, highs, lows, closes)
    reversal_score = reversal['score']

    # 鍥犲瓙6: 琛屼笟鍔ㄩ噺
    if sector_momentum and sector and sector in sector_momentum:
        sm = sector_momentum[sector]
        sector_score = max(0.0, min(1.0, (sm + 0.5) / 1.0))
    else:
        sector_score = 0.5

    total = (
        w['rsi_oversold']    * rsi_score +
        w['trend_align']     * trend_score +
        w['volume_surge']    * vol_score +
        w['drawdown']        * dd_score +
        w['reversal_form']   * reversal_score +
        w['sector_momentum'] * sector_score
    )

    if total >= entry_threshold:
        confidence = min(1.0, total)
        return {
            'action': 'BUY',
            'confidence': confidence,
            'score': round(total, 4),
            'rsi': round(rsi, 1),
            'reason': '澶氬洜瀛愯瘎鍒?.3f RSI=%.0f' % (total, rsi),
        }

    return {'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'rsi': round(rsi, 1), 'reason': '璇勫垎%.3f < %.2f' % (total, entry_threshold)}


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    鍧囧€煎洖褰掔瓥鐣ョ殑鍑哄満閫昏緫銆?

    鍑哄満浼樺厛绾?
      1. ATR 璺熻釜姝㈢泩
      2. ATR 鍥哄畾姝㈡崯
      3. RSI 杩囩儹
      4. 鏃堕棿姝㈡崯锛堟棤鐩堝埄鍒欏嚭鍦猴級

    V18: 鍘婚櫎 MA60 瓒嬪娍鍑哄満锛屽噺灏戣繃鏃╂鎹熴€?
    """
    closes = df['close'].values
    highs  = df['high'].values
    lows   = df['low'].values

    if len(closes) < 2:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    peak = pos_info.get('peak', cost)
    entry_date = pos_info.get('entry_date', '')

    # 鏇存柊宄板€?
    if cur_price > peak:
        peak = cur_price

    # ---- ATR ----
    atr = indicators.calc_atr(highs, lows, closes, config.ATR_PERIOD)
    if atr is None:
        atr = cur_price * 0.03

    pnl = (cur_price - cost) / cost
    regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

    # 1. ATR 璺熻釜姝㈢泩
    if peak > cost:
        trail_pct = atr / cur_price * config.ATR_TRAIL_MULT
        trail_pct = max(trail_pct, 0.04)
        if cur_price <= peak * (1.0 - trail_pct):
            return {
                'action': 'SELL',
                'confidence': 0.9,
                'reason': 'MR_ATR璺熻釜姝㈢泩(%.1f%%)' % (trail_pct * 100),
            }

    # 2. ATR 姝㈡崯
    stop_mult = regime_cfg.get('atr_stop_mult', config.ATR_STOP_MULT)
    stop_loss_pct = min(atr / cur_price * stop_mult, config.STOP_LOSS_CAP)
    stop_loss_pct = max(stop_loss_pct, 0.04)  # V19.1: 3%鈫?%锛岄伩鍏嶆甯告尝鍔ㄨЕ鍙?
    if pnl <= -stop_loss_pct:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'MR_ATR姝㈡崯(%.1f%%)' % (stop_loss_pct * 100),
        }

    # 3. RSI 杩囩儹
    rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
    if rsi is not None and rsi > config.RSI_EXIT:
        return {
            'action': 'SELL',
            'confidence': 0.8,
            'reason': 'MR_RSI杩囩儹(%.0f)' % rsi,
        }

    # 4. 鏃堕棿姝㈡崯
    days_held = _count_days(entry_date, context, today_str)
    if days_held >= config.TIME_STOP_DAYS and pnl < 0.03:
            return {
                'action': 'SELL',
                'confidence': 0.7,
                'reason': 'MR_鏃堕棿姝㈡崯(%dd)' % days_held,
            }

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}


def _count_days(entry_date, context=None, today_str=None):
    """璁＄畻鎸佷粨澶╂暟銆備紭鍏堜娇鐢ㄤ紶鍏ョ殑 today_str锛屽叾娆?context._today锛屾渶鍚?datetime.now()銆?""
    if not entry_date:
        return 0
    try:
        if not today_str:
            if context and hasattr(context, '_today'):
                today_str = context._today
        if not today_str:
            from datetime import datetime
            today_str = datetime.now().strftime('%Y-%m-%d')

        from datetime import datetime as dt
        entry = dt.strptime(entry_date, '%Y-%m-%d')
        today = dt.strptime(today_str, '%Y-%m-%d')
        return (today - entry).days
    except Exception:
        return 0
