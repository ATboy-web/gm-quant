"""
indicators.py - 鎶€鏈寚鏍囪绠楁ā鍧?(V16 鎵╁睍鐗?

鎵€鏈夊嚱鏁板潎涓虹函鍑芥暟: 杈撳叆 numpy 鏁扮粍锛岃緭鍑鸿绠楃粨鏋溿€?涓嶄緷璧?GM SDK 鎴栦换浣曞閮ㄧ姸鎬侊紝鏂逛究鍗曠嫭娴嬭瘯鍜屽鐢ㄣ€?
鎸囨爣娓呭崟:
  calc_rsi()             - 鐩稿寮哄急鎸囨爣
  calc_atr()             - 骞冲潎鐪熷疄娉㈠箙锛堝姩鎬佹鎹熷熀纭€锛?  calc_sma()             - 绠€鍗曠Щ鍔ㄥ钩鍧?  calc_volume_ratio()    - 閲忔瘮锛堝綋鏃ラ噺 / N鏃ュ潎閲忥級
  calc_drawdown()        - 杩戞湡鏈€澶у洖鎾ゅ箙搴?  detect_reversal()      - K绾垮弽杞舰鎬佽瘑鍒?  detect_bullish_engulfing() - 鐪嬫定鍚炴病褰㈡€?  detect_hammer()        - 閿ゅ瓙绾垮舰鎬?  classify_regime()      - 甯傚満鐘舵€佸垎绫伙紙鐗?鐔?闇囪崱锛?"""

import numpy as np


# =============================================================================
# RSI 鈥?鐩稿寮哄急鎸囨爣
# =============================================================================

def calc_rsi(closes, period=6):
    """
    璁＄畻 RSI锛堢浉瀵瑰己寮辨寚鏍囷級銆?
    绠楁硶:
      1. 鍙栨渶杩?period+1 涓敹鐩樹环锛岃绠?period 涓定璺屽彉鍖?螖P
      2. 鍒嗙娑ㄥ箙锛堟鍊硷級鍜岃穼骞咃紙璐熷€煎彇缁濆鍊硷級
      3. RS = 骞冲潎娑ㄥ箙 / 骞冲潎璺屽箙
      4. RSI = 100 - 100 / (1 + RS)

    鍙傛暟:
        closes : np.ndarray  鏀剁洏浠峰簭鍒楋紙鏃р啋鏂帮級
        period : int         RSI 鍛ㄦ湡锛岄粯璁?6

    杩斿洖:
        float | None  RSI 鈭?[0, 100]锛屾暟鎹笉瓒宠繑鍥?None
    """
    n = len(closes)
    if n < period + 1:
        return None

    recent = closes[-(period + 1):]
    deltas = np.diff(recent)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)

    if avg_loss == 0:
        return 100.0  # 鍏ㄦ定 鈫?RSI 婊″€?
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


# =============================================================================
# ATR 鈥?骞冲潎鐪熷疄娉㈠箙锛堝姩鎬佹鎹熸牳蹇冩寚鏍囷級
# =============================================================================

def calc_atr(highs, lows, closes, period=14):
    """
    璁＄畻 ATR锛圓verage True Range锛屽钩鍧囩湡瀹炴尝骞咃級銆?
    ATR 搴﹂噺鐨勬槸浠锋牸鐨勭湡瀹炴尝鍔ㄨ寖鍥达紝鑰冭檻闅斿璺崇┖褰卞搷銆?    鐢ㄤ簬鍔ㄦ€佹鎹? 姝㈡崯骞呭害 = N 脳 ATR锛岃€岄潪鍥哄畾鐧惧垎姣斻€?
    绠楁硶:
      1. True Range = max(褰撴棩楂?褰撴棩浣?
                          |褰撴棩楂?鍓嶆棩鏀秥,
                          |褰撴棩浣?鍓嶆棩鏀秥)
      2. ATR = TR 鐨?N 鏃ョ畝鍗曠Щ鍔ㄥ钩鍧?
    鍙傛暟:
        highs  : np.ndarray  鏈€楂樹环搴忓垪
        lows   : np.ndarray  鏈€浣庝环搴忓垪
        closes : np.ndarray  鏀剁洏浠峰簭鍒?        period : int         ATR 鍛ㄦ湡锛岄粯璁?14

    杩斿洖:
        float | None  ATR 鍊硷紝鏁版嵁涓嶈冻杩斿洖 None

    浣跨敤绀轰緥:
        瀵逛簬浠锋牸涓?10 鍏冪殑鑲＄エ锛孉TR=0.3 鈫?娉㈠姩鐜?3%
        1.5x ATR 姝㈡崯 = 4.5% 鈥?缁欐甯告尝鍔ㄧ暀瓒崇┖闂?    """
    n = len(closes)
    if n < period + 1:
        return None

    # 鍙栨渶杩?period+1 涓?bar
    h = highs[-(period + 1):]
    l = lows[-(period + 1):]
    c = closes[-(period + 1):]

    # 璁＄畻 True Range
    tr_list = []
    for i in range(1, len(h)):
        tr = max(
            h[i] - l[i],                     # 褰撴棩鎸箙
            abs(h[i] - c[i - 1]),            # 褰撴棩楂?- 鍓嶆敹
            abs(l[i] - c[i - 1])             # 褰撴棩浣?- 鍓嶆敹
        )
        tr_list.append(tr)

    return float(np.mean(tr_list))


