"""
sector_config.py - V19.2 行业差异化策略配置

V19.2 改进:
  1. 新增突破策略(BK)和红利策略(DV)
  2. 新能源/公用事业参数大幅优化
  3. 高波动行业(有色/科技/军工/新能源)添加BK策略
  4. 低波动行业(金融/消费/煤炭/公用事业)添加DV策略

V19 核心改进:
  不同行业拥有不同的波动特性、周期属性和资金偏好，
  因此每个行业应该有独立的策略参数配置，而非一套参数走天下。

配置维度:
  1. 策略组合: 哪些策略对该行业有效，各自权重
  2. RSI 参数: 买入/出场/极度超卖阈值
  3. ATR 参数: 止损/止盈倍数
  4. 仓位参数: 单只占比、最大持仓
  5. 时间参数: 持仓周期上限
  6. 行业特征: 波动率分组、周期性、适合策略描述

V19.1 调优:
  - 时间止损放宽（10d→15d / 12d→18d 等），给反弹更多时间
  - ATR 止损门槛提高（3.0%→4.0%），避免正常波动触发止损
  - MOM 跌破MA20 改为连续2天确认

使用方法:
    import sector_config
    cfg = sector_config.get_sector_config('金融')
    # cfg = {'rsi_buy': 32, 'strategies': ['MR', 'VP'], ...}
"""

# =============================================================================
# 行业策略配置表
# =============================================================================

