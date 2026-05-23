"""
screener.py - 澶氬洜瀛愰€夎偂鎵撳垎寮曟搸 (V16 鏍稿績妯″潡)

姣忓ぉ瀵规墍鏈夊€欓€夎偂绁ㄨ繘琛岄噺鍖栨墦鍒嗭紝鑷姩璇嗗埆"鏈夋満浼?鍜?璇ユ矇娣€"鐨勮偂绁ㄣ€?
鍏洜瀛愭ā鍨?
  1. RSI 瓒呭崠娣卞害   (30%) 鈥?鍧囧€煎洖褰掓牳蹇冧俊鍙?  2. 瓒嬪娍瀵归綈       (20%) 鈥?椤哄娍鑰屼负锛屼笉鎶勪笅璺岃偂
  3. 鎴愪氦閲忕‘璁?    (15%) 鈥?鏀鹃噺鍙嶅脊鎵嶆湁璇氭剰
  4. 杩戞湡璺屽箙       (15%) 鈥?璺屽緱瓒婂鍙嶅脊绌洪棿瓒婂ぇ
  5. 鍙嶈浆褰㈡€?      (10%) 鈥?K绾跨粍鍚堢‘璁ゅ簳閮?  6. 琛屼笟鍔ㄩ噺       (10%) 鈥?浼橀€夊己鍔胯涓氫腑鐨勮秴鍗栬偂

璇勫垎杈撳嚭:
  鎬诲垎 鈭?[0, 1]锛屽彧涔板叆鎬诲垎 鈮?ENTRY_THRESHOLD 鐨勮偂绁ㄣ€?  鎸夋€诲垎闄嶅簭鎺掑垪锛屼紭鍏堜拱鍏ュ緱鍒嗘渶楂樼殑鏍囩殑銆?"""

import numpy as np
import config
import indicators
import stock_pool


def screen_all(context, sector_momentum=None):
    """
    瀵硅偂绁ㄦ睜涓墍鏈夊€欓€夎偂绁ㄨ繘琛屾墦鍒嗙瓫閫夈€?
    鍙傛暟:
        context          : GM 绛栫暐涓婁笅鏂?        sector_momentum  : dict {sector: momentum_score} 鎴?None

    杩斿洖:
        list[dict]: 閫氳繃绛涢€夌殑鑲＄エ鍒楄〃锛屾寜鎬诲垎闄嶅簭鎺掑垪
        姣忛」鍖呭惈: symbol, score, price, rsi, sector, details
    """
    candidates = []

    for sym in stock_pool.get_all_symbols():
        # 宸叉寔浠撶殑璺宠繃锛堝湪 main.py 涓鐞嗭紝杩欓噷涓嶉噸澶嶏級
        df = context.data_cache.get(sym)
        if df is None:
            continue

        # 鑾峰彇琛屼笟
        sector = SYMBOL_SECTOR_MAP.get(sym, '鏈煡')

        # ---- 蹇€熷垵绛?----
        if not _quick_filter(df, sym):
            continue

        # ---- 澶氬洜瀛愭墦鍒?----
        result = _score_stock(df, sym, sector, sector_momentum)
        if result is None:
            continue  # 鏁版嵁涓嶈冻

        if result['total'] >= config.ENTRY_THRESHOLD:
            candidates.append(result)

    # 鎸夋€诲垎闄嶅簭鎺掑垪锛堝緱鍒嗛珮鐨勪紭鍏堬級
    candidates.sort(key=lambda x: x['total'], reverse=True)

    return candidates


def _quick_filter(df, sym):
    """
    蹇€熷垵绛? 鐢ㄦ渶浣庢垚鏈帓闄ゆ槑鏄句笉绗﹀悎鏉′欢鐨勮偂绁ㄣ€?
    杩囨护鏉′欢锛堟寜浼樺厛绾э級:
      1. RSI 蹇呴』澶勪簬瓒呭崠鍖猴紙鏍稿績鏉′欢锛屼笉杩囨鍏充竴寰嬭烦杩囷級
      2. 鏁版嵁涓嶈冻
      3. 鑲′环寮傚父锛堜粰鑲℃垨澶╀环鑲★級
      4. 娑ㄨ穼鍋滄澘
    """
    closes = df['close'].values
    if len(closes) < config.RSI_PERIOD + 1:
        return False

    # ---- 鏉′欢 0: RSI 瓒呭崠纭€ф鏌ワ紙鍧囧€煎洖褰掔瓥鐣ョ殑鏍稿績锛?---
    # 鏃犺鍏朵粬鍥犲瓙澶氬ソ锛孯SI 涓嶈秴鍗栧氨涓嶄拱
    rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
    if rsi is None or rsi >= config.RSI_BUY:
        return False

    cur  = float(closes[-1])
    prev = float(closes[-2])

    # 浠锋牸鍖洪棿
    if cur < config.PRICE_MIN or cur > config.PRICE_MAX:
        return False

    # 娑ㄨ穼骞呰繃婊?    chg = abs(cur - prev) / prev if prev > 0 else 0
    if chg > config.PRICE_CHG_LIMIT:
        return False

    return True


