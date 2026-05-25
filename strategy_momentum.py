"""
strategy_momentum.py - 动量趋势策略 (V29)

趋势跟踪选手：做多强势股，捕捉持续上涨行情。
与均值回归策略形成互补 —— 趋势市中动量赚钱，震荡市中均值回归赚钱。

V29 优化（解决 -65.9% 亏损）:
  1. 入场门槛: score 0.35→0.55, 只取强动量
  2. 量能硬门: vol_ratio>=1.3（不再是纯打分）
  3. RSI 下限: >45（动量必须有强度）
  4. 均线分离度: MA20/MA60>1.5%（不再是纯>0）
  5. 金叉优先: 5日内金叉额外加分
  6. 移动止损: 盈利>5%后止盈线缩至10%

V18 信号逻辑:
  买入: 均线多头排列 (MA20 > MA60) + 价格在 MA20 上方 + 放量配合
  卖出: 价格跌破 MA20 或均线死叉
  置信度: 基于趋势强度（均线分离度 + 近期收益率 + 量能）
"""

import numpy as np
import config
import indicators


# 动量策略专用参数 (V29 收紧)
MOM_MA_FAST   = 20    # 快线
MOM_MA_SLOW   = 60    # 慢线
MOM_VOL_MIN   = 1.3   # V29: 1.1→1.3, 量能硬门提高
MOM_STOP_LOSS = 0.06  # 固定止损 6%
MOM_TAKE_PROFIT = 0.15  # 固定止盈 15%
MOM_STRENGTH_PERIOD = 10  # 趋势强度计算窗口
MOM_SCORE_MIN  = 0.55  # V29: 0.35→0.55, 只取强动量信号
MOM_MA_SPREAD_MIN = 0.015  # V29: 新增, MA20必须比MA60高1.5%
MOM_RSI_MIN    = 45    # V29: 新增, RSI下限，动量必须有强度
MOM_RSI_MAX    = 70    # V29: 75→70, 不在极端超买时追入
MOM_GOLDEN_CROSS_DAYS = 5  # V29: 新增, 5日内金叉优先
MOM_TRAIL_PROFIT = 0.05  # V29: 新增, 盈利5%后启动移动止盈


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

    # ---- V29: 硬门1 — 均线多头排列且有足够分离度 ----
    if ma60 <= 0:
        return None
    ma_spread = (ma20 - ma60) / ma60
    if ma_spread < MOM_MA_SPREAD_MIN:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_均线分离不足(%.1f%%<%.1f%%)' % (ma_spread * 100, MOM_MA_SPREAD_MIN * 100),
        }

    # ---- V29: 硬门2 — 价格必须在 MA20 上方 ----
    if cur_price <= ma20:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_价格未站上MA20(%.2f<=%.2f)' % (cur_price, ma20),
        }

    # ---- V29: 硬门3 — 量能必须达标（不再是纯打分） ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0
    if vol_ratio < MOM_VOL_MIN:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_量能不足(%.1f<%.1f)' % (vol_ratio, MOM_VOL_MIN),
        }

    # ---- V29: RSI 检查 — 必须在合理区间 ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None
    if rsi < MOM_RSI_MIN:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_RSI太弱(%.0f<%d)' % (rsi, MOM_RSI_MIN),
        }
    if rsi > MOM_RSI_MAX:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'MOM_RSI超买(%.0f>%d)' % (rsi, MOM_RSI_MAX),
        }

    # ---- 短期动量（近5日涨幅） ----
    if n >= 6:
        ret_5d = (closes[-1] / closes[-6] - 1)
    else:
        ret_5d = 0

    # ---- V29: 金叉检测（N日内金叉） ----
    golden_cross = False
    golden_cross_days = 999
    if prev_ma20 is not None and prev_ma60 is not None:
        # 当天金叉
        if prev_ma20 <= prev_ma60 and ma20 > ma60:
            golden_cross = True
            golden_cross_days = 0
        else:
            # 回溯N日看是否有最近金叉
            for lookback in range(1, MOM_GOLDEN_CROSS_DAYS + 1):
                idx = -(lookback + 1)
                if n < abs(idx) + MOM_MA_SLOW:
                    break
                past_closes = closes[:idx]
                if len(past_closes) < MOM_MA_SLOW + 1:
                    break
                past_ma20 = indicators.calc_sma(past_closes, MOM_MA_FAST)
                past_ma60 = indicators.calc_sma(past_closes, MOM_MA_SLOW)
                past_prev = closes[:idx - 1] if idx - 1 >= -len(closes) else None
                if past_ma20 is None or past_ma60 is None:
                    continue
                # 检查前一天
                past_prev_ma20 = indicators.calc_sma(closes[:idx - 1], MOM_MA_FAST) if len(closes[:idx - 1]) >= MOM_MA_FAST else None
                past_prev_ma60 = indicators.calc_sma(closes[:idx - 1], MOM_MA_SLOW) if len(closes[:idx - 1]) >= MOM_MA_SLOW else None
                if past_prev_ma20 is not None and past_prev_ma60 is not None:
                    if past_prev_ma20 <= past_prev_ma60 and past_ma20 > past_ma60:
                        golden_cross = True
                        golden_cross_days = lookback
                        break

    # ---- 趋势强度评分 ----
    # 1. 均线分离度
    spread_score = min(1.0, max(0.0, (ma_spread - MOM_MA_SPREAD_MIN) / 0.10))

    # 2. 近期涨幅: 10日收益率
    if n >= MOM_STRENGTH_PERIOD + 1:
        ret_10d = (closes[-1] / closes[-(MOM_STRENGTH_PERIOD + 1)] - 1)
    else:
        ret_10d = 0
    ret_score = min(1.0, max(0.0, (ret_10d + 0.03) / 0.18))  # -3%~15% → 0~1

    # 3. 量能打分
    vol_score = min(1.0, (vol_ratio - MOM_VOL_MIN) / 1.5)

    # 综合评分
    score = spread_score * 0.40 + ret_score * 0.30 + vol_score * 0.20 + (rsi - MOM_RSI_MIN) / 40 * 0.10

    # 金叉额外加分
    if golden_cross:
        score = min(1.0, score + 0.12 + max(0, 0.03 * (MOM_GOLDEN_CROSS_DAYS - golden_cross_days)))

    # ---- V29 决策: 门槛从 0.35 提高到 0.55 ----
    if score >= MOM_SCORE_MIN:
        reason_parts = []
        if golden_cross:
            if golden_cross_days == 0:
                reason_parts.append('金叉')
            else:
                reason_parts.append('%dd前金叉' % golden_cross_days)
        reason_parts.append('动量%.3f' % score)
        reason_parts.append('spread%.1f%%' % (ma_spread * 100))
        if ret_5d > 0:
            reason_parts.append('5d%+.1f%%' % (ret_5d * 100))

        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'reason': 'MOM_' + '|'.join(reason_parts),
            'ma20': round(ma20, 2),
            'ma60': round(ma60, 2),
            'spread': round(ma_spread * 100, 1),
            'rsi': round(rsi, 1),
        }

    # 趋势在、但评分不够 → 观望
    return {
        'action': 'HOLD',
        'confidence': score,
        'score': round(score, 4),
        'reason': 'MOM_评分%.3f不足(需≥%.2f)' % (score, MOM_SCORE_MIN),
    }