SECTOR_CONFIGS = {
    # ==================================================================
    # 金融（银行、保险）— 低波动、防御性、均值回归为主
    # ==================================================================
    '金融': {
        'vol_group': 'low',
        'cycle_type': 'defensive',
        'description': '低波动防御，RSI反弹确定性高，红利加持',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 3.0},
            'DV':  {'enabled': True,  'weight': 1.5},    # V19.2: 新增红利
            'VP':  {'enabled': True,  'weight': 1.0},    # V19.2: 1.5→1.0
            'MOM': {'enabled': True,  'weight': 0.5},
        },
        'rsi_buy': 32,
        'rsi_exit': 75,
        'rsi_deep_oversold': 20,
        'atr_stop_mult': 1.5,       # V19.1: 1.2→1.5 放宽
        'atr_trail_mult': 2.5,      # V19.1: 2.0→2.5
        'stop_loss_cap': 0.07,      # V19.1: 0.06→0.07
        'position_pct': 0.30,
        'time_stop_days': 15,       # V19.1: 12→15
        'entry_threshold': 0.30,
        'vol_surge_min': 1.1,
        'vp_vol_decline': 0.70,
        'mom_stop_loss': 0.06,      # V19.1: 0.05→0.06
        'mom_take_profit': 0.12,
    },

    # ==================================================================
    # 消费（食品饮料、家电）— 低波动、防御性
    # ==================================================================
    '消费': {
        'vol_group': 'low',
        'cycle_type': 'defensive',
        'description': '消费白马超卖反弹可靠，红利加持',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 3.0},
            'DV':  {'enabled': True,  'weight': 1.5},    # V19.2: 新增红利
            'VP':  {'enabled': True,  'weight': 1.0},    # V19.2: 1.5→1.0
            'MOM': {'enabled': True,  'weight': 0.5},
        },
        'rsi_buy': 32,
        'rsi_exit': 75,
        'rsi_deep_oversold': 20,
        'atr_stop_mult': 1.5,
        'atr_trail_mult': 2.5,
        'stop_loss_cap': 0.07,
        'position_pct': 0.30,
        'time_stop_days': 18,       # V19.1: 15→18
        'entry_threshold': 0.30,
        'vol_surge_min': 1.1,
        'vp_vol_decline': 0.70,
        'mom_stop_loss': 0.06,
        'mom_take_profit': 0.12,
    },

    # ==================================================================
    # 医药 — 中波动、防御性+成长性
    # ==================================================================
    '医药': {
        'vol_group': 'medium',
        'cycle_type': 'defensive',
        'description': '政策敏感，MR+VP双重确认',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 2.5},
            'VP':  {'enabled': True,  'weight': 2.0},
            'MOM': {'enabled': True,  'weight': 0.5},
        },
        'rsi_buy': 30,
        'rsi_exit': 78,
        'rsi_deep_oversold': 18,
        'atr_stop_mult': 1.8,       # V19.1: 1.5→1.8
        'atr_trail_mult': 2.5,
        'stop_loss_cap': 0.08,      # V19.1: 0.07→0.08
        'position_pct': 0.25,
        'time_stop_days': 18,       # V19.1: 15→18
        'entry_threshold': 0.35,
        'vol_surge_min': 1.2,
        'vp_vol_decline': 0.65,
        'mom_stop_loss': 0.07,
        'mom_take_profit': 0.15,
    },

    # ==================================================================
    # 科技（安防、AI、通信）— 高波动、成长性
    # ==================================================================
    '科技': {
        'vol_group': 'high',
        'cycle_type': 'growth',
        'description': '趋势性强，MOM+突破权重高，RSI需收紧',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 2.0},
            'MOM': {'enabled': True,  'weight': 2.0},
            'BK':  {'enabled': True,  'weight': 1.5},    # V19.2: 新增突破
            'VP':  {'enabled': True,  'weight': 1.0},
        },
        'rsi_buy': 28,
        'rsi_exit': 82,
        'rsi_deep_oversold': 18,
        'atr_stop_mult': 2.0,       # V19.1: 1.8→2.0
        'atr_trail_mult': 3.0,
        'stop_loss_cap': 0.10,
        'position_pct': 0.20,
        'time_stop_days': 15,       # V19.1: 10→15
        'entry_threshold': 0.35,
        'vol_surge_min': 1.3,
        'vp_vol_decline': 0.60,
        'mom_stop_loss': 0.08,
        'mom_take_profit': 0.18,
    },

    # ==================================================================
    # 新能源（光伏、风电）— 高波动、强周期
    # V19.2: 大幅放宽止损+持仓，降低MR权重，避免过早止损导致反复小亏
    # ==================================================================
    '新能源': {
        'vol_group': 'high',
        'cycle_type': 'cyclical',
        'description': '景气周期波动大，VP量价背离为主+MR辅助',
        'strategies': {
            'VP':  {'enabled': True,  'weight': 2.5},    # V19.2: VP升为主导
            'MR':  {'enabled': True,  'weight': 1.5},    # V19.2: MR降权(2.0→1.5)
            'MOM': {'enabled': True,  'weight': 0.8},
            'BK':  {'enabled': True,  'weight': 1.0},    # V19.2: 新增突破策略
        },
        'rsi_buy': 30,           # V19.2: 28→30 稍放宽（避免接更深的飞刀）
        'rsi_exit': 78,          # V19.2: 80→78 稍收紧止盈
        'rsi_deep_oversold': 18,
        'atr_stop_mult': 2.5,    # V19.1: 2.0→2.5 大幅放宽止损
        'atr_trail_mult': 3.5,   # V19.1: 2.8→3.5 让利润跑更远
        'stop_loss_cap': 0.12,   # V19.1: 0.10→0.12 提高止损上限
        'position_pct': 0.18,    # V19.2: 0.20→0.18 略降仓位
        'time_stop_days': 22,    # V19.2: 15→22 给强周期更多修复时间
        'entry_threshold': 0.38, # V19.2: 0.35→0.38 提高门槛减少误入
        'vol_surge_min': 1.3,
        'vp_vol_decline': 0.60,
        'mom_stop_loss': 0.10,   # V19.2: 0.08→0.10
        'mom_take_profit': 0.20, # V19.2: 0.15→0.20
    },

    # ==================================================================
    # 制造（工程机械、家电）— 中波动、周期性
    # ==================================================================
    '制造': {
        'vol_group': 'medium',
        'cycle_type': 'cyclical',
        'description': '经济周期驱动，MR+MOM并重',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 2.5},
            'MOM': {'enabled': True,  'weight': 1.5},
            'VP':  {'enabled': True,  'weight': 1.0},
        },
        'rsi_buy': 30,
        'rsi_exit': 78,
        'rsi_deep_oversold': 20,
        'atr_stop_mult': 1.8,       # V19.1: 1.5→1.8
        'atr_trail_mult': 2.5,
        'stop_loss_cap': 0.08,
        'position_pct': 0.25,
        'time_stop_days': 18,       # V19.1: 15→18
        'entry_threshold': 0.33,
        'vol_surge_min': 1.2,
        'vp_vol_decline': 0.65,
        'mom_stop_loss': 0.07,
        'mom_take_profit': 0.15,
    },

    # ==================================================================
    # 有色（黄金、铜、铝、钼）— 高波动、强周期
    # ==================================================================
    '有色': {
        'vol_group': 'high',
        'cycle_type': 'cyclical',
        'description': '商品周期驱动，VP+MOM+突破捕捉周期转折',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 2.0},
            'VP':  {'enabled': True,  'weight': 2.0},
            'MOM': {'enabled': True,  'weight': 1.5},
            'BK':  {'enabled': True,  'weight': 1.0},    # V19.2: 新增突破
        },
        'rsi_buy': 28,
        'rsi_exit': 80,
        'rsi_deep_oversold': 18,
        'atr_stop_mult': 2.0,       # V19.1: 1.8→2.0
        'atr_trail_mult': 2.8,
        'stop_loss_cap': 0.10,
        'position_pct': 0.20,
        'time_stop_days': 15,       # V19.1: 12→15
        'entry_threshold': 0.33,
        'vol_surge_min': 1.3,
        'vp_vol_decline': 0.60,
        'mom_stop_loss': 0.08,
        'mom_take_profit': 0.18,
    },

    # ==================================================================
    # 汽车（整车、零部件）— 中波动、周期性+政策敏感
    # ==================================================================
    '汽车': {
        'vol_group': 'medium',
        'cycle_type': 'cyclical',
        'description': '政策刺激影响大，MOM+MR结合',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 2.5},
            'MOM': {'enabled': True,  'weight': 1.5},
            'VP':  {'enabled': True,  'weight': 1.0},
        },
        'rsi_buy': 30,
        'rsi_exit': 78,
        'rsi_deep_oversold': 20,
        'atr_stop_mult': 1.8,
        'atr_trail_mult': 2.5,
        'stop_loss_cap': 0.08,
        'position_pct': 0.25,
        'time_stop_days': 15,       # V19.1: 12→15
        'entry_threshold': 0.33,
        'vol_surge_min': 1.2,
        'vp_vol_decline': 0.65,
        'mom_stop_loss': 0.07,
        'mom_take_profit': 0.15,
    },

    # ==================================================================
    # 化工 — 中波动、强周期
    # ==================================================================
    '化工': {
        'vol_group': 'medium',
        'cycle_type': 'cyclical',
        'description': '产品价格周期驱动，VP+MR结合',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 2.5},
            'VP':  {'enabled': True,  'weight': 1.5},
            'MOM': {'enabled': True,  'weight': 0.8},
        },
        'rsi_buy': 30,
        'rsi_exit': 78,
        'rsi_deep_oversold': 20,
        'atr_stop_mult': 1.8,
        'atr_trail_mult': 2.5,
        'stop_loss_cap': 0.08,
        'position_pct': 0.25,
        'time_stop_days': 18,       # V19.1: 15→18
        'entry_threshold': 0.33,
        'vol_surge_min': 1.2,
        'vp_vol_decline': 0.65,
        'mom_stop_loss': 0.07,
        'mom_take_profit': 0.15,
    },

    # ==================================================================
    # 公用事业（电力）— 低波动、防御性
    # V19.2: MR绝对主导+红利策略，拉长持仓，降低入场门槛
    # ==================================================================
    '公用事业': {
        'vol_group': 'low',
        'cycle_type': 'defensive',
        'description': '最稳定，超卖必反弹，MR+红利双驱',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 4.0},    # V19.2: 3.5→4.0 绝对主导
            'DV':  {'enabled': True,  'weight': 2.0},    # V19.2: 新增红利策略
            'VP':  {'enabled': True,  'weight': 0.5},    # V19.2: 1.0→0.5 降权
            'MOM': {'enabled': False, 'weight': 0.0},
        },
        'rsi_buy': 38,           # V19.2: 35→38 大幅放宽（公用事业超卖浅就能弹）
        'rsi_exit': 70,          # V19.2: 72→70 稍收紧
        'rsi_deep_oversold': 25, # V19.2: 22→25 公用事业极少到20以下
        'atr_stop_mult': 1.5,   # V19.2: 1.3→1.5
        'atr_trail_mult': 2.5,   # V19.2: 2.0→2.5
        'stop_loss_cap': 0.07,   # V19.2: 0.06→0.07
        'position_pct': 0.35,    # V19.2: 0.30→0.35 公用事业安全，可加大仓位
        'time_stop_days': 25,    # V19.2: 15→25 防御股修复慢，给足时间
        'entry_threshold': 0.25, # V19.2: 0.28→0.25 降低门槛（MR权重高足以过滤）
        'vol_surge_min': 1.0,
        'vp_vol_decline': 0.80,  # V19.2: 0.75→0.80 公用事业本身量就低
        'mom_stop_loss': 0.04,
        'mom_take_profit': 0.10,
    },

    # ==================================================================
    # 军工 — 高波动、政策驱动
    # ==================================================================
    '军工': {
        'vol_group': 'high',
        'cycle_type': 'growth',
        'description': '政策事件驱动，突发性强，止损要宽',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 2.0},
            'VP':  {'enabled': True,  'weight': 1.5},
            'BK':  {'enabled': True,  'weight': 1.0},    # V19.2: 新增突破
            'MOM': {'enabled': True,  'weight': 1.0},
        },
        'rsi_buy': 28,
        'rsi_exit': 82,
        'rsi_deep_oversold': 18,
        'atr_stop_mult': 2.2,       # V19.1: 2.0→2.2
        'atr_trail_mult': 3.0,
        'stop_loss_cap': 0.10,
        'position_pct': 0.20,
        'time_stop_days': 15,       # V19.1: 12→15
        'entry_threshold': 0.35,
        'vol_surge_min': 1.3,
        'vp_vol_decline': 0.60,
        'mom_stop_loss': 0.08,
        'mom_take_profit': 0.18,
    },

    # ==================================================================
    # 煤炭 — 中波动、强周期
    # ==================================================================
    '煤炭': {
        'vol_group': 'medium',
        'cycle_type': 'cyclical',
        'description': '煤价周期驱动，MR抄底+VP确认+红利',
        'strategies': {
            'MR':  {'enabled': True,  'weight': 3.0},
            'DV':  {'enabled': True,  'weight': 1.0},    # V19.2: 新增红利
            'VP':  {'enabled': True,  'weight': 1.5},
            'MOM': {'enabled': True,  'weight': 0.8},
        },
        'rsi_buy': 30,
        'rsi_exit': 78,
        'rsi_deep_oversold': 20,
        'atr_stop_mult': 1.8,       # V19.1: 1.5→1.8
        'atr_trail_mult': 2.5,
        'stop_loss_cap': 0.08,
        'position_pct': 0.25,
        'time_stop_days': 18,       # V19.1: 15→18
        'entry_threshold': 0.33,
        'vol_surge_min': 1.2,
        'vp_vol_decline': 0.65,
        'mom_stop_loss': 0.07,
        'mom_take_profit': 0.15,
    },
}

