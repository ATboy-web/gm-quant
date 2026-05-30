"""
trade_utils.py - V30.5 交易工具集 (三合一)
交易日历 + 费用 + 滑点 + 通知
"""
from datetime import datetime, date, timedelta
import numpy as np
import os, json, urllib.request
from enum import Enum

"""
trading_calendar.py - V30.5 A股交易日历 (借鉴 ai_quant_trade)
过滤周末和法定节假日, 确保回测日期准确
"""
from datetime import datetime, date, timedelta

# 2024-2025 A股休市日期 (法定节假日+调休)
_HOLIDAYS_2024 = {
    '2024-01-01',  # 元旦
    '2024-02-09', '2024-02-12', '2024-02-13', '2024-02-14', '2024-02-15', '2024-02-16',  # 春节
    '2024-04-04', '2024-04-05',  # 清明
    '2024-05-01', '2024-05-02', '2024-05-03',  # 劳动节
    '2024-06-10',  # 端午
    '2024-09-16', '2024-09-17',  # 中秋
    '2024-10-01', '2024-10-02', '2024-10-03', '2024-10-04', '2024-10-07',  # 国庆
}

_HOLIDAYS_2025 = {
    '2025-01-01',  # 元旦
    '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31',  # 春节
    '2025-02-03', '2025-02-04',
    '2025-04-04',  # 清明
    '2025-05-01', '2025-05-02',  # 劳动节
    '2025-06-02',  # 端午补休
    '2025-10-01', '2025-10-02', '2025-10-03', '2025-10-06', '2025-10-07', '2025-10-08',  # 国庆+中秋
}

# 合并
ALL_HOLIDAYS = _HOLIDAYS_2024 | _HOLIDAYS_2025


def is_trading_day(d: date) -> bool:
    """判断是否为A股交易日 (周一至周五且非节假日)"""
    if d.weekday() >= 5:  # 周末
        return False
    return d.strftime('%Y-%m-%d') not in ALL_HOLIDAYS


def get_trading_dates(start: str, end: str) -> list:
    """
    获取区间内所有A股交易日。

    Args:
        start: '2024-01-01'
        end: '2025-05-30'

    Returns:
        list of date strings
    """
    d_start = datetime.strptime(start, '%Y-%m-%d').date()
    d_end = datetime.strptime(end, '%Y-%m-%d').date()

    dates = []
    d = d_start
    while d <= d_end:
        if is_trading_day(d):
            dates.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)
    return dates


# ============================================================
# 交易费用计算
# ============================================================

# A股费用标准 (2024)
STAMP_DUTY_RATE = 0.0005   # 印花税 0.05% (仅卖出)
COMMISSION_RATE = 0.00025  # 佣金 0.025% (买卖双向)
MIN_COMMISSION = 5.0       # 最低佣金 ¥5
TRANSFER_FEE_RATE = 0.00001  # 过户费 0.001% (买卖双向, 仅上海)


def calc_buy_fee(amount: float, market='SHSE') -> dict:
    """
    计算买入费用。

    Args:
        amount: 成交金额 (price * shares)
        market: 'SHSE' 或 'SZSE'

    Returns:
        {'commission': float, 'transfer': float, 'total': float}
    """
    commission = max(MIN_COMMISSION, amount * COMMISSION_RATE)
    transfer = amount * TRANSFER_FEE_RATE if market == 'SHSE' else 0
    return {
        'commission': round(commission, 2),
        'transfer': round(transfer, 2),
        'total': round(commission + transfer, 2)
    }


def calc_sell_fee(amount: float, market='SHSE') -> dict:
    """
    计算卖出费用。

    Args:
        amount: 成交金额 (price * shares)
        market: 'SHSE' 或 'SZSE'

    Returns:
        {'commission': float, 'stamp': float, 'transfer': float, 'total': float}
    """
    commission = max(MIN_COMMISSION, amount * COMMISSION_RATE)
    stamp = amount * STAMP_DUTY_RATE
    transfer = amount * TRANSFER_FEE_RATE if market == 'SHSE' else 0
    return {
        'commission': round(commission, 2),
        'stamp': round(stamp, 2),
        'transfer': round(transfer, 2),
        'total': round(commission + stamp + transfer, 2)
    }


