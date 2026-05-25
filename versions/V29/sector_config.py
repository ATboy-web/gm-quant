"""


sector_config.py - V24 琛屼笟宸紓鍖栫瓥鐣ラ厤缃?


V28 鏀硅繘:
  鍚勮涓?entry_threshold 浠?V27 鍊奸檷浣?~0.02锛屽洖鍒?V26/V27 涓偣
  楂樻尝鍔ㄨ涓氫粨浣嶅井璋?(+0.01), bear 甯傚満闂ㄦ浠?+0.10->0.08

V29 鏀硅繘:
  MOM 鍦?涓潪瓒嬪娍琛屼笟绂佺敤锛堥噾铻?娑堣垂/鍖昏嵂/鍒堕€?姹借溅/鍖栧伐/鍏敤浜嬩笟/鐓ょ偔锛?
  MOM 鍦?涓秼鍔胯涓氶檷鏉冿紙绉戞妧2.0鈫?.0, 鏂拌兘婧?.8鈫?.5, 鏈夎壊1.5鈫?.8, 鍐涘伐1.0鈫?.5锛?
  DV 鍏ㄨ涓氶檷鏉儈30%锛堥噾铻?.5鈫?.0, 娑堣垂1.5鈫?.0, 鍏敤浜嬩笟1.5鈫?.0, 鐓ょ偔2.0鈫?.2锛?
  BK 琛ュ伩鎻愭潈锛堢鎶€1.5鈫?.0, 鍐涘伐1.0鈫?.5锛?



V19.2 鏀硅繘:


  1. 鏂板绐佺牬绛栫暐(BK)鍜岀孩鍒╃瓥鐣?DV)


  2. 鏂拌兘婧?鍏敤浜嬩笟鍙傛暟澶у箙浼樺寲


  3. 楂樻尝鍔ㄨ涓?鏈夎壊/绉戞妧/鍐涘伐/鏂拌兘婧?娣诲姞BK绛栫暐


  4. 浣庢尝鍔ㄨ涓?閲戣瀺/娑堣垂/鐓ょ偔/鍏敤浜嬩笟)娣诲姞DV绛栫暐


V19 鏍稿績鏀硅繘:


  涓嶅悓琛屼笟鎷ユ湁涓嶅悓鐨勬尝鍔ㄧ壒鎬с€佸懆鏈熷睘鎬у拰璧勯噾鍋忓ソ锛?


  鍥犳姣忎釜琛屼笟搴旇鏈夌嫭绔嬬殑绛栫暐鍙傛暟閰嶇疆锛岃€岄潪涓€濂楀弬鏁拌蛋澶╀笅銆?


閰嶇疆缁村害:


  1. 绛栫暐缁勫悎: 鍝簺绛栫暐瀵硅琛屼笟鏈夋晥锛屽悇鑷潈閲?


  2. RSI 鍙傛暟: 涔板叆/鍑哄満/鏋佸害瓒呭崠闃堝€?


  3. ATR 鍙傛暟: 姝㈡崯/姝㈢泩鍊嶆暟


  4. 浠撲綅鍙傛暟: 鍗曞彧鍗犳瘮銆佹渶澶ф寔浠?


  5. 鏃堕棿鍙傛暟: 鎸佷粨鍛ㄦ湡涓婇檺


  6. 琛屼笟鐗瑰緛: 娉㈠姩鐜囧垎缁勩€佸懆鏈熸€с€侀€傚悎绛栫暐鎻忚堪


V19.1 璋冧紭:


  - 鏃堕棿姝㈡崯鏀惧锛?0d鈫?5d / 12d鈫?8d 绛夛級锛岀粰鍙嶅脊鏇村鏃堕棿


  - ATR 姝㈡崯闂ㄦ鎻愰珮锛?.0%鈫?.0%锛夛紝閬垮厤姝ｅ父娉㈠姩瑙﹀彂姝㈡崯


  - MOM 璺岀牬MA20 鏀逛负杩炵画2澶╃‘璁?


浣跨敤鏂规硶:


    import sector_config


    cfg = sector_config.get_sector_config('閲戣瀺')


    # cfg = {'rsi_buy': 32, 'strategies': ['MR', 'VP'], ...}


"""


