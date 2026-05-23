"""
stock_pool.py - 鑲＄エ姹犵鐞嗘ā鍧?(V16 鎵╁睍鐗?

鎻愪緵 35 鍙簿閫変富鏉胯偂绁ㄧ殑鍊欓€夋睜锛岃鐩?12 涓涓氥€?閰嶅悎 screener.py 鐨勬瘡鏃ユ墦鍒嗭紝绛栫暐浠庡€欓€夋睜涓嚜鍔ㄩ€夊嚭鏈€浼樻爣鐨勩€?
閫夎偂鏍囧噯:
  1. 浠呴檺涓绘澘锛圫HSE 600/601/603锛孲ZSE 000/001/002锛?     鎺掗櫎鍒涗笟鏉?30xxxx)鍜岀鍒涙澘(688xxx)
  2. 琛屼笟榫欏ご鎴栫粏鍒嗕紭璐ㄦ爣鐨?  3. 鏃ュ潎鎴愪氦棰?> 1 浜匡紙娴佸姩鎬ц繃婊わ級
  4. 涓婂競鏃堕棿鏃╀簬 2024-01-01
  5. 琛屼笟鍒嗘暎锛岃鐩?12 涓富瑕佹澘鍧?
浣跨敤鏂规硶:
    import stock_pool
    symbols = stock_pool.get_all_symbols()        # 鍏ㄩ儴鍊欓€?    sym_sec = stock_pool.get_symbol_sector_map()  # 绗﹀彿鈫掕涓氭槧灏?    tech    = stock_pool.filter_by_sector('绉戞妧')  # 鎸夎涓氱瓫閫?"""

# =============================================================================
# 鑲＄エ姹? 35 鍙?脳 12 琛屼笟
# =============================================================================

STOCK_POOL = {
    # ---- 閲戣瀺锛堥摱琛屻€佷繚闄╋級鈥?浣庢尝鍔?----
    '閲戣瀺': [
        'SHSE.600036',   # 鎷涘晢閾惰
        'SHSE.601318',   # 涓浗骞冲畨
        'SHSE.601166',   # 鍏翠笟閾惰
    ],

    # ---- 娑堣垂锛堥鍝侀ギ鏂欍€佸鐢碉級鈥?浣庢尝鍔?----
    '娑堣垂': [
        'SHSE.600887',   # 浼婂埄鑲′唤
        'SZSE.000858',   # 浜旂伯娑?        'SHSE.603288',   # 娴峰ぉ鍛充笟
    ],

    # ---- 鍖昏嵂 鈥?涓尝鍔?----
    '鍖昏嵂': [
        'SHSE.600276',   # 鎭掔憺鍖昏嵂
        'SZSE.000538',   # 浜戝崡鐧借嵂
        'SHSE.600436',   # 鐗囦粩鐧€
    ],

    # ---- 绉戞妧锛堝畨闃层€丄I銆侀€氫俊锛夆€?楂樻尝鍔?----
    '绉戞妧': [
        'SZSE.002415',   # 娴峰悍濞佽
        'SZSE.002230',   # 绉戝ぇ璁
        'SZSE.000063',   # 涓叴閫氳
    ],

    # ---- 鏂拌兘婧愶紙鍏変紡銆侀鐢碉級鈥?楂樻尝鍔?----
    '鏂拌兘婧?: [
        'SHSE.601012',   # 闅嗗熀缁胯兘
        'SHSE.600438',   # 閫氬▉鑲′唤
        'SHSE.600089',   # 鐗瑰彉鐢靛伐
    ],

    # ---- 鍒堕€狅紙宸ョ▼鏈烘銆佸鐢碉級鈥?涓尝鍔?----
    '鍒堕€?: [
        'SHSE.600031',   # 涓変竴閲嶅伐
        'SZSE.000333',   # 缇庣殑闆嗗洟
        'SZSE.000651',   # 鏍煎姏鐢靛櫒
    ],

    # ---- 鏈夎壊锛堥粍閲戙€侀摐銆侀摑銆侀捈锛夆€?楂樻尝鍔?----
    '鏈夎壊': [
        'SHSE.601899',   # 绱噾鐭夸笟
        'SHSE.603993',   # 娲涢槼閽间笟
        'SHSE.600362',   # 姹熻タ閾滀笟
    ],

    # ---- 姹借溅锛堟暣杞︺€侀浂閮ㄤ欢锛夆€?涓尝鍔?----
    '姹借溅': [
        'SZSE.002594',   # 姣斾簹杩?        'SHSE.600104',   # 涓婃苯闆嗗洟
        'SHSE.601633',   # 闀垮煄姹借溅
    ],

    # ---- 鍖栧伐 鈥?涓尝鍔?----
    '鍖栧伐': [
        'SHSE.600309',   # 涓囧崕鍖栧
        'SHSE.600426',   # 鍗庨瞾鎭掑崌
        'SHSE.600346',   # 鎭掑姏鐭冲寲
    ],

    # ---- 鍏敤浜嬩笟锛堢數鍔涳級鈥?浣庢尝鍔?----
    '鍏敤浜嬩笟': [
        'SHSE.600900',   # 闀挎睙鐢靛姏
        'SHSE.601985',   # 涓浗鏍哥數
        'SHSE.600886',   # 鍥芥姇鐢靛姏
    ],

    # ---- 鍐涘伐 鈥?楂樻尝鍔?----
    '鍐涘伐': [
        'SHSE.600760',   # 涓埅娌堥
        'SHSE.600150',   # 涓浗鑸硅埗
        'SHSE.600893',   # 鑸彂鍔ㄥ姏
    ],

    # ---- 鐓ょ偔 鈥?涓尝鍔?----
    '鐓ょ偔': [
        'SHSE.601088',   # 涓浗绁炲崕
        'SHSE.601225',   # 闄曡タ鐓や笟
    ],
}


