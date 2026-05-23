"""
strategy_breakout.py - 突破策略 (V19.2)

适用于高波动行业（有色/科技/军工/新能源），
捕捉价格突破关键阻力位后的趋势加速行情。

核心逻辑:
  买入:
    - 价格突破 N 日高点（如 20 日新高）
    - 突破日成交量显著放大（≥1.5 倍均量）
    - 非极度超买区（RSI < 75，避免追高）
    - 均线多头排列加分
  卖出:
    - 突破失败（3 日内回落至突破价下方）
    - 固定止损 / 止盈
    - 量能萎缩 + 价格高位 → 动量衰竭
"""

import numpy as np
import config
import indicators


# 突破策略参数
BK_BREAKOUT_PERIOD = 20    # 突破检测窗口（N日新高）
BK_VOL_SURGE       = 1.5   # 突破日最小量比
BK_STOP_LOSS       = 0.07  # 固定止损 7%
BK_TAKE_PROFIT     = 0.15  # 固定止盈 15%
BK_FAIL_DAYS       = 3     # 突破失败检测天数
BK_FAIL_DROP       = -0.03  # 突破失败跌幅阈值


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    突破策略买入信号。

    检测:
      1. 价格创 N 日新高
      2. 突破日放量
      3. RSI 未超买
      4. 均线多头排列加分
    """
    closes = df['close'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < BK_BREAKOUT_PERIOD + 5:
        return None

    cur_price = float(closes[-1])

    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 1. 价格突破 N 日新高 ----
    recent_high = np.max(closes[-(BK_BREAKOUT_PERIOD + 1):-1])
    breakout = (cur_price > recent_high)

    if not breakout:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'BK_未突破%d日高(%.2f<%.2f)' % (BK_BREAKOUT_PERIOD, cur_price, recent_high),
        }

    # ---- 2. 突破日放量 ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    vol_breakout = (vol_ratio >= BK_VOL_SURGE)
    vol_score = min(1.0, (vol_ratio - 1.0) / 2.0) if vol_ratio > 1.0 else 0.0

    # ---- 3. RSI 检查（避免追高） ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    if rsi > 75:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'BK_RSI超买(%.0f)不追高' % rsi,
        }

    # ---- 4. 均线多头排列加分 ----
    ma20 = indicators.calc_sma(closes, 20)
    ma60 = indicators.calc_sma(closes, 60)
    ma_bullish = (ma20 is not None and ma60 is not None and ma20 > ma60)
    ma_score = 0.3 if ma_bullish else 0.0

    # ---- 5. 行业动量加分 ----
    sector_score = 0.0
    if sector_momentum and sector and sector in sector_momentum:
        sm = sector_momentum[sector]
        sector_score = max(0.0, min(0.3, sm / 0.1 * 0.3))

    # ---- 综合评分 ----
    score = 0.40  # 基础分：已突破

    if vol_breakout:
        score += 0.25  # 放量确认
    else:
        score += vol_score * 0.15  # 部分放量

    score += ma_score
    score += sector_score

    # RSI 在合理区间加分
    if 30 <= rsi <= 55:
        score += 0.10  # RSI 在健康区间

    score = min(1.0, score)

    if score >= 0.55:
        reason_parts = ['突破%d日高' % BK_BREAKOUT_PERIOD]
        if vol_breakout:
            reason_parts.append('放量%.1f' % vol_ratio)
        if ma_bullish:
            reason_parts.append('多头')
        if sector_score > 0:
            reason_parts.append('行业动量+')

        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'rsi': round(rsi, 1),
            'reason': 'BK_' + '|'.join(reason_parts),
        }

    return {
        'action': 'HOLD',
        'confidence': score,
        'score': round(score, 4),
        'reason': 'BK_突破但评分不足(%.3f)' % score,
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    突破策略出场逻辑。

    出场条件:
      1. 突破失败（3 日内回落到突破价下方 -3%）
      2. 固定止损
      3. 固定止盈
      4. 量能萎缩 + 价格高位 → 动量衰竭
    """
    closes = df['close'].values
    vols   = df['volume'].values

    if len(closes) < 5:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    # ---- 1. 突破失败检测 ----
    entry_date = pos_info.get('entry_date', '')
    if entry_date and today_str:
        try:
            from datetime import datetime as dt
            days_held = (dt.strptime(today_str, '%Y-%m-%d') -
                         dt.strptime(entry_date, '%Y-%m-%d')).days
            if days_held <= BK_FAIL_DAYS and pnl < BK_FAIL_DROP:
                return {
                    'action': 'SELL',
                    'confidence': 0.85,
                    'reason': 'BK_突破失败(%dd %+.1f%%)' % (days_held, pnl * 100),
                }
        except Exception:
            pass

    # ---- 2. 固定止损 ----
    if pnl <= -BK_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'BK_止损(%+.1f%%)' % (pnl * 100),
        }

    # ---- 3. 固定止盈 ----
    if pnl >= BK_TAKE_PROFIT:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'BK_止盈(%+.1f%%)' % (pnl * 100),
        }

    # ---- 4. 量能衰竭（高位缩量） ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    if pnl > 0.05 and vol_ratio < 0.6:
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'BK_高位缩量(%.1f)' % vol_ratio,
        }

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
