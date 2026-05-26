"""
strategy_factory.py - V29.8 (VRC replaces VP)
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
    _CREATORS = ["MR", "MOM", "VRC", "BK", "DV", "RT"]

    def create_for_sector(self, sector_name, regime="range"):
        cfg = sector_config.get_sector_config(sector_name)
        if cfg is None:
            cfg = sector_config.get_default_config()
        strategies_cfg = cfg.get("strategies", {})
        instances = []
        for name in self._CREATORS:
            if name in strategies_cfg:
                info = strategies_cfg[name]
                if not info.get("enabled", False):
                    continue
                w = info.get("weight", 1.0)
                if name == "MR":
                    instances.append(MRStrategyWrapper(w, cfg))
                elif name == "MOM":
                    instances.append(MOMStrategyWrapper(w, cfg))
                elif name == "VRC":
                    instances.append(VRCStrategyWrapper(w, cfg))
                elif name == "BK":
                    instances.append(BKStrategyWrapper(w, cfg))
                elif name == "DV":
                    instances.append(DVStrategyWrapper(w, cfg))
                elif name == "RT":
                    instances.append(RTStrategyWrapper(w, cfg))
        return instances


class MRStrategyWrapper:
    name = "MR"
    def __init__(self, weight, sector_cfg):
        self.weight = weight; self.sector_cfg = sector_cfg
    def get_signal(self, df, sector=None, sector_momentum=None, regime="range", sector_cfg=None):
        return strategy_mr.get_signal(df, sector, sector_momentum, regime)
    def check_exit(self, df, pos_info, regime="range", context=None, sector_cfg=None, today_str=None):
        return strategy_mr.check_exit(df, pos_info, regime, context)


class MOMStrategyWrapper:
    name = "MOM"
    def __init__(self, weight, sector_cfg):
        self.weight = weight; self.sector_cfg = sector_cfg
    def get_signal(self, df, sector=None, sector_momentum=None, regime="range", sector_cfg=None):
        return strategy_momentum.get_signal(df, sector, sector_momentum, regime)
    def check_exit(self, df, pos_info, regime="range", context=None, sector_cfg=None, today_str=None):
        return strategy_momentum.check_exit(df, pos_info, regime, context)


class VRCStrategyWrapper:
    name = "VRC"
    def __init__(self, weight, sector_cfg):
        self.weight = weight; self.sector_cfg = sector_cfg
    def get_signal(self, df, sector=None, sector_momentum=None, regime="range", sector_cfg=None):
        if not config.STRATEGY_VRC_ENABLED:
            return None
        return strategy_vrc.get_signal(df, sector, sector_momentum, regime)
    def check_exit(self, df, pos_info, regime="range", context=None, sector_cfg=None, today_str=None):
        return strategy_vrc.check_exit(df, pos_info, regime, context)


class BKStrategyWrapper:
    name = "BK"
    def __init__(self, weight, sector_cfg):
        self.weight = weight; self.sector_cfg = sector_cfg
    def get_signal(self, df, sector=None, sector_momentum=None, regime="range", sector_cfg=None):
        return strategy_breakout.get_signal(df, sector, sector_momentum, regime)
    def check_exit(self, df, pos_info, regime="range", context=None, sector_cfg=None, today_str=None):
        return strategy_breakout.check_exit(df, pos_info, regime, context)


class DVStrategyWrapper:
    name = "DV"
    def __init__(self, weight, sector_cfg):
        self.weight = weight; self.sector_cfg = sector_cfg
    def get_signal(self, df, sector=None, sector_momentum=None, regime="range", sector_cfg=None):
        return strategy_dividend.get_signal(df, sector, sector_momentum, regime)
    def check_exit(self, df, pos_info, regime="range", context=None, sector_cfg=None, today_str=None):
        return strategy_dividend.check_exit(df, pos_info, regime, context)


class RTStrategyWrapper:
    name = "RT"
    def __init__(self, weight, sector_cfg):
        self.weight = weight; self.sector_cfg = sector_cfg
    def get_signal(self, df, sector=None, sector_momentum=None, regime="range", sector_cfg=None):
        return strategy_reversal.get_signal(df, sector, sector_momentum, regime)
    def check_exit(self, df, pos_info, regime="range", context=None, sector_cfg=None, today_str=None):
        return strategy_reversal.check_exit(df, pos_info, regime, context)