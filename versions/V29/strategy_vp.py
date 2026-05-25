"""
strategy_vp.py - 閲忎环鑳岀绛栫暐 (V29.3)

閲忎环鍒嗘瀽閫夋墜锛氶€氳繃浠锋牸涓庢垚浜ら噺鐨勮儗绂诲叧绯绘崟鎹夎浆鎶樼偣銆?

V29.3 淇 (2026-05-25):
  鍥為€€ V29.2 鐨?executor 鏀瑰姩 鈥?缃俊搴﹀叕寮忔敼鍥?avg(confidences)銆?
  V29.2 鐨?max+鍏辫瘑鍔犳垚瀵艰嚧澶氱瓥鐣ヤ俊鍙锋帓鍚嶆孩浠凤紝
  MR 璧勯噾琚尋鍘嬶紝鏀剁泭浠?+105% 璺岃嚦 -44%銆?
  VP 瓒嬪娍纭棬宸插湪 V29.2 绉婚櫎锛堝崟绛栫暐璇佸疄鏈夊锛夛紝鏈増鏈繚鐣欍€?

V29.2 淇 (2026-05-25):
  宸茬Щ闄?V29.1 瓒嬪娍纭棬 鈥?鍗曠瓥鐣ュ洖娴嬭瘉瀹炴湁瀹?(+8.29%鈫?0.75%)銆?
  瓒嬪娍纭棬璇潃 VP 鏍稿績閫昏緫 (搴曢儴鑳岀鏃朵环蹇呯劧鍦∕A20涓嬫柟)銆?

鏍稿績閫昏緫:
  涔板叆锛堝簳閮ㄨ儗绂伙級:
    - 浠锋牸鍒?N 鏃ユ柊浣庯紝浣嗘垚浜ら噺钀庣缉锛堟姏鍘嬭€楀敖锛?
    - 鎴栵細浠锋牸妯洏/寰穼锛屾垚浜ら噺鎸佺画缂╁皬 鈫?娲楃洏灏惧０
  鍗栧嚭:
    - 鏀鹃噺鍙嶅脊鍚庣缉閲?鈫?鍙嶅脊鍔ㄥ姏鑰楀敖
    - 鏀鹃噺婊炴定 鈫?鍑鸿揣淇″彿
    - 鏃堕棿姝㈡崯锛堣儗绂诲悗杩熻繜涓嶅弽寮癸級

涓庡潎鍊煎洖褰掔殑鍖哄埆:
  - 鍧囧€煎洖褰掔湅 RSI 鏁板€硷紙瓒呭崠绋嬪害锛?
  - 閲忎环鑳岀鐪嬩环閲忓叧绯荤殑鍙樺寲瓒嬪娍锛堢粨鏋勬€х殑鎶涘帇琛扮锛?
"""

import numpy as np
import config
import indicators


