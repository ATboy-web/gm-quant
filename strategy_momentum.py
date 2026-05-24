"""
strategy_momentum.py - 动量趋势策略 (V18)

趋势跟踪选手：做多强势股，捕捉持续上涨行情。
与均值回归策略形成互补 —— 趋势市中动量赚钱，震荡市中均值回归赚钱。

信号逻辑:
  买入: 均线多头排列 (MA20 > MA60) + 价格在 MA20 上方 + 放量配合
  卖出: 价格跌破 MA20 或均线死叉
  置信度: 基于趋势强度（均线分离度 + 近期收益率 + 量能）
"""

import numpy as np
import config
import indicators


# 动量策略专用参数
MOM_MA_FAST   = 20    # 快线
MOM_MA_SLOW   = 60    # 慢线
MOM_VOL_MIN   = 1.1   # 最小量比
MOM_STOP_LOSS = 0.06  # 固定止损 6%
MOM_TAKE_PROFIT = 0.15  # 固定止盈 15%
MOM_STRENGTH_PERIOD = 10  # 趋势强度计算窗口


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    动量趋势买入信号。

    Args:
        df: DataFrame with [open, high, low, close, volume]
        sector: 行业（未使用，保留接口）
        sector_momentum: 行业动量（未使用）
        regime: 市场状态

    Returns:
        dict | None: {'action', 'confidence', 'score', 'reason'}
    """
    closes = df['close'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < MOM_MA_SLOW + 1:
        return None

    cur_price = float(closes[-1])

    # ---- 价格过滤 ----
    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 均线计算 ----
    ma20 = indicators.calc_sma(closes, MOM_MA_FAST)
    ma60 = indicators.calc_sma(closes, MOM_MA_SLOW)

    if ma20 is None or ma60 is None:
        return None

    prev_closes = closes[:-1]
    prev_ma20 = indicators.calc_sma(prev_closes, MOM_MA_FAST)
    prev_ma60 = indicators.calc_sma(prev_closes, MOM_MA_SLOW)

    # ---- 条件1: 均线多头排列 ----
    ma_bullish = (ma20 > ma60)

    # ---- 条件2: 价格在 MA20 上方 ----
    price_above_ma20 = (cur_price > ma20)

    # ---- 条件3: 量能确认 ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0
    vol_ok = (vol_ratio >= MOM_VOL_MIN)

    # ---- 条件4: 短期动量（近5日涨幅） ----
    if n >= 6:
        ret_5d = (closes[-1] / closes[-6] - 1)
    else:
        ret_5d = 0

    # ---- 条件5: 避免追太高 ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is not None and rsi > 75:
        # 已经严重超买，动量策略也应该暂缓
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'MOM_RSI超买(%.0f)，暂不追高' % rsi,
        }

    # ---- 均线金叉加分 ----
    golden_cross = False
    if prev_ma20 is not None and prev_ma60 is not None:
        golden_cross = (prev_ma20 <= prev_ma60) and (ma20 > ma60)

    # ---- 趋势强度评分 ----
    # 1. 均线分离度: MA20偏离MA60的程度
    ma_spread = (ma20 - ma60) / ma60 if ma60 > 0 else 0
    spread_score = min(1.0, max(0.0, ma_spread / 0.10))  # 10% = 满分

    # 2. 近期涨幅: 10日收益率
    if n >= MOM_STRENGTH_PERIOD + 1:
        ret_10d = (closes[-1] / closes[-(MOM_STRENGTH_PERIOD + 1)] - 1)
    else:
        ret_10d = 0
    ret_score = min(1.0, max(0.0, (ret_10d + 0.05) / 0.15))  # -5%~10% → 0~1

    # 3. 量能打分
    vol_score = min(1.0, (vol_ratio - 0.8) / 1.2)

    # 综合评分
    score = spread_score * 0.4 + ret_score * 0.35 + vol_score * 0.25

    # 金叉额外加分
    if golden_cross:
        score = min(1.0, score + 0.15)

    # ---- 决策 ----
    if ma_bullish and price_above_ma20 and score >= 0.50:
        reason_parts = []
        if golden_cross:
            reason_parts.append('金叉')
        reason_parts.append('多头排列')
        reason_parts.append('动量%.3f' % score)
        if ret_5d > 0:
            reason_parts.append('5d: %+.1f%%' % (ret_5d * 100))

        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'reason': 'MOM_' + '|'.join(reason_parts),
            'ma20': round(ma20, 2),
            'ma60': round(ma60, 2),
            'spread': round(ma_spread * 100, 1),
        }

    # 趋势在、但评分不够 → 观望而非卖出
    if ma_bullish:
        return {
            'action': 'HOLD',
            'confidence': score,
            'score': round(score, 4),
            'reason': 'MOM_评分%.3f不足(需≥0.50)' % score,
        }

    return {
        'action': 'HOLD',
        'confidence': 0.0,
        'score': 0.0,
        'reason': 'MOM_非多头排列',
    }


def check_exit(df, pos_info, regime='range', context=None):
    """
    动量策略出场逻辑。

    出场条件:
      1. 价格跌破 MA20（趋势转弱）
      2. MA20 下穿 MA60（死叉）
      3. 固定止损/止盈
      4. RSI 极度超买 (>85)
    """
    closes = df['close'].values

    if len(closes) < MOM_MA_SLOW + 1:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    ma20 = indicators.calc_sma(closes, MOM_MA_FAST)
    ma60 = indicators.calc_sma(closes, MOM_MA_SLOW)

    if ma20 is None or ma60 is None:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    prev_closes = closes[:-1]
    prev_ma20 = indicators.calc_sma(prev_closes, MOM_MA_FAST)
    prev_ma60 = indicators.calc_sma(prev_closes, MOM_MA_SLOW)

    # 1. 死叉 = 立即出场
    if prev_ma20 is not None and prev_ma60 is not None:
        if prev_ma20 >= prev_ma60 and ma20 < ma60:
            return {
                'action': 'SELL',
                'confidence': 1.0,
                'reason': 'MOM_死叉(MA20<MA60)',
            }

    # 2. 跌破 MA20（V19: 需连续2天跌破才触发，避免单日噪音）
    if cur_price < ma20:
        # 检查前一天是否也跌破
        prev_below_ma20 = False
        if len(closes) >= 2:
            prev_price = float(closes[-2])
            prev_ma20_check = indicators.calc_sma(closes[:-1], MOM_MA_FAST)
            if prev_ma20_check is not None and prev_price < prev_ma20_check:
                prev_below_ma20 = True

        if prev_below_ma20:
            # 连续2天跌破 → 确认趋势转弱
            return {
                'action': 'SELL',
                'confidence': 0.9,
                'reason': 'MOM_连续跌破MA20(%.2f<%.2f)' % (cur_price, ma20),
            }
        # 仅1天跌破 → 降低置信度，需要融合投票决定
        return {
            'action': 'SELL',
            'confidence': 0.5,   # V19: 降低置信度，不再是铁板出场
            'reason': 'MOM_短暂破MA20(%.2f<%.2f)' % (cur_price, ma20),
        }

    # 3. 固定止损
    if pnl <= -MOM_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'MOM_止损(%+.1f%%)' % (pnl * 100),
        }

    # 4. 固定止盈
    if pnl >= MOM_TAKE_PROFIT:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'MOM_止盈(%+.1f%%)' % (pnl * 100),
        }

    # 5. RSI 极度超买
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is not None and rsi > 85:
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'MOM_RSI极度超买(%.0f)' % rsi,
        }

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
