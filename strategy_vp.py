"""
strategy_vp.py - 量价背离策略 (V29.3)

量价分析选手：通过价格与成交量的背离关系捕捉转折点。

V29.3 修复 (2026-05-25):
  回退 V29.2 的 executor 改动 — 置信度公式改回 avg(confidences)。
  V29.2 的 max+共识加成导致多策略信号排名溢价，
  MR 资金被挤压，收益从 +105% 跌至 -44%。
  VP 趋势硬门已在 V29.2 移除（单策略证实有害），本版本保留。

V29.2 修复 (2026-05-25):
  已移除 V29.1 趋势硬门 — 单策略回测证实有害 (+8.29%→+0.75%)。
  趋势硬门误杀 VP 核心逻辑 (底部背离时价必然在MA20下方)。

核心逻辑:
  买入（底部背离）:
    - 价格创 N 日新低，但成交量萎缩（抛压耗尽）
    - 或：价格横盘/微跌，成交量持续缩小 → 洗盘尾声
  卖出:
    - 放量反弹后缩量 → 反弹动力耗尽
    - 放量滞涨 → 出货信号
    - 时间止损（背离后迟迟不反弹）

与均值回归的区别:
  - 均值回归看 RSI 数值（超卖程度）
  - 量价背离看价量关系的变化趋势（结构性的抛压衰竭）
"""

import numpy as np
import config
import indicators


