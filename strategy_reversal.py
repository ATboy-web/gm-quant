"""
strategy_reversal.py - 反转确认策略 (V20)

适用于左侧行业（化工/新能源/煤炭等持续下跌行业），
核心思想：不抄底，等反转确认后再入场。

问题背景:
  V19.2 的 MR 策略在化工(-3.7%)、新能源(-2.1%)、煤炭(-1.1%) 反复抄底被套，
  因为这些行业处于持续下跌趋势中（左侧），RSI 超卖不代表反弹。

核心逻辑:
  买入（右侧反转确认）:
    1. 短期趋势反转: MA5 > MA10（金叉或刚金叉）
    2. 反转日放量: 当日量比 ≥ 1.3
    3. 价格站上 MA20: 确认脱离底部
    4. RSI 回升至 40-60 区间: 非超卖，说明已有买盘介入
    5. 底部特征确认: 近20日出现过RSI<30的超卖（刚从底部起来）
  卖出:
    1. MA5 跌破 MA10（死叉）
    2. 跌破 MA20（趋势再破）
    3. 固定止损 6%
    4. 固定止盈 12%（反转行情不贪）
    5. 时间止损 20 天

与其他策略的互补:
  - MR 看超卖抄底（左侧），RT 看反转确认（右侧）
  - MOM 看趋势追涨（高位），RT 看底部反转（低位刚起来）
  - VP 看量价背离（预判），RT 看量价确认（确认）
  - BK 看突破加速（中位），RT 看趋势拐点（底部）
  - DV 看低位价值（防御），RT 看低位反转（进攻）
"""

import numpy as np
import config
import indicators


