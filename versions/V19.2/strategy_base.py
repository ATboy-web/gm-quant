"""
strategy_base.py - V19 策略基类

定义所有策略的统一接口，确保策略可互换、可组合。
子类只需实现 get_signal() 和 check_exit() 两个方法。
"""

from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    """
    策略基类 — 所有策略必须继承此类并实现两个核心方法。

    属性:
        name:      策略名称缩写 (MR/MOM/VP)
        full_name: 策略全称
        weight:    策略在投票中的权重 (由 sector_config 动态设置)
    """

    name = 'BASE'
    full_name = '基类策略'

    def __init__(self, weight=1.0):
        self.weight = weight

    @abstractmethod
    def get_signal(self, df, sector=None, sector_momentum=None, regime='range', sector_cfg=None):
        """
        计算买入信号。

        Args:
            df:              DataFrame with [open, high, low, close, volume]
            sector:          行业名称
            sector_momentum: 行业动量字典
            regime:          市场状态 'bull'|'range'|'bear'
            sector_cfg:      行业差异化配置 (from sector_config.py)

        Returns:
            dict | None: {
                'action': 'BUY' | 'HOLD',
                'confidence': 0.0 ~ 1.0,
                'score': float,
                'reason': str,
            }
        """
        pass

    @abstractmethod
    def check_exit(self, df, pos_info, regime='range', context=None, sector_cfg=None, today_str=None):
        """
        检查是否应该卖出。

        Args:
            df:         DataFrame
            pos_info:   持仓信息 dict {cost, peak, entry_date, ...}
            regime:     市场状态
            context:    上下文 (可选)
            sector_cfg: 行业差异化配置
            today_str:  当前日期字符串

        Returns:
            dict: {
                'action': 'SELL' | 'HOLD',
                'confidence': 0.0 ~ 1.0,
                'reason': str,
            }
        """
        pass

    def __repr__(self):
        return '<%s(%s) weight=%.1f>' % (self.__class__.__name__, self.name, self.weight)
