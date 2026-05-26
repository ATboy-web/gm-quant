"""
strategy_sr.py - 板块轮动策略 (V29.8, 替代原 DV 红利策略)

原 DV (红利/防御) 问题:
  - AND 条件(60d<0% AND 20d<-4%) + 价格<MA60 = 熊市防御逻辑
  - 2024-2026牛市中仅14笔/35.7%胜
  - 牛市中防御型策略天然低效

新 SR (板块轮动) 逻辑:
  买弱势板块中有反弹潜力的个股 — 捕捉资金轮动。
  不防御，主动进攻。

入口条件:
  1. 股票所属行业在近20日动量最低的3个行业中
  2. 个股RSI在20-40区间（超卖但非死猫跳）
  3. 今日放量阳线（量>1.2x均量 + 收阳）
  4. 价格高于3日低点（已止血，不再创新低）

出场:
  - 止盈 +6%（轮动行情不贪）
  - 止损 -4%（紧止损）
  - 时间止损 8天（板块不转就撤）
  - RSI > 65 过热止盈
"""

import numpy as np
import config
import indicators


SR_PERIOD       = 20     # 行业动量回看窗口
SR_RSI_LOW      = 20     # RSI 下限
SR_RSI_HIGH     = 40     # RSI 上限
SR_VOL_SURGE    = 1.2    # 确认量比
SR_STOP_LOSS    = 0.04   # 止损 4%
SR_TAKE_PROFIT  = 0.06   # 止盈 6%
SR_TIME_STOP    = 8      # 时间止损天数
SR_SECTOR_RANK  = 3      # 取动量最差的N个行业


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    板块轮动买入信号。

    核心: 买最弱行业中止血反弹的个股，赌资金轮动。

    Args:
        df: DataFrame
        sector: 行业名
        sector_momentum: dict of {sector: momentum_score}
        regime: 市场状态
    """
    closes = df['close'].values
    opens  = df['open'].values
    highs  = df['high'].values
    lows   = df['low'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < SR_PERIOD + 3:
        return None

    cur_price = float(closes[-1])
    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    # ---- 硬门1: 行业必须处于弱势（动量最低的N个行业） ----
    if sector is None or sector_momentum is None:
        return None

    # 按动量排序，取最差的 N 个
    sorted_sectors = sorted(sector_momentum.items(), key=lambda x: x[1])
    weak_sectors = set(s[0] for s in sorted_sectors[:SR_SECTOR_RANK])

    if sector not in weak_sectors:
        return None  # 不在弱势行业，不做轮动

    # ---- 硬门2: RSI 在超卖区间 ----
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None

    if rsi < SR_RSI_LOW or rsi > SR_RSI_HIGH:
        return {
            'action': 'HOLD', 'confidence': 0, 'score': 0,
            'reason': 'SR_RSI=%.0f不在(%d-%d)' % (rsi, SR_RSI_LOW, SR_RSI_HIGH),
        }

    # ---- 硬门3: 已止血（不再创新低） ----
    price_3d_low = np.min(lows[-3:])
    if cur_price <= price_3d_low:
        return {
            'action': 'HOLD', 'confidence': 0, 'score': 0,
            'reason': 'SR_还在创新低',
        }

    # ---- 确认: 放量阳线 ----
    is_green = (closes[-1] > opens[-1])
    vol_20d_avg = np.mean(vols[-SR_PERIOD:])
    vol_ratio = vols[-1] / vol_20d_avg if vol_20d_avg > 0 else 1.0
    has_volume = (vol_ratio >= SR_VOL_SURGE)

    if not (is_green and has_volume):
        return {
            'action': 'HOLD', 'confidence': 0.2, 'score': 0.2,
            'reason': 'SR_未确认(阳线=%s 放量=%s %.1fx)' % (is_green, has_volume, vol_ratio),
        }

    # ---- 评分 ----
    score = 0.40   # 基础: 弱势行业 + 超卖 + 放量阳线

    # 加分: 连续2日阳线
    if n >= 2 and closes[-2] > opens[-2]:
        score += 0.10

    # 加分: 从低点反弹了
    price_5d_low = np.min(lows[-5:])
    rebound_pct = (cur_price - price_5d_low) / price_5d_low if price_5d_low > 0 else 0
    if rebound_pct > 0.03:
        score += 0.10

    # 加分: 价格站上MA5
    ma5 = indicators.calc_sma(closes, 5)
    if ma5 and cur_price > ma5:
        score += 0.10

    # 加分: RSI 在甜点区 (25-35)
    if 25 <= rsi <= 35:
        score += 0.10

    # 行业动量越差，轮动潜力越大
    sector_mom = sector_momentum.get(sector, 0)
    if sector_mom < -0.05:
        score += 0.10

    score = min(1.0, score)

    if score < 0.45:
        return {
            'action': 'HOLD', 'confidence': score,
            'score': round(score, 4),
            'reason': 'SR_弱(%.2f)' % score,
        }

    return {
        'action': 'BUY',
        'confidence': score,
        'score': round(score, 4),
        'rsi': round(rsi, 1),
        'reason': 'SR_弱势行业反弹|%s' % sector,
    }


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    SR 出场逻辑:
      1. 止盈 +6%
      2. 止损 -4%
      3. 时间止损 8天
      4. RSI > 65 过热
    """
    closes = df['close'].values
    highs  = df['high'].values
    vols   = df['volume'].values
    n = len(closes)
    if n < 3:
        return None

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    peak = pos_info.get('peak', cost)
    bar_count = pos_info.get('bar_count', 0)
    pnl_pct = (cur_price - cost) / cost

    if cur_price > peak:
        pos_info['peak'] = cur_price

    rsi = indicators.calc_rsi(closes, period=14)

    # 止损
    if pnl_pct <= -SR_STOP_LOSS:
        return {
            'action': 'SELL', 'price': cur_price,
            'reason': 'SR_止损(%.1f%%)' % (pnl_pct * 100),
        }

    # 止盈
    if pnl_pct >= SR_TAKE_PROFIT:
        return {
            'action': 'SELL', 'price': cur_price,
            'reason': 'SR_止盈(%.1f%%)' % (pnl_pct * 100),
        }

    # 时间止损
    if bar_count >= SR_TIME_STOP and pnl_pct <= 0:
        return {
            'action': 'SELL', 'price': cur_price,
            'reason': 'SR_时间止损(%dd)' % bar_count,
        }

    # RSI 过热
    if rsi and rsi > 65 and pnl_pct > 0:
        return {
            'action': 'SELL', 'price': cur_price,
            'reason': 'SR_RSI过热(%.0f)' % rsi,
        }

    # 放量滞涨
    if n >= 5:
        vol_avg = np.mean(vols[-5:])
        if vols[-1] > vol_avg * 1.2 and closes[-1] < closes[-2] and pnl_pct > 0:
            return {
                'action': 'SELL', 'price': cur_price,
                'reason': 'SR_放量滞涨',
            }

    return None
