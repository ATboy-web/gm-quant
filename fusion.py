"""
fusion.py - V30.5 多策略投票融合引擎 (借鉴 abu UMP裁判系统)

UMP架构:
  边裁 (Edge Judge): 专项信号分析器 → 对特定维度投票
  主裁 (Main Judge): 汇总边裁投票 → 最终 BUY/SELL/HOLD 决策
  否决权 (Veto):    止损/止盈信号可一票否决主裁

边裁类型:
  - OversoldJudge:    超卖深度 (RSI/跌幅)
  - MomentumJudge:    多头趋势确认 (MA排列/金叉)
  - VolumeJudge:      量价配合 (缩量止跌/放量反弹)
  - BreakdownJudge:   破位检测 (均线/支撑)[出场]
  - RegimeJudge:      市场状态适配 [出场]
  - ExitConsensus:    多策略共识退出 [出场]
"""

import config


# ============================================================
# 边裁基类
# ============================================================
class EdgeJudge:
    """边裁基类 — 对单一维度做出独立判断"""
    def __init__(self, name, weight=1.0):
        self.name = name
        self.weight = weight

    def vote_entry(self, data, regime='range'):
        """入场投票: 'BUY' | 'HOLD' + confidence"""
        return 'HOLD', 0.0

    def vote_exit(self, data, regime='range'):
        """出场投票: 'SELL' | 'HOLD' + confidence"""
        return 'HOLD', 0.0


# ============================================================
# 入场边裁
# ============================================================
class OversoldJudge(EdgeJudge):
    """超卖边裁 — RSI/跌幅评分"""
    def vote_entry(self, data, regime='range'):
        rsi = data.get('rsi', 50)
        close = data.get('close', 0)
        ma20 = data.get('ma20', 0)
        dd_20d = data.get('dd_20d', 0)  # 20日跌幅

        score = 0.0
        # RSI超卖
        if rsi < 25:   score += 0.4
        elif rsi < 30: score += 0.3
        elif rsi < 35: score += 0.15

        # 近期跌幅
        if dd_20d < -15:   score += 0.3
        elif dd_20d < -10: score += 0.2
        elif dd_20d < -5:  score += 0.1

        # 价格在MA20下方（超卖特征）
        if ma20 > 0 and close < ma20:
            score += 0.1

        conf = min(0.95, score)
        if conf >= 0.25:
            return 'BUY', conf
        return 'HOLD', 0.0

    def vote_exit(self, data, regime='range'):
        rsi = data.get('rsi', 50)
        # RSI过热出场
        if rsi > 80:
            return 'SELL', 0.9
        elif rsi > 70:
            return 'SELL', 0.6
        return 'HOLD', 0.0


class MomentumJudge(EdgeJudge):
    """动量边裁 — MA多头排列/金叉"""
    def vote_entry(self, data, regime='range'):
        ma20 = data.get('ma20', 0)
        ma60 = data.get('ma60', 0)
        close = data.get('close', 0)
        golden_cross = data.get('golden_cross', False)

        if regime == 'bull':
            # 牛市：站上MA20即可
            if ma20 > 0 and close > ma20:
                return 'BUY', 0.5
        elif regime == 'range':
            # 震荡：需要多头排列
            if ma20 > 0 and ma60 > 0 and close > ma20 > ma60:
                return 'BUY', 0.6
        else:
            # 熊市：动量弱化
            if golden_cross:
                return 'BUY', 0.3

        return 'HOLD', 0.0

    def vote_exit(self, data, regime='range'):
        close = data.get('close', 0)
        ma20 = data.get('ma20', 0)
        if ma20 > 0 and close < ma20 * 0.97:
            return 'SELL', 0.7
        return 'HOLD', 0.0


class VolumeJudge(EdgeJudge):
    """量价边裁 — 放量止跌/缩量下跌"""
    def vote_entry(self, data, regime='range'):
        vol_ratio = data.get('vol_ratio', 1.0)
        close = data.get('close', 0)
        open_p = data.get('open', 0)

        # 放量阳线确认（跌后反弹信号）
        if close > open_p and vol_ratio > 1.2:
            return 'BUY', 0.55
        # 缩量止跌（抛压耗尽）
        if vol_ratio < 0.7:
            return 'BUY', 0.35
        return 'HOLD', 0.0

    def vote_exit(self, data, regime='range'):
        vol_ratio = data.get('vol_ratio', 1.0)
        close = data.get('close', 0)
        open_p = data.get('open', 0)
        # 放量下跌 = 抛压
        if close < open_p and vol_ratio > 1.5:
            return 'SELL', 0.8
        return 'HOLD', 0.0


