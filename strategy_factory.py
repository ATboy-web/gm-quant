"""
strategy_factory.py - V30.1 策略工厂 (6策略: MR/MOM/VRC/BK/DV/RT, 恢复V24 dict架构)
"""

import strategy_mr
import strategy_momentum
import strategy_vrc
import strategy_breakout
import strategy_dividend
import strategy_reversal
import sector_config
import config


class StrategyFactory:
    """策略工厂 — 为每个行业创建定制化策略实例。"""

    # 策略名 → 创建函数 映射
    _CREATORS = {
        'MR':  '_create_mr',
        'MOM': '_create_mom',
        'VRC': '_create_vrc',
        'BK':  '_create_bk',
        'DV':  '_create_dv',
        'RT':  '_create_rt',
    }

    def create_for_sector(self, sector, regime='range'):
        """
        为指定行业创建启用策略实例列表。

        Args:
            sector: 行业名称
            regime: 市场状态

        Returns:
            list of strategy objects, sorted by weight desc
        """
        cfg = sector_config.get_sector_config(sector, regime)
        strategies = []
        strategy_cfgs = cfg.get('strategies', {})

        for name, info in strategy_cfgs.items():
            if not info.get('enabled', False):
                continue

            weight = info.get('weight', 1.0)
            creator_name = self._CREATORS.get(name)
            if creator_name is None:
                continue

            creator = getattr(self, creator_name, None)
            if creator is None:
                continue

            strat = creator(cfg, weight)
            if strat is not None:
                strategies.append(strat)

        # 按权重降序
        strategies.sort(key=lambda s: s.weight, reverse=True)
        return strategies

    def create_all(self, regime='range'):
        """为所有行业创建策略映射。返回 {sector: [strategies]}"""
        result = {}
        for sector_name in sector_config.get_all_sectors():
            result[sector_name] = self.create_for_sector(sector_name, regime)
        return result

    # ==================================================================
    # 各策略创建方法（传入行业配置参数）
    # ==================================================================

    def _create_mr(self, sector_cfg, weight):
        return MRStrategyWrapper(weight, sector_cfg)

    def _create_mom(self, sector_cfg, weight):
        return MOMStrategyWrapper(weight, sector_cfg)

    def _create_vrc(self, sector_cfg, weight):
        return VRCStrategyWrapper(weight, sector_cfg)

    def _create_bk(self, sector_cfg, weight):
        return BKStrategyWrapper(weight, sector_cfg)

    def _create_dv(self, sector_cfg, weight):
        return DVStrategyWrapper(weight, sector_cfg)

    def _create_rt(self, sector_cfg, weight):
        return RTStrategyWrapper(weight, sector_cfg)


# =============================================================================
# 策略包装器 — 把行业配置注入现有策略模块
# =============================================================================

class MRStrategyWrapper:
    """均值回归策略包装器 — 注入行业差异化参数。"""
    name = 'MR'
    full_name = '均值回归'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        """使用行业配置覆盖全局 config 参数。"""
        cfg = sector_cfg or self.sector_cfg
        _saved = {}
        _overrides = {
            'RSI_BUY': cfg.get('rsi_buy', config.RSI_BUY),
            'RSI_EXIT': cfg.get('rsi_exit', config.RSI_EXIT),
            'RSI_DEEP_OVERSOLD': cfg.get('rsi_deep_oversold', config.RSI_DEEP_OVERSOLD),
            'ATR_STOP_MULT': cfg.get('atr_stop_mult', config.ATR_STOP_MULT),
            'ATR_TRAIL_MULT': cfg.get('atr_trail_mult', config.ATR_TRAIL_MULT),
            'STOP_LOSS_CAP': cfg.get('stop_loss_cap', config.STOP_LOSS_CAP),
            'ENTRY_THRESHOLD': cfg.get('entry_threshold', config.ENTRY_THRESHOLD),
            'VOL_SURGE_MIN': cfg.get('vol_surge_min', config.VOL_SURGE_MIN),
            'TIME_STOP_DAYS': cfg.get('time_stop_days', config.TIME_STOP_DAYS),
        }
        for k, v in _overrides.items():
            _saved[k] = getattr(config, k, None)
            setattr(config, k, v)

        try:
            result = strategy_mr.get_signal(df, sector, sector_momentum, regime)
        finally:
            for k, v in _saved.items():
                if v is not None:
                    setattr(config, k, v)
        return result

    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        cfg = sector_cfg or self.sector_cfg
        _saved = {}
        _overrides = {
            'RSI_EXIT': cfg.get('rsi_exit', config.RSI_EXIT),
            'ATR_STOP_MULT': cfg.get('atr_stop_mult', config.ATR_STOP_MULT),
            'ATR_TRAIL_MULT': cfg.get('atr_trail_mult', config.ATR_TRAIL_MULT),
            'STOP_LOSS_CAP': cfg.get('stop_loss_cap', config.STOP_LOSS_CAP),
            'TIME_STOP_DAYS': cfg.get('time_stop_days', config.TIME_STOP_DAYS),
        }
        for k, v in _overrides.items():
            _saved[k] = getattr(config, k, None)
            setattr(config, k, v)

        try:
            result = strategy_mr.check_exit(df, pos_info, regime, context, today_str=today_str)
        finally:
            for k, v in _saved.items():
                if v is not None:
                    setattr(config, k, v)
        return result


