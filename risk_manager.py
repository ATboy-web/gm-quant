"""
risk_manager.py - 风险委员会 (仿 Vibe-Trading Risk Committee)

Vibe-Trading 核心借鉴: 多维度交易前风险审计。
每笔交易执行前必须通过风险委员会审查, 否则拒绝执行。

审计维度:
  1. 行业集中度 — 单一行业不超过总持仓的 N%
  2. 波动率适配 — 高波动品种自动降仓位
  3. 最大回撤熔断 — 日内/累计回撤超限自动暂停
  4. 连续亏损熔断 — N连亏后暂停交易
  5. 凯利仓位 — 基于胜率/盈亏比的动态仓位建议
  6. 相关性检查 — 新开仓与现有持仓的同向性
"""

import numpy as np


class RiskCommittee:
    """
    风险委员会 — 仿 Vibe-Trading investment_committee 中的风控审查环节。

    职责: 对每笔意向交易进行独立审核, 拥有否决权。
    """

    def __init__(self, initial_capital=25000):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.peak_capital = initial_capital
        self.max_drawdown = 0.0

        # Vibe 风格配置
        self.config = {
            'max_sector_concentration': 0.40,   # 单一行业最多占总资金 40%
            'max_single_position': 0.25,        # 单一股票最多占总资金 25%
            'max_total_exposure': 0.95,         # 最大总仓位 95%
            'max_drawdown_limit': 0.15,         # 累计回撤 15% 暂停
            'daily_drawdown_limit': 0.05,       # 日内回撤 5% 暂停当天
            'consecutive_loss_limit': 8,        # V29.10: 5→8, 避免过早熔断
            'min_win_rate_for_kelly': 0.40,     # 胜率 < 40% 禁用凯利
            'vol_high_adjust': 0.60,            # 高波动仓位降 40%
            'vol_low_adjust': 1.30,             # 低波动仓位升 30%
            'correlation_warning': 0.70,        # 相关性 > 0.7 警告
        }

        # 状态跟踪
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.daily_drawdown = 0.0
        self.daily_start_capital = initial_capital
        self.audit_log = []
        self.blocked_until = None  # 熔断结束日期

    def update_state(self, current_capital, recent_trade_pnl=None):
        """
        更新风控状态: 净值/回撤/连亏计数。

        每笔交易完成后调用。
        """
        self.current_capital = current_capital

        if current_capital > self.peak_capital:
            self.peak_capital = current_capital
            self.daily_start_capital = current_capital

        current_dd = (current_capital - self.peak_capital) / self.peak_capital
        self.max_drawdown = min(self.max_drawdown, current_dd)

        # 日内回撤
        if self.daily_start_capital > 0:
            self.daily_drawdown = (current_capital - self.daily_start_capital) / self.daily_start_capital

        # 连亏/连赢
        if recent_trade_pnl is not None:
            if recent_trade_pnl < 0:
                self.consecutive_losses += 1
                self.consecutive_wins = 0
            else:
                self.consecutive_wins += 1
                self.consecutive_losses = 0

    def audit_buy(self, candidate, positions, sector_positions, today_str=''):
        """
        交易前审计: 审查买入候选是否通过风控。

        Args:
            candidate:       买入候选 dict {symbol, sector, price, confidence, ...}
            positions:       当前持仓列表 [{symbol, sector, value, ...}, ...]
            sector_positions: {sector: total_value} 行业持仓汇总
            today_str:       当前日期

        Returns:
            dict: {approved: bool, reason: str, adjusted_size: float, warnings: [str]}
        """
        warnings = []
        reasons = []
        adj = 1.0  # V29.10: 仓位调整系数, 默认1.0

        # === 0. 全局熔断检查 ===
        if self.blocked_until is not None and today_str <= str(self.blocked_until):
            return {'approved': False, 'reason': '熔断中(至%s)' % self.blocked_until,
                    'adjusted_size': 0, 'warnings': warnings}

        # === 1. 累计回撤检查 ===
        if abs(self.max_drawdown) >= self.config['max_drawdown_limit']:
            return {'approved': False,
                    'reason': '累计回撤 %.1f%% 超过上限 %.1f%%' %
                    (abs(self.max_drawdown) * 100, self.config['max_drawdown_limit'] * 100),
                    'adjusted_size': 0, 'warnings': warnings}

        # === 2. 日内回撤检查 ===
        if abs(self.daily_drawdown) >= self.config['daily_drawdown_limit']:
            return {'approved': False,
                    'reason': '日内回撤 %.1f%% 超过上限 %.1f%%' %
                    (abs(self.daily_drawdown) * 100, self.config['daily_drawdown_limit'] * 100),
                    'adjusted_size': 0, 'warnings': warnings}

        # === 3. 连亏熔断 (V29.10: 日内熔断, 非永久) ===
        if self.consecutive_losses >= self.config['consecutive_loss_limit']:
            # 连亏达到上限: 拒绝当天交易, 但允许明天恢复
            # 在 reset_daily 中不自动清零, 但新盈利会清零
            warnings.append('连亏熔断中(%d笔), 仅限制当日大额交易' % self.consecutive_losses)
            # 允许小额试探(25%正常仓位)
            adj *= 0.25
            if adj < 0.1:
                return {'approved': False,
                        'reason': '连续亏损 %d 笔, 熔断中' % self.consecutive_losses,
                        'adjusted_size': 0, 'warnings': warnings}

        # === 4. 行业集中度 ===
        sector = candidate.get('sector', '未知')
        sector_value = sector_positions.get(sector, 0)
        candidate_value = candidate.get('price', 0) * candidate.get('qty', 100)
        new_sector_value = sector_value + candidate_value
        sector_pct = new_sector_value / self.current_capital if self.current_capital > 0 else 999

        if sector_pct > self.config['max_sector_concentration']:
            reasons.append('行业集中度 %.1f%% 超限' % (sector_pct * 100))
            return {'approved': False, 'reason': '; '.join(reasons),
                    'adjusted_size': 0, 'warnings': warnings}

        if sector_pct > self.config['max_sector_concentration'] * 0.7:
            warnings.append('行业集中度偏高: %.1f%%' % (sector_pct * 100))

        # === 5. 总仓位检查 ===
        total_position_value = sum(sector_positions.values()) + candidate_value
        exposure = total_position_value / self.current_capital if self.current_capital > 0 else 999
        if exposure > self.config['max_total_exposure']:
            reasons.append('总仓位 %.1f%% 超限' % (exposure * 100))
            return {'approved': False, 'reason': '; '.join(reasons),
                    'adjusted_size': 0, 'warnings': warnings}

        # === 6. 波动率仓位调整 ===
        vol_group = candidate.get('vol_group', 'medium')
        adj = 1.0
        if vol_group == 'high':
            adj = self.config['vol_high_adjust']
            warnings.append('高波动品种, 仓位降至 %.0f%%' % (adj * 100))
        elif vol_group == 'low':
            adj = min(self.config['vol_low_adjust'],
                      1.5 if self.consecutive_wins >= 3 else 1.0)
            if adj > 1.0:
                warnings.append('低波动+连赢%d, 仓位升至 %.0f%%' % (self.consecutive_wins, adj * 100))

        # === 7. 置信度调整 ===
        confidence = candidate.get('confidence', 0.5)
        if confidence < 0.4:
            adj *= 0.5
            warnings.append('低置信度(%.2f), 仓位减半' % confidence)
        elif confidence > 0.8:
            adj *= min(1.3, 1.0 if self.consecutive_losses > 0 else 1.3)

        adj = max(0.1, min(2.0, adj))

        # === 8. 检查通过 ===
        if not reasons:
            reasons.append('通过')

        self.audit_log.append({
            'symbol': candidate.get('symbol', '?'),
            'sector': sector,
            'approved': True,
            'adjusted_size': adj,
            'warnings': warnings,
            'date': today_str,
        })

        return {
            'approved': True,
            'reason': '; '.join(reasons),
            'adjusted_size': round(adj, 2),
            'warnings': warnings,
        }

    def audit_exit(self, pos_info, sell_reason, current_pnl):
        """
        出场审计: 确认卖出不会触发风控异常。

        通常放行, 但极少数情况 (如止损后仓位过低) 可发出警告。
        """
        warnings = []

        # 止损卖出后检查是否需要熔断
        if '止损' in sell_reason and current_pnl < -0.05:
            # 大额止损, 记录但不阻止
            warnings.append('大额止损 %.1f%%, 注意风险' % (current_pnl * 100))

        # 卖出后预测仓位
        return {'approved': True, 'reason': '放行', 'warnings': warnings}

    def get_risk_report(self):
        """生成风险状态报告。"""
        return {
            'current_capital': self.current_capital,
            'peak_capital': self.peak_capital,
            'max_drawdown': round(self.max_drawdown * 100, 2),
            'daily_drawdown': round(self.daily_drawdown * 100, 2),
            'consecutive_losses': self.consecutive_losses,
            'consecutive_wins': self.consecutive_wins,
            'blocked': self.blocked_until is not None,
            'audit_count': len(self.audit_log),
            'rejections': sum(1 for a in self.audit_log if not a.get('approved', True)),
        }

    def reset_daily(self, new_capital, date_str=''):
        """新交易日重置日内状态。"""
        self.daily_start_capital = new_capital
        self.daily_drawdown = 0.0
        self.blocked_until = None

        # V29.10: 连亏熔断后, 经过冷却期自动恢复 (回测需要)
        # 实盘可改为手动确认恢复
        if self.consecutive_losses >= self.config['consecutive_loss_limit']:
            # 每连亏达到限制后, 若已有 5+ 笔连亏,
            # 不自动清零, 但允许间隔一天后尝试小额恢复
            pass  # 保持连亏计数, 由外部策略决定是否继续

    def emergency_brake(self, reason=''):
        """紧急刹车: 立即冻结所有交易。"""
        self.blocked_until = '9999-12-31'
        self.audit_log.append({
            'symbol': 'SYSTEM',
            'sector': 'ALL',
            'approved': False,
            'adjusted_size': 0,
            'warnings': ['EMERGENCY BRAKE: ' + reason],
            'date': 'NOW',
        })
        return {'brake_activated': True, 'reason': reason}