def calc_net_pnl(buy_price: float, sell_price: float, shares: int, market='SHSE') -> dict:
    """
    计算扣除费用后的净盈亏。

    Returns:
        {'gross': gross pnl, 'fees': total fees, 'net': net pnl, 'net_pct': net pct}
    """
    buy_amt = buy_price * shares
    sell_amt = sell_price * shares
    buy_fee = calc_buy_fee(buy_amt, market)['total']
    sell_fee = calc_sell_fee(sell_amt, market)['total']
    total_fee = buy_fee + sell_fee
    gross = sell_amt - buy_amt
    net = gross - total_fee
    net_pct = (net / buy_amt) * 100 if buy_amt > 0 else 0
    return {
        'gross': round(gross, 2),
        'fees': round(total_fee, 2),
        'net': round(net, 2),
        'net_pct': round(net_pct, 2)
    }
"""
slippage_model.py - V30.5 滑点与涨跌停模型 (借鉴 abu SlippageBu)

A股特殊规则:
  - 涨跌停 ±10% (ST ±5%)
  - 涨停: 买入成交概率极低
  - 跌停: 卖出成交概率极低
  - 开盘价: 买入用开盘价(更接近实际成交)
"""
import numpy as np


# A股涨跌停阈值
LIMIT_UP_PCT = 0.098   # 9.8% (允许浮点误差)
LIMIT_DOWN_PCT = -0.098

# 涨停买入成交概率 (借鉴 abu: g_limit_up_deal_chance=1, 集合竞价=0.2)
LIMIT_UP_BUY_CHANCE = 0.15   # 散户追涨停成功概率很低
LIMIT_DOWN_SELL_CHANCE = 0.20  # 跌停跑路概率也很低


def check_limit_status(prev_close: float, high: float, low: float, close: float) -> dict:
    """
    检查涨跌停状态。

    Returns:
        {'limit_up': bool, 'limit_down': bool, 'can_buy': bool, 'can_sell': bool}
    """
    if prev_close <= 0:
        return {'limit_up': False, 'limit_down': False, 'can_buy': True, 'can_sell': True}

    up_pct = (high - prev_close) / prev_close
    down_pct = (low - prev_close) / prev_close

    limit_up = up_pct >= LIMIT_UP_PCT
    limit_down = down_pct <= LIMIT_DOWN_PCT

    # 涨停：集合竞价封板 vs 盘中封板
    if limit_up:
        is_pre_limit = (high == low)  # 开盘即涨停
        # V30.6: 移除随机数，改为确定性逻辑
        # 涨停时无法买入（除非是开盘即涨停且价格未触及涨停价）
        can_buy = False
    else:
        can_buy = True

    # 跌停
    if limit_down:
        # V30.6: 移除随机数，改为确定性逻辑
        # 跌停时无法卖出
        can_sell = False
    else:
        can_sell = True

    return {'limit_up': limit_up, 'limit_down': limit_down,
            'can_buy': can_buy, 'can_sell': can_sell}


def get_execution_price(open_price: float, high: float, low: float,
                        close: float, prev_close: float, side: str = 'buy') -> float:
    """
    获取滑点调整后的执行价格 (借鉴 abu 日内滑点模型)。

    买入: 用 (open + high + low + close) / 4 的均值，偏保守
    卖出: 同理，但取偏低价格

    也可直接用开盘价(更贴近实盘)
    """
    limit = check_limit_status(prev_close, high, low, close)

    if side == 'buy' and not limit['can_buy']:
        return None  # 涨停无法买入
    if side == 'sell' and not limit['can_sell']:
        return None  # 跌停无法卖出

    # 均值滑点模型
    mean_price = (open_price + high + low + close) / 4

    if side == 'buy':
        # 买入: 取开盘价和均值的较高者(偏保守)
        return max(open_price, mean_price * 0.995)
    else:
        # 卖出: 取开盘价和均值的较低者
        return min(open_price, mean_price * 1.005)


def apply_slippage(target_price: float, side: str = 'buy', slippage_pct: float = 0.001) -> float:
    """
    简单滑点模型 — 相对于目标价格。

    Args:
        target_price: 期望成交价
        side: 'buy' 或 'sell'
        slippage_pct: 滑点比例 (默认0.1%)

    Returns:
        滑点调整后的价格
    """
    if side == 'buy':
        return target_price * (1 + slippage_pct)
    else:
        return target_price * (1 - slippage_pct)
