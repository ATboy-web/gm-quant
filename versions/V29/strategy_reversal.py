"""
strategy_reversal.py - 鍙嶈浆纭绛栫暐 (V20)

閫傜敤浜庡乏渚ц涓氾紙鍖栧伐/鏂拌兘婧?鐓ょ偔绛夋寔缁笅璺岃涓氾級锛?
鏍稿績鎬濇兂锛氫笉鎶勫簳锛岀瓑鍙嶈浆纭鍚庡啀鍏ュ満銆?

闂鑳屾櫙:
  V19.2 鐨?MR 绛栫暐鍦ㄥ寲宸?-3.7%)銆佹柊鑳芥簮(-2.1%)銆佺叅鐐?-1.1%) 鍙嶅鎶勫簳琚锛?
  鍥犱负杩欎簺琛屼笟澶勪簬鎸佺画涓嬭穼瓒嬪娍涓紙宸︿晶锛夛紝RSI 瓒呭崠涓嶄唬琛ㄥ弽寮广€?

鏍稿績閫昏緫:
  涔板叆锛堝彸渚у弽杞‘璁わ級:
    1. 鐭湡瓒嬪娍鍙嶈浆: MA5 > MA10锛堥噾鍙夋垨鍒氶噾鍙夛級
    2. 鍙嶈浆鏃ユ斁閲? 褰撴棩閲忔瘮 鈮?1.3
    3. 浠锋牸绔欎笂 MA20: 纭鑴辩搴曢儴
    4. RSI 鍥炲崌鑷?40-60 鍖洪棿: 闈炶秴鍗栵紝璇存槑宸叉湁涔扮洏浠嬪叆
    5. 搴曢儴鐗瑰緛纭: 杩?0鏃ュ嚭鐜拌繃RSI<30鐨勮秴鍗栵紙鍒氫粠搴曢儴璧锋潵锛?
  鍗栧嚭:
    1. MA5 璺岀牬 MA10锛堟鍙夛級
    2. 璺岀牬 MA20锛堣秼鍔垮啀鐮达級
    3. 鍥哄畾姝㈡崯 6%
    4. 鍥哄畾姝㈢泩 12%锛堝弽杞鎯呬笉璐級
    5. 鏃堕棿姝㈡崯 20 澶?

涓庡叾浠栫瓥鐣ョ殑浜掕ˉ:
  - MR 鐪嬭秴鍗栨妱搴曪紙宸︿晶锛夛紝RT 鐪嬪弽杞‘璁わ紙鍙充晶锛?
  - MOM 鐪嬭秼鍔胯拷娑紙楂樹綅锛夛紝RT 鐪嬪簳閮ㄥ弽杞紙浣庝綅鍒氳捣鏉ワ級
  - VP 鐪嬮噺浠疯儗绂伙紙棰勫垽锛夛紝RT 鐪嬮噺浠风‘璁わ紙纭锛?
  - BK 鐪嬬獊鐮村姞閫燂紙涓綅锛夛紝RT 鐪嬭秼鍔挎嫄鐐癸紙搴曢儴锛?
  - DV 鐪嬩綆浣嶄环鍊硷紙闃插尽锛夛紝RT 鐪嬩綆浣嶅弽杞紙杩涙敾锛?
"""

import numpy as np
import config
import indicators