def calc_atr_pct(highs, lows, closes, period=14):
    """
    璁＄畻 ATR 鍗犱环鏍肩殑姣斾緥锛堟尝鍔ㄧ巼鐧惧垎姣旓級銆?
    杩斿洖:
        float | None  ATR / 褰撳墠浠锋牸锛屽 0.03 琛ㄧず娉㈠姩鐜?3%
    """
    atr = calc_atr(highs, lows, closes, period)
    if atr is None:
        return None
    price = closes[-1]
    if price <= 0:
        return None
    return atr / price


# =============================================================================
# SMA 鈥?绠€鍗曠Щ鍔ㄥ钩鍧?# =============================================================================

def calc_sma(closes, period=20):
    """
    璁＄畻绠€鍗曠Щ鍔ㄥ钩鍧囷紙SMA锛夈€?
    鍙傛暟:
        closes : np.ndarray  鏀剁洏浠峰簭鍒?        period : int         鍧囩嚎鍛ㄦ湡

    杩斿洖:
        float | None  MA 鍊?    """
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))


# =============================================================================
# 鎴愪氦閲忓垎鏋?# =============================================================================

def calc_volume_ratio(volumes, period=20):
    """
    璁＄畻閲忔瘮: 褰撴棩鎴愪氦閲?/ N 鏃ュ潎閲忋€?
    鏀鹃噺璇存槑鏈夎祫閲戜粙鍏ワ紝閰嶅悎 RSI 瓒呭崠鍙兘鏄弽杞俊鍙枫€?    缂╅噺鍙嶅脊鍒欏彲闈犳€ц緝浣庛€?
    鍙傛暟:
        volumes : np.ndarray  鎴愪氦閲忓簭鍒?        period  : int         鍧囬噺鍛ㄦ湡

    杩斿洖:
        float | None  閲忔瘮锛屽 1.5 琛ㄧず鏀鹃噺 50%
    """
    n = len(volumes)
    if n < period + 1:
        return None

    today_vol = float(volumes[-1])
    avg_vol   = float(np.mean(volumes[-(period + 1):-1]))

    if avg_vol <= 0:
        return 1.0

    return today_vol / avg_vol


# =============================================================================
# 璺屽箙鍒嗘瀽
# =============================================================================

def calc_drawdown(closes, period=20):
    """
    璁＄畻杩戞湡鏈€澶у洖鎾わ紙浠?N 鏃ュ唴鏈€楂樼偣鍒板綋鍓嶄环鐨勮穼骞咃級銆?
    鍧囧€煎洖褰掔瓥鐣ョ殑鏍稿績鍋囪: 璺屽箙瓒婂ぇ锛屽弽寮瑰姩鍔涜秺寮恒€?    浣嗛渶瑕侀厤鍚堝叾浠栧洜瀛愯繃婊ゆ寔缁笅璺岀殑"浠峰€奸櫡闃?銆?
    鍙傛暟:
        closes : np.ndarray  鏀剁洏浠峰簭鍒?        period : int         鍥炵湅绐楀彛

    杩斿洖:
        float | None  鍥炴挙姣斾緥锛屽 0.15 琛ㄧず浠庨珮鐐硅穼浜?15%
    """
    if len(closes) < period:
        return None

    recent  = closes[-period:]
    peak    = np.max(recent)
    current = recent[-1]

    if peak <= 0:
        return None

    return (peak - current) / peak


# =============================================================================
# K绾垮弽杞舰鎬佽瘑鍒?# =============================================================================

def detect_bullish_engulfing(opens, highs, lows, closes):
    """
    璇嗗埆鐪嬫定鍚炴病褰㈡€併€?
    褰㈡€佺壒寰?
      - 鍓嶄竴鏃ヤ负闃寸嚎锛坈lose < open锛?      - 褰撴棩涓洪槼绾匡紙close > open锛?      - 褰撴棩瀹炰綋瀹屽叏鍚炴病鍓嶄竴鏃ュ疄浣?        (褰撴棩寮€ 鈮?鍓嶆棩鏀?AND 褰撴棩鏀?鈮?鍓嶆棩寮€)

    鐪嬫定鍚炴病鏄己鍙嶈浆淇″彿锛屽挨鍏跺湪涓嬭穼瓒嬪娍鏈鍑虹幇鏃躲€?
    杩斿洖:
        bool
    """
    if len(closes) < 2:
        return False

    prev_open  = float(opens[-2])
    prev_close = float(closes[-2])
    cur_open   = float(opens[-1])
    cur_close  = float(closes[-1])

    # 鍓嶆棩闃寸嚎
    if prev_close >= prev_open:
        return False
    # 褰撴棩闃崇嚎
    if cur_close <= cur_open:
        return False
    # 鍚炴病鏉′欢
    if cur_open <= prev_close and cur_close >= prev_open:
        return True

    return False