# =============================================================================


# 琛屼笟绛栫暐閰嶇疆琛?


# =============================================================================


SECTOR_CONFIGS = {


    # ==================================================================


    # 閲戣瀺锛堥摱琛屻€佷繚闄╋級鈥?浣庢尝鍔ㄣ€侀槻寰℃€с€佸潎鍊煎洖褰掍负涓?


    # ==================================================================


    '閲戣瀺': {


        'vol_group': 'low',


        'cycle_type': 'defensive',


        'description': '浣庢尝鍔ㄩ槻寰★紝RSI鍙嶅脊纭畾鎬ч珮锛岀孩鍒╁姞鎸?,


        'strategies': {


            'MR':  {'enabled': True,  'weight': 3.0},


            'DV':  {'enabled': True,  'weight': 1.0},    # V29: 1.5鈫?.0


            'VP':  {'enabled': True,  'weight': 1.0},    # V19.2: 1.5鈫?.0


            'MOM': {'enabled': False, 'weight': 0.0},  # V29: 绂佺敤, 闈炶秼鍔?


        },


        'rsi_buy': 32,


        'rsi_exit': 75,


        'rsi_deep_oversold': 20,


        'atr_stop_mult': 1.5,       # V19.1: 1.2鈫?.5 鏀惧


        'atr_trail_mult': 2.5,      # V19.1: 2.0鈫?.5


        'stop_loss_cap': 0.07,      # V19.1: 0.06鈫?.07


        'position_pct': 0.30,


        'time_stop_days': 15,       # V19.1: 12鈫?5


        'entry_threshold': 0.36,   # V28: 0.38鈫?.36

        'vol_surge_min': 1.1,


        'vp_vol_decline': 0.70,


        'mom_stop_loss': 0.06,      # V19.1: 0.05鈫?.06


        'mom_take_profit': 0.12,


    },


    # ==================================================================


    # 娑堣垂锛堥鍝侀ギ鏂欍€佸鐢碉級鈥?浣庢尝鍔ㄣ€侀槻寰℃€?


    # ==================================================================


    '娑堣垂': {


        'vol_group': 'low',


        'cycle_type': 'defensive',


        'description': '娑堣垂鐧介┈瓒呭崠鍙嶅脊鍙潬锛岀孩鍒╁姞鎸?,


        'strategies': {


            'MR':  {'enabled': True,  'weight': 3.0},


            'DV':  {'enabled': True,  'weight': 1.0},    # V29: 1.5鈫?.0


            'VP':  {'enabled': True,  'weight': 1.0},    # V19.2: 1.5鈫?.0


            'MOM': {'enabled': False, 'weight': 0.0},  # V29: 绂佺敤, 闈炶秼鍔?


        },


        'rsi_buy': 32,


        'rsi_exit': 75,


        'rsi_deep_oversold': 20,


        'atr_stop_mult': 1.5,


        'atr_trail_mult': 2.5,


        'stop_loss_cap': 0.07,


        'position_pct': 0.30,


        'time_stop_days': 18,       # V19.1: 15鈫?8


        'entry_threshold': 0.36,   # V28: 0.38鈫?.36

        'vol_surge_min': 1.1,


        'vp_vol_decline': 0.70,


        'mom_stop_loss': 0.06,


        'mom_take_profit': 0.12,


    },


    # ==================================================================


    # 鍖昏嵂 鈥?涓尝鍔ㄣ€侀槻寰℃€?鎴愰暱鎬?


    # ==================================================================


    '鍖昏嵂': {


        'vol_group': 'medium',


        'cycle_type': 'defensive',


        'description': '鏀跨瓥鏁忔劅锛孧R+VP鍙岄噸纭',


        'strategies': {


            'MR':  {'enabled': True,  'weight': 2.5},


            'VP':  {'enabled': True,  'weight': 2.0},


            'MOM': {'enabled': False, 'weight': 0.0},  # V29: 绂佺敤


        },


        'rsi_buy': 30,


        'rsi_exit': 78,


        'rsi_deep_oversold': 18,


        'atr_stop_mult': 1.8,       # V19.1: 1.5鈫?.8


        'atr_trail_mult': 2.5,


        'stop_loss_cap': 0.08,      # V19.1: 0.07鈫?.08


        'position_pct': 0.25,


        'time_stop_days': 18,       # V19.1: 15鈫?8


        'entry_threshold': 0.41,   # V28: 0.43鈫?.41

        'vol_surge_min': 1.2,


        'vp_vol_decline': 0.65,


        'mom_stop_loss': 0.07,


        'mom_take_profit': 0.15,


    },


    # ==================================================================


    # 绉戞妧锛堝畨闃层€丄I銆侀€氫俊锛夆€?楂樻尝鍔ㄣ€佹垚闀挎€?


    # ==================================================================


    '绉戞妧': {


        'vol_group': 'high',


        'cycle_type': 'growth',


        'description': '瓒嬪娍鎬у己锛孧OM+绐佺牬鏉冮噸楂橈紝RSI闇€鏀剁揣',


        'strategies': {


            'MR':  {'enabled': True,  'weight': 2.0},


            'MOM': {'enabled': True,  'weight': 1.0},  # V29: 2.0鈫?.0


            'BK':  {'enabled': True,  'weight': 2.0},    # V29: 1.5鈫?.0, 琛ュ伩MOM


            'VP':  {'enabled': True,  'weight': 1.0},


        },


        'rsi_buy': 28,


        'rsi_exit': 82,


        'rsi_deep_oversold': 18,


        'atr_stop_mult': 2.0,       # V19.1: 1.8鈫?.0


        'atr_trail_mult': 3.0,


        'stop_loss_cap': 0.10,


        'position_pct': 0.19,   # V28: 0.18鈫?.19, 楂樻尝鍔ㄧ暐鏀惧


        'time_stop_days': 15,       # V19.1: 10鈫?5


        'entry_threshold': 0.41,   # V28: 0.43鈫?.41

        'vol_surge_min': 1.3,


        'vp_vol_decline': 0.60,


        'mom_stop_loss': 0.08,


        'mom_take_profit': 0.18,


    },


    # ==================================================================


    # 鏂拌兘婧愶紙鍏変紡銆侀鐢碉級鈥?楂樻尝鍔ㄣ€佸己鍛ㄦ湡


    # ==================================================================


    '鏂拌兘婧?: {


        'vol_group': 'high',


        'cycle_type': 'cyclical',


        'description': '鏅皵鍛ㄦ湡娉㈠姩澶э紝MR+VP+绐佺牬绛栫暐',


        'strategies': {


            'MR':  {'enabled': True,  'weight': 2.0},


            'VP':  {'enabled': True,  'weight': 2.0},


            'BK':  {'enabled': True,  'weight': 1.0},


            'MOM': {'enabled': True,  'weight': 0.5},  # V29: 0.8鈫?.5


        },


        'rsi_buy': 28,


        'rsi_exit': 80,


        'rsi_deep_oversold': 18,


        'atr_stop_mult': 2.5,    # 鏀惧姝㈡崯


        'atr_trail_mult': 3.5,   # 璁╁埄娑﹁窇鏇磋繙


        'stop_loss_cap': 0.12,   # 鎻愰珮姝㈡崯涓婇檺


        'position_pct': 0.16,   # V28: 0.15鈫?.16, 鏂拌兘婧愮暐鏀惧


        'time_stop_days': 22,    # 缁欏己鍛ㄦ湡鏇村淇鏃堕棿


        'entry_threshold': 0.41,   # V28: 0.43鈫?.41

        'vol_surge_min': 1.3,


        'vp_vol_decline': 0.60,


        'mom_stop_loss': 0.08,


        'mom_take_profit': 0.15,


    },


    # ==================================================================


    # 鍒堕€狅紙宸ョ▼鏈烘銆佸鐢碉級鈥?涓尝鍔ㄣ€佸懆鏈熸€?


    # V21: 鏂板RT(涓変竴閲嶅伐2绗?10%), MR闄嶆潈


    # ==================================================================


    '鍒堕€?: {


        'vol_group': 'medium',


        'cycle_type': 'cyclical',


        'description': '缁忔祹鍛ㄦ湡椹卞姩锛孧R+MOM+RT',


        'strategies': {


            'MR':  {'enabled': True,  'weight': 2.0},    # V21: 2.5鈫?.0


            'MOM': {'enabled': False, 'weight': 0.0},  # V29: 绂佺敤, 闈炶秼鍔?


            'RT':  {'enabled': True,  'weight': 1.0},    # V21: 鏂板


            'VP':  {'enabled': True,  'weight': 1.0},


        },


        'rsi_buy': 30,


        'rsi_exit': 78,


        'rsi_deep_oversold': 20,


        'atr_stop_mult': 1.8,       # V19.1: 1.5鈫?.8


        'atr_trail_mult': 2.5,


        'stop_loss_cap': 0.08,


        'position_pct': 0.25,


        'time_stop_days': 18,       # V19.1: 15鈫?8


        'entry_threshold': 0.39,   # V28: 0.41鈫?.39

        'vol_surge_min': 1.2,


        'vp_vol_decline': 0.65,


        'mom_stop_loss': 0.07,


        'mom_take_profit': 0.15,


    },


    # ==================================================================


    # 鏈夎壊锛堥粍閲戙€侀摐銆侀摑銆侀捈锛夆€?楂樻尝鍔ㄣ€佸己鍛ㄦ湡


    # ==================================================================


    '鏈夎壊': {


        'vol_group': 'high',


        'cycle_type': 'cyclical',


        'description': '鍟嗗搧鍛ㄦ湡椹卞姩锛孷P+MOM+绐佺牬鎹曟崏鍛ㄦ湡杞姌',


        'strategies': {


            'MR':  {'enabled': True,  'weight': 2.0},


            'VP':  {'enabled': True,  'weight': 2.0},


            'MOM': {'enabled': True,  'weight': 0.8},  # V29: 1.5鈫?.8


            'BK':  {'enabled': True,  'weight': 1.0},    # V19.2: 鏂板绐佺牬


        },


        'rsi_buy': 28,


        'rsi_exit': 80,


        'rsi_deep_oversold': 18,


        'atr_stop_mult': 2.0,       # V19.1: 1.8鈫?.0


        'atr_trail_mult': 2.8,


        'stop_loss_cap': 0.10,


        'position_pct': 0.19,   # V28: 0.18鈫?.19, 楂樻尝鍔ㄧ暐鏀惧


        'time_stop_days': 15,       # V19.1: 12鈫?5


        'entry_threshold': 0.39,   # V28: 0.41鈫?.39

        'vol_surge_min': 1.3,


        'vp_vol_decline': 0.60,


        'mom_stop_loss': 0.08,


        'mom_take_profit': 0.18,


    },


    # ==================================================================


    # 姹借溅锛堟暣杞︺€侀浂閮ㄤ欢锛夆€?涓尝鍔ㄣ€佸懆鏈熸€?鏀跨瓥鏁忔劅


    # ==================================================================


    '姹借溅': {


        'vol_group': 'medium',


        'cycle_type': 'cyclical',


        'description': '鏀跨瓥鍒烘縺褰卞搷澶э紝MOM+MR缁撳悎',


        'strategies': {


            'MR':  {'enabled': True,  'weight': 2.5},


            'MOM': {'enabled': False, 'weight': 0.0},  # V29: 绂佺敤, 琛屼笟宸?


            'VP':  {'enabled': True,  'weight': 1.0},


        },


        'rsi_buy': 30,


        'rsi_exit': 78,


        'rsi_deep_oversold': 20,


        'atr_stop_mult': 1.8,


        'atr_trail_mult': 2.5,


        'stop_loss_cap': 0.08,


        'position_pct': 0.25,


        'time_stop_days': 15,       # V19.1: 12鈫?5


        'entry_threshold': 0.39,   # V28: 0.41鈫?.39

        'vol_surge_min': 1.2,


        'vp_vol_decline': 0.65,


        'mom_stop_loss': 0.07,


        'mom_take_profit': 0.15,


    },


    # ==================================================================


    # 鍖栧伐 鈥?涓尝鍔ㄣ€佸己鍛ㄦ湡


    # ==================================================================


    '鍖栧伐': {


        'vol_group': 'medium',


        'cycle_type': 'cyclical',


        'description': '浜у搧浠锋牸鍛ㄦ湡椹卞姩锛孷P+MR缁撳悎',


        'strategies': {


            'MR':  {'enabled': True,  'weight': 2.5},


            'VP':  {'enabled': True,  'weight': 1.5},


            'MOM': {'enabled': False, 'weight': 0.0},  # V29: 绂佺敤


        },


        'rsi_buy': 30,


        'rsi_exit': 78,


        'rsi_deep_oversold': 20,


        'atr_stop_mult': 1.8,


        'atr_trail_mult': 2.5,


        'stop_loss_cap': 0.08,


        'position_pct': 0.25,


        'time_stop_days': 18,       # V19.1: 15鈫?8


        'entry_threshold': 0.39,   # V28: 0.41鈫?.39

        'vol_surge_min': 1.2,


        'vp_vol_decline': 0.65,


        'mom_stop_loss': 0.07,


        'mom_take_profit': 0.15,


    },


    # ==================================================================


    # 鍏敤浜嬩笟锛堢數鍔涳級鈥?浣庢尝鍔ㄣ€侀槻寰℃€?


    # V20鍘熺増: MR缁濆涓诲, 瀹芥澗鍙傛暟


    # ==================================================================


    '鍏敤浜嬩笟': {


        'vol_group': 'low',


        'cycle_type': 'defensive',


        'description': '鏈€绋冲畾锛岃秴鍗栧繀鍙嶅脊锛孧R+绾㈠埄鍙岄┍',


        'strategies': {


            'MR':  {'enabled': True,  'weight': 4.0},    # 缁濆涓诲


            'DV':  {'enabled': True,  'weight': 1.0},  # V29: 1.5鈫?.0


            'VP':  {'enabled': True,  'weight': 0.5},


            'MOM': {'enabled': False, 'weight': 0.0},


        },


        'rsi_buy': 38,


        'rsi_exit': 70,


        'rsi_deep_oversold': 25,


        'atr_stop_mult': 1.5,


        'atr_trail_mult': 2.5,


        'stop_loss_cap': 0.07,


        'position_pct': 0.35,


        'time_stop_days': 25,


        'entry_threshold': 0.31,   # V28: 0.33鈫?.31

        'vol_surge_min': 1.0,


        'vp_vol_decline': 0.80,


        'mom_stop_loss': 0.04,


        'mom_take_profit': 0.10,


    },


    # ==================================================================


    # 鍐涘伐 鈥?楂樻尝鍔ㄣ€佹斂绛栭┍鍔?


    # ==================================================================


    '鍐涘伐': {


        'vol_group': 'high',


        'cycle_type': 'growth',


        'description': '鏀跨瓥浜嬩欢椹卞姩锛岀獊鍙戞€у己锛屾鎹熻瀹?,


        'strategies': {


            'MR':  {'enabled': True,  'weight': 2.0},


            'VP':  {'enabled': True,  'weight': 1.5},


            'BK':  {'enabled': True,  'weight': 1.5},    # V29: 1.0鈫?.5, 琛ュ伩MOM


            'MOM': {'enabled': True,  'weight': 0.5},  # V29: 1.0鈫?.5


        },


        'rsi_buy': 28,


        'rsi_exit': 82,


        'rsi_deep_oversold': 18,


        'atr_stop_mult': 2.2,       # V19.1: 2.0鈫?.2


        'atr_trail_mult': 3.0,


        'stop_loss_cap': 0.10,


        'position_pct': 0.19,   # V28: 0.18鈫?.19, 楂樻尝鍔ㄧ暐鏀惧


        'time_stop_days': 15,       # V19.1: 12鈫?5


        'entry_threshold': 0.41,   # V28: 0.43鈫?.41

        'vol_surge_min': 1.3,


        'vp_vol_decline': 0.60,


        'mom_stop_loss': 0.08,


        'mom_take_profit': 0.18,


    },


    # ==================================================================


    # 鐓ょ偔 鈥?涓尝鍔ㄣ€佸己鍛ㄦ湡


    # V20: DV鎻愭潈+RT鍙嶈浆纭锛孧R闄嶆潈閬垮厤宸︿晶鎶勫簳


    # ==================================================================


    '鐓ょ偔': {


        'vol_group': 'medium',


        'cycle_type': 'cyclical',


        'description': '鐓や环鍛ㄦ湡椹卞姩锛孯T鍙嶈浆+DV绾㈠埄+MR鎶勫簳',


        'strategies': {


            'MR':  {'enabled': True,  'weight': 2.0},    # V20: 3.0鈫?.0锛岄檷浣庢妱搴曟潈閲?


            'DV':  {'enabled': True,  'weight': 1.2},    # V29: 2.0鈫?.2, 鐓ょ偔


            'RT':  {'enabled': True,  'weight': 1.5},    # V20: 鏂板鍙嶈浆纭


            'VP':  {'enabled': True,  'weight': 1.0},    # V20: 1.5鈫?.0


            'MOM': {'enabled': False, 'weight': 0.0},    # V29: 绂佺敤, 闈炶秼鍔胯涓?


        },


        'rsi_buy': 30,


        'rsi_exit': 78,


        'rsi_deep_oversold': 20,


        'atr_stop_mult': 1.8,       # V19.1: 1.5鈫?.8


        'atr_trail_mult': 2.5,


        'stop_loss_cap': 0.08,


        'position_pct': 0.25,


        'time_stop_days': 18,       # V19.1: 15鈫?8


        'entry_threshold': 0.39,   # V28: 0.41鈫?.39

        'vol_surge_min': 1.2,


        'vp_vol_decline': 0.65,


        'mom_stop_loss': 0.07,


        'mom_take_profit': 0.15,


    },


}