# =============================================================================
# 澶氬洜瀛愯瘎鍒嗘牳蹇?# =============================================================================

def _score_stock(df, sym, sector, sector_momentum):
    """
    瀵瑰崟鍙偂绁ㄨ繘琛屽叚鍥犲瓙缁煎悎璇勫垎銆?
    鍙傛暟:
        df              : pd.DataFrame  鏃ョ嚎鏁版嵁
        sym             : str           鑲＄エ浠ｇ爜
        sector          : str           鎵€灞炶涓?        sector_momentum : dict | None   琛屼笟鍔ㄩ噺鏁版嵁

    杩斿洖:
        dict | None: {
            'symbol': str,
            'sector': str,
            'total': float,      鎬诲垎 (0~1)
            'price': float,      褰撳墠浠?            'rsi': float,        RSI 鍊?            'details': {         鍚勫洜瀛愬緱鍒嗘槑缁?                'rsi_score': ...,
                'trend_score': ...,
                ...
            }
        }
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

    # ==================================================================
    # 鍥犲瓙 1: RSI 瓒呭崠娣卞害锛堟潈閲?0.30锛?    #
    # RSI 瓒婁綆 鈫?瓒呭崠瓒婁弗閲?鈫?寰楀垎瓒婇珮
    # RSI < RSI_BUY 鎵嶇粰鍒嗭紝RSI >= RSI_BUY 寰?0 鍒?    # ==================================================================
    rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
    if rsi is None:
        return None

    if rsi < config.RSI_BUY:
        # 绾挎€ф槧灏? RSI=RIS_BUY 鈫?0, RSI=RSI_DEEP_OVERSOLD 鈫?1
        # RSI 浣庝簬 DEEP_OVERSOLD 鏃跺鍔辨渶楂?1.0锛堜笉鍐嶉澶栨孩鍑猴級
        rsi_score = (config.RSI_BUY - rsi) / (config.RSI_BUY - config.RSI_DEEP_OVERSOLD)
        rsi_score = min(1.0, max(0.0, rsi_score))  # 閽冲埗鍦?0~1
    else:
        rsi_score = 0.0

    # ==================================================================
    # 鍥犲瓙 2: 瓒嬪娍瀵归綈锛堟潈閲?0.20锛?    #
    # 浠锋牸鍦?MA20 涓婃柟 鈫?+0.5
    # 浠锋牸鍦?MA60 涓婃柟 鈫?+0.5
    # 鍏ㄩ儴鍦ㄤ笂鏂?= 1.0锛屽叏閮ㄥ湪涓嬫柟 = 0.0
    # 鍧囧€煎洖褰?+ 涓婅瓒嬪娍 = 鑳滅巼鏇撮珮鐨勭粍鍚?    # ==================================================================
    trend_score = 0.0
    ma20 = indicators.calc_sma(closes, config.MA_SHORT)
    ma60 = indicators.calc_sma(closes, config.MA_LONG)

    if ma20 and cur_price > ma20:
        trend_score += 0.5
    if ma60 and cur_price > ma60:
        trend_score += 0.5

    # ==================================================================
    # 鍥犲瓙 3: 鎴愪氦閲忕‘璁わ紙鏉冮噸 0.15锛?    #
    # 閲忔瘮 = 褰撴棩閲?/ 20鏃ュ潎閲?    # 閲忔瘮瓒婂ぇ璇存槑璧勯噾浠嬪叆瓒婄Н鏋侊紝鍙嶅脊淇″彿瓒婂彲闈?    # ==================================================================
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    if vol_ratio >= config.VOL_SURGE_MIN:
        # 绾挎€ф槧灏? 1.2x 鈫?0.0, 2.0x 鈫?1.0
        vol_score = min(1.0, (vol_ratio - config.VOL_SURGE_MIN) / (2.0 - config.VOL_SURGE_MIN))
    else:
        # 閲忚兘涓嶈冻锛岀嚎鎬ф槧灏? 0 鈫?0.0, VOL_SURGE_MIN 鈫?0.0锛堜笉缁欏垎锛?        vol_score = 0.0

    # ==================================================================
    # 鍥犲瓙 4: 杩戞湡璺屽箙锛堟潈閲?0.15锛?    #
    # 浠?20 鏃ュ唴鏈€楂樼偣璺屼簡澶氬皯
    # 璺屽箙瓒婂ぇ 鈫?鍧囧€煎洖褰掓綔鍔涜秺澶?鈫?寰楀垎瓒婇珮
    # 浣?> 20% 鐨勬瀬绔穼骞呭彲鑳芥湁闂锛堝熀鏈潰鎭跺寲锛夛紝缁欏垎闄嶄綆
    # ==================================================================
    dd = indicators.calc_drawdown(closes, 20)
    if dd is None:
        dd_score = 0.0
    elif dd > 0.20:
        # 鏋佺璺屽箙 鈫?鍙兘鏄熀鏈潰闂锛岄檷鍒?        dd_score = 0.5
    elif dd > 0.05:
        # 涓瓑璺屽箙锛?%~20%锛? 鏈€浣冲弽寮瑰尯闂?        dd_score = dd / 0.15  # 15% 璺屽箙 = 1.0 鍒?        dd_score = min(1.0, dd_score)
    else:
        # 璺屽箙 < 5%: 鍙嶅脊绌洪棿鏈夐檺
        dd_score = dd / 0.05 * 0.5

    # ==================================================================
    # 鍥犲瓙 5: 鍙嶈浆褰㈡€侊紙鏉冮噸 0.10锛?    #
    # K 绾垮舰鎬佺‘璁ゅ簳閮ㄥ弽杞?    # ==================================================================
    reversal = indicators.detect_reversal(opens, highs, lows, closes)
    reversal_score = reversal['score']

    # ==================================================================
    # 鍥犲瓙 6: 琛屼笟鍔ㄩ噺锛堟潈閲?0.10锛?    #
    # 濡傛灉琛屼笟鏁翠綋璧板己锛岃琛屼笟鐨勮秴鍗栧弽寮规洿鍙潬
    # 濡傛灉琛屼笟鎸佺画璧板急锛屽嵆浣夸釜鑲¤秴鍗栦篃鍙兘鏄涓氭€ч棶棰?    # ==================================================================
    if sector_momentum and sector in sector_momentum:
        sm = sector_momentum[sector]
        # 鍔ㄩ噺浠?-1 鍒?+1锛屾槧灏勫埌 0~1
        sector_score = max(0.0, min(1.0, (sm + 0.5) / 1.0))
    else:
        sector_score = 0.5  # 鏃犳暟鎹椂缁欎腑鎬у垎

    # ==================================================================
    # 鍔犳潈鍚堟垚鎬诲垎
    # ==================================================================
    w = config.SCORING_WEIGHTS
    total = (
        w['rsi_oversold']    * rsi_score +
        w['trend_align']     * trend_score +
        w['volume_surge']    * vol_score +
        w['drawdown']        * dd_score +
        w['reversal_form']   * reversal_score +
        w['sector_momentum'] * sector_score
    )

    return {
        'symbol':  sym,
        'sector':  sector,
        'total':   round(total, 4),
        'price':   cur_price,
        'rsi':     round(rsi, 1),
        'details': {
            'rsi_score':       round(rsi_score, 3),
            'trend_score':     round(trend_score, 3),
            'vol_score':       round(vol_score, 3),
            'dd_score':        round(dd_score, 3),
            'reversal_score':  round(reversal_score, 3),
            'sector_score':    round(sector_score, 3),
        },
    }


# =============================================================================
# 琛屼笟鍔ㄩ噺璁＄畻
# =============================================================================

def calc_sector_momentum(context):
    """
    璁＄畻鍚勮涓氱殑鍔ㄩ噺寰楀垎銆?
    瀵规瘡涓涓氾紝鍙栨墍鏈夋垚鍒嗚偂鐨勫钩鍧?10 鏃ユ定璺屽箙浣滀负琛屼笟鍔ㄩ噺銆?    姝ｅ€?= 琛屼笟璧板己锛岃礋鍊?= 琛屼笟璧板急銆?
    杩斿洖:
        dict: {sector: momentum_score}
    """
    momentum = {}
    sector_map = stock_pool.get_symbol_sector_map()

    for sector in stock_pool.get_sector_list():
        stocks = stock_pool.filter_by_sector(sector)
        rets = []

        for sym in stocks:
            df = context.data_cache.get(sym)
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


# =============================================================================
# 棰勫姞杞? 纭繚 stock_pool 鐨勬槧灏勫彲鐢?# =============================================================================

# 鍦ㄦā鍧楀姞杞芥椂鏋勫缓鐨勬槧灏勶紝渚?screen_all 蹇€熸煡璇?SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()
