"""
strategy_breakout.py - 绐佺牬绛栫暐 

閫傜敤浜庨珮娉㈠姩琛屼笟锛堟湁鑹?绉戞妧/鍐涘伐/鏂拌兘婧愶級锛?
鎹曟崏浠锋牸绐佺牬鍏抽敭闃诲姏浣嶅悗鐨勮秼鍔垮姞閫熻鎯呫€?

鏍稿績閫昏緫:
  涔板叆:
    - 浠锋牸绐佺牬 N 鏃ラ珮鐐癸紙濡?20 鏃ユ柊楂橈級
    - 绐佺牬鏃ユ垚浜ら噺鏄捐憲鏀惧ぇ锛堚墺1.5 鍊嶅潎閲忥級
    - 闈炴瀬搴﹁秴涔板尯锛圧SI < 75锛岄伩鍏嶈拷楂橈級
    - 鍧囩嚎澶氬ご鎺掑垪鍔犲垎
  鍗栧嚭:
    - 绐佺牬澶辫触锛? 鏃ュ唴鍥炶惤鑷崇獊鐮翠环涓嬫柟锛?
    - 鍥哄畾姝㈡崯 / 姝㈢泩
    - 閲忚兘钀庣缉 + 浠锋牸楂樹綅 鈫?鍔ㄩ噺琛扮
"""

import numpy as np
import config
import indicators


# 绐佺牬绛栫暐鍙傛暟
BK_BREAKOUT_PERIOD = 20    # 绐佺牬妫€娴嬬獥鍙ｏ紙N鏃ユ柊楂橈級
BK_VOL_SURGE       = 1.5   # 绐佺牬鏃ユ渶灏忛噺姣?
BK_STOP_LOSS       = 0.07  # 鍥哄畾姝㈡崯 7%
BK_TAKE_PROFIT     = 0.15  # 鍥哄畾姝㈢泩 15%
BK_FAIL_DAYS       = 3     # 绐佺牬澶辫触妫€娴嬪ぉ鏁?
BK_FAIL_DROP       = -0.03  # 绐佺牬澶辫触璺屽箙闃堝€?


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    绐佺牬绛栫暐涔板叆淇″彿銆?

    妫€娴?
      1. 浠锋牸鍒?N 鏃ユ柊楂?
      2. 绐佺牬鏃ユ斁閲?
      3. RSI 鏈秴涔?
      4. 鍧囩嚎澶氬ご鎺掑垪鍔犲垎
    """
    closes = df['close'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < BK_BREAKOUT_PERIOD + 5:
        return None

    cur_price = float(closes[-1])

    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 1. 浠锋牸绐佺牬 N 鏃ユ柊楂?----
    recent_high = np.max(closes[-(BK_BREAKOUT_PERIOD + 1):-1])
    breakout = (cur_price > recent_high)

    if not breakout:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'BK_鏈獊鐮?d鏃ラ珮(%.2f<%.2f)' % (BK_BREAKOUT_PERIOD, cur_price, recent_high),
        }

    # ---- 2. 绐佺牬鏃ユ斁閲?----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    vol_breakout = (vol_ratio >= BK_VOL_SURGE)
    vol_score = min(1.0, (vol_ratio - 1.0) / 2.0) if vol_ratio > 1.0 else 0.0

    # ---- 3. RSI 妫€鏌ワ紙閬垮厤杩介珮锛?----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    if rsi > 75:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'BK_RSI瓒呬拱(%.0f)涓嶈拷楂? % rsi,
        }

    # ---- 4. 鍧囩嚎澶氬ご鎺掑垪鍔犲垎 ----
    ma20 = indicators.calc_sma(closes, 20)
    ma60 = indicators.calc_sma(closes, 60)
    ma_bullish = (ma20 is not None and ma60 is not None and ma20 > ma60)
    ma_score = 0.3 if ma_bullish else 0.0

    # ---- 5. 琛屼笟鍔ㄩ噺鍔犲垎 ----
    sector_score = 0.0
    if sector_momentum and sector and sector in sector_momentum:
        sm = sector_momentum[sector]
        sector_score = max(0.0, min(0.3, sm / 0.1 * 0.3))

    # ---- 缁煎悎璇勫垎 ----
    score = 0.40  # 鍩虹鍒嗭細宸茬獊鐮?

    if vol_breakout:
        score += 0.25  # 鏀鹃噺纭
    else:
        score += vol_score * 0.15  # 閮ㄥ垎鏀鹃噺

    score += ma_score
    score += sector_score

    # RSI 鍦ㄥ悎鐞嗗尯闂村姞鍒?
    if 30 <= rsi <= 55:
        score += 0.10  # RSI 鍦ㄥ仴搴峰尯闂?

    score = min(1.0, score)

    if score >= 0.60:   # V26: 0.55鈫?.60, 鏀剁揣鍏ュ満鎻愬崌鑳滅巼
        reason_parts = ['绐佺牬%d鏃ラ珮' % BK_BREAKOUT_PERIOD]
        if vol_breakout:
            reason_parts.append('鏀鹃噺%.1f' % vol_ratio)
        if ma_bullish:
            reason_parts.append('澶氬ご')
        if sector_score > 0:
            reason_parts.append('琛屼笟鍔ㄩ噺+')

        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'rsi': round(rsi, 1),
            'reason': 'BK_' + '|'.join(reason_parts),
        }

    return {
        'action': 'HOLD',
        'confidence': score,
        'score': round(score, 4),
        'reason': 'BK_绐佺牬浣嗚瘎鍒嗕笉瓒?%.3f)' % score,
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    绐佺牬绛栫暐鍑哄満閫昏緫銆?

    鍑哄満鏉′欢:
      1. 绐佺牬澶辫触锛? 鏃ュ唴鍥炶惤鍒扮獊鐮翠环涓嬫柟 -3%锛?
      2. 鍥哄畾姝㈡崯
      3. 鍥哄畾姝㈢泩
      4. 閲忚兘钀庣缉 + 浠锋牸楂樹綅 鈫?鍔ㄩ噺琛扮
    """
    closes = df['close'].values
    vols   = df['volume'].values

    if len(closes) < 5:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    # ---- 1. 绐佺牬澶辫触妫€娴?----
    entry_date = pos_info.get('entry_date', '')
    if entry_date and today_str:
        try:
            from datetime import datetime as dt
            days_held = (dt.strptime(today_str, '%Y-%m-%d') -
                         dt.strptime(entry_date, '%Y-%m-%d')).days
            if days_held <= BK_FAIL_DAYS and pnl < BK_FAIL_DROP:
                return {
                    'action': 'SELL',
                    'confidence': 0.85,
                    'reason': 'BK_绐佺牬澶辫触(%dd %+.1f%%)' % (days_held, pnl * 100),
                }
        except Exception:
            pass

    # ---- 2. 鍥哄畾姝㈡崯 ----
    if pnl <= -BK_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'BK_姝㈡崯(%+.1f%%)' % (pnl * 100),
        }

    # ---- 3. 鍥哄畾姝㈢泩 ----
    if pnl >= BK_TAKE_PROFIT:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'BK_姝㈢泩(%+.1f%%)' % (pnl * 100),
        }

    # ---- 4. 閲忚兘琛扮锛堥珮浣嶇缉閲忥級 ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    if pnl > 0.05 and vol_ratio < 0.6:
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'BK_楂樹綅缂╅噺(%.1f)' % vol_ratio,
        }

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
