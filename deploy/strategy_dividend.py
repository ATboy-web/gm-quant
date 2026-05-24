"""
strategy_dividend.py - 红利策略 (V19.2)

适用于低波动防御行业（金融/消费/煤炭/公用事业），
以股息率+低估值为核心，追求稳健收益。

核心逻辑:
  买入:
    - 价格处于相对低位（近 60 日涨幅 < 5% 或近 20 日跌幅 > 3%）
    - 成交量不异常放量（排除利空出逃）
    - RSI 在 35-55 区间（非极端超卖，也不追高）
    - 均线长期趋势不破（价格 > MA60 或 MA20 接近 MA60）
  卖出:
    - 固定止盈 10%（防御股不贪）
    - 固定止损 5%（防守型，止损严格）
    - 时间止损 30 天无收益 → 退出
    - RSI > 75 过热

与其他策略的互补:
  - MR 看超卖反弹，DV 看低位价值
  - MOM 看趋势追涨，DV 看低位买入
  - VP 看量价背离，DV 不依赖量价
  - BK 看突破加速，DV 看低位稳健
"""

import numpy as np
import config
import indicators


# 红利策略参数
DV_LOOKBACK       = 60    # 长期回看窗口
DV_SHORT_LOOKBACK = 20    # 短期回看窗口
DV_STOP_LOSS      = 0.05  # 固定止损 5%
DV_TAKE_PROFIT    = 0.10  # 固定止盈 10%
DV_TIME_STOP      = 30    # 时间止损天数
DV_RSI_BUY_LOW    = 35    # RSI 买入下限
DV_RSI_BUY_HIGH   = 55    # RSI 买入上限


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    红利策略买入信号。

    检测:
      1. 价格处于相对低位（近 60 日涨幅不大 或 近 20 日有回调）
      2. 成交量不异常（排除恐慌出逃）
      3. RSI 在合理区间
      4. 均线长期趋势不破
    """
    closes = df['close'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < DV_LOOKBACK + 5:
        return None

    cur_price = float(closes[-1])

    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 1. 价格处于相对低位 ----
    # 近 60 日涨幅
    if n >= DV_LOOKBACK + 1 and closes[-(DV_LOOKBACK + 1)] > 0:
        ret_60d = (cur_price / closes[-(DV_LOOKBACK + 1)] - 1)
    else:
        ret_60d = 0

    # 近 20 日跌幅
    if n >= DV_SHORT_LOOKBACK + 1 and closes[-(DV_SHORT_LOOKBACK + 1)] > 0:
        ret_20d = (cur_price / closes[-(DV_SHORT_LOOKBACK + 1)] - 1)
    else:
        ret_20d = 0

    # 低位条件: 60日涨幅 < 5% 或 20日跌幅 > 3%
    low_position = (ret_60d < 0.05) or (ret_20d < -0.03)
    if not low_position:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'DV_价格非低位(60d:%+.1f%% 20d:%+.1f%%)' % (ret_60d * 100, ret_20d * 100),
        }

    # ---- 2. 成交量不异常放量 ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    if vol_ratio >= 2.5:
        # 异常放量，可能是利空出逃
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'reason': 'DV_异常放量(%.1f)可能利空' % vol_ratio,
        }

    vol_ok = (vol_ratio < 1.5)
    vol_score = max(0.0, (1.5 - vol_ratio) / 1.5) if vol_ratio < 1.5 else 0.0

    # ---- 3. RSI 在合理区间 ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    if rsi < DV_RSI_BUY_LOW:
        # 太低，可能还有下跌空间，让 MR 去处理
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'rsi': round(rsi, 1),
            'reason': 'DV_RSI太低(%.0f)让MR处理' % rsi,
        }

    if rsi > DV_RSI_BUY_HIGH:
        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'score': 0.0,
            'rsi': round(rsi, 1),
            'reason': 'DV_RSI偏高(%.0f)' % rsi,
        }

    rsi_score = 1.0 - abs(rsi - 45) / 20.0  # RSI=45 时满分
    rsi_score = max(0.0, min(1.0, rsi_score))

    # ---- 4. 均线长期趋势不破 ----
    ma20 = indicators.calc_sma(closes, 20)
    ma60 = indicators.calc_sma(closes, 60)

    ma_ok = False
    ma_score = 0.0
    if ma60 is not None and cur_price > ma60:
        ma_ok = True
        ma_score = 0.4
    elif ma20 is not None and ma60 is not None:
        # MA20 接近 MA60，可能是支撑位
        spread = abs(ma20 - ma60) / ma60
        if spread < 0.03:
            ma_ok = True
            ma_score = 0.2

    # ---- 综合评分 ----
    score = 0.20  # 基础分：已在低位

    score += 0.25 * rsi_score   # RSI 在合理区间
    score += 0.20 * vol_score  # 成交量平稳
    score += ma_score           # 均线支撑
    score += 0.10 if ret_20d < -0.05 else 0.0  # 近期回调较大
    score += 0.05 if vol_ok else 0.0           # 量能平稳加分

    score = min(1.0, score)

    if score >= 0.60:
        reason_parts = ['低位']
        if ret_20d < -0.05:
            reason_parts.append('回调%.1f%%' % (ret_20d * 100))
        if vol_ok:
            reason_parts.append('量稳')
        if ma_ok:
            reason_parts.append('MA支撑')
        reason_parts.append('RSI=%.0f' % rsi)

        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'rsi': round(rsi, 1),
            'reason': 'DV_' + '|'.join(reason_parts),
        }

    return {
        'action': 'HOLD',
        'confidence': score,
        'score': round(score, 4),
        'rsi': round(rsi, 1),
        'reason': 'DV_评分不足(%.3f)' % score,
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    红利策略出场逻辑。

    出场条件:
      1. 固定止损 5%
      2. 固定止盈 10%
      3. 时间止损（30 天无收益）
      4. RSI 过热 > 75
    """
    closes = df['close'].values

    if len(closes) < 2:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    # 1. 固定止损
    if pnl <= -DV_STOP_LOSS:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'DV_止损(%+.1f%%)' % (pnl * 100),
        }

    # 2. 固定止盈
    if pnl >= DV_TAKE_PROFIT:
        return {
            'action': 'SELL',
            'confidence': 0.85,
            'reason': 'DV_止盈(%+.1f%%)' % (pnl * 100),
        }

    # 3. RSI 过热
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is not None and rsi > 75:
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'DV_RSI过热(%.0f)' % rsi,
        }

    # 4. 时间止损
    entry_date = pos_info.get('entry_date', '')
    if entry_date and today_str:
        try:
            from datetime import datetime as dt
            days = (dt.strptime(today_str, '%Y-%m-%d') -
                    dt.strptime(entry_date, '%Y-%m-%d')).days
            if days >= DV_TIME_STOP and pnl < 0.01:
                return {
                    'action': 'SELL',
                    'confidence': 0.7,
                    'reason': 'DV_时间止损(%dd)' % days,
                }
        except Exception:
            pass

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