# 默认配置（未知行业兜底）
DEFAULT_CONFIG = {
    'vol_group': 'medium',
    'cycle_type': 'mixed',
    'description': '默认配置',
    'strategies': {
        'MR':  {'enabled': True,  'weight': 2.5},
        'MOM': {'enabled': True,  'weight': 1.0},
        'VP':  {'enabled': True,  'weight': 1.0},
        'BK':  {'enabled': False, 'weight': 0.0},
        'DV':  {'enabled': False, 'weight': 0.0},
    },
    'rsi_buy': 30,
    'rsi_exit': 80,
    'rsi_deep_oversold': 20,
    'atr_stop_mult': 1.8,
    'atr_trail_mult': 2.5,
    'stop_loss_cap': 0.08,
    'position_pct': 0.25,
    'time_stop_days': 18,
    'entry_threshold': 0.35,
    'vol_surge_min': 1.2,
    'vp_vol_decline': 0.65,
    'mom_stop_loss': 0.07,
    'mom_take_profit': 0.15,
}


# =============================================================================
# 市场状态覆盖层（叠加在行业配置之上）
# =============================================================================

REGIME_OVERRIDE = {
    'bull': {
        'position_multiplier': 1.2,
        'rsi_buy_adjust': 2,
        'entry_threshold_adjust': -0.05,
    },
    'range': {
        'position_multiplier': 1.0,
        'rsi_buy_adjust': 0,
        'entry_threshold_adjust': 0.0,
    },
    'bear': {
        'position_multiplier': 0.7,
        'rsi_buy_adjust': -3,
        'entry_threshold_adjust': 0.10,
    },
}


