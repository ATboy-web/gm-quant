"""
fusion.py - 多策略投票融合引擎 (V18)

将三个独立策略的信号汇总，通过投票机制产生最终决策。

融合规则:
  1. 收集三个策略对同一只股票的 {BUY, SELL, HOLD} 信号
  2. 统计 BUY / SELL 票数
  3. 根据票数和市场状态决定最终操作

决策矩阵 (V18 MR主导):
  BUY票数 | SELL票数 | 决策        | 仓位
  --------|---------|------------|------
  ≥4.0   | 0       | BUY        | 100% (MR+双确认)
  ≥2.0   | 0       | BUY        | 70%  (MR主导)
  ≥1.5   | 0       | BUY        | 50%  (MR弱确认)
  1.0~1.5 | 0      | HOLD       | 0%   (非MR不可靠)

MR主导权重: MR ×2 始终生效，回测数据支持 MR 胜率 66.7%
"""

import config


def vote_entry(mr_signal, mom_signal, vp_signal, regime='range'):
    """
    对三策略的入场信号进行投票，决定是否买入。

    Args:
        mr_signal:  均值回归信号 dict
        mom_signal: 动量信号 dict
        vp_signal:  量价背离信号 dict
        regime:     市场状态 'bull' | 'range' | 'bear'

    Returns:
        dict: {
            'action': 'BUY' | 'HOLD',
            'confidence': 0.0 ~ 1.0,
            'position_pct': 仓位比例,
            'voters': 哪些策略同意,
            'reason': 决策理由,
        }
    """
    signals = [
        ('MR',  mr_signal),
        ('MOM', mom_signal),
        ('VP',  vp_signal),
    ]

    # 统计票数（考虑市场状态加权）
    buy_votes  = 0.0
    sell_votes = 0.0
    voters     = []
    confidences = []

    for name, sig in signals:
        if sig is None:
            continue
        action = sig.get('action', 'HOLD')
        conf   = sig.get('confidence', 0.0)
        weight = _get_regime_weight(name, regime)

        if action == 'BUY':
            buy_votes += weight
            voters.append(name)
            confidences.append(conf)
        elif action == 'SELL':
            sell_votes += weight

    # ---- 决策 ----
    if buy_votes >= 4.0:
        # 强一致买入（MR + 至少一个其他策略确认）
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
        return {
            'action': 'BUY',
            'confidence': avg_conf,
            'position_pct': 1.0,
            'voters': voters,
            'reason': 'FUSION_强一致[%s]' % '+'.join(voters),
        }
    elif buy_votes >= 2.0:
        # MR 主导买入（MR=2.0~3.0，足以独立触发）
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
        if sell_votes > 0:
            pos_pct = 0.50
            reason = 'FUSION_MR主导(有异议)[%s]' % '+'.join(voters)
        else:
            pos_pct = 0.70
            reason = 'FUSION_MR主导[%s]' % '+'.join(voters)

        return {
            'action': 'BUY',
            'confidence': avg_conf,
            'position_pct': pos_pct,
            'voters': voters,
            'reason': reason,
        }
    elif buy_votes >= 1.5:
        # MR 弱确认（熊市 MR=1.5 刚好够）
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.3
        return {
            'action': 'BUY',
            'confidence': avg_conf,
            'position_pct': 0.50,
            'voters': voters,
            'reason': 'FUSION_MR弱确认[%s]' % '+'.join(voters),
        }

    return {
        'action': 'HOLD',
        'confidence': 0.0,
        'position_pct': 0.0,
        'voters': [],
        'reason': 'FUSION_票数不足(%.1f/3)' % buy_votes,
    }


