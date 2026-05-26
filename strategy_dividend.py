"""
strategy_dividend.py - 红利策略 (V29)

适用于低波动防御行业（金融/消费/煤炭/公用事业），
以股息率+低估值为核心，追求稳健收益。

V29 优化（解决 -32.2% 亏损、153笔高频低质交易）:
  1. "低位"重定义: 60d涨幅<0% AND 20d跌幅<-4%（原 OR，门槛大幅提高）
  2. RSI区间收窄: 33-52（原 30-60）
  3. 入场门槛: 0.60→0.72
  4. 止损放宽: 5%→6%（减少正常波动被止损）
  5. 时间止损: 30→18天（更快淘汰无效持仓）
  6. 新增MA过滤: 价格必须低于MA60（真正的价值买点）

V18 核心逻辑:
  买入:
    - 价格处于相对低位（近 60 日下跌 + 近 20 日明显回调）
    - 成交量不异常放量（排除利空出逃）
    - RSI 在 33-52 区间（非极端，但不追高）
    - 价格低于 MA60（价值区间）
  卖出:
    - 固定止盈 10%（防御股不贪）
    - 固定止损 6%
    - 时间止损 18 天无收益 → 退出
    - RSI > 70 过热
"""

import numpy as np
import config
import indicators


# 红利策略参数 (V29 收紧)
DV_LOOKBACK       = 60    # 长期回看窗口
DV_SHORT_LOOKBACK = 20    # 短期回看窗口
DV_STOP_LOSS      = 0.06  # V29: 0.05→0.06, 放宽减少噪音止损
DV_TAKE_PROFIT    = 0.10  # 固定止盈 10%
DV_TIME_STOP      = 18    # V29: 30→18, 更快淘汰无效持仓
DV_RSI_BUY_LOW    = 33    # V29: 30→33, RSI下限收窄
DV_RSI_BUY_HIGH   = 52    # V29: 60→52, RSI上限收窄
DV_SCORE_MIN      = 0.72  # V29: 0.60→0.72, 入场门槛提高
DV_LONG_RET_MAX   = 0.0   # V29: 新增, 60d涨幅必须<0%
DV_SHORT_RET_MIN  = -0.04 # V29: 新增, 20d跌幅必须<-4%


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    红利策略买入信号 (V29)。

    检测:
      1. V29: 价格处于相对低位（60d 下跌 AND 20d 明显回调）
      2. 成交量不异常（排除恐慌出逃）
      3. RSI 在 33-52 区间
      4. V29: 价格低于 MA60（价值买入区间）
    """
    closes = df['close'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < DV_LOOKBACK + 5:
        return None

    cur_price = float(closes[-1])

    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- V29: 硬门1 — 价格处于相对低位（AND 关系，不再是 OR） ----
    # 近 60 日涨幅 < 0（必须下跌）
    if n >= DV_LOOKBACK + 1 and closes[-(DV_LOOKBACK + 1)] > 0:
        ret_60d = (cur_price / closes[-(DV_LOOKBACK + 1)] - 1)
    else:
        ret_60d = 0

    # 近 20 日跌幅
    if n >= DV_SHORT_LOOKBACK + 1 and closes[-(DV_SHORT_LOOKBACK + 1)] > 0:
        ret_20d = (cur_price / closes[-(DV_SHORT_LOOKBACK + 1)] - 1)
    else:
        ret_20d = 0

    # V29: 双重条件 — 60d必须下跌 AND 20d必须明显回调
    if ret_60d >= DV_LONG_RET_MAX:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'DV_60d未下跌(%+.1f%%)' % (ret_60d * 100),
        }
    if ret_20d > DV_SHORT_RET_MIN:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'DV_20d回调不足(%+.1f%%>%.0f%%)' % (ret_20d * 100, DV_SHORT_RET_MIN * 100),
        }

    # ---- 2. 成交量不异常放量 ----
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    if vol_ratio >= 2.5:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'DV_异常放量(%.1f)可能利空' % vol_ratio,
        }

    vol_ok = (vol_ratio < 1.5)
    vol_score = max(0.0, (1.5 - vol_ratio) / 1.5) if vol_ratio < 1.5 else 0.0

    # ---- 3. RSI 在合理区间 ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    if rsi < DV_RSI_BUY_LOW:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'rsi': round(rsi, 1),
            'reason': 'DV_RSI太低(%.0f)让MR处理' % rsi,
        }

    if rsi > DV_RSI_BUY_HIGH:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'rsi': round(rsi, 1),
            'reason': 'DV_RSI偏高(%.0f)' % rsi,
        }

    rsi_score = 1.0 - abs(rsi - 42) / 20.0  # V29: RSI=42 时满分
    rsi_score = max(0.0, min(1.0, rsi_score))

    # ---- V29: 硬门4 — 价格必须低于 MA60（价值区间） ----
    ma20 = indicators.calc_sma(closes, 20)
    ma60 = indicators.calc_sma(closes, 60)

    if ma60 is None:
        return None
    if cur_price >= ma60:
        return {
            'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'reason': 'DV_价格高于MA60(%.2f>=%.2f)' % (cur_price, ma60),
        }

    # MA20 接近 MA60（均线收敛中的价值区域）
    ma_converge = False
    if ma20 is not None and ma60 > 0:
        spread = abs(ma20 - ma60) / ma60
        if spread < 0.04:
            ma_converge = True

    # ---- V29 综合评分 ----
    score = 0.15  # 基础分：60d下跌+20d回调

    score += 0.25 * rsi_score       # RSI 在合理区间
    score += 0.15 * vol_score       # 成交量平稳
    score += 0.15 if ma_converge else 0.05  # 均线收敛加分
    score += 0.10 if ret_20d < -0.08 else 0.0  # 20d跌超8%额外加分
    score += 0.15 if ret_60d < -0.15 else 0.0  # 60d跌超15%深度价值
    score += 0.10 if vol_ok else 0.0            # 量能平稳

    score = min(1.0, score)

    if score >= DV_SCORE_MIN:
        reason_parts = ['价值']
        reason_parts.append('60d%+.1f%%' % (ret_60d * 100))
        reason_parts.append('20d%+.1f%%' % (ret_20d * 100))
        if ma_converge:
            reason_parts.append('MA收敛')
        if vol_ok:
            reason_parts.append('量稳')
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
        'reason': 'DV_评分不足(%.3f<%.2f)' % (score, DV_SCORE_MIN),
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    红利策略出场逻辑 (V29)。

    出场条件:
      1. 固定止损 6%
      2. 固定止盈 10%
      3. 时间止损（18 天无收益）
      4. RSI 过热 > 70 (V29: 75→70)
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

    # 3. RSI 过热 (V29: 75→70, 防御股不需要太热)
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is not None and rsi > 70:
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