class BreakdownJudge(EdgeJudge):
    """破位边裁 — 出场专用"""
    def vote_exit(self, data, regime='range'):
        close = data.get('close', 0)
        low_10d = data.get('low_10d', close)
        ma60 = data.get('ma60', 0)

        # 跌破10日最低
        if low_10d > 0 and close < low_10d:
            return 'SELL', 0.85
        # 跌破MA60（中期破位）
        if ma60 > 0 and close < ma60 * 0.95:
            return 'SELL', 0.75
        return 'HOLD', 0.0


class RegimeJudge(EdgeJudge):
    """市场状态边裁 — 出场专用"""
    def vote_exit(self, data, regime='range'):
        if regime == 'bear':
            return 'SELL', 0.5  # 熊市倾向退出
        return 'HOLD', 0.0


# ============================================================
# 主裁
# ============================================================
class UmpMainJudge:
    """
    主裁 — 汇总边裁投票 + 策略信号 = 最终决策

    借鉴 abu UMP:
      - 边裁投票达到阈值 → 确认信号
      - 否决不通过(边裁分歧大) → 保守HOLD
      - 存在否决权信号(止损) → 直接SELL
    """

    def __init__(self):
        self.entry_judges = [
            OversoldJudge('超卖', 1.5),
            MomentumJudge('动量', 1.0),
            VolumeJudge('量价', 1.0),
        ]
        self.exit_judges = [
            OversoldJudge('过热', 0.8),
            MomentumJudge('破位', 0.8),
            VolumeJudge('抛压', 0.8),
            BreakdownJudge('跌破', 1.0),
            RegimeJudge('市态', 0.3),
        ]
        self.VETO_CONFIDENCE = 0.85  # 否决权阈值

    def judge_entry(self, strategy_signals, ohlcv_data=None, regime='range'):
        """
        入场审判。

        Args:
            strategy_signals: {'MR': {...}, 'MOM': {...}, 'VRC': {...}, ...}
            ohlcv_data: {'close': ..., 'rsi': ..., 'ma20': ..., ...}
            regime: 'bull'/'range'/'bear'

        Returns:
            {action, confidence, position_pct, voters, reason}
        """
        data = ohlcv_data or {}
        edge_buys = 0
        edge_cons = []

        # 1. 边裁投票
        for judge in self.entry_judges:
            action, conf = judge.vote_entry(data, regime)
            if action == 'BUY' and conf > 0:
                edge_buys += judge.weight
                edge_cons.append(conf)

        # 2. 策略信号收集
        strat_buys = 0.0
        strat_voters = []
        for name, sig in strategy_signals.items():
            if sig and sig.get('action') == 'BUY':
                w = _get_regime_weight(name, regime)
                strat_buys += w
                strat_voters.append(name)

        # 3. 合并主裁判决
        total_buys = strat_buys + edge_buys * 0.5  # 边裁权重半折

        if total_buys >= 4.0:
            conf = sum(edge_cons) / len(edge_cons) if edge_cons else 0.7
            return {'action': 'BUY', 'confidence': min(0.95, conf),
                    'position_pct': 1.0, 'voters': strat_voters,
                    'reason': 'UMP_强一致[%s]' % '+'.join(strat_voters)}
        elif total_buys >= 2.5:
            conf = sum(edge_cons) / len(edge_cons) if edge_cons else 0.5
            pos = 0.70
            reason = f'UMP_确认[{'+'.join(strat_voters)}]' if strat_voters else 'UMP_边裁信号'
            return {'action': 'BUY', 'confidence': conf,
                    'position_pct': pos, 'voters': strat_voters, 'reason': reason}
        elif total_buys >= 1.5 and strat_voters:
            return {'action': 'BUY', 'confidence': 0.4, 'position_pct': 0.50,
                    'voters': strat_voters,
                    'reason': 'UMP_弱确认[%s]' % '+'.join(strat_voters)}

        return {'action': 'HOLD', 'confidence': 0.0, 'position_pct': 0.0,
                'voters': [], 'reason': f'UMP_否决(总分{total_buys:.1f}<1.5)'}

    def judge_exit(self, strategy_exits, owner_strategy=None, ohlcv_data=None, regime='range'):
        """
        出场审判。

        Args:
            strategy_exits: {'MR': {...}, 'MOM': {...}, ...}
            owner_strategy: 当前持仓的归属策略
            ohlcv_data: OHLCV数据
            regime: 市场状态

        Returns:
            {action, confidence, reason}
        """
        data = ohlcv_data or {}
        reasons = []
        has_veto = False
        owner_sell = False
        total_sells = 0.0

        # 1. 策略信号收集
        for name, sig in strategy_exits.items():
            if sig is None or sig.get('action') != 'SELL':
                continue
            reason = sig.get('reason', name)
            conf = sig.get('confidence', 0.5)
            reasons.append(reason)

            # 否决权检测: 止损/止盈
            for kw in ('止损', 'stop', 'STP', '止盈'):
                if kw in reason and conf > 0.7:
                    has_veto = True
                    break

            if name == owner_strategy:
                owner_sell = True

            w = _get_regime_weight(name, regime)
            total_sells += w

        # 2. 边裁投票
        edge_sells = 0
        for judge in self.exit_judges:
            action, conf = judge.vote_exit(data, regime)
            if action == 'SELL':
                edge_sells += judge.weight * conf

        # 3. 审判
        # 否决权: 止损信号无条件通过
        if has_veto:
            return {'action': 'SELL', 'confidence': 0.90,
                    'reason': 'UMP_否决权|%s' % '|'.join(reasons)}

        # 归属策略
        if owner_sell:
            return {'action': 'SELL', 'confidence': 0.85,
                    'reason': 'UMP_归属[%s]|%s' % (owner_strategy, '|'.join(reasons))}

        # 多数确认 — 提高阈值, MR/VRC不受边裁干扰
        edge_boost = 0 if owner_strategy in ('MR', 'VRC') else edge_sells
        if total_sells >= 2.5 or (total_sells >= 1.5 and edge_boost >= 1.0):
            return {'action': 'SELL', 'confidence': 0.75,
                    'reason': 'UMP_确认%s|%s' %
                    (f'({edge_sells:.1f})' if edge_sells > 0 else '', '|'.join(reasons))}

        # 边裁强卖（即使策略没信号）— MR/VRC持仓不受边裁干扰
        if owner_strategy not in ('MR', 'VRC') and edge_sells >= 2.5:
            return {'action': 'SELL', 'confidence': 0.65,
                    'reason': 'UMP_边裁强卖'}

        return {'action': 'HOLD', 'confidence': 0.0, 'reason': 'UMP_无需出场'}


