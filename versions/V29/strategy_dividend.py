"""
strategy_dividend.py - 绾㈠埄绛栫暐 (V29)

閫傜敤浜庝綆娉㈠姩闃插尽琛屼笟锛堥噾铻?娑堣垂/鐓ょ偔/鍏敤浜嬩笟锛夛紝
浠ヨ偂鎭巼+浣庝及鍊间负鏍稿績锛岃拷姹傜ǔ鍋ユ敹鐩娿€?

V29 浼樺寲锛堣В鍐?-32.2% 浜忔崯銆?53绗旈珮棰戜綆璐ㄤ氦鏄擄級:
  1. "浣庝綅"閲嶅畾涔? 60d娑ㄥ箙<0% AND 20d璺屽箙<-4%锛堝師 OR锛岄棬妲涘ぇ骞呮彁楂橈級
  2. RSI鍖洪棿鏀剁獎: 33-52锛堝師 30-60锛?
  3. 鍏ュ満闂ㄦ: 0.60鈫?.72
  4. 姝㈡崯鏀惧: 5%鈫?%锛堝噺灏戞甯告尝鍔ㄨ姝㈡崯锛?
  5. 鏃堕棿姝㈡崯: 30鈫?8澶╋紙鏇村揩娣樻卑鏃犳晥鎸佷粨锛?
  6. 鏂板MA杩囨护: 浠锋牸蹇呴』浣庝簬MA60锛堢湡姝ｇ殑浠峰€间拱鐐癸級

V18 鏍稿績閫昏緫:
  涔板叆:
    - 浠锋牸澶勪簬鐩稿浣庝綅锛堣繎 60 鏃ヤ笅璺?+ 杩?20 鏃ユ槑鏄惧洖璋冿級
    - 鎴愪氦閲忎笉寮傚父鏀鹃噺锛堟帓闄ゅ埄绌哄嚭閫冿級
    - RSI 鍦?33-52 鍖洪棿锛堥潪鏋佺锛屼絾涓嶈拷楂橈級
    - 浠锋牸浣庝簬 MA60锛堜环鍊煎尯闂达級
  鍗栧嚭:
    - 鍥哄畾姝㈢泩 10%锛堥槻寰¤偂涓嶈椽锛?
    - 鍥哄畾姝㈡崯 6%
    - 鏃堕棿姝㈡崯 18 澶╂棤鏀剁泭 鈫?閫€鍑?
    - RSI > 70 杩囩儹
"""

import numpy as np
import config
import indicators


