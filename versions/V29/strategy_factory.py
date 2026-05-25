"""
strategy_factory.py - V29 绛栫暐宸ュ巶 (6绛栫暐: MR/MOM/VP/BK/DV/RT)
"""

import strategy_mr
import strategy_momentum
import strategy_vp
import strategy_breakout
import strategy_dividend
import strategy_reversal
import sector_config


class StrategyFactory:
    """
    绛栫暐宸ュ巶 鈥?涓烘瘡涓涓氬垱寤哄畾鍒跺寲绛栫暐瀹炰緥銆?
    """

    # 绛栫暐鍚?鈫?鍒涘缓鍑芥暟 鏄犲皠
    _CREATORS = {
        'MR':  '_create_mr',
        'MOM': '_create_mom',
        'VP':  '_create_vp',
        'BK':  '_create_bk',
        'DV':  '_create_dv',
        'RT':  '_create_rt',
    }

    def create_for_sector(self, sector, regime='range'):
        """
        涓烘寚瀹氳涓氬垱寤哄惎鐢ㄧ瓥鐣ュ疄渚嬪垪琛ㄣ€?

        Args:
            sector: 琛屼笟鍚嶇О
            regime: 甯傚満鐘舵€?

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

        # 鎸夋潈閲嶉檷搴?
        strategies.sort(key=lambda s: s.weight, reverse=True)
        return strategies

    def create_all(self, regime='range'):
        """涓烘墍鏈夎涓氬垱寤虹瓥鐣ユ槧灏勩€傝繑鍥?{sector: [strategies]}"""
        result = {}
        for sector in sector_config.get_all_sectors():
            result[sector] = self.create_for_sector(sector, regime)
        return result

    # ==================================================================
    # 鍚勭瓥鐣ュ垱寤烘柟娉曪紙浼犲叆琛屼笟閰嶇疆鍙傛暟锛?
    # ==================================================================

    def _create_mr(self, sector_cfg, weight):
        """鍒涘缓鍧囧€煎洖褰掔瓥鐣ュ疄渚嬶紝娉ㄥ叆琛屼笟鍙傛暟銆?""
        # 鐩存帴浣跨敤妯″潡绾у嚱鏁帮紝浣嗛€氳繃 wrapper 浼犻€?sector_cfg
        return MRStrategyWrapper(weight, sector_cfg)

    def _create_mom(self, sector_cfg, weight):
        """鍒涘缓鍔ㄩ噺瓒嬪娍绛栫暐瀹炰緥銆?""
        return MOMStrategyWrapper(weight, sector_cfg)

    def _create_vp(self, sector_cfg, weight):
        """鍒涘缓閲忎环鑳岀绛栫暐瀹炰緥銆?""
        return VPStrategyWrapper(weight, sector_cfg)

    def _create_bk(self, sector_cfg, weight):
        """鍒涘缓绐佺牬绛栫暐瀹炰緥銆?""
        return BKStrategyWrapper(weight, sector_cfg)

    def _create_dv(self, sector_cfg, weight):
        """鍒涘缓绾㈠埄绛栫暐瀹炰緥銆?""
        return DVStrategyWrapper(weight, sector_cfg)

    def _create_rt(self, sector_cfg, weight):
        """鍒涘缓鍙嶈浆纭绛栫暐瀹炰緥銆?""
        return RTStrategyWrapper(weight, sector_cfg)


# =============================================================================
# 绛栫暐鍖呰鍣?鈥?鎶婅涓氶厤缃敞鍏ョ幇鏈夌瓥鐣ユā鍧?
# =============================================================================

class MRStrategyWrapper:
    """鍧囧€煎洖褰掔瓥鐣ュ寘瑁呭櫒 鈥?娉ㄥ叆琛屼笟宸紓鍖栧弬鏁般€?""
    name = 'MR'
    full_name = '鍧囧€煎洖褰?

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        """浣跨敤琛屼笟閰嶇疆瑕嗙洊鍏ㄥ眬 config 鍙傛暟銆?""
        cfg = sector_cfg or self.sector_cfg
        # 涓存椂瑕嗙洊 config 鍙傛暟
        import config
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
            # 鎭㈠鍏ㄥ眬閰嶇疆
            for k, v in _saved.items():
                if v is not None:
                    setattr(config, k, v)
        return result

    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        cfg = sector_cfg or self.sector_cfg
        import config
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
    """鍔ㄩ噺瓒嬪娍绛栫暐鍖呰鍣ㄣ€?""
    name = 'MOM'
    full_name = '鍔ㄩ噺瓒嬪娍'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        cfg = sector_cfg or self.sector_cfg
        import config
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
        # 鍔ㄩ噺绛栫暐浣跨敤琛屼笟鐗瑰畾鐨勬鎹熸鐩堝弬鏁?
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


class VPStrategyWrapper:
    """閲忎环鑳岀绛栫暐鍖呰鍣ㄣ€?""
    name = 'VP'
    full_name = '閲忎环鑳岀'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        cfg = sector_cfg or self.sector_cfg
        import strategy_vp as svp
        _saved = svp.VP_VOL_DECLINE
        svp.VP_VOL_DECLINE = cfg.get('vp_vol_decline', 0.65)
        try:
            return svp.get_signal(df, sector, sector_momentum, regime)
        finally:
            svp.VP_VOL_DECLINE = _saved

    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        cfg = sector_cfg or self.sector_cfg
        import strategy_vp as svp
        _saved_stop = svp.VP_STOP_LOSS
        _saved_time = svp.VP_TIME_STOP
        _saved_tp = svp.VP_EXIT_PROFIT
        svp.VP_STOP_LOSS = cfg.get('stop_loss_cap', 0.05)
        svp.VP_TIME_STOP = cfg.get('time_stop_days', 20)
        svp.VP_EXIT_PROFIT = cfg.get('mom_take_profit', 0.08)  # 澶嶇敤
        try:
            return svp.check_exit(df, pos_info, regime, context, today_str=today_str)
        finally:
            svp.VP_STOP_LOSS = _saved_stop
            svp.VP_TIME_STOP = _saved_time
            svp.VP_EXIT_PROFIT = _saved_tp


class BKStrategyWrapper:
    """绐佺牬绛栫暐鍖呰鍣ㄣ€?""
    name = 'BK'
    full_name = '绐佺牬绛栫暐'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        cfg = sector_cfg or self.sector_cfg
        import strategy_breakout as sbk
        import config
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
    """绾㈠埄绛栫暐鍖呰鍣ㄣ€?""
    name = 'DV'
    full_name = '绾㈠埄绛栫暐'

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
    """鍙嶈浆纭绛栫暐鍖呰鍣ㄣ€?""
    name = 'RT'
    full_name = '鍙嶈浆纭'

    def __init__(self, weight, sector_cfg):
        self.weight = weight
        self.sector_cfg = sector_cfg

    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        import strategy_reversal as srt
        return srt.get_signal(df, sector, sector_momentum, regime)

    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        import strategy_reversal as srt
        return srt.check_exit(df, pos_info, regime, context, today_str=today_str)