VP_PERIOD       = 20    # 鑳岀妫€娴嬬獥鍙?
VP_PRICE_DECLINE = -0.03  # 浠锋牸鏂颁綆骞呭害闃堝€?
VP_VOL_DECLINE  = 0.65   # 鎴愪氦閲忚悗缂╅槇鍊硷紙閲忔瘮涓哄潎閲忕殑65%浠ヤ笅锛?
VP_STOP_LOSS    = 0.05   # 鍥哄畾姝㈡崯 5%
VP_TIME_STOP    = 20     # 鏃堕棿姝㈡崯澶╂暟锛圴18璋冧紭: 10鈫?0锛岀粰鑳岀淇鏇村鏃堕棿锛?
VP_EXIT_PROFIT  = 0.08   # 姝㈢泩 8%


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    閲忎环鑳岀涔板叆淇″彿銆?

    妫€娴嬩互涓嬭儗绂诲舰鎬?
      1. 搴曡儗绂? 浠锋牸鍒涙柊浣?+ 鎴愪氦閲忔寔缁悗缂?
      2. 缂╅噺姝㈣穼: 杩炵画3鏃ョ缉閲?+ 浠锋牸妯洏/寰穼
      3. 鑳岀鍚庣殑鏀鹃噺纭锛堝姞鍒嗛」锛?
    """
    closes = df['close'].values
    vols   = df['volume'].values
    highs  = df['high'].values
    lows   = df['low'].values

    n = len(closes)
    if n < VP_PERIOD + 3:
        return None

    cur_price = float(closes[-1])

    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 閲忎环鐗瑰緛鎻愬彇 ----
    # 杩?鏃?vs 鍓?5鏃ワ紙涓€鍏?0鏃ョ獥鍙ｏ級
    recent_5c = closes[-5:]
    recent_5v = vols[-5:]
    prior_15c = closes[-20:-5]
    prior_15v = vols[-20:-5]

    if len(prior_15c) < 5:
        return None

    # 浠锋牸鐗瑰緛
    price_5d_high = np.max(recent_5c)
    price_5d_low  = np.min(recent_5c)
    price_20d_high = np.max(closes[-20:])
    price_20d_low  = np.min(closes[-20:])

    # 鎴愪氦閲忕壒寰?
    vol_5d_avg  = np.mean(recent_5v)
    vol_15d_avg = np.mean(prior_15v)
    vol_ratio_5_15 = vol_5d_avg / vol_15d_avg if vol_15d_avg > 0 else 1.0

    # 閲忔瘮
    vol_ratio_full = indicators.calc_volume_ratio(vols, VP_PERIOD)
    if vol_ratio_full is None:
        vol_ratio_full = 1.0

    # ---- 褰㈡€?: 浠锋牸鍒涙柊浣?+ 缂╅噺锛堝簳閮ㄨ儗绂伙級 ----
    price_new_low = (cur_price <= price_20d_low * 1.01)
    vol_shrinking = (vol_ratio_5_15 < VP_VOL_DECLINE)

    # ---- 褰㈡€?: 杩炵画缂╅噺锛?鏃ラ噺姣?< 0.7锛?----
    vol_ratios_3d = []
    for i in range(3):
        if n > VP_PERIOD + i:
            sub_vols = vols[:n - i]
            vr = indicators.calc_volume_ratio(sub_vols, VP_PERIOD)
            if vr is not None:
                vol_ratios_3d.append(vr)

    consecutive_low_vol = (
        len(vol_ratios_3d) >= 2 and
        all(v < 0.7 for v in vol_ratios_3d)
    )

    # ---- 褰㈡€?: 浠锋牸璺屽箙鏈夐檺 + 閲忕缉锛堟礂鐩樿€岄潪鍑鸿揣锛?----
    if n >= 10:
        ret_10d = (closes[-1] / closes[-10] - 1)
    else:
        ret_10d = 0
    moderate_decline = (-0.10 < ret_10d <= -0.02)

    # ---- 鍔犲垎椤? 鏀鹃噺闃崇嚎纭 ----
    vol_surge_with_green = (
        vol_ratio_full >= 1.2 and
        closes[-1] > closes[-2]
    )

    # ---- RSI 纭锛堥伩鍏嶆帴椋炲垁锛?----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    # RSI 澶綆涔熶笉琛岋紙鍙兘杩樻湁鏇村ぇ璺屽箙锛?
    rsi_ok = (18 <= rsi <= 45)

    # ---- 璇勫垎璁＄畻 ----
    score = 0.0
    reasons = []

    if price_new_low and vol_shrinking:
        score += 0.50
        reasons.append('浠锋柊浣?閲忕缉')

    if consecutive_low_vol:
        score += 0.25
        reasons.append('杩炵画缂╅噺')

    if moderate_decline and vol_shrinking:
        score += 0.20
        reasons.append('娓╁拰涓嬭穼+缂╅噺')

    if vol_surge_with_green:
        score += 0.15
        reasons.append('鏀鹃噺闃崇嚎纭')

    # RSI 涓嶅湪鍚堢悊鍖洪棿锛岄檷鍒?
    if not rsi_ok:
        score *= 0.5

    # V29.2: 宸茬Щ闄?V29.1 瓒嬪娍纭棬
    # 鍗曠瓥鐣ュ洖娴嬭瘉鏄? VP 鐙珛 +8.29% vs 甯︾‖闂?+0.75%
    # 瓒嬪娍纭棬鎯╃綒 VP 鏈€鏍稿績鐨勫簳閮ㄥ弽杞俊鍙?浠峰湪MA20涓?涓嬭穼涓?鑳岀), 鍙嶅櫖绛栫暐閫昏緫
    # VP 浜忔崯鏍瑰洜鏄绛栫暐绔炰簤涓殑浠撲綅姝ц, 宸查€氳繃 executor V29.2 鎶曠エ鏈哄埗淇

    score = min(1.0, score)

    if score >= 0.55:   # V26: 0.50鈫?.55, 鏀剁揣鍏ュ満鎻愬崌鑳滅巼
        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'rsi': round(rsi, 1),
            'reason': 'VP_' + '|'.join(reasons),
        }

    if score >= 0.25:
        return {
            'action': 'HOLD',
            'confidence': score,
            'score': round(score, 4),
            'reason': 'VP_淇″彿寮?%.3f)' % score,
        }

    return {
        'action': 'HOLD',
        'confidence': 0.0,
        'score': 0.0,
        'reason': 'VP_鏃犻噺浠疯儗绂?,
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    閲忎环鑳岀绛栫暐鍑哄満閫昏緫銆?

    鍑哄満鏉′欢:
      1. 鏀鹃噺鍙嶅脊鍚庣缉閲?鈫?鍙嶅脊琛扮
      2. 鏀鹃噺婊炴定锛堥噺澶т絾浠蜂笉娑級鈫?鍑鸿揣
      3. 鍥哄畾姝㈡崯
      4. 鏃堕棿姝㈡崯锛堣儗绂诲悗杩熻繜涓嶆定锛?
    """
    closes = df['close'].values
    vols   = df['volume'].values
    highs  = df['high'].values
    lows   = df['low'].values

    n = len(closes)
    if n < VP_PERIOD + 1:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    vol_ratio = indicators.calc_volume_ratio(vols, VP_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    # 1. 鏀鹃噺鍙嶅脊鍚庣缉閲?鈫?鍙嶅脊琛扮
    if n >= 4:
        prev_day_vol_ratio = indicators.calc_volume_ratio(vols[:-1], VP_PERIOD)
        if (prev_day_vol_ratio and prev_day_vol_ratio >= 1.5 and
            vol_ratio < 0.8 and pnl > 0.03):
            return {
                'action': 'SELL',
                'confidence': 0.8,
                'reason': 'VP_鍙嶅脊缂╅噺琛扮',
            }

    # 2. 鏀鹃噺婊炴定
    if vol_ratio >= 1.5 and pnl > 0 and cur_price <= closes[-2] * 1.005:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'VP_鏀鹃噺婊炴定',
        }

    # 3. 鍥哄畾姝㈡崯
    if pnl <= -VP_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'VP_姝㈡崯(%+.1f%%)' % (pnl * 100),
        }

    # 4. 姝㈢泩
    if pnl >= VP_EXIT_PROFIT:
        return {
            'action': 'SELL',
            'confidence': 0.8,
            'reason': 'VP_姝㈢泩(%+.1f%%)' % (pnl * 100),
        }

    # 5. 鏃堕棿姝㈡崯
    entry_date = pos_info.get('entry_date', '')
    if entry_date:
        try:
            if not today_str:
                if context and hasattr(context, '_today'):
                    today_str = context._today
            if not today_str:
                from datetime import datetime
                today_str = datetime.now().strftime('%Y-%m-%d')

            from datetime import datetime as dt
            days = (dt.strptime(today_str, '%Y-%m-%d') -
                    dt.strptime(entry_date, '%Y-%m-%d')).days
            if days >= VP_TIME_STOP and pnl < 0.01:
                return {
                    'action': 'SELL',
                    'confidence': 0.7,
                    'reason': 'VP_鏃堕棿姝㈡崯(%dd)' % days,
                }
        except Exception:
            pass

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