# 榛樿閰嶇疆锛堟湭鐭ヨ涓氬厹搴曪級


DEFAULT_CONFIG = {


    'vol_group': 'medium',


    'cycle_type': 'mixed',


    'description': '榛樿閰嶇疆',


    'strategies': {


        'MR':  {'enabled': True,  'weight': 2.5},


        'MOM': {'enabled': True,  'weight': 1.0},


        'VP':  {'enabled': True,  'weight': 1.0},


        'BK':  {'enabled': False, 'weight': 0.0},


        'DV':  {'enabled': False, 'weight': 0.0},


        'RT':  {'enabled': False, 'weight': 0.0},


    },


    'rsi_buy': 30,


    'rsi_exit': 80,


    'rsi_deep_oversold': 20,


    'atr_stop_mult': 1.8,


    'atr_trail_mult': 2.5,


    'stop_loss_cap': 0.08,


    'position_pct': 0.25,


    'time_stop_days': 18,


    'entry_threshold': 0.40,

    'vol_surge_min': 1.2,


    'vp_vol_decline': 0.65,


    'mom_stop_loss': 0.07,


    'mom_take_profit': 0.15,


}


# =============================================================================


# 甯傚満鐘舵€佽鐩栧眰锛堝彔鍔犲湪琛屼笟閰嶇疆涔嬩笂锛?