# 绾㈠埄绛栫暐鍙傛暟 (V29 鏀剁揣)
DV_LOOKBACK       = 60    # 闀挎湡鍥炵湅绐楀彛
DV_SHORT_LOOKBACK = 20    # 鐭湡鍥炵湅绐楀彛
DV_STOP_LOSS      = 0.06  # V29: 0.05鈫?.06, 鏀惧鍑忓皯鍣煶姝㈡崯
DV_TAKE_PROFIT    = 0.10  # 鍥哄畾姝㈢泩 10%
DV_TIME_STOP      = 18    # V29: 30鈫?8, 鏇村揩娣樻卑鏃犳晥鎸佷粨
DV_RSI_BUY_LOW    = 33    # V29: 30鈫?3, RSI涓嬮檺鏀剁獎
DV_RSI_BUY_HIGH   = 52    # V29: 60鈫?2, RSI涓婇檺鏀剁獎
DV_SCORE_MIN      = 0.72  # V29: 0.60鈫?.72, 鍏ュ満闂ㄦ鎻愰珮
DV_LONG_RET_MAX   = 0.0   # V29: 鏂板, 60d娑ㄥ箙蹇呴』<0%
DV_SHORT_RET_MIN  = -0.04 # V29: 鏂板, 20d璺屽箙蹇呴』<-4%


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    绾㈠埄绛栫暐涔板叆淇″彿 (V29)銆?

    妫€娴?
      1. V29: 浠锋牸澶勪簬鐩稿浣庝綅锛?0d 涓嬭穼 AND 20d 鏄庢樉鍥炶皟锛?
      2. 鎴愪氦閲忎笉寮傚父锛堟帓闄ゆ亹鎱屽嚭閫冿級
      3. RSI 鍦?33-52 鍖洪棿
      4. V29: 浠锋牸浣庝簬 MA60锛堜环鍊间拱鍏ュ尯闂达級
    """
    closes = df['close'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < DV_LOOKBACK + 5:
        return None

    cur_price = float(closes[-1])

    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- V29: 纭棬1 鈥?浠锋牸澶勪簬鐩稿浣庝綅锛圓ND 鍏崇郴锛屼笉鍐嶆槸 OR锛?----
    # 杩?60 鏃ユ定骞?< 0锛堝繀椤讳笅璺岋級
    if n >= DV_LOOKBACK + 1 and closes[-(DV_LOOKBACK + 1)] > 0:
        ret_60d = (cur_price / closes[-(DV_LOOKBACK + 1)] - 1)
    else:
        ret_60d = 0

    # 杩?20 鏃ヨ穼骞?
    if n >= DV_SHORT_LOOKBACK + 1 and closes[-(DV_SHORT_LOOKBACK + 1)] > 0:
        ret_20d = (cur_price / closes[-(DV_SHORT_LOOKBACK + 1)] - 1)
    else:
        ret_20d = 0

    # V29: 鍙岄噸鏉′欢 鈥?60d蹇呴』涓嬭穼 AND 20d蹇呴』鏄庢樉鍥炶皟
    if ret_60d >= DV_LONG_RET_MAX:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'DV_60d鏈笅璺?%+.1f%%)' % (ret_60d * 100),
        }
    if ret_20d > DV_SHORT_RET_MIN:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'DV_20d鍥炶皟涓嶈冻(%+.1f%%>%.0f%%)' % (ret_20d * 100, DV_SHORT_RET_MIN * 100),
        }

    # ---- 2. 鎴愪氦閲忎笉寮傚父鏀鹃噺 ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    if vol_ratio >= 2.5:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'DV_寮傚父鏀鹃噺(%.1f)鍙兘鍒╃┖' % vol_ratio,
        }

    vol_ok = (vol_ratio < 1.5)
    vol_score = max(0.0, (1.5 - vol_ratio) / 1.5) if vol_ratio < 1.5 else 0.0

    # ---- 3. RSI 鍦ㄥ悎鐞嗗尯闂?----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    if rsi < DV_RSI_BUY_LOW:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'rsi': round(rsi, 1),
            'reason': 'DV_RSI澶綆(%.0f)璁㎝R澶勭悊' % rsi,
        }

    if rsi > DV_RSI_BUY_HIGH:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'rsi': round(rsi, 1),
            'reason': 'DV_RSI鍋忛珮(%.0f)' % rsi,
        }

    rsi_score = 1.0 - abs(rsi - 42) / 20.0  # V29: RSI=42 鏃舵弧鍒?
    rsi_score = max(0.0, min(1.0, rsi_score))

    # ---- V29: 纭棬4 鈥?浠锋牸蹇呴』浣庝簬 MA60锛堜环鍊煎尯闂达級 ----
    ma20 = indicators.calc_sma(closes, 20)
    ma60 = indicators.calc_sma(closes, 60)

    if ma60 is None:
        return None
    if cur_price >= ma60:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'DV_浠锋牸楂樹簬MA60(%.2f>=%.2f)' % (cur_price, ma60),
        }

    # MA20 鎺ヨ繎 MA60锛堝潎绾挎敹鏁涗腑鐨勪环鍊煎尯鍩燂級
    ma_converge = False
    if ma20 is not None and ma60 > 0:
        spread = abs(ma20 - ma60) / ma60
        if spread < 0.04:
            ma_converge = True

    # ---- V29 缁煎悎璇勫垎 ----
    score = 0.15  # 鍩虹鍒嗭細60d涓嬭穼+20d鍥炶皟

    score += 0.25 * rsi_score       # RSI 鍦ㄥ悎鐞嗗尯闂?
    score += 0.15 * vol_score       # 鎴愪氦閲忓钩绋?
    score += 0.15 if ma_converge else 0.05  # 鍧囩嚎鏀舵暃鍔犲垎
    score += 0.10 if ret_20d < -0.08 else 0.0  # 20d璺岃秴8%棰濆鍔犲垎
    score += 0.15 if ret_60d < -0.15 else 0.0  # 60d璺岃秴15%娣卞害浠峰€?
    score += 0.10 if vol_ok else 0.0            # 閲忚兘骞崇ǔ

    score = min(1.0, score)

    if score >= DV_SCORE_MIN:
        reason_parts = ['浠峰€?]
        reason_parts.append('60d%+.1f%%' % (ret_60d * 100))
        reason_parts.append('20d%+.1f%%' % (ret_20d * 100))
        if ma_converge:
            reason_parts.append('MA鏀舵暃')
        if vol_ok:
            reason_parts.append('閲忕ǔ')
        reason_parts.append('RSI=%.0f' % rsi)

        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'rsi': round(rsi, 1),
            'reason': 'DV_' + '|'.join(reason_parts),
        }

    return {
        'action': 'HOLD',
        'confidence': score,
        'score': round(score, 4),
        'rsi': round(rsi, 1),
        'reason': 'DV_璇勫垎涓嶈冻(%.3f<%.2f)' % (score, DV_SCORE_MIN),
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    绾㈠埄绛栫暐鍑哄満閫昏緫 (V29)銆?

    鍑哄満鏉′欢:
      1. 鍥哄畾姝㈡崯 6%
      2. 鍥哄畾姝㈢泩 10%
      3. 鏃堕棿姝㈡崯锛?8 澶╂棤鏀剁泭锛?
      4. RSI 杩囩儹 > 70 (V29: 75鈫?0)
    """
    closes = df['close'].values

    if len(closes) < 2:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    # 1. 鍥哄畾姝㈡崯
    if pnl <= -DV_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'DV_姝㈡崯(%+.1f%%)' % (pnl * 100),
        }

    # 2. 鍥哄畾姝㈢泩
    if pnl >= DV_TAKE_PROFIT:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'DV_姝㈢泩(%+.1f%%)' % (pnl * 100),
        }

    # 3. RSI 杩囩儹 (V29: 75鈫?0, 闃插尽鑲′笉闇€瑕佸お鐑?
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is not None and rsi > 70:
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'DV_RSI杩囩儹(%.0f)' % rsi,
        }

    # 4. 鏃堕棿姝㈡崯
    entry_date = pos_info.get('entry_date', '')
    if entry_date and today_str:
        try:
            from datetime import datetime as dt
            days = (dt.strptime(today_str, '%Y-%m-%d') -
                    dt.strptime(entry_date, '%Y-%m-%d')).days
            if days >= DV_TIME_STOP and pnl < 0.01:
                return {
                    'action': 'SELL',
                    'confidence': 0.7,
                    'reason': 'DV_鏃堕棿姝㈡崯(%dd)' % days,
                }
        except Exception:
            pass

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