"""
trade_notify.py - V30.5 交易通知 (借鉴 Qbot larkbot/wxbot)

支持多种通知渠道:
  - 控制台日志 (默认)
  - 飞书 Webhook
  - 企业微信 Webhook
  - 邮件通知

配置: 在 config.py 或环境变量中设置
"""
import os
import json
import time
import urllib.request
from enum import Enum


class NotifyLevel(Enum):
    INFO = 'info'
    TRADE = 'trade'
    WARNING = 'warning'
    ERROR = 'error'


class TradeNotifier:
    """交易通知器"""

    def __init__(self):
        self.channels = ['console']  # 默认控制台
        self._load_config()

    def _load_config(self):
        """从环境变量加载通知配置"""
        # 飞书
        if os.environ.get('FEISHU_WEBHOOK'):
            self.channels.append('feishu')
        # 企业微信
        if os.environ.get('WECOM_WEBHOOK'):
            self.channels.append('wecom')
        # 邮件
        if os.environ.get('SMTP_HOST'):
            self.channels.append('email')

    def notify(self, message: str, level: NotifyLevel = NotifyLevel.INFO, extra: dict = None):
        """
        发送通知到所有已配置渠道。

        Args:
            message: 通知内容
            level: 级别
            extra: 额外数据 (交易详情等)
        """
        timestamp = datetime.now().strftime('%H:%M:%S')
        prefix = {'info': 'ℹ️', 'trade': '💰', 'warning': '⚠️', 'error': '❌'}.get(level.value, '📢')

        formatted = f'[{timestamp}] {prefix} {message}'
        print(formatted)  # 控制台始终输出

        if extra:
            for k, v in extra.items():
                print(f'   {k}: {v}')

        # 飞书
        if 'feishu' in self.channels:
            self._send_feishu(message, level, extra)

    def trade_buy(self, symbol: str, price: float, qty: int, strategy: str, reason: str = ''):
        """买入通知"""
        self.notify(
            f'买入 {symbol} ¥{price:.2f} × {qty}股 [{strategy}]',
            NotifyLevel.TRADE,
            {'价格': f'¥{price:.2f}', '数量': f'{qty}股', '金额': f'¥{price*qty:.0f}',
             '策略': strategy, '理由': reason[:50] if reason else ''}
        )

    def trade_sell(self, symbol: str, price: float, pnl_pct: float, strategy: str, reason: str = ''):
        """卖出通知"""
        emoji = '📈' if pnl_pct > 0 else '📉'
        self.notify(
            f'{emoji} 卖出 {symbol} ¥{price:.2f} {pnl_pct:+.2f}% [{strategy}]',
            NotifyLevel.TRADE,
            {'价格': f'¥{price:.2f}', '盈亏': f'{pnl_pct:+.2f}%', '策略': strategy,
             '理由': reason[:50] if reason else ''}
        )

    def daily_summary(self, nav: float, ret: float, positions: int, trades: int, max_dd: float):
        """每日摘要"""
        self.notify(
            f'日结 | 净值 ¥{nav:.0f} ({ret:+.1f}%) | 持仓{positions}只 | 交易{trades}笔 | 回撤{max_dd:.1f}%',
            NotifyLevel.INFO
        )

    def _send_feishu(self, message: str, level: NotifyLevel, extra: dict = None):
        webhook = os.environ.get('FEISHU_WEBHOOK', '')
        if not webhook:
            return
        content = [{'tag': 'text', 'text': message}]
        if extra:
            for k, v in extra.items():
                content.append({'tag': 'text', 'text': f'\n{k}: {v}'})
        payload = json.dumps({
            'msg_type': 'interactive',
            'card': {
                'header': {'title': {'tag': 'plain_text', 'content': 'Qbot 交易通知'}},
                'elements': content
            }
        }).encode()
        try:
            req = urllib.request.Request(webhook, data=payload, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass


# 全局单例
_notifier = None


def get_notifier() -> TradeNotifier:
    global _notifier
    if _notifier is None:
        _notifier = TradeNotifier()
    return _notifier
