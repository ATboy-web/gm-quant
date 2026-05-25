"""
strategy_momentum.py - 鍔ㄩ噺瓒嬪娍绛栫暐 (V29)

瓒嬪娍璺熻釜閫夋墜锛氬仛澶氬己鍔胯偂锛屾崟鎹夋寔缁笂娑ㄨ鎯呫€?
涓庡潎鍊煎洖褰掔瓥鐣ュ舰鎴愪簰琛?鈥斺€?瓒嬪娍甯備腑鍔ㄩ噺璧氶挶锛岄渿鑽″競涓潎鍊煎洖褰掕禋閽便€?

V29 浼樺寲锛堣В鍐?-65.9% 浜忔崯锛?
  1. 鍏ュ満闂ㄦ: score 0.35鈫?.55, 鍙彇寮哄姩閲?
  2. 閲忚兘纭棬: vol_ratio>=1.3锛堜笉鍐嶆槸绾墦鍒嗭級
  3. RSI 涓嬮檺: >45锛堝姩閲忓繀椤绘湁寮哄害锛?
  4. 鍧囩嚎鍒嗙搴? MA20/MA60>1.5%锛堜笉鍐嶆槸绾?0锛?
  5. 閲戝弶浼樺厛: 5鏃ュ唴閲戝弶棰濆鍔犲垎
  6. 绉诲姩姝㈡崯: 鐩堝埄>5%鍚庢鐩堢嚎缂╄嚦10%

V18 淇″彿閫昏緫:
  涔板叆: 鍧囩嚎澶氬ご鎺掑垪 (MA20 > MA60) + 浠锋牸鍦?MA20 涓婃柟 + 鏀鹃噺閰嶅悎
  鍗栧嚭: 浠锋牸璺岀牬 MA20 鎴栧潎绾挎鍙?
  缃俊搴? 鍩轰簬瓒嬪娍寮哄害锛堝潎绾垮垎绂诲害 + 杩戞湡鏀剁泭鐜?+ 閲忚兘锛?
"""

import numpy as np
import config
import indicators