def detect_hammer(opens, highs, lows, closes):
    """
    璇嗗埆閿ゅ瓙绾垮舰鎬併€?
    褰㈡€佺壒寰?
      - 瀹炰綋杈冨皬锛堝疄浣?/ 鎬绘尟骞?< 0.3锛?      - 涓嬪奖绾垮緢闀匡紙涓嬪奖绾?鈮?2 脳 瀹炰綋锛?      - 涓婂奖绾垮緢鐭紙涓婂奖绾?鈮?0.3 脳 瀹炰綋锛?      - 鍑虹幇鍦ㄤ笅璺岃秼鍔夸腑锛堢敱璋冪敤鏂圭‘璁わ級

    閿ゅ瓙绾胯〃绀哄崠鏂规浘澶у箙鎵撳帇浣嗕拱鏂瑰己鍔垮弽鍑伙紝
    鏄綔鍦ㄧ殑搴曢儴鍙嶈浆淇″彿銆?
    杩斿洖:
        bool
    """
    if len(closes) < 1:
        return False

    op   = float(opens[-1])
    hi   = float(highs[-1])
    lo   = float(lows[-1])
    cl   = float(closes[-1])

    body   = abs(cl - op)
    total  = hi - lo
    upper  = hi - max(op, cl)
    lower  = min(op, cl) - lo

    if total <= 0 or body <= 0:
        return False

    # 瀹炰綋鍗犳瘮灏忥紙< 30% 鎸箙锛?    if body / total > 0.3:
        return False

    # 涓嬪奖绾胯嚦灏?2 鍊嶅疄浣?    if lower < 2 * body:
        return False

    # 涓婂奖绾跨煭
    if upper > 0.3 * body:
        return False

    return True


def detect_reversal(opens, highs, lows, closes):
    """
    缁煎悎鍙嶈浆褰㈡€佹娴嬨€?
    杩斿洖:
        dict: {
            'bullish_engulfing': bool,
            'hammer': bool,
            'score': float (0~1),  鍙嶈浆淇″彿寮哄害
        }
    """
    engulfing = detect_bullish_engulfing(opens, highs, lows, closes)
    hammer    = detect_hammer(opens, highs, lows, closes)

    # 褰㈡€佽瘎鍒? 鍚炴病 = 1.0, 閿ゅ瓙绾?= 0.7, 鏅€氶槼绾?= 0.3
    score = 0.0
    if engulfing:
        score = 1.0
    elif hammer:
        score = 0.7
    elif closes[-1] > opens[-1]:
        score = 0.3

    return {
        'bullish_engulfing': engulfing,
        'hammer': hammer,
        'score': score,
    }


# =============================================================================
# 甯傚満鐘舵€佸垎绫?# =============================================================================

def classify_regime(closes, ma_period=60, bear_threshold=-0.08):
    """
    鍒ゆ柇褰撳墠甯傚満鐘舵€? 鐗涘競 / 鐔婂競 / 闇囪崱銆?
    鍩轰簬涓や釜缁村害鍒ゆ柇:
      1. 瓒嬪娍鏂瑰悜: 浠锋牸 vs MA(ma_period)
      2. 杩戞湡鍔ㄩ噺: N 鏃ユ定璺屽箙

    鍙傛暟:
        closes        : np.ndarray  鎸囨暟鏀剁洏浠峰簭鍒?        ma_period     : int         瓒嬪娍鍧囩嚎鍛ㄦ湡
        bear_threshold: float       鐔婂競鍒ゅ畾闃堝€硷紙20鏃ヨ穼骞咃級

    杩斿洖:
        str: 'bull' | 'range' | 'bear'
    """
    if len(closes) < ma_period:
        return 'range'  # 鏁版嵁涓嶈冻锛岄粯璁ら渿鑽?
    current = closes[-1]
    ma      = calc_sma(closes, ma_period)

    if ma is None:
        return 'range'

    # 璁＄畻杩戞湡鍔ㄩ噺锛堢敤 MA_PERIOD 瀵瑰簲鐨勬椂闂寸獥鍙ｏ級
    n = len(closes)
    if n >= ma_period + 1:
        chg = (closes[-1] / closes[-(ma_period + 1)] - 1) if closes[-(ma_period + 1)] > 0 else 0
    elif n >= 22:
        chg = (closes[-1] / closes[-22] - 1) if closes[-22] > 0 else 0
    elif n >= 5:
        chg = (closes[-1] / closes[-5] - 1) if closes[-5] > 0 else 0
    else:
        chg = 0

    # 鍒嗙被閫昏緫
    if chg <= bear_threshold:
        return 'bear'    # 杩戞湡璺屽箙瓒呰繃闃堝€?鈫?鐔婂競

    if current > ma:
        return 'bull'    # 浠锋牸鍦ㄥ潎绾夸笂鏂?鈫?鐗涘競

    return 'range'       # 鍏朵綑 鈫?闇囪崱