VP_PERIOD       = 20    # 背离检测窗口
VP_PRICE_DECLINE = -0.03  # 价格新低幅度阈值
VP_VOL_DECLINE  = 0.65   # 成交量萎缩阈值（量比为均量的65%以下）
VP_STOP_LOSS    = 0.05   # 固定止损 5%
VP_TIME_STOP    = 20     # 时间止损天数（V18调优: 10→20，给背离修复更多时间）
VP_EXIT_PROFIT  = 0.08   # 止盈 8%


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    量价背离买入信号。

    检测以下背离形态:
      1. 底背离: 价格创新低 + 成交量持续萎缩
      2. 缩量止跌: 连续3日缩量 + 价格横盘/微跌
      3. 背离后的放量确认（加分项）
    """
    closes = df['close'].values
    vols   = df['volume'].values
    highs  = df['high'].values
    lows   = df['low'].values

    n = len(closes)
    if n < VP_PERIOD + 3:
        return None

    cur_price = float(closes[-1])

    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 量价特征提取 ----
    # 近5日 vs 前15日（一共20日窗口）
    recent_5c = closes[-5:]
    recent_5v = vols[-5:]
    prior_15c = closes[-20:-5]
    prior_15v = vols[-20:-5]

    if len(prior_15c) < 5:
        return None

    # 价格特征
    price_5d_high = np.max(recent_5c)
    price_5d_low  = np.min(recent_5c)
    price_20d_high = np.max(closes[-20:])
    price_20d_low  = np.min(closes[-20:])

    # 成交量特征
    vol_5d_avg  = np.mean(recent_5v)
    vol_15d_avg = np.mean(prior_15v)
    vol_ratio_5_15 = vol_5d_avg / vol_15d_avg if vol_15d_avg > 0 else 1.0

    # 量比
    vol_ratio_full = indicators.calc_volume_ratio(vols, VP_PERIOD)
    if vol_ratio_full is None:
        vol_ratio_full = 1.0

    # ---- 形态1: 价格创新低 + 缩量（底部背离） ----
    price_new_low = (cur_price <= price_20d_low * 1.01)
    vol_shrinking = (vol_ratio_5_15 < VP_VOL_DECLINE)

    # ---- 形态2: 连续缩量（3日量比 < 0.7） ----
    vol_ratios_3d = []
    for i in range(3):
        if n > VP_PERIOD + i:
            sub_vols = vols[:n - i]
            vr = indicators.calc_volume_ratio(sub_vols, VP_PERIOD)
            if vr is not None:
                vol_ratios_3d.append(vr)

    consecutive_low_vol = (
        len(vol_ratios_3d) >= 2 and
        all(v < 0.7 for v in vol_ratios_3d)
    )

    # ---- 形态3: 价格跌幅有限 + 量缩（洗盘而非出货） ----
    if n >= 10:
        ret_10d = (closes[-1] / closes[-10] - 1)
    else:
        ret_10d = 0
    moderate_decline = (-0.10 < ret_10d <= -0.02)

    # ---- 加分项: 放量阳线确认 ----
    vol_surge_with_green = (
        vol_ratio_full >= 1.2 and
        closes[-1] > closes[-2]
    )

    # ---- RSI 确认（避免接飞刀） ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    # RSI 太低也不行（可能还有更大跌幅）
    rsi_ok = (18 <= rsi <= 45)

    # ---- 评分计算 ----
    score = 0.0
    reasons = []

    if price_new_low and vol_shrinking:
        score += 0.50
        reasons.append('价新低+量缩')

    if consecutive_low_vol:
        score += 0.25
        reasons.append('连续缩量')

    if moderate_decline and vol_shrinking:
        score += 0.20
        reasons.append('温和下跌+缩量')

    if vol_surge_with_green:
        score += 0.15
        reasons.append('放量阳线确认')

    # RSI 不在合理区间，降分
    if not rsi_ok:
        score *= 0.5

    # V29.2: 已移除 V29.1 趋势硬门
    # 单策略回测证明: VP 独立 +8.29% vs 带硬门 +0.75%
    # 趋势硬门惩罚 VP 最核心的底部反转信号(价在MA20下+下跌中=背离), 反噬策略逻辑
    # VP 亏损根因是多策略竞争中的仓位歧视, 已通过 executor V29.2 投票机制修复

    score = min(1.0, score)

    if score >= 0.55:   # V26: 0.50→0.55, 收紧入场提升胜率
        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'rsi': round(rsi, 1),
            'reason': 'VP_' + '|'.join(reasons),
        }

    if score >= 0.25:
        return {
            'action': 'HOLD',
            'confidence': score,
            'score': round(score, 4),
            'reason': 'VP_信号弱(%.3f)' % score,
        }

    return {
        'action': 'HOLD',
        'confidence': 0.0,
        'score': 0.0,
        'reason': 'VP_无量价背离',
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    量价背离策略出场逻辑。

    出场条件:
      1. 放量反弹后缩量 → 反弹衰竭
      2. 放量滞涨（量大但价不涨）→ 出货
      3. 固定止损
      4. 时间止损（背离后迟迟不涨）
    """
    closes = df['close'].values
    vols   = df['volume'].values
    highs  = df['high'].values
    lows   = df['low'].values

    n = len(closes)
    if n < VP_PERIOD + 1:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    vol_ratio = indicators.calc_volume_ratio(vols, VP_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    # 1. 放量反弹后缩量 → 反弹衰竭
    if n >= 4:
        prev_day_vol_ratio = indicators.calc_volume_ratio(vols[:-1], VP_PERIOD)
        if (prev_day_vol_ratio and prev_day_vol_ratio >= 1.5 and
            vol_ratio < 0.8 and pnl > 0.03):
            return {
                'action': 'SELL',
                'confidence': 0.8,
                'reason': 'VP_反弹缩量衰竭',
            }

    # 2. 放量滞涨
    if vol_ratio >= 1.5 and pnl > 0 and cur_price <= closes[-2] * 1.005:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'VP_放量滞涨',
        }

    # 3. 固定止损
    if pnl <= -VP_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'VP_止损(%+.1f%%)' % (pnl * 100),
        }

    # 4. 止盈
    if pnl >= VP_EXIT_PROFIT:
        return {
            'action': 'SELL',
            'confidence': 0.8,
            'reason': 'VP_止盈(%+.1f%%)' % (pnl * 100),
        }

    # 5. 时间止损
    entry_date = pos_info.get('entry_date', '')
    if entry_date:
        try:
            if not today_str:
                if context and hasattr(context, '_today'):
                    today_str = context._today
            if not today_str:
                from datetime import datetime
                today_str = datetime.now().strftime('%Y-%m-%d')

            from datetime import datetime as dt
            days = (dt.strptime(today_str, '%Y-%m-%d') -
                    dt.strptime(entry_date, '%Y-%m-%d')).days
            if days >= VP_TIME_STOP and pnl < 0.01:
                return {
                    'action': 'SELL',
                    'confidence': 0.7,
                    'reason': 'VP_时间止损(%dd)' % days,
                }
        except Exception:
            pass

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
