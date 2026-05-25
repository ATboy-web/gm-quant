"""

鍏瓥鐣?MR/MOM/VP/BK/DV/RT)淇″彿铻嶅悎 + 鎶曠エ鍐崇瓥銆?

鍏ュ満: executor._vote_with_sector_weights() 琛屼笟宸紓鍖栨潈閲?+ 鍏瓥鐣ュ姞鏉冩姇绁ㄣ€?
鍑哄満: vote_exit() 褰掑睘浼樺厛 + 姝㈡崯瀹夊叏闃€ + 瓒嬪娍绫讳氦鍙夐獙璇併€?

鍑哄満瑙勫垯:
  1. 褰掑睘绛栫暐鍠?SELL 鈫?鐩存帴鍗?
  2. 浠讳綍姝㈡崯绫讳俊鍙?鈫?瀹夊叏闃€鐩存帴鎵ц
  3. 瓒嬪娍/鏃堕棿绫诲嚭鍦?鈫?闇€褰掑睘绛栫暐鎴栦氦鍙夐獙璇?

"""

import config


def vote_entry(mr_signal, mom_signal, vp_signal, regime='range'):
    """[宸插簾寮僝 鏃т笁绛栫暐鍏ュ満鎶曠エ銆俈27 璧风敱 executor._vote_with_sector_weights() 鏇夸唬锛屼繚鐣欎粎涓哄悜鍚庡吋瀹广€?""
    return {'action': 'HOLD', 'confidence': 0.0, 'position_pct': 0.0, 'voters': [], 'reason': 'DEPRECATED_use_executor'}


def vote_exit(mr_exit, mom_exit, vp_exit, bk_exit=None, dv_exit=None, rt_exit=None,
              regime='range', owner_strategy=None):
    """
    瀵瑰叚绛栫暐(MR/MOM/VP/BK/DV/RT)鐨勫嚭鍦轰俊鍙疯繘琛屾姇绁紝鍐冲畾鏄惁鍗栧嚭銆?

      1. 褰掑睘绛栫暐鍠?SELL 鈫?鐩存帴鍗栵紙浼樺厛鏉冿級
      2. 浠讳綍姝㈡崯/姝㈢泩淇″彿 鈫?鐩存帴鍗栵紙瀹夊叏闃€锛岄槻姝㈢瓥鐣ヤ笉鍖归厤瀵艰嚧浜忔崯鎵╁ぇ锛?
      3. 闈炲綊灞炵瓥鐣ョ殑瓒嬪娍/鏃堕棿绫诲嚭鍦?鈫?闇€瑕佷氦鍙夐獙璇侊紙鈮?涓瓥鐣ュ悓鎰忥級
      
    鍖哄垎銆屾鎹熺被銆嶏紙楂樹紭鍏堢骇锛夊拰銆岃秼鍔?鏃堕棿绫汇€嶏紙浣庝紭鍏堢骇锛夛細
      - 姝㈡崯绫? ATR姝㈡崯銆佽穼鐮碝A20銆佸浐瀹氭鎹熴€乂P姝㈡崯銆丅K姝㈡崯 鈥?鐩存帴鎵ц
      - 瓒嬪娍绫? 鏃堕棿姝㈡崯銆丷SI杩囩儹 鈥?闇€瑕佸綊灞炵瓥鐣ユ垨浜ゅ弶楠岃瘉
    """
    signals = [
        ('MR',  mr_exit),
        ('MOM', mom_exit),
        ('VP',  vp_exit),
        ('BK',  bk_exit),
        ('DV',  dv_exit),
        ('RT',  rt_exit),
    ]

    # 姝㈡崯鍏抽敭璇嶏紙楂樹紭鍏堢骇锛屼换浣曠瓥鐣ラ兘鍙互瑙﹀彂锛?
    STOP_KEYWORDS = ['姝㈡崯', 'stop', 'STP']

    sell_votes  = 0.0
    reasons     = []
    owner_sell  = False
    has_stop_signal = False  # 鏄惁鏈夋鎹熺被淇″彿

    for name, sig in signals:
        if sig is None:
            continue
        action = sig.get('action', 'HOLD')
        weight = _get_regime_weight(name, regime)
        reason = sig.get('reason', name)
        conf = sig.get('confidence', 0.0)

        if action == 'SELL':
            is_weak_trend = (conf <= 0.5 and '鐭殏' in reason)
            if not is_weak_trend:
                sell_votes += weight
            reasons.append(reason)
            if name == owner_strategy:
                owner_sell = True
            # 妫€鏌ユ槸鍚︿负姝㈡崯绫讳俊鍙?
            for kw in STOP_KEYWORDS:
                if kw in reason:
                    has_stop_signal = True
                    break

    # ---- 鍑哄満鍐崇瓥 ----

    # 1. 褰掑睘绛栫暐鍠婂崠 鈫?鐩存帴鎵ц
    if owner_sell:
        return {
            'action': 'SELL',
            'confidence': 0.9,
            'reason': 'FUSION_褰掑睘绛栫暐[%s]鍗栧嚭|%s' % (owner_strategy, '|'.join(reasons)),
        }

    # 2. 浠讳綍姝㈡崯绫讳俊鍙?鈫?瀹夊叏闃€锛岀洿鎺ユ墽琛岋紙闃叉浜忔崯鎵╁ぇ锛?
    if has_stop_signal:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'FUSION_姝㈡崯淇濇姢|%s' % '|'.join(reasons),
        }

    # 3. 鎵€鏈夌瓥鐣ュ己鍗?
    if sell_votes >= 2.5:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'FUSION_寮哄崠[%s]' % '|'.join(reasons),
        }

    # 4. 瓒嬪娍/鏃堕棿绫诲嚭鍦?鈫?闇€浜ゅ弶楠岃瘉锛圴20: 鈮?.5, 鏀惧鍏ュ満涔熸斁瀹藉嚭鍦猴級
    if sell_votes >= 1.5:
        # 鑷冲皯2涓瓥鐣ュ悓鎰忚秼鍔?鏃堕棿鍑哄満
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'FUSION_浜ゅ弶楠岃瘉[%s]' % '|'.join(reasons),
        }

    return {
        'action': 'HOLD',
        'confidence': 0.0,
        'reason': 'FUSION_鏃犻渶鍑哄満',
    }


def _get_regime_weight(strategy_name, regime):
    """鏍规嵁甯傚満鐘舵€佽皟鏁寸瓥鐣ユ潈閲嶃€侻R 濮嬬粓涓诲锛堝洖娴嬭儨鐜?66.7%锛夈€?""
    if strategy_name == 'MR':
        # MR 濮嬬粓楂樻潈閲嶏紝浠庝笉闄嶆潈
        if regime == 'range':
            return 3.0   # 闇囪崱甯?MR 鏈€寮?
        elif regime == 'bear':
            return 1.5   # 鐔婂競 MR 浠嶄繚鐣欒瘽璇潈
        else:
            return 2.0   # 鐗涘競 MR 淇濇寔涓诲

    if strategy_name == 'MOM':
        if regime == 'bull':
            return 2.0   # 瓒嬪娍甯傚姩閲忓姞鍊?
        elif regime == 'range':
            return 0.5   # 闇囪崱甯傚姩閲忛檷鏉?
        elif regime == 'bear':
            return 0.3   # 鐔婂競鍔ㄩ噺澶у箙闄嶆潈

    if strategy_name == 'VP':
        if regime == 'bear':
            return 2.0   # 鐔婂競閲忎环鑳岀鍔犲€?
        else:
            return 1.0   # 鍏朵粬甯傚満姝ｅ父鏉冮噸

    if strategy_name == 'BK':
        return 1.0  # 绐佺牬绛栫暐姝ｅ父鏉冮噸

    if strategy_name == 'DV':
        return 1.0  # 绾㈠埄绛栫暐姝ｅ父鏉冮噸

    if strategy_name == 'RT':
        if regime == 'bear':
            return 2.0   # 鐔婂競鍙嶈浆纭楂樻潈閲嶏紙鎶勫簳纭鍨嬶級
        elif regime == 'range':
            return 1.5   # 闇囪崱甯傚弽杞‘璁や腑绛夋潈閲?
        else:
            return 0.8   # 鐗涘競涓嶉渶瑕佹妱搴曠‘璁?

    return 1.0


def _regime_tiebreaker(regime):
    """鍒嗘鏃舵寜甯傚満鐘舵€侀€夋柟鍚戙€?""
    if regime == 'bull':
        return '瓒嬪娍甯傚亸澶?
    elif regime == 'bear':
        return '鐔婂競鍋忕┖'
    else:
        return '闇囪崱甯傚亸澶?鍧囧€煎洖褰?'