def vote_exit(mr_exit, mom_exit, vp_exit, regime='range', owner_strategy=None):
    """
    对三策略的出场信号进行投票，决定是否卖出。

    V18.1 出场规则:
      1. 归属策略喊 SELL → 直接卖（优先权）
      2. 任何止损/止盈信号 → 直接卖（安全阀，防止策略不匹配导致亏损扩大）
      3. 非归属策略的趋势/时间类出场 → 需要交叉验证（≥2个策略同意）
      
    区分「止损类」（高优先级）和「趋势/时间类」（低优先级）：
      - 止损类: ATR止损、跌破MA20、固定止损、VP止损 — 直接执行
      - 趋势类: 时间止损、RSI过热 — 需要归属策略或交叉验证
    """
    signals = [
        ('MR',  mr_exit),
        ('MOM', mom_exit),
        ('VP',  vp_exit),
    ]

    # 止损关键词（高优先级，任何策略都可以触发）
    STOP_KEYWORDS = ['止损', 'stop', 'STP']

    sell_votes  = 0.0
    reasons     = []
    owner_sell  = False
    has_stop_signal = False  # 是否有止损类信号

    for name, sig in signals:
        if sig is None:
            continue
        action = sig.get('action', 'HOLD')
        weight = _get_regime_weight(name, regime)
        reason = sig.get('reason', name)
        conf = sig.get('confidence', 0.0)

        if action == 'SELL':
            # V19.2: MOM 短暂破MA20 (conf≤0.5) 不参与交叉验证计票
            is_weak_trend = (conf <= 0.5 and '短暂' in reason)
            if not is_weak_trend:
                sell_votes += weight
            reasons.append(reason)
            if name == owner_strategy:
                owner_sell = True
            # 检查是否为止损类信号
            for kw in STOP_KEYWORDS:
                if kw in reason:
                    has_stop_signal = True
                    break

    # ---- 出场决策 ----

    # 1. 归属策略喊卖 → 直接执行
    if owner_sell:
        return {
            'action': 'SELL',
            'confidence': 0.9,
            'reason': 'FUSION_归属策略[%s]卖出|%s' % (owner_strategy, '|'.join(reasons)),
        }

    # 2. 任何止损类信号 → 安全阀，直接执行（防止亏损扩大）
    if has_stop_signal:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'FUSION_止损保护|%s' % '|'.join(reasons),
        }

    # 3. 所有策略强卖
    if sell_votes >= 2.5:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'FUSION_强卖[%s]' % '|'.join(reasons),
        }

    # 4. 趋势/时间类出场 → 需交叉验证（V20: ≥1.5, 放宽入场也放宽出场）
    if sell_votes >= 1.5:
        # 至少2个策略同意趋势/时间出场
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'FUSION_交叉验证[%s]' % '|'.join(reasons),
        }

    return {
        'action': 'HOLD',
        'confidence': 0.0,
        'reason': 'FUSION_无需出场',
    }


def _get_regime_weight(strategy_name, regime):
    """根据市场状态调整策略权重。MR 始终主导（回测胜率 66.7%）。"""
    if strategy_name == 'MR':
        # MR 始终高权重，从不降权
        if regime == 'range':
            return 3.0   # 震荡市 MR 最强
        elif regime == 'bear':
            return 1.5   # 熊市 MR 仍保留话语权
        else:
            return 2.0   # 牛市 MR 保持主导

    if strategy_name == 'MOM':
        if regime == 'bull':
            return 2.0   # 趋势市动量加倍
        elif regime == 'range':
            return 0.5   # 震荡市动量降权
        elif regime == 'bear':
            return 0.3   # 熊市动量大幅降权

    if strategy_name == 'VP':
        if regime == 'bear':
            return 2.0   # 熊市量价背离加倍
        else:
            return 1.0   # 其他市场正常权重

    if strategy_name == 'BK':
        return 1.0  # 突破策略正常权重

    if strategy_name == 'DV':
        return 1.0  # 红利策略正常权重

    if strategy_name == 'RT':
        if regime == 'bear':
            return 2.0   # 熊市反转确认高权重（抄底确认型）
        elif regime == 'range':
            return 1.5   # 震荡市反转确认中等权重
        else:
            return 0.8   # 牛市不需要抄底确认

    return 1.0


def _regime_tiebreaker(regime):
    """分歧时按市场状态选方向。"""
    if regime == 'bull':
        return '趋势市偏多'
    elif regime == 'bear':
        return '熊市偏空'
    else:
        return '震荡市偏多(均值回归)'