# ---- 单例 ----
_main_judge = None


def get_main_judge() -> UmpMainJudge:
    global _main_judge
    if _main_judge is None:
        _main_judge = UmpMainJudge()
    return _main_judge


# ============================================================
# 对外接口 (保持向后兼容)
# ============================================================

def vote_entry(mr_signal=None, mom_signal=None, vp_signal=None, regime='range',
               bk_signal=None, dv_signal=None, rt_signal=None, ohlcv=None):
    """
    六策略入场投票 (UMP增强版)。

    兼容旧API，内部委托给 UmpMainJudge。
    """
    signals = {}
    if mr_signal:   signals['MR'] = mr_signal
    if mom_signal:  signals['MOM'] = mom_signal
    if vp_signal:   signals['VRC'] = vp_signal
    if bk_signal:   signals['BK'] = bk_signal
    if dv_signal:   signals['DV'] = dv_signal
    if rt_signal:   signals['RT'] = rt_signal

    return get_main_judge().judge_entry(signals, ohlcv, regime)


def vote_exit(mr_exit=None, mom_exit=None, vp_exit=None, regime='range',
              owner_strategy=None, bk_exit=None, dv_exit=None, rt_exit=None, ohlcv=None):
    """
    六策略出场投票 (UMP增强版)。
    """
    exits = {}
    if mr_exit:   exits['MR'] = mr_exit
    if mom_exit:  exits['MOM'] = mom_exit
    if vp_exit:   exits['VRC'] = vp_exit
    if bk_exit:   exits['BK'] = bk_exit
    if dv_exit:   exits['DV'] = dv_exit
    if rt_exit:   exits['RT'] = rt_exit

    return get_main_judge().judge_exit(exits, owner_strategy, ohlcv, regime)


# ============================================================
# 权重映射 (保持不变)
# ============================================================

def _get_regime_weight(strategy_name, regime):
    """根据市场状态调整策略权重。MR 始终主导。"""
    if strategy_name == 'MR':
        weights = {'range': 3.0, 'bear': 1.5, 'bull': 2.0}
        return weights.get(regime, 2.0)
    if strategy_name == 'MOM':
        weights = {'bull': 2.0, 'range': 0.5, 'bear': 0.3}
        return weights.get(regime, 0.5)
    if strategy_name in ('VP', 'VRC'):
        return 2.0 if regime == 'bear' else 1.0
    if strategy_name == 'BK':
        return 1.0
    if strategy_name == 'DV':
        return 1.0
    if strategy_name == 'RT':
        return 2.0 if regime == 'bear' else (1.5 if regime == 'range' else 0.8)
    return 1.0
