"""
strategy_vrc.py - 成交量反转确认策略 (V29.7)

替代原 VP（量价背离）策略。核心改进：不做预测，只做确认。

原 VP 问题: 背离检测捕捉的是结构性弱势而非反转点 → -28%三版本不变
新 VRC 逻辑: 下跌衰竭 → 等确认阳线 → 确认后才入场

确认条件（全部必须）:
  1. 价格从20日高点跌10%+（有跌幅才有反弹空间）
  2. 近3日成交量递减（抛压衰竭）
  3. 今日: 阳线 + 量 > 1.5x 均量（主力进场确认）
  4. RSI 18-45（超卖但非极端）
  
出场:
  - 盈利 +8% → 移动止盈线 5%
  - 跌破入场日最低价 → 止损
  - 10天未反弹 → 时间止损
  - RSI > 70 → 止盈
"""

import numpy as np
import config
import indicators


VRC_PERIOD       = 20     # 回看窗口
VRC_DECLINE_MIN  = -0.10  # V29.8: 恢复巅峰参数
VRC_VOL_SURGE    = 1.5    # V29.8: 恢复巅峰参数
VRC_STOP_LOSS    = 0.04   # 硬止损 4%
VRC_TIME_STOP    = 10     # 时间止损天数
VRC_TAKE_PROFIT  = 0.08   # 止盈 8%
VRC_TRAIL_PROFIT = 0.05   # 移动止盈线
VRC_SCORE_MIN    = 0.55   # 评分门槛


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    VRC 买入信号: 等待反转确认，不提前抄底。

    三阶段逻辑:
      Phase 1 — 确认有下跌: 从20日高点跌10%+
      Phase 2 — 确认抛压衰竭: 近3日成交量递减
      Phase 3 — 确认主力进场: 今日放量阳线
    全部确认 → BUY
    """
    closes = df['close'].values
    opens  = df['open'].values
    vols   = df['volume'].values
    highs  = df['high'].values
    lows   = df['low'].values

    n = len(closes)
    if n < VRC_PERIOD + 3:
        return None

    cur_price = float(closes[-1])
    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- Phase 1: 确认有下跌空间 ----
    price_20d_high = np.max(highs[-20:])
    decline_from_high = (cur_price - price_20d_high) / price_20d_high
    
    if decline_from_high > VRC_DECLINE_MIN:
        # 没跌够，不关注
        return {
            'action': 'HOLD',
            'confidence': 0,
            'score': 0,
            'reason': 'VRC_跌幅不足(%.1f%%)' % (decline_from_high * 100),
        }

    # ---- Phase 2: 确认抛压衰竭 (近3日量递减) ----
    vol_3d = vols[-3:]
    vol_declining = (vol_3d[0] > vol_3d[1] > vol_3d[2])
    
    if not vol_declining:
        # 还在放量，没跌透
        return {
            'action': 'HOLD',
            'confidence': 0.1,
            'score': 0.1,
            'reason': 'VRC_抛压未衰竭',
        }

    # ---- Phase 3: 确认主力进场 (今日放量阳线) ----
    is_green = (closes[-1] > opens[-1])
    is_up_from_yesterday = (closes[-1] > closes[-2])
    
    vol_20d_avg = np.mean(vols[-20:])
    vol_surge_ratio = vols[-1] / vol_20d_avg if vol_20d_avg > 0 else 1.0
    
    reversal_confirmed = (
        is_green and
        is_up_from_yesterday and
        vol_surge_ratio >= VRC_VOL_SURGE
    )

    # ---- RSI 检查 ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    rsi_sweet_spot = (18 <= rsi <= 45)

    # ---- 加分项 ----
    # 价格离近期低点不远（没反弹太多）
    price_5d_low = np.min(lows[-5:])
    near_low = (cur_price < price_5d_low * 1.05)  # 距5日低点5%内
    
    # 连续2日阳线
    two_green_days = (closes[-1] > opens[-1] and closes[-2] > opens[-2])
    
    # 放巨量（>2x均量）
    huge_volume = (vol_surge_ratio >= 2.0)

    # ---- 评分 ----
    score = 0.0
    reasons = []
    
    if reversal_confirmed:
        score += 0.40
        reasons.append('放量阳线确认')
    
    if rsi_sweet_spot:
        score += 0.15
        reasons.append('RSI=%.0f' % rsi)
    
    if near_low:
        score += 0.10
        reasons.append('近低点')
    
    if two_green_days:
        score += 0.10
        reasons.append('连阳')
    
    if huge_volume:
        score += 0.10
        reasons.append('巨量')
    
    # 跌幅加分（跌越多反弹空间越大）
    decline_bonus = min(0.15, abs(decline_from_high + 0.10) * 0.5)
    score += decline_bonus
    
    score = min(1.0, score)

    if not reversal_confirmed or score < VRC_SCORE_MIN:
        if score >= 0.20:
            return {
                'action': 'HOLD',
                'confidence': score,
                'score': round(score, 4),
                'reason': 'VRC_信号弱(%.2f)' % score,
            }
        return None

    return {
        'action': 'BUY',
        'confidence': score,
        'score': round(score, 4),
        'rsi': round(rsi, 1),
        'reason': 'VRC_' + '|'.join(reasons),
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    VRC 出场逻辑:
      1. 盈利 +8% → 移动止盈线 5%（最高价回撤5%离场）
      2. 跌破入场日最低价 → 止损
      3. 10天未涨 → 时间止损
      4. RSI > 70 → 过热止盈
    """
    closes = df['close'].values
    highs  = df['high'].values
    lows   = df['low'].values
    vols   = df['volume'].values
    n = len(closes)
    if n < 3:
        return None

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    peak = pos_info.get('peak', cost)
    bar_count = pos_info.get('bar_count', 0)
    pnl_pct = (cur_price - cost) / cost
    entry_low = pos_info.get('entry_low', cost * 0.97)  # 默认入场日最低

    # 更新峰值
    if cur_price > peak:
        peak = cur_price
        pos_info['peak'] = peak

    rsi = indicators.calc_rsi(closes, period=14)

    # === 出场判断 ===

    # 1. ATR 止损
    atr_val = indicators.calc_atr(highs, lows, closes, 14)
    stop_price = cost * (1 - VRC_STOP_LOSS)
    if atr_val and atr_val > 0:
        atr_stop = cost - atr_val * 1.5
        stop_price = max(stop_price, atr_stop)

    if cur_price <= stop_price:
        return {
            'action': 'SELL',
            'price': cur_price,
            'reason': 'VRC_止损(%.1f%%)' % (pnl_pct * 100),
        }

    # 2. 移动止盈
    if pnl_pct >= VRC_TAKE_PROFIT:
        trail_stop = peak * (1 - VRC_TRAIL_PROFIT)
        if cur_price <= trail_stop:
            return {
                'action': 'SELL',
                'price': cur_price,
                'reason': 'VRC_移止(%.1f%%)' % (pnl_pct * 100),
            }

    # 3. 时间止损
    if bar_count >= VRC_TIME_STOP and pnl_pct <= 0.01:
        return {
            'action': 'SELL',
            'price': cur_price,
            'reason': 'VRC_时间止损(%dd)' % bar_count,
        }

    # 4. RSI 过热
    if rsi and rsi > 70 and pnl_pct > 0:
        return {
            'action': 'SELL',
            'price': cur_price,
            'reason': 'VRC_RSI过热(%.0f)' % rsi,
        }

    # 5. 放量滞涨（出场信号）
    if n >= 5:
        vol_avg = np.mean(vols[-5:])
        if vols[-1] > vol_avg * 1.3 and closes[-1] < closes[-2]:
            return {
                'action': 'SELL',
                'price': cur_price,
                'reason': 'VRC_放量滞涨',
            }

    return None
