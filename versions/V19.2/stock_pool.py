"""
stock_pool.py - 股票池管理模块 (V16 扩展版)

提供 35 只精选主板股票的候选池，覆盖 12 个行业。
配合 screener.py 的每日打分，策略从候选池中自动选出最优标的。

选股标准:
  1. 仅限主板（SHSE 600/601/603，SZSE 000/001/002）
     排除创业板(30xxxx)和科创板(688xxx)
  2. 行业龙头或细分优质标的
  3. 日均成交额 > 1 亿（流动性过滤）
  4. 上市时间早于 2024-01-01
  5. 行业分散，覆盖 12 个主要板块

使用方法:
    import stock_pool
    symbols = stock_pool.get_all_symbols()        # 全部候选
    sym_sec = stock_pool.get_symbol_sector_map()  # 符号→行业映射
    tech    = stock_pool.filter_by_sector('科技')  # 按行业筛选
"""

# =============================================================================
# 股票池: 35 只 × 12 行业
# =============================================================================

STOCK_POOL = {
    # ---- 金融（银行、保险）— 低波动 ----
    '金融': [
        'SHSE.600036',   # 招商银行
        'SHSE.601318',   # 中国平安
        'SHSE.601166',   # 兴业银行
    ],

    # ---- 消费（食品饮料、家电）— 低波动 ----
    '消费': [
        'SHSE.600887',   # 伊利股份
        'SZSE.000858',   # 五粮液
        'SHSE.603288',   # 海天味业
    ],

    # ---- 医药 — 中波动 ----
    '医药': [
        'SHSE.600276',   # 恒瑞医药
        'SZSE.000538',   # 云南白药
        'SHSE.600436',   # 片仔癀
    ],

    # ---- 科技（安防、AI、通信）— 高波动 ----
    '科技': [
        'SZSE.002415',   # 海康威视
        'SZSE.002230',   # 科大讯飞
        'SZSE.000063',   # 中兴通讯
    ],

    # ---- 新能源（光伏、风电）— 高波动 ----
    '新能源': [
        'SHSE.601012',   # 隆基绿能
        'SHSE.600438',   # 通威股份
        'SHSE.600089',   # 特变电工
    ],

    # ---- 制造（工程机械、家电）— 中波动 ----
    '制造': [
        'SHSE.600031',   # 三一重工
        'SZSE.000333',   # 美的集团
        'SZSE.000651',   # 格力电器
    ],

    # ---- 有色（黄金、铜、铝、钼）— 高波动 ----
    '有色': [
        'SHSE.601899',   # 紫金矿业
        'SHSE.603993',   # 洛阳钼业
        'SHSE.600362',   # 江西铜业
    ],

    # ---- 汽车（整车、零部件）— 中波动 ----
    '汽车': [
        'SZSE.002594',   # 比亚迪
        'SHSE.600104',   # 上汽集团
        'SHSE.601633',   # 长城汽车
    ],

    # ---- 化工 — 中波动 ----
    '化工': [
        'SHSE.600309',   # 万华化学
        'SHSE.600426',   # 华鲁恒升
        'SHSE.600346',   # 恒力石化
    ],

    # ---- 公用事业（电力）— 低波动 ----
    '公用事业': [
        'SHSE.600900',   # 长江电力
        'SHSE.601985',   # 中国核电
        'SHSE.600886',   # 国投电力
    ],

    # ---- 军工 — 高波动 ----
    '军工': [
        'SHSE.600760',   # 中航沈飞
        'SHSE.600150',   # 中国船舶
        'SHSE.600893',   # 航发动力
    ],

    # ---- 煤炭 — 中波动 ----
    '煤炭': [
        'SHSE.601088',   # 中国神华
        'SHSE.601225',   # 陕西煤业
    ],
}


# =============================================================================
# 公开接口
# =============================================================================

def get_all_symbols():
    """获取全部候选股票代码列表。"""
    symbols = []
    for stocks in STOCK_POOL.values():
        symbols.extend(stocks)
    return symbols


def get_symbol_sector_map():
    """获取股票代码 → 行业名称的映射字典。"""
    sym_sec = {}
    for sector, stocks in STOCK_POOL.items():
        for s in stocks:
            sym_sec[s] = sector
    return sym_sec


def get_sector_list():
    """获取所有行业名称列表。"""
    return list(STOCK_POOL.keys())


def filter_by_sector(sector):
    """按行业筛选股票。"""
    return STOCK_POOL.get(sector, [])


def filter_by_market(market='SHSE'):
    """按交易所筛选股票。"""
    result = []
    for stocks in STOCK_POOL.values():
        for s in stocks:
            if s.startswith(market + '.'):
                result.append(s)
    return result


def get_sector_volatility_group(sector):
    """
    获取行业的波动率分组。

    分组定义在 config.py 中集中管理:
      - HIGH_VOL_SECTORS: 科技、新能源、有色、军工、汽车
      - LOW_VOL_SECTORS:  金融、公用事业、消费

    返回:
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
# 测试
# =============================================================================

if __name__ == '__main__':
    syms = get_all_symbols()
    sectors = get_sector_list()

    print('=' * 60)
    print('  V16 股票池统计 — %d 只 / %d 行业' % (len(syms), len(sectors)))
    print('=' * 60)

    sh = filter_by_market('SHSE')
    sz = filter_by_market('SZSE')
    print('  上交所: %d 只 | 深交所: %d 只' % (len(sh), len(sz)))
    print('-' * 60)

    for sec in sectors:
        stocks = filter_by_sector(sec)
        grp = get_sector_volatility_group(sec)
        print('  %s (%s波动): %d 只' % (sec, grp, len(stocks)))
        for s in stocks:
            print('    %s' % s)