# 鍔ㄩ噺绛栫暐涓撶敤鍙傛暟 (V29 鏀剁揣)
MOM_MA_FAST   = 20    # 蹇嚎
MOM_MA_SLOW   = 60    # 鎱㈢嚎
MOM_VOL_MIN   = 1.3   # V29: 1.1鈫?.3, 閲忚兘纭棬鎻愰珮
MOM_STOP_LOSS = 0.06  # 鍥哄畾姝㈡崯 6%
MOM_TAKE_PROFIT = 0.15  # 鍥哄畾姝㈢泩 15%
MOM_STRENGTH_PERIOD = 10  # 瓒嬪娍寮哄害璁＄畻绐楀彛
MOM_SCORE_MIN  = 0.55  # V29: 0.35鈫?.55, 鍙彇寮哄姩閲忎俊鍙?
MOM_MA_SPREAD_MIN = 0.015  # V29: 鏂板, MA20蹇呴』姣擬A60楂?.5%
MOM_RSI_MIN    = 45    # V29: 鏂板, RSI涓嬮檺锛屽姩閲忓繀椤绘湁寮哄害
MOM_RSI_MAX    = 70    # V29: 75鈫?0, 涓嶅湪鏋佺瓒呬拱鏃惰拷鍏?
MOM_GOLDEN_CROSS_DAYS = 5  # V29: 鏂板, 5鏃ュ唴閲戝弶浼樺厛
MOM_TRAIL_PROFIT = 0.05  # V29: 鏂板, 鐩堝埄5%鍚庡惎鍔ㄧЩ鍔ㄦ鐩?


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    鍔ㄩ噺瓒嬪娍涔板叆淇″彿銆?

    Args:
        df: DataFrame with [open, high, low, close, volume]
        sector: 琛屼笟锛堟湭浣跨敤锛屼繚鐣欐帴鍙ｏ級
        sector_momentum: 琛屼笟鍔ㄩ噺锛堟湭浣跨敤锛?
        regime: 甯傚満鐘舵€?

    Returns:
        dict | None: {'action', 'confidence', 'score', 'reason'}
    """
    closes = df['close'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < MOM_MA_SLOW + 1:
        return None

    cur_price = float(closes[-1])

    # ---- 浠锋牸杩囨护 ----
    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 鍧囩嚎璁＄畻 ----
    ma20 = indicators.calc_sma(closes, MOM_MA_FAST)
    ma60 = indicators.calc_sma(closes, MOM_MA_SLOW)

    if ma20 is None or ma60 is None:
        return None

    prev_closes = closes[:-1]
    prev_ma20 = indicators.calc_sma(prev_closes, MOM_MA_FAST)
    prev_ma60 = indicators.calc_sma(prev_closes, MOM_MA_SLOW)

    # ---- V29: 纭棬1 鈥?鍧囩嚎澶氬ご鎺掑垪涓旀湁瓒冲鍒嗙搴?----
    if ma60 <= 0:
        return None
    ma_spread = (ma20 - ma60) / ma60
    if ma_spread < MOM_MA_SPREAD_MIN:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_鍧囩嚎鍒嗙涓嶈冻(%.1f%%<%.1f%%)' % (ma_spread * 100, MOM_MA_SPREAD_MIN * 100),
        }

    # ---- V29: 纭棬2 鈥?浠锋牸蹇呴』鍦?MA20 涓婃柟 ----
    if cur_price <= ma20:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_浠锋牸鏈珯涓奙A20(%.2f<=%.2f)' % (cur_price, ma20),
        }

    # ---- V29: 纭棬3 鈥?閲忚兘蹇呴』杈炬爣锛堜笉鍐嶆槸绾墦鍒嗭級 ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0
    if vol_ratio < MOM_VOL_MIN:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_閲忚兘涓嶈冻(%.1f<%.1f)' % (vol_ratio, MOM_VOL_MIN),
        }

    # ---- V29: RSI 妫€鏌?鈥?蹇呴』鍦ㄥ悎鐞嗗尯闂?----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None
    if rsi < MOM_RSI_MIN:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_RSI澶急(%.0f<%d)' % (rsi, MOM_RSI_MIN),
        }
    if rsi > MOM_RSI_MAX:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_RSI瓒呬拱(%.0f>%d)' % (rsi, MOM_RSI_MAX),
        }

    # ---- 鐭湡鍔ㄩ噺锛堣繎5鏃ユ定骞咃級 ----
    if n >= 6:
        ret_5d = (closes[-1] / closes[-6] - 1)
    else:
        ret_5d = 0

    # ---- V29: 閲戝弶妫€娴嬶紙N鏃ュ唴閲戝弶锛?----
    golden_cross = False
    golden_cross_days = 999
    if prev_ma20 is not None and prev_ma60 is not None:
        # 褰撳ぉ閲戝弶
        if prev_ma20 <= prev_ma60 and ma20 > ma60:
            golden_cross = True
            golden_cross_days = 0
        else:
            # 鍥炴函N鏃ョ湅鏄惁鏈夋渶杩戦噾鍙?
            for lookback in range(1, MOM_GOLDEN_CROSS_DAYS + 1):
                idx = -(lookback + 1)
                if n < abs(idx) + MOM_MA_SLOW:
                    break
                past_closes = closes[:idx]
                if len(past_closes) < MOM_MA_SLOW + 1:
                    break
                past_ma20 = indicators.calc_sma(past_closes, MOM_MA_FAST)
                past_ma60 = indicators.calc_sma(past_closes, MOM_MA_SLOW)
                past_prev = closes[:idx - 1] if idx - 1 >= -len(closes) else None
                if past_ma20 is None or past_ma60 is None:
                    continue
                # 妫€鏌ュ墠涓€澶?
                past_prev_ma20 = indicators.calc_sma(closes[:idx - 1], MOM_MA_FAST) if len(closes[:idx - 1]) >= MOM_MA_FAST else None
                past_prev_ma60 = indicators.calc_sma(closes[:idx - 1], MOM_MA_SLOW) if len(closes[:idx - 1]) >= MOM_MA_SLOW else None
                if past_prev_ma20 is not None and past_prev_ma60 is not None:
                    if past_prev_ma20 <= past_prev_ma60 and past_ma20 > past_ma60:
                        golden_cross = True
                        golden_cross_days = lookback
                        break

    # ---- 瓒嬪娍寮哄害璇勫垎 ----
    # 1. 鍧囩嚎鍒嗙搴?
    spread_score = min(1.0, max(0.0, (ma_spread - MOM_MA_SPREAD_MIN) / 0.10))

    # 2. 杩戞湡娑ㄥ箙: 10鏃ユ敹鐩婄巼
    if n >= MOM_STRENGTH_PERIOD + 1:
        ret_10d = (closes[-1] / closes[-(MOM_STRENGTH_PERIOD + 1)] - 1)
    else:
        ret_10d = 0
    ret_score = min(1.0, max(0.0, (ret_10d + 0.03) / 0.18))  # -3%~15% 鈫?0~1

    # 3. 閲忚兘鎵撳垎
    vol_score = min(1.0, (vol_ratio - MOM_VOL_MIN) / 1.5)

    # 缁煎悎璇勫垎
    score = spread_score * 0.40 + ret_score * 0.30 + vol_score * 0.20 + (rsi - MOM_RSI_MIN) / 40 * 0.10

    # 閲戝弶棰濆鍔犲垎
    if golden_cross:
        score = min(1.0, score + 0.12 + max(0, 0.03 * (MOM_GOLDEN_CROSS_DAYS - golden_cross_days)))

    # ---- V29 鍐崇瓥: 闂ㄦ浠?0.35 鎻愰珮鍒?0.55 ----
    if score >= MOM_SCORE_MIN:
        reason_parts = []
        if golden_cross:
            if golden_cross_days == 0:
                reason_parts.append('閲戝弶')
            else:
                reason_parts.append('%dd鍓嶉噾鍙? % golden_cross_days)
        reason_parts.append('鍔ㄩ噺%.3f' % score)
        reason_parts.append('spread%.1f%%' % (ma_spread * 100))
        if ret_5d > 0:
            reason_parts.append('5d%+.1f%%' % (ret_5d * 100))

        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'reason': 'MOM_' + '|'.join(reason_parts),
            'ma20': round(ma20, 2),
            'ma60': round(ma60, 2),
            'spread': round(ma_spread * 100, 1),
            'rsi': round(rsi, 1),
        }

    # 瓒嬪娍鍦ㄣ€佷絾璇勫垎涓嶅 鈫?瑙傛湜
    return {
        'action': 'HOLD',
        'confidence': score,
        'score': round(score, 4),
        'reason': 'MOM_璇勫垎%.3f涓嶈冻(闇€鈮?.2f)' % (score, MOM_SCORE_MIN),
    }


def check_exit(df, pos_info, regime='range', context=None):
    """
    鍔ㄩ噺绛栫暐鍑哄満閫昏緫 (V29)銆?

    鍑哄満鏉′欢:
      1. 浠锋牸璺岀牬 MA20锛堣秼鍔胯浆寮憋級
      2. MA20 涓嬬┛ MA60锛堟鍙夛級
      3. 鍥哄畾姝㈡崯/姝㈢泩
      4. V29: 绉诲姩姝㈢泩 鈥?鐩堝埄 > 5% 鍚庢鐩堢嚎缂╄嚦 10%
      5. RSI 鏋佸害瓒呬拱 (>80, V29: 85鈫?0)
    """
    closes = df['close'].values

    if len(closes) < MOM_MA_SLOW + 1:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    ma20 = indicators.calc_sma(closes, MOM_MA_FAST)
    ma60 = indicators.calc_sma(closes, MOM_MA_SLOW)

    if ma20 is None or ma60 is None:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    # 姝诲弶妫€娴嬮渶瑕佸墠涓€鏍筨ar鐨勫潎绾垮€硷紝纭繚closes[:-1]瓒冲闀?
    prev_closes = closes[:-1]
    if len(prev_closes) < MOM_MA_SLOW:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
    prev_ma20 = indicators.calc_sma(prev_closes, MOM_MA_FAST)
    prev_ma60 = indicators.calc_sma(prev_closes, MOM_MA_SLOW)

    # 1. 姝诲弶 = 绔嬪嵆鍑哄満
    if prev_ma20 is not None and prev_ma60 is not None:
        if prev_ma20 >= prev_ma60 and ma20 < ma60:
            return {
                'action': 'SELL',
                'confidence': 1.0,
                'reason': 'MOM_姝诲弶(MA20<MA60)',
            }

    # 2. 璺岀牬 MA20锛圴19: 闇€杩炵画2澶╄穼鐮存墠瑙﹀彂锛岄伩鍏嶅崟鏃ュ櫔闊筹級
    if cur_price < ma20:
        # 妫€鏌ュ墠涓€澶╂槸鍚︿篃璺岀牬
        prev_below_ma20 = False
        if len(closes) >= 2:
            prev_price = float(closes[-2])
            prev_ma20_check = indicators.calc_sma(closes[:-1], MOM_MA_FAST)
            if prev_ma20_check is not None and prev_price < prev_ma20_check:
                prev_below_ma20 = True

        if prev_below_ma20:
            # 杩炵画2澶╄穼鐮?鈫?纭瓒嬪娍杞急
            return {
                'action': 'SELL',
                'confidence': 0.9,
                'reason': 'MOM_杩炵画璺岀牬MA20(%.2f<%.2f)' % (cur_price, ma20),
            }
        # 浠?澶╄穼鐮?鈫?闄嶄綆缃俊搴︼紝闇€瑕佽瀺鍚堟姇绁ㄥ喅瀹?
        return {
            'action': 'SELL',
            'confidence': 0.5,   # V19: 闄嶄綆缃俊搴︼紝涓嶅啀鏄搧鏉垮嚭鍦?
            'reason': 'MOM_鐭殏鐮碝A20(%.2f<%.2f)' % (cur_price, ma20),
        }

    # 3. 鍥哄畾姝㈡崯
    if pnl <= -MOM_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'MOM_姝㈡崯(%+.1f%%)' % (pnl * 100),
        }

    # 4. V29: 绉诲姩姝㈢泩 鈥?鐩堝埄>5%鍚庢鐩堢嚎鏀剁揣鑷?0%
    peak = pos_info.get('peak', cur_price)
    peak_pnl = (peak - cost) / cost
    if peak_pnl >= MOM_TRAIL_PROFIT and pnl < MOM_TAKE_PROFIT * 0.67:
        # 浠庨珮鐐瑰洖鎾わ紝鐢ㄦ洿绱х殑姝㈢泩
        effective_tp = MOM_TAKE_PROFIT * 0.67  # 10%
    else:
        effective_tp = MOM_TAKE_PROFIT

    if pnl >= effective_tp:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'MOM_姝㈢泩(%+.1f%%, 绾?.0f%%)' % (pnl * 100, effective_tp * 100),
        }

    # 5. RSI 鏋佸害瓒呬拱
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is not None and rsi > 80:
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'MOM_RSI鏋佸害瓒呬拱(%.0f)' % rsi,
        }

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