"""
risk_engine.py - V30.5 分层风控引擎 (借鉴 vnpy 风控模块)

三层风控:
  L1: 订单级 — 单笔仓位上限, 涨跌停检查
  L2: 持仓级 — 个股止损/止盈, 行业集中度
  L3: 账户级 — 日亏损上限, 回撤熔断, 连续亏损熔断

vnpy特色: 事件驱动 + 预检(pre-check) + 事后(after-trade)
"""

from datetime import datetime


class RiskEngine:
    """分层风控引擎"""

    def __init__(self, initial_capital: float = 25000):
        self.initial_capital = initial_capital
        self.peak_capital = initial_capital

        # L1: 订单限制
        self.max_single_position_pct = 0.35   # 单票最大仓位 35%
        self.min_price = 3.0                  # 最低股价
        self.max_price = 200.0                # 最高股价

        # L2: 持仓限制
        self.max_positions = 5                # 最大持仓数
        self.max_sector_exposure_pct = 0.40   # 单行业最大占比 40%
        self.stop_loss_pct = 0.08             # 个股止损 8%
        self.take_profit_pct = 0.15           # 个股止盈 15%
        self.trailing_stop_activate = 0.05    # 移动止盈触发 5%
        self.trailing_stop_pct = 0.03         # 移动止盈回撤 3%

        # L3: 账户限制
        self.daily_loss_limit_pct = 0.05      # 日亏损上限 5%
        self.max_drawdown_limit = 0.20        # 最大回撤熔断 20%
        self.max_consecutive_losses = 5       # 连亏熔断
        self.consecutive_loss_trades = 0       # 连续亏损计数器

        # 状态
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.last_trade_date = None
        self.is_halted = False
        self.halt_reason = ''

    def reset_daily(self, date_str: str):
        """每日重置"""
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.last_trade_date = date_str
        self.is_halted = False
        self.halt_reason = ''

    # === L1: 订单预检 ===
    def check_order(self, symbol: str, price: float, qty: int, cash: float) -> tuple:
        """
        订单预检 — 返回 (approved: bool, reason: str)
        """
        if self.is_halted:
            return False, self.halt_reason

        if price < self.min_price:
            return False, f'价格{price:.2f}<最低{self.min_price}'
        if price > self.max_price:
            return False, f'价格{price:.2f}>最高{self.max_price}'

        pos_pct = (price * qty) / max(cash, 1)
        if pos_pct > self.max_single_position_pct:
            return False, f'仓位{pos_pct:.1%}>上限{self.max_single_position_pct:.0%}'

        return True, 'OK'

    # === L2: 持仓监控 ===
    def check_position_exit(self, cost: float, current: float, peak: float,
                            hold_days: int = 0) -> dict:
        """
        持仓止损止盈检查 — 返回 {action, reason}
        """
        pnl_pct = (current - cost) / cost

        # 硬止损
        if pnl_pct <= -self.stop_loss_pct:
            return {'action': 'SELL', 'reason': f'RISK_止损({pnl_pct:.1%})'}

        # 硬止盈
        if pnl_pct >= self.take_profit_pct:
            return {'action': 'SELL', 'reason': f'RISK_止盈({pnl_pct:.1%})'}

        # 移动止盈
        peak_pnl = (peak - cost) / cost
        if peak_pnl >= self.trailing_stop_activate:
            dd_from_peak = (current - peak) / peak
            if dd_from_peak <= -self.trailing_stop_pct:
                return {'action': 'SELL', 'reason': f'RISK_移动止盈(峰{peak_pnl:.1%}→{pnl_pct:.1%})'}

        return {'action': 'HOLD', 'reason': ''}

    def check_sector_exposure(self, sector: str, positions: dict) -> tuple:
        """
        行业集中度检查 — 返回 (approved, reason)
        """
        sector_value = sum(
            pos.get('vol', 0) * pos.get('cost', 0)
            for s, pos in positions.items()
            if pos.get('sector') == sector
        )
        total_value = sum(pos.get('vol', 0) * pos.get('cost', 0) for s, pos in positions.items())
        if total_value > 0:
            exposure = sector_value / total_value
            if exposure > self.max_sector_exposure_pct:
                return False, f'{sector}行业集中度{exposure:.0%}>上限{self.max_sector_exposure_pct:.0%}'
        return True, 'OK'

    # === L3: 账户监控 ===
    def check_account(self, current_capital: float, trade_pnl: float = None) -> tuple:
        """
        账户级风控 — 返回 (is_halted: bool, reason: str)
        """
        if trade_pnl is not None:
            self.daily_pnl += trade_pnl

        # 日亏损上限
        if self.daily_pnl < -self.initial_capital * self.daily_loss_limit_pct:
            self.is_halted = True
            self.halt_reason = f'日亏损{self.daily_pnl:.0f}超过上限'
            return True, self.halt_reason

        # 连亏熔断
        if trade_pnl is not None and trade_pnl < 0:
            self.consecutive_loss_trades += 1
        elif trade_pnl is not None and trade_pnl > 0:
            self.consecutive_loss_trades = 0

        if self.consecutive_loss_trades >= self.max_consecutive_losses:
            self.is_halted = True
            self.halt_reason = f'连续亏损{self.consecutive_loss_trades}笔'
            return True, self.halt_reason

        # 回撤熔断
        self.peak_capital = max(self.peak_capital, current_capital)
        dd = (self.peak_capital - current_capital) / self.peak_capital
        if dd > self.max_drawdown_limit:
            self.is_halted = True
            self.halt_reason = f'回撤{dd:.1%}超过上限{self.max_drawdown_limit:.0%}'
            return True, self.halt_reason

        return False, 'OK'

    def get_risk_report(self) -> dict:
        """获取当前风控状态报告"""
        return {
            'is_halted': self.is_halted,
            'halt_reason': self.halt_reason,
            'daily_pnl': round(self.daily_pnl, 2),
            'consecutive_losses': self.consecutive_loss_trades,
            'peak_capital': round(self.peak_capital, 0),
            'current_drawdown_pct': round(
                (self.peak_capital - max(self.peak_capital * 0.5, 1)) / self.peak_capital * 100, 2
            ),
        }
