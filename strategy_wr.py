"""
strategy_wr.py - Williams %R 超卖反弹策略 (V22)

Williams %R 与 RSI 互补：RSI看价格变化速度，WR看价格在近期区间的相对位置。
WR < -80 时价格接近近期低点，配合量缩 = 恐慌抛售尾声，反弹概率高。

核心逻辑:
  买入:
    1. Williams %R < -85 (极度超卖)
    2. 成交量不异常放大（排除恐慌出逃）
    3. RSI < 40（确认超卖，避免追低）
    4. 价格 > 20日最低点 * 1.02（已有止跌迹象）
  卖出:
    1. WR > -20 (超买区)
    2. 止损 5%
    3. 止盈 8%
    4. 时间止损 10天
"""

import numpy as np
import config
import indicators


# Williams %R 策略参数
WR_PERIOD       = 14     # WR 周期
WR_BUY          = -85    # WR 买入阈值（极度超卖）
WR_EXIT         = -20    # WR 出场阈值（超买）
WR_STOP_LOSS    = 0.05   # 止损 5%
WR_TAKE_PROFIT  = 0.08   # 止盈 8%
WR_TIME_STOP    = 10     # 时间止损天数


def _calc_williams_r(highs, lows, closes, period=14):
    """计算 Williams %R。值范围 [-100, 0]"""
    n = len(closes)
    if n < period:
        return None
    hh = max(highs[-period:])
    ll = min(lows[-period:])
    if hh == ll:
        return 0
    return (hh - closes[-1]) / (hh - ll) * -100


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    Williams %R 超卖反弹买入信号。
    """
    closes = df['close'].values
    highs  = df['high'].values
    lows   = df['low'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < WR_PERIOD + 5:
        return None

    cur_price = float(closes[-1])
    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 1. Williams %R 极度超卖 ----
    wr = _calc_williams_r(highs, lows, closes, WR_PERIOD)
    if wr is None:
        return None

    if wr > WR_BUY:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'WR_未超卖(%.0f > %d)' % (wr, WR_BUY),
        }

    # ---- 2. 量能确认（不放量 = 非恐慌出逃） ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    if vol_ratio >= 2.0:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'WR_异常放量(%.1f)恐慌中' % vol_ratio,
        }

    # ---- 3. RSI 确认 ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    if rsi > 40:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'rsi': round(rsi, 1),
            'reason': 'WR_RSI偏高(%.0f)非超卖' % rsi,
        }

    # ---- 4. 止跌确认（价格 > 20日最低 * 1.02） ----
    price_20d_low = min(lows[-20:])
    if cur_price <= price_20d_low * 1.02:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'WR_价格仍在低点(未止跌)',
        }

    # ---- 评分 ----
    wr_depth = abs(wr - WR_BUY) / abs(WR_BUY)  # 超卖深度
    score = 0.25 + wr_depth * 0.45  # 基础0.25 + 深度0~0.45

    if rsi < 25:
        score += 0.15  # RSI极度超卖加分
    elif rsi < 35:
        score += 0.08

    if vol_ratio < 1.0:
        score += 0.10  # 缩量加分

    # 行业动量正向加分
    if sector_momentum and sector and sector in sector_momentum:
        sm = sector_momentum[sector]
        if sm > 0:
            score += min(0.10, sm * 0.3)

    score = min(1.0, score)

    if score >= 0.50:
        reason_parts = ['WR极度超卖%.0f' % wr]
        if rsi < 30:
            reason_parts.append('RSI=%.0f' % rsi)
        if vol_ratio < 1.0:
            reason_parts.append('缩量')
        return {
            'action': 'BUY',
            'confidence': score,
            'score': round(score, 4),
            'rsi': round(rsi, 1),
            'reason': 'WR_' + '|'.join(reason_parts),
        }

    return {
        'action': 'HOLD', 'confidence': score, 'score': round(score, 4),
        'rsi': round(rsi, 1), 'reason': 'WR_评分不足(%.3f)' % score,
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    Williams %R 出场逻辑。
    """
    closes = df['close'].values
    highs  = df['high'].values
    lows   = df['low'].values

    if len(closes) < WR_PERIOD + 1:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost

    # 1. WR 进入超买区
    wr = _calc_williams_r(highs, lows, closes, WR_PERIOD)
    if wr is not None and wr > WR_EXIT:
        return {
            'action': 'SELL', 'confidence': 0.80,
            'reason': 'WR_超买(%.0f)' % wr,
        }

    # 2. 止损
    if pnl <= -WR_STOP_LOSS:
        return {
            'action': 'SELL', 'confidence': 1.0,
            'reason': 'WR_止损(%+.1f%%)' % (pnl * 100),
        }

    # 3. 止盈
    if pnl >= WR_TAKE_PROFIT:
        return {
            'action': 'SELL', 'confidence': 0.80,
            'reason': 'WR_止盈(%+.1f%%)' % (pnl * 100),
        }

    # 4. 时间止损
    entry_date = pos_info.get('entry_date', '')
    if entry_date and today_str:
        try:
            from datetime import datetime as dt
            days = (dt.strptime(today_str, '%Y-%m-%d') -
                    dt.strptime(entry_date, '%Y-%m-%d')).days
            if days >= WR_TIME_STOP and pnl < 0.01:
                return {
                    'action': 'SELL', 'confidence': 0.7,
                    'reason': 'WR_时间止损(%dd)' % days,
                }
        except Exception:
            pass

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}
