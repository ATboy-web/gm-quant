"""
faction_config.py - V30.6 三大派系配置

三大派系:
  1. 保守派 (Conservative): 低频交易、严格止损、防御型策略为主
     - 目标: 年化8-15%, 回撤<8%, 胜率>55%
     - 策略: MR(40%) + DV(35%) + RT(25%)
     - 特点: RSI阈值严格、止损紧、止盈低、持仓时间短

  2. 平衡派 (Balanced): 中频交易、均衡配置
     - 目标: 年化15-25%, 回撤<12%, 胜率>48%
     - 策略: MR(25%) + MOM(20%) + VRC(15%) + BK(15%) + DV(15%) + RT(10%)
     - 特点: 六策略均衡、中等参数

  3. 激进派 (Aggressive): 高频交易、追涨杀跌、动量策略为主
     - 目标: 年化25%+, 回撤<18%, 胜率>42%
     - 策略: MOM(35%) + BK(30%) + VRC(20%) + MR(15%)
     - 特点: 放宽入场、追突破、容忍更大回撤
"""

# 派系列表
FACTIONS = ['conservative', 'balanced', 'aggressive']
FACTION_NAMES = {
    'conservative': '保守派',
    'balanced': '平衡派',
    'aggressive': '激进派',
}


def get_faction_config(faction='balanced'):
    """
    获取指定派系的完整配置。

    Returns:
        dict: 包含所有策略参数的配置字典
    """
    configs = {
        'conservative': _conservative_config(),
        'balanced': _balanced_config(),
        'aggressive': _aggressive_config(),
    }
    return configs.get(faction, configs['balanced'])


def _conservative_config():
    """保守派配置 — 低频、严格、防御型"""
    return {
        'name': '保守派',
        'description': '低频交易、严格止损、防御型策略为主',

        # 全局参数
        'max_positions': 3,           # 最多3只持仓
        'position_pct': 0.10,         # V30.6: 12%→10% 降低单只仓位
        'entry_threshold': 0.65,      # V30.6: 0.60→0.65 入场更严格
        'cooldown_days': 5,           # V30.6: 3→5 冷却期更长
        'time_stop_days': 8,          # V30.6: 10→8 时间止损更紧

        # 止损止盈
        'stop_loss_cap': 0.04,        # V30.6: 5%→4% 止损更紧
        'atr_stop_mult': 1.0,         # V30.6: 1.2→1.0 ATR止损更紧
        'atr_trail_mult': 1.8,        # V30.6: 2.0→1.8 跟踪止盈更紧

        # RSI参数
        'rsi_buy': 22,                # V30.6: 25→22 RSI更严格
        'rsi_exit': 70,               # V30.6: 75→70 提前出场
        'rsi_deep_oversold': 15,      # V30.6: 18→15

        # 策略开关和权重
        'strategies': {
            'MR':  {'enabled': True,  'weight': 1.5},
            'MOM': {'enabled': False, 'weight': 0.0},
            'VRC': {'enabled': True,  'weight': 0.5},   # V30.6: 0.6→0.5
            'BK':  {'enabled': False, 'weight': 0.0},
            'DV':  {'enabled': True,  'weight': 1.2},
            'RT':  {'enabled': True,  'weight': 0.6},   # V30.6: 0.8→0.6
        },

        # 行业限制
        'forbidden_sectors': [],
        'preferred_sectors': ['金融', '公用事业', '消费', '煤炭'],

        # 风控
        'max_drawdown_limit': 0.06,   # V30.6: 8%→6% 更严格
        'daily_loss_limit': 0.02,     # V30.6: 3%→2% 更严格
        'consecutive_loss_limit': 2,  # V30.6: 3→2 更敏感

        # 高级指标
        'use_supertrend': True,
        'use_ichimoku': True,
        'supertrend_mult': 2.0,       # V30.6: 2.5→2.0 更紧
    }


def _balanced_config():
    """平衡派配置 — 六策略均衡"""
    return {
        'name': '平衡派',
        'description': '六策略均衡配置，攻守兼备',

        # 全局参数
        'max_positions': 4,           # V30.6: 5→4 降低持仓数
        'position_pct': 0.15,         # V30.6: 18%→15% 降低单只仓位
        'entry_threshold': 0.55,      # V30.6: 0.50→0.55 入场更严格
        'cooldown_days': 2,           # V30.6: 1→2 冷却期更长
        'time_stop_days': 12,         # V30.6: 14→12 时间止损更紧

        # 止损止盈
        'stop_loss_cap': 0.06,        # V30.6: 8%→6% 止损更紧
        'atr_stop_mult': 1.3,         # V30.6: 1.5→1.3 ATR止损更紧
        'atr_trail_mult': 2.0,        # V30.6: 2.5→2.0 跟踪止盈更紧

        # RSI参数
        'rsi_buy': 26,                # V30.6: 29→26 RSI更严格
        'rsi_exit': 75,               # V30.6: 80→75 提前出场
        'rsi_deep_oversold': 20,      # V30.6: 22→20

        # 策略开关和权重
        'strategies': {
            'MR':  {'enabled': True, 'weight': 1.0},    # V30.6: 1.2->1.0
            'MOM': {'enabled': True, 'weight': 1.0},    # V30.6: 0.6->1.0, 恢复
            'VRC': {'enabled': True, 'weight': 0.8},    # V30.6: 0.7->0.8
            'BK':  {'enabled': True, 'weight': 1.2},    # V30.6: 0.6->1.2, BK是主要盈利策略
            'DV':  {'enabled': True, 'weight': 0.8},
            'RT':  {'enabled': True, 'weight': 0.6},    # V30.6: 0.5->0.6
        },

        # 行业限制
        'forbidden_sectors': [],
        'preferred_sectors': [],

        # 风控
        'max_drawdown_limit': 0.10,   # V30.6: 12%→10% 更严格
        'daily_loss_limit': 0.03,     # V30.6: 5%→3% 更严格
        'consecutive_loss_limit': 3,  # V30.6: 5→3 更敏感

        # 高级指标
        'use_supertrend': True,
        'use_ichimoku': False,
        'supertrend_mult': 2.5,       # V30.6: 3.0→2.5 更紧
    }