# =============================================================================


REGIME_OVERRIDE = {


    'bull': {


        'position_multiplier': 1.15,       # V27: 1.2鈫?.15


        'rsi_buy_adjust': 2,


        'entry_threshold_adjust': -0.03,   # V28: -0.02鈫?0.03, 鐗涘競鐣ユ斁鏉?


    },


    'range': {


        'position_multiplier': 1.0,


        'rsi_buy_adjust': 0,


        'entry_threshold_adjust': 0.0,


    },


    'bear': {


        'position_multiplier': 0.65,       # V27: 0.7鈫?.65, 鐔婂競鏇翠繚瀹?


        'rsi_buy_adjust': -3,


        'entry_threshold_adjust': 0.08,    # V28: 0.10鈫?.08, 鐔婂競绋嶆斁鏉?


    },


}


# =============================================================================


# 鍏紑鎺ュ彛


# =============================================================================


def get_sector_config(sector, regime='range'):


    """鑾峰彇琛屼笟閰嶇疆锛屽彔鍔犲競鍦虹姸鎬佽皟鏁淬€?""


    cfg = SECTOR_CONFIGS.get(sector, DEFAULT_CONFIG).copy()


    override = REGIME_OVERRIDE.get(regime, REGIME_OVERRIDE['range'])


    cfg['rsi_buy'] = cfg.get('rsi_buy', 30) + override.get('rsi_buy_adjust', 0)


    cfg['entry_threshold'] = cfg.get('entry_threshold', 0.35) + override.get('entry_threshold_adjust', 0)


    cfg['position_pct'] = cfg.get('position_pct', 0.25) * override.get('position_multiplier', 1.0)


    return cfg


def get_strategy_weight(sector, strategy_name, regime='range'):


    """鑾峰彇鏌愮瓥鐣ュ湪鏌愯涓?甯傚満鐘舵€佷笅鐨勬潈閲嶃€?""


    cfg = get_sector_config(sector, regime)


    strategies = cfg.get('strategies', {})


    return strategies.get(strategy_name, {}).get('weight', 0.0)