# 鍙嶈浆纭绛栫暐鍙傛暟
RT_MA_FAST       = 5     # 蹇€熷潎绾?
RT_MA_SLOW       = 10    # 鎱㈤€熷潎绾?
RT_TREND_MA      = 20    # 瓒嬪娍纭鍧囩嚎
RT_VOL_SURGE     = 1.3   # 鍙嶈浆鏃ユ渶灏忛噺姣?
RT_STOP_LOSS     = 0.06  # 鍥哄畾姝㈡崯 6%
RT_TAKE_PROFIT   = 0.12  # 鍥哄畾姝㈢泩 12%
RT_TIME_STOP     = 20    # 鏃堕棿姝㈡崯澶╂暟
RT_RSI_LOW       = 40    # RSI 涔板叆涓嬮檺锛堥潪瓒呭崠锛?
RT_RSI_HIGH      = 60    # RSI 涔板叆涓婇檺锛堥潪杩囩儹锛?
RT_OVERSOLD_LOOKBACK = 30  # 搴曢儴瓒呭崠鍥炵湅澶╂暟
RT_OVERSOLD_RSI  = 30    # 搴曢儴瓒呭崠闃堝€?


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    鍙嶈浆纭绛栫暐涔板叆淇″彿銆?

    妫€娴?
      1. MA5 > MA10锛堢煭鏈熻秼鍔垮弽杞級
      2. 鏀鹃噺纭锛堝弽杞棩閲忔瘮鈮?.3锛?
      3. 浠锋牸绔欎笂MA20
      4. RSI鍦?0-60鍖洪棿锛堝凡鑴辩瓒呭崠锛屼絾鏈繃鐑級
      5. 杩戞湡鏈夎秴鍗栧巻鍙诧紙纭鏄粠搴曢儴鍙嶈浆锛?
    """
    closes = df['close'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < 60:
        return None

    cur_price = float(closes[-1])

    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 1. 鐭湡瓒嬪娍鍙嶈浆: MA5 > MA10 ----
    ma5 = indicators.calc_sma(closes, RT_MA_FAST)
    ma10 = indicators.calc_sma(closes, RT_MA_SLOW)

    if ma5 is None or ma10 is None:
        return None

    trend_reversal = (ma5 > ma10)

    if not trend_reversal:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'RT_MA5<=MA10(%.2f<=%.2f)瓒嬪娍鏈弽杞? % (ma5, ma10),
        }

    # 妫€鏌ユ槸鍚﹀垰閲戝弶锛?澶╁唴锛夛紝閲戝弶姣旈暱鏈熼噾鍙夋洿鏈変俊鍙蜂环鍊?
    recent_golden_cross = False
    if n > RT_MA_SLOW + 3:
        for i in range(1, min(4, n - RT_MA_SLOW)):
            ma5_prev = indicators.calc_sma(closes[:n - i], RT_MA_FAST)
            ma10_prev = indicators.calc_sma(closes[:n - i], RT_MA_SLOW)
            if ma5_prev is not None and ma10_prev is not None:
                if ma5_prev <= ma10_prev:
                    recent_golden_cross = True
                    break

    # ---- 2. 鏀鹃噺纭 ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    vol_confirm = (vol_ratio >= RT_VOL_SURGE)
    vol_score = min(1.0, (vol_ratio - 0.8) / 1.5) if vol_ratio > 0.8 else 0.0

    # ---- 3. 浠锋牸绔欎笂MA20 ----
    ma20 = indicators.calc_sma(closes, RT_TREND_MA)
    above_ma20 = (ma20 is not None and cur_price > ma20)

    if ma20 is None:
        return None

    if not above_ma20:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'RT_浠锋牸鍦∕A20涓嬫柟(%.2f<%.2f)' % (cur_price, ma20),
        }

    # 绔欎笂MA20鐨勮窛绂伙紙鍒氱珯涓婂姞鍒嗘洿澶氾級
    ma20_dist = (cur_price - ma20) / ma20
    if ma20_dist > 0.05:
        # 绂籑A20澶繙锛屽彲鑳藉凡鍦ㄩ珮浣嶏紝涓嶆槸搴曢儴鍙嶈浆
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'RT_杩滅MA20(%.1f%%)闈炲簳閮ㄥ弽杞? % (ma20_dist * 100),
        }

    # ---- 4. RSI 鍦?40-60 鍖洪棿 ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    rsi_ok = (RT_RSI_LOW <= rsi <= RT_RSI_HIGH)
    if not rsi_ok:
        if rsi < RT_RSI_LOW:
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'score': 0.0,
                'rsi': round(rsi, 1),
                'reason': 'RT_RSI澶綆(%.0f)浠嶅湪瓒呭崠' % rsi,
            }
        else:
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'score': 0.0,
                'rsi': round(rsi, 1),
                'reason': 'RT_RSI鍋忛珮(%.0f)宸茶繃鐑? % rsi,
            }

    # ---- 5. 杩戞湡瓒呭崠鍘嗗彶锛堝簳閮ㄧ壒寰佺‘璁わ級 鈥?蹇呰鏉′欢 ----
    has_oversold_history = False
    oversold_score = 0.0
    lookback = min(RT_OVERSOLD_LOOKBACK, n - 1)
    if lookback > 14:  # 闇€瑕佽冻澶熸暟鎹绠桼SI
        recent_closes = closes[-lookback:]
        # 妫€鏌ヨ繎30鏃ュ唴鏄惁鏈塕SI<30鐨勮褰?
        for i in range(14, len(recent_closes)):
            rsi_i = indicators.calc_rsi(recent_closes[:i + 1], period=14)
            if rsi_i is not None and rsi_i < RT_OVERSOLD_RSI:
                has_oversold_history = True
                # 瓒呭崠瓒婃繁鍔犲垎瓒婂
                depth = (RT_OVERSOLD_RSI - rsi_i) / RT_OVERSOLD_RSI
                oversold_score = max(oversold_score, depth)
                break

    # V20.1: 娌℃湁搴曢儴瓒呭崠鍘嗗彶鍒欎笉瑙﹀彂RT锛圧T鐨勬牳蹇冧环鍊煎氨鏄‘璁ゅ簳閮ㄥ弽杞級
    if not has_oversold_history:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'rsi': round(rsi, 1),
            'reason': 'RT_鏃犲簳閮ㄨ秴鍗栧巻鍙?,
        }

    # ---- 缁煎悎璇勫垎 ----
    score = 0.15  # 鍩虹鍒嗭細MA5>MA10

    # 鍒氶噾鍙夊姞鍒嗭紙寮轰俊鍙凤級
    if recent_golden_cross:
        score += 0.25
    else:
        score += 0.10  # 闀挎湡閲戝弶

    # 鏀鹃噺纭
    if vol_confirm:
        score += 0.20
    else:
        score += vol_score * 0.10  # 閮ㄥ垎鏀鹃噺

    # MA20璺濈鍔犲垎锛堝垰绔欎笂鏈€濂斤級
    if ma20_dist < 0.02:
        score += 0.15  # 鍒氱珯涓奙A20
    else:
        score += 0.08  # 绋嶈繙

    # 搴曢儴瓒呭崠鍘嗗彶鍔犲垎锛堝凡鏄繀瑕佹潯浠讹紝杩欓噷璋冩暣娣卞害鍒嗭級
    score += 0.15 + oversold_score * 0.05

    # 琛屼笟鍔ㄩ噺鍔犲垎
    sector_score = 0.0
    if sector_momentum and sector and sector in sector_momentum:
        sm = sector_momentum[sector]
        # 琛屼笟鍔ㄩ噺姝ｅ€硷紙姝ｅ湪澶嶈嫃锛夊姞鍒?
        if sm > 0:
            sector_score = min(0.10, sm * 0.5)
            score += sector_score

    score = min(1.0, score)

    if score >= 0.75:   # V26: 0.60鈫?.75, 澶у箙鏀剁揣(鍘熻儨鐜?7.5%), 浠呭畬缇庝俊鍙疯Е鍙?
        reason_parts = ['鍙嶈浆纭']
        if recent_golden_cross:
            reason_parts.append('閲戝弶')
        if vol_confirm:
            reason_parts.append('鏀鹃噺%.1f' % vol_ratio)
        reason_parts.append('绔欎笂MA20')
        if has_oversold_history:
            reason_parts.append('搴曢儴瓒呭崠')
        reason_parts.append('RSI=%.0f' % rsi)
        if sector_score > 0:
            reason_parts.append('琛屼笟澶嶈嫃')

        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'rsi': round(rsi, 1),
            'reason': 'RT_' + '|'.join(reason_parts),
        }

    return {
        'action': 'HOLD',
        'confidence': score,
        'score': round(score, 4),
        'rsi': round(rsi, 1),
        'reason': 'RT_璇勫垎涓嶈冻(%.3f)' % score,
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    鍙嶈浆纭绛栫暐鍑哄満閫昏緫銆?

    鍑哄満鏉′欢:
      1. MA5 璺岀牬 MA10锛堟鍙夛紝瓒嬪娍鍐嶇牬锛?
      2. 璺岀牬 MA20锛堣秼鍔跨‘璁ゅけ璐ワ級
      3. 鍥哄畾姝㈡崯 6%
      4. 鍥哄畾姝㈢泩 12%
      5. 鏃堕棿姝㈡崯 20澶?
    """
    closes = df['close'].values

    if len(closes) < RT_MA_SLOW + 5:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    # ---- 1. MA5 < MA10锛堟鍙夛級 ----
    ma5 = indicators.calc_sma(closes, RT_MA_FAST)
    ma10 = indicators.calc_sma(closes, RT_MA_SLOW)

    if ma5 is not None and ma10 is not None and ma5 < ma10:
        # 纭鏄惁鍒氭鍙夛紙鏇寸揣鎬ワ級
        return {
            'action': 'SELL',
            'confidence': 0.80,
            'reason': 'RT_姝诲弶(MA5<MA10)',
        }

    # ---- 2. 璺岀牬MA20 ----
    ma20 = indicators.calc_sma(closes, RT_TREND_MA)
    if ma20 is not None and cur_price < ma20:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'RT_璺岀牬MA20(%.2f<%.2f)' % (cur_price, ma20),
        }

    # ---- 3. 鍥哄畾姝㈡崯 ----
    if pnl <= -RT_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'RT_姝㈡崯(%+.1f%%)' % (pnl * 100),
        }

    # ---- 4. 鍥哄畾姝㈢泩 ----
    if pnl >= RT_TAKE_PROFIT:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'RT_姝㈢泩(%+.1f%%)' % (pnl * 100),
        }

    # ---- 5. 鏃堕棿姝㈡崯 ----
    entry_date = pos_info.get('entry_date', '')
    if entry_date and today_str:
        try:
            from datetime import datetime as dt
            days = (dt.strptime(today_str, '%Y-%m-%d') -
                    dt.strptime(entry_date, '%Y-%m-%d')).days
            if days >= RT_TIME_STOP and pnl < 0.02:
                return {
                    'action': 'SELL',
                    'confidence': 0.7,
                    'reason': 'RT_鏃堕棿姝㈡崯(%dd)' % days,
                }
        except Exception:
            pass

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