# =============================================================================
# 鍏紑鎺ュ彛
# =============================================================================

def get_all_symbols():
    """鑾峰彇鍏ㄩ儴鍊欓€夎偂绁ㄤ唬鐮佸垪琛ㄣ€?""
    symbols = []
    for stocks in STOCK_POOL.values():
        symbols.extend(stocks)
    return symbols


def get_symbol_sector_map():
    """鑾峰彇鑲＄エ浠ｇ爜 鈫?琛屼笟鍚嶇О鐨勬槧灏勫瓧鍏搞€?""
    sym_sec = {}
    for sector, stocks in STOCK_POOL.items():
        for s in stocks:
            sym_sec[s] = sector
    return sym_sec


def get_sector_list():
    """鑾峰彇鎵€鏈夎涓氬悕绉板垪琛ㄣ€?""
    return list(STOCK_POOL.keys())


def filter_by_sector(sector):
    """鎸夎涓氱瓫閫夎偂绁ㄣ€?""
    return STOCK_POOL.get(sector, [])


def filter_by_market(market='SHSE'):
    """鎸変氦鏄撴墍绛涢€夎偂绁ㄣ€?""
    result = []
    for stocks in STOCK_POOL.values():
        for s in stocks:
            if s.startswith(market + '.'):
                result.append(s)
    return result


def get_sector_volatility_group(sector):
    """
    鑾峰彇琛屼笟鐨勬尝鍔ㄧ巼鍒嗙粍銆?
    鍒嗙粍瀹氫箟鍦?config.py 涓泦涓鐞?
      - HIGH_VOL_SECTORS: 绉戞妧銆佹柊鑳芥簮銆佹湁鑹层€佸啗宸ャ€佹苯杞?      - LOW_VOL_SECTORS:  閲戣瀺銆佸叕鐢ㄤ簨涓氥€佹秷璐?
    杩斿洖:
        str: 'high' | 'medium' | 'low'
    """
    try:
        import config
        if sector in config.HIGH_VOL_SECTORS:
            return 'high'
        if sector in config.LOW_VOL_SECTORS:
            return 'low'
    except ImportError:
        pass
    return 'medium'


# =============================================================================
# 娴嬭瘯
# =============================================================================

if __name__ == '__main__':
    syms = get_all_symbols()
    sectors = get_sector_list()

    print('=' * 60)
    print('  V16 鑲＄エ姹犵粺璁?鈥?%d 鍙?/ %d 琛屼笟' % (len(syms), len(sectors)))
    print('=' * 60)

    sh = filter_by_market('SHSE')
    sz = filter_by_market('SZSE')
    print('  涓婁氦鎵€: %d 鍙?| 娣变氦鎵€: %d 鍙? % (len(sh), len(sz)))
    print('-' * 60)

    for sec in sectors:
        stocks = filter_by_sector(sec)
        grp = get_sector_volatility_group(sec)
        print('  %s (%s娉㈠姩): %d 鍙? % (sec, grp, len(stocks)))
        for s in stocks:
            print('    %s' % s)