class MOMStrategyWrapper:
    """动量趋势策略包装器。"""
    name = 'MOM'
    full_name = '动量趋势'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        cfg = sector_cfg or self.sector_cfg
        _saved = {}
        _overrides = {
            'VOL_SURGE_MIN': cfg.get('vol_surge_min', config.VOL_SURGE_MIN),
        }
        for k, v in _overrides.items():
            _saved[k] = getattr(config, k, None)
            setattr(config, k, v)
        try:
            return strategy_momentum.get_signal(df, sector, sector_momentum, regime)
        finally:
            for k, v in _saved.items():
                if v is not None:
                    setattr(config, k, v)

    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        cfg = sector_cfg or self.sector_cfg
        # 动量策略使用行业特定的止损止盈参数
        stop_loss = cfg.get('mom_stop_loss', 0.06)
        take_profit = cfg.get('mom_take_profit', 0.15)

        import strategy_momentum as sm
        _saved_stop = sm.MOM_STOP_LOSS
        _saved_tp = sm.MOM_TAKE_PROFIT
        sm.MOM_STOP_LOSS = stop_loss
        sm.MOM_TAKE_PROFIT = take_profit

        try:
            return sm.check_exit(df, pos_info, regime, context)
        finally:
            sm.MOM_STOP_LOSS = _saved_stop
            sm.MOM_TAKE_PROFIT = _saved_tp


class VRCStrategyWrapper:
    """成交量反转确认策略包装器 — 注入行业差异化参数。"""
    name = 'VRC'
    full_name = '量价反转确认'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        cfg = sector_cfg or self.sector_cfg
        import strategy_vrc as svrc

        _saved = {}
        _overrides = {
            'VRC_DECLINE_MIN': cfg.get('vrc_decline_min', svrc.VRC_DECLINE_MIN),
            'VRC_VOL_SURGE': cfg.get('vrc_vol_surge', svrc.VRC_VOL_SURGE),
            'VRC_SCORE_MIN': cfg.get('vrc_score_min', svrc.VRC_SCORE_MIN),
            'VRC_STOP_LOSS': cfg.get('vrc_stop_loss', svrc.VRC_STOP_LOSS),
            'VRC_TIME_STOP': cfg.get('vrc_time_stop', svrc.VRC_TIME_STOP),
            'VRC_TAKE_PROFIT': cfg.get('vrc_take_profit', svrc.VRC_TAKE_PROFIT),
            'VRC_TRAIL_PROFIT': cfg.get('vrc_trail_profit', svrc.VRC_TRAIL_PROFIT),
        }
        for k, v in _overrides.items():
            _saved[k] = getattr(svrc, k, None)
            setattr(svrc, k, v)

        try:
            return svrc.get_signal(df, sector, sector_momentum, regime)
        finally:
            for k, v in _saved.items():
                if v is not None:
                    setattr(svrc, k, v)

    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        cfg = sector_cfg or self.sector_cfg
        import strategy_vrc as svrc

        _saved = {}
        _overrides = {
            'VRC_STOP_LOSS': cfg.get('vrc_stop_loss', svrc.VRC_STOP_LOSS),
            'VRC_TIME_STOP': cfg.get('vrc_time_stop', svrc.VRC_TIME_STOP),
            'VRC_TAKE_PROFIT': cfg.get('vrc_take_profit', svrc.VRC_TAKE_PROFIT),
            'VRC_TRAIL_PROFIT': cfg.get('vrc_trail_profit', svrc.VRC_TRAIL_PROFIT),
        }
        for k, v in _overrides.items():
            _saved[k] = getattr(svrc, k, None)
            setattr(svrc, k, v)

        try:
            return svrc.check_exit(df, pos_info, regime, context)
        finally:
            for k, v in _saved.items():
                if v is not None:
                    setattr(svrc, k, v)


class BKStrategyWrapper:
    """突破策略包装器。"""
    name = 'BK'
    full_name = '突破策略'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        cfg = sector_cfg or self.sector_cfg
        import strategy_breakout as sbk
        _saved = {}
        _overrides = {
            'VOL_SURGE_MIN': cfg.get('vol_surge_min', config.VOL_SURGE_MIN),
        }
        for k, v in _overrides.items():
            _saved[k] = getattr(config, k, None)
            setattr(config, k, v)
        try:
            return sbk.get_signal(df, sector, sector_momentum, regime)
        finally:
            for k, v in _saved.items():
                if v is not None:
                    setattr(config, k, v)

    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        import strategy_breakout as sbk
        return sbk.check_exit(df, pos_info, regime, context, today_str=today_str)


class DVStrategyWrapper:
    """红利策略包装器。"""
    name = 'DV'
    full_name = '红利策略'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        import strategy_dividend as sdv
        return sdv.get_signal(df, sector, sector_momentum, regime)

    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        import strategy_dividend as sdv
        return sdv.check_exit(df, pos_info, regime, context, today_str=today_str)


class RTStrategyWrapper:
    """反转确认策略包装器。"""
    name = 'RT'
    full_name = '反转确认'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        import strategy_reversal as srt
        return srt.get_signal(df, sector, sector_momentum, regime)

    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        import strategy_reversal as srt
        return srt.check_exit(df, pos_info, regime, context, today_str=today_str)