def _aggressive_config():
    """激进派配置 — 高频、追涨、动量主导"""
    return {
        'name': '激进派',
        'description': '高频交易、追涨杀跌、动量策略为主',

        # 全局参数
        'max_positions': 4,           # V30.6: 5→4 降低持仓数
        'position_pct': 0.18,         # V30.6: 22%→18% 降低单只仓位
        'entry_threshold': 0.45,      # V30.6: 0.40→0.45 入场更严格
        'cooldown_days': 1,           # V30.6: 0→1 加冷却期
        'time_stop_days': 15,         # V30.6: 20→15 时间止损更紧

        # 止损止盈
        'stop_loss_cap': 0.08,        # V30.6: 10%→8% 止损更紧
        'atr_stop_mult': 1.5,         # V30.6: 1.8→1.5 ATR止损更紧
        'atr_trail_mult': 2.5,        # V30.6: 3.0→2.5 跟踪止盈更紧

        # RSI参数
        'rsi_buy': 30,                # V30.6: 35→30 RSI更严格
        'rsi_exit': 80,               # V30.6: 85→80 提前出场
        'rsi_deep_oversold': 22,      # V30.6: 25→22

        # 策略开关和权重
        'strategies': {
            'MR':  {'enabled': True, 'weight': 0.6},
            'MOM': {'enabled': True, 'weight': 1.2},    # V30.6: 1.5→1.2
            'VRC': {'enabled': True, 'weight': 0.8},    # V30.6: 1.0→0.8
            'BK':  {'enabled': True, 'weight': 1.2},    # V30.6: 1.5→1.2
            'DV':  {'enabled': True, 'weight': 0.3},
            'RT':  {'enabled': True, 'weight': 0.6},    # V30.6: 0.8→0.6
        },

        # 行业限制
        'forbidden_sectors': [],
        'preferred_sectors': ['科技', '新能源', '军工', '有色'],

        # 风控
        'max_drawdown_limit': 0.15,   # V30.6: 18%→15% 更严格
        'daily_loss_limit': 0.04,     # V30.6: 6%→4% 更严格
        'consecutive_loss_limit': 4,  # V30.6: 6→4 更敏感

        # 高级指标
        'use_supertrend': True,
        'use_ichimoku': False,
        'supertrend_mult': 3.0,       # V30.6: 3.5→3.0 更紧
    }


def print_faction_summary(faction='balanced'):
    """打印派系配置摘要。"""
    cfg = get_faction_config(faction)
    print('=' * 60)
    print('  派系: %s (%s)' % (cfg['name'], faction))
    print('  %s' % cfg['description'])
    print('=' * 60)
    print('  持仓上限: %d只 | 单只仓位: %.0f%%' % (cfg['max_positions'], cfg['position_pct'] * 100))
    print('  入场门槛: %.2f | 止损: %.0f%% | 时间止损: %d天' %
          (cfg['entry_threshold'], cfg['stop_loss_cap'] * 100, cfg['time_stop_days']))
    print('  最大回撤: %.0f%% | 日亏损上限: %.0f%%' %
          (cfg['max_drawdown_limit'] * 100, cfg['daily_loss_limit'] * 100))
    print('  ---- 策略组合 ----')
    for name, info in cfg['strategies'].items():
        status = 'ON %.1fx' % info['weight'] if info['enabled'] else 'OFF'
        print('  %s: %s' % (name, status))
    if cfg['forbidden_sectors']:
        print('  禁止行业: %s' % ', '.join(cfg['forbidden_sectors']))
    if cfg['preferred_sectors']:
        print('  偏好行业: %s' % ', '.join(cfg['preferred_sectors']))
    print('=' * 60)


def get_sector_faction_override(sector, faction='balanced'):
    """
    获取特定行业在特定派系下的参数覆盖。

    Returns:
        dict: 需要覆盖的参数 (可能为空)
    """
    cfg = get_faction_config(faction)

    # 禁止行业检查
    if sector in cfg.get('forbidden_sectors', []):
        return {'enabled': False}

    # 偏好行业加权
    overrides = {}
    if sector in cfg.get('preferred_sectors', []):
        overrides['position_pct'] = cfg['position_pct'] * 1.2  # 偏好行业仓位+20%

    return overrides