def check_exit(df, pos_info, regime='range', context=None):
    """
    动量策略出场逻辑 (V29)。

    出场条件:
      1. 价格跌破 MA20（趋势转弱）
      2. MA20 下穿 MA60（死叉）
      3. 固定止损/止盈
      4. V29: 移动止盈 — 盈利 > 5% 后止盈线缩至 10%
      5. RSI 极度超买 (>80, V29: 85→80)
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

    # 死叉检测需要前一根bar的均线值，确保closes[:-1]足够长
    prev_closes = closes[:-1]
    if len(prev_closes) < MOM_MA_SLOW:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
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

    # 4. V29: 移动止盈 — 盈利>5%后止盈线收紧至10%
    peak = pos_info.get('peak', cur_price)
    peak_pnl = (peak - cost) / cost
    if peak_pnl >= MOM_TRAIL_PROFIT and pnl < MOM_TAKE_PROFIT * 0.67:
        # 从高点回撤，用更紧的止盈
        effective_tp = MOM_TAKE_PROFIT * 0.67  # 10%
    else:
        effective_tp = MOM_TAKE_PROFIT

    if pnl >= effective_tp:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'MOM_止盈(%+.1f%%, 线%.0f%%)' % (pnl * 100, effective_tp * 100),
        }

    # 5. RSI 极度超买
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is not None and rsi > 80:
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'MOM_RSI极度超买(%.0f)' % rsi,
        }

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