def is_strategy_enabled(sector, strategy_name, regime='range'):


    """鍒ゆ柇鏌愮瓥鐣ュ湪鏌愯涓?甯傚満鐘舵€佷笅鏄惁鍚敤銆?""


    cfg = get_sector_config(sector, regime)


    strategies = cfg.get('strategies', {})


    return strategies.get(strategy_name, {}).get('enabled', False)


def get_sector_strategies(sector, regime='range'):


    """鑾峰彇鏌愯涓氬湪褰撳墠甯傚満鐘舵€佷笅鍚敤鐨勭瓥鐣ュ垪琛ㄣ€?""


    cfg = get_sector_config(sector, regime)


    strategies = cfg.get('strategies', {})


    return [name for name, info in strategies.items() if info.get('enabled', False)]


def get_all_sectors():


    """鑾峰彇鎵€鏈夐厤缃簡绛栫暐鐨勮涓氬垪琛ㄣ€?""


    return list(SECTOR_CONFIGS.keys())


def print_summary():


    print('=' * 70)


    print('  V24 琛屼笟宸紓鍖栫瓥鐣ラ厤缃?鈥?%d 涓涓? % len(SECTOR_CONFIGS))


    print('=' * 70)


    for sector, cfg in SECTOR_CONFIGS.items():


        enabled = [n for n, i in cfg['strategies'].items() if i['enabled']]


        weights = {n: i['weight'] for n, i in cfg['strategies'].items() if i['enabled']}


        print('  %-6s | %s | %s | RSI<%d | ATR脳%.1f | 浠?.0f%% | 姝㈡崯%.0f%% | 鏃堕棿%dd | 绛栫暐: %s'


              % (sector, cfg['vol_group'][:3], cfg['cycle_type'][:4],


                 cfg['rsi_buy'], cfg['atr_stop_mult'],


                 cfg['position_pct'] * 100, cfg['stop_loss_cap'] * 100,


                 cfg['time_stop_days'],


                 '+'.join('%s(%.1f)' % (n, w) for n, w in weights.items())))


    print('-' * 70)


    print('  甯傚満鐘舵€佸彔鍔?')


    for regime, ov in REGIME_OVERRIDE.items():


        print('    %s: RSI%+d | 闂ㄦ%+.2f | 浠撲綅脳%.1f'


              % (regime, ov['rsi_buy_adjust'],


                 ov['entry_threshold_adjust'],


                 ov['position_multiplier']))


    print('=' * 70)


if __name__ == '__main__':


    print_summary()