# =============================================================================
# 公开接口
# =============================================================================

def get_sector_config(sector, regime='range'):
    """获取行业配置，叠加市场状态调整。"""
    cfg = SECTOR_CONFIGS.get(sector, DEFAULT_CONFIG).copy()
    override = REGIME_OVERRIDE.get(regime, REGIME_OVERRIDE['range'])
    cfg['rsi_buy'] = cfg.get('rsi_buy', 30) + override.get('rsi_buy_adjust', 0)
    cfg['entry_threshold'] = cfg.get('entry_threshold', 0.35) + override.get('entry_threshold_adjust', 0)
    cfg['position_pct'] = cfg.get('position_pct', 0.25) * override.get('position_multiplier', 1.0)
    return cfg


def get_strategy_weight(sector, strategy_name, regime='range'):
    """获取某策略在某行业+市场状态下的权重。"""
    cfg = get_sector_config(sector, regime)
    strategies = cfg.get('strategies', {})
    return strategies.get(strategy_name, {}).get('weight', 0.0)


def is_strategy_enabled(sector, strategy_name, regime='range'):
    """判断某策略在某行业+市场状态下是否启用。"""
    cfg = get_sector_config(sector, regime)
    strategies = cfg.get('strategies', {})
    return strategies.get(strategy_name, {}).get('enabled', False)