# 反转确认策略参数
RT_MA_FAST       = 5     # 快速均线
RT_MA_SLOW       = 10    # 慢速均线
RT_TREND_MA      = 20    # 趋势确认均线
RT_VOL_SURGE     = 1.3   # 反转日最小量比
RT_STOP_LOSS     = 0.06  # 固定止损 6%
RT_TAKE_PROFIT   = 0.12  # 固定止盈 12%
RT_TIME_STOP     = 20    # 时间止损天数
RT_RSI_LOW       = 40    # RSI 买入下限（非超卖）
RT_RSI_HIGH      = 60    # RSI 买入上限（非过热）
RT_OVERSOLD_LOOKBACK = 30  # 底部超卖回看天数
RT_OVERSOLD_RSI  = 30    # 底部超卖阈值


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    反转确认策略买入信号。

    检测:
      1. MA5 > MA10（短期趋势反转）
      2. 放量确认（反转日量比≥1.3）
      3. 价格站上MA20
      4. RSI在40-60区间（已脱离超卖，但未过热）
      5. 近期有超卖历史（确认是从底部反转）
    """
    closes = df['close'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < 60:
        return None

    cur_price = float(closes[-1])

    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 1. 短期趋势反转: MA5 > MA10 ----
    ma5 = indicators.calc_sma(closes, RT_MA_FAST)
    ma10 = indicators.calc_sma(closes, RT_MA_SLOW)

    if ma5 is None or ma10 is None:
        return None

    trend_reversal = (ma5 > ma10)

    if not trend_reversal:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'RT_MA5<=MA10(%.2f<=%.2f)趋势未反转' % (ma5, ma10),
        }

    # 检查是否刚金叉（3天内），金叉比长期金叉更有信号价值
    recent_golden_cross = False
    if n > RT_MA_SLOW + 3:
        for i in range(1, min(4, n - RT_MA_SLOW)):
            ma5_prev = indicators.calc_sma(closes[:n - i], RT_MA_FAST)
            ma10_prev = indicators.calc_sma(closes[:n - i], RT_MA_SLOW)
            if ma5_prev is not None and ma10_prev is not None:
                if ma5_prev <= ma10_prev:
                    recent_golden_cross = True
                    break

    # ---- 2. 放量确认 ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    vol_confirm = (vol_ratio >= RT_VOL_SURGE)
    vol_score = min(1.0, (vol_ratio - 0.8) / 1.5) if vol_ratio > 0.8 else 0.0

    # ---- 3. 价格站上MA20 ----
    ma20 = indicators.calc_sma(closes, RT_TREND_MA)
    above_ma20 = (ma20 is not None and cur_price > ma20)

    if ma20 is None:
        return None

    if not above_ma20:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'RT_价格在MA20下方(%.2f<%.2f)' % (cur_price, ma20),
        }

    # 站上MA20的距离（刚站上加分更多）
    ma20_dist = (cur_price - ma20) / ma20
    if ma20_dist > 0.05:
        # 离MA20太远，可能已在高位，不是底部反转
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'RT_远离MA20(%.1f%%)非底部反转' % (ma20_dist * 100),
        }

    # ---- 4. RSI 在 40-60 区间 ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    rsi_ok = (RT_RSI_LOW <= rsi <= RT_RSI_HIGH)
    if not rsi_ok:
        if rsi < RT_RSI_LOW:
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'score': 0.0,
                'rsi': round(rsi, 1),
                'reason': 'RT_RSI太低(%.0f)仍在超卖' % rsi,
            }
        else:
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'score': 0.0,
                'rsi': round(rsi, 1),
                'reason': 'RT_RSI偏高(%.0f)已过热' % rsi,
            }

    # ---- 5. 近期超卖历史（底部特征确认） — 必要条件 ----
    has_oversold_history = False
    oversold_score = 0.0
    lookback = min(RT_OVERSOLD_LOOKBACK, n - 1)
    if lookback > 14:  # 需要足够数据计算RSI
        recent_closes = closes[-lookback:]
        # 检查近30日内是否有RSI<30的记录
        for i in range(14, len(recent_closes)):
            rsi_i = indicators.calc_rsi(recent_closes[:i + 1], period=14)
            if rsi_i is not None and rsi_i < RT_OVERSOLD_RSI:
                has_oversold_history = True
                # 超卖越深加分越多
                depth = (RT_OVERSOLD_RSI - rsi_i) / RT_OVERSOLD_RSI
                oversold_score = max(oversold_score, depth)
                break

    # V20.1: 没有底部超卖历史则不触发RT（RT的核心价值就是确认底部反转）
    if not has_oversold_history:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'rsi': round(rsi, 1),
            'reason': 'RT_无底部超卖历史',
        }

    # ---- 综合评分 ----
    score = 0.15  # 基础分：MA5>MA10

    # 刚金叉加分（强信号）
    if recent_golden_cross:
        score += 0.25
    else:
        score += 0.10  # 长期金叉

    # 放量确认
    if vol_confirm:
        score += 0.20
    else:
        score += vol_score * 0.10  # 部分放量

    # MA20距离加分（刚站上最好）
    if ma20_dist < 0.02:
        score += 0.15  # 刚站上MA20
    else:
        score += 0.08  # 稍远

    # 底部超卖历史加分（已是必要条件，这里调整深度分）
    score += 0.15 + oversold_score * 0.05

    # 行业动量加分
    sector_score = 0.0
    if sector_momentum and sector and sector in sector_momentum:
        sm = sector_momentum[sector]
        # 行业动量正值（正在复苏）加分
        if sm > 0:
            sector_score = min(0.10, sm * 0.5)
            score += sector_score

    score = min(1.0, score)

    if score >= 0.75:   # V26: 0.60→0.75, 大幅收紧(原胜率37.5%), 仅完美信号触发
        reason_parts = ['反转确认']
        if recent_golden_cross:
            reason_parts.append('金叉')
        if vol_confirm:
            reason_parts.append('放量%.1f' % vol_ratio)
        reason_parts.append('站上MA20')
        if has_oversold_history:
            reason_parts.append('底部超卖')
        reason_parts.append('RSI=%.0f' % rsi)
        if sector_score > 0:
            reason_parts.append('行业复苏')

        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'rsi': round(rsi, 1),
            'reason': 'RT_' + '|'.join(reason_parts),
        }

    return {
        'action': 'HOLD',
        'confidence': score,
        'score': round(score, 4),
        'rsi': round(rsi, 1),
        'reason': 'RT_评分不足(%.3f)' % score,
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    反转确认策略出场逻辑。

    出场条件:
      1. MA5 跌破 MA10（死叉，趋势再破）
      2. 跌破 MA20（趋势确认失败）
      3. 固定止损 6%
      4. 固定止盈 12%
      5. 时间止损 20天
    """
    closes = df['close'].values

    if len(closes) < RT_MA_SLOW + 5:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    # ---- 1. MA5 < MA10（死叉） ----
    ma5 = indicators.calc_sma(closes, RT_MA_FAST)
    ma10 = indicators.calc_sma(closes, RT_MA_SLOW)

    if ma5 is not None and ma10 is not None and ma5 < ma10:
        # 确认是否刚死叉（更紧急）
        return {
            'action': 'SELL',
            'confidence': 0.80,
            'reason': 'RT_死叉(MA5<MA10)',
        }

    # ---- 2. 跌破MA20 ----
    ma20 = indicators.calc_sma(closes, RT_TREND_MA)
    if ma20 is not None and cur_price < ma20:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'RT_跌破MA20(%.2f<%.2f)' % (cur_price, ma20),
        }

    # ---- 3. 固定止损 ----
    if pnl <= -RT_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'RT_止损(%+.1f%%)' % (pnl * 100),
        }

    # ---- 4. 固定止盈 ----
    if pnl >= RT_TAKE_PROFIT:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'RT_止盈(%+.1f%%)' % (pnl * 100),
        }

    # ---- 5. 时间止损 ----
    entry_date = pos_info.get('entry_date', '')
    if entry_date and today_str:
        try:
            from datetime import datetime as dt
            days = (dt.strptime(today_str, '%Y-%m-%d') -
                    dt.strptime(entry_date, '%Y-%m-%d')).days
            if days >= RT_TIME_STOP and pnl < 0.02:
                return {
                    'action': 'SELL',
                    'confidence': 0.7,
                    'reason': 'RT_时间止损(%dd)' % days,
                }
        except Exception:
            pass

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