def get_sector_strategies(sector, regime='range'):
    """获取某行业在当前市场状态下启用的策略列表。"""
    cfg = get_sector_config(sector, regime)
    strategies = cfg.get('strategies', {})
    return [name for name, info in strategies.items() if info.get('enabled', False)]


def get_all_sectors():
    """获取所有配置了策略的行业列表。"""
    return list(SECTOR_CONFIGS.keys())


def print_summary():
    print('=' * 70)
    print('  V19.2 行业差异化策略配置 — %d 个行业' % len(SECTOR_CONFIGS))
    print('=' * 70)
    for sector, cfg in SECTOR_CONFIGS.items():
        enabled = [n for n, i in cfg['strategies'].items() if i['enabled']]
        weights = {n: i['weight'] for n, i in cfg['strategies'].items() if i['enabled']}
        print('  %-6s | %s | %s | RSI<%d | ATR×%.1f | 仓%.0f%% | 止损%.0f%% | 时间%dd | 策略: %s'
              % (sector, cfg['vol_group'][:3], cfg['cycle_type'][:4],
                 cfg['rsi_buy'], cfg['atr_stop_mult'],
                 cfg['position_pct'] * 100, cfg['stop_loss_cap'] * 100,
                 cfg['time_stop_days'],
                 '+'.join('%s(%.1f)' % (n, w) for n, w in weights.items())))
    print('-' * 70)
    print('  市场状态叠加:')
    for regime, ov in REGIME_OVERRIDE.items():
        print('    %s: RSI%+d | 门槛%+.2f | 仓位×%.1f'
              % (regime, ov['rsi_buy_adjust'],
                 ov['entry_threshold_adjust'],
                 ov['position_multiplier']))
    print('=' * 70)


if __name__ == '__main__':
    print_summary()
