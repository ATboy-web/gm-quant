"""
indicators.py - 技术指标计算模块 (V16 扩展版)

所有函数均为纯函数: 输入 numpy 数组，输出计算结果。
不依赖 GM SDK 或任何外部状态，方便单独测试和复用。

指标清单:
  calc_rsi()             - 相对强弱指标
  calc_atr()             - 平均真实波幅（动态止损基础）
  calc_sma()             - 简单移动平均
  calc_volume_ratio()    - 量比（当日量 / N日均量）
  calc_drawdown()        - 近期最大回撤幅度
  detect_reversal()      - K线反转形态识别
  detect_bullish_engulfing() - 看涨吞没形态
  detect_hammer()        - 锤子线形态
  classify_regime()      - 市场状态分类（牛/熊/震荡）
"""

import numpy as np


# =============================================================================
# RSI — 相对强弱指标
# =============================================================================

def calc_rsi(closes, period=6):
    """
    计算 RSI（相对强弱指标）。

    算法:
      1. 取最近 period+1 个收盘价，计算 period 个涨跌变化 ΔP
      2. 分离涨幅（正值）和跌幅（负值取绝对值）
      3. RS = 平均涨幅 / 平均跌幅
      4. RSI = 100 - 100 / (1 + RS)

    参数:
        closes : np.ndarray  收盘价序列（旧→新）
        period : int         RSI 周期，默认 6

    返回:
        float | None  RSI ∈ [0, 100]，数据不足返回 None
    """
    n = len(closes)
    if n < period + 1:
        return None

    recent = closes[-(period + 1):]
    deltas = np.diff(recent)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)

    if avg_loss == 0:
        return 100.0  # 全涨 → RSI 满值

    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


# =============================================================================
# ATR — 平均真实波幅（动态止损核心指标）
# =============================================================================

def calc_atr(highs, lows, closes, period=14):
    """
    计算 ATR（Average True Range，平均真实波幅）。

    ATR 度量的是价格的真实波动范围，考虑隔夜跳空影响。
    用于动态止损: 止损幅度 = N × ATR，而非固定百分比。

    算法:
      1. True Range = max(当日高-当日低,
                          |当日高-前日收|,
                          |当日低-前日收|)
      2. ATR = TR 的 N 日简单移动平均

    参数:
        highs  : np.ndarray  最高价序列
        lows   : np.ndarray  最低价序列
        closes : np.ndarray  收盘价序列
        period : int         ATR 周期，默认 14

    返回:
        float | None  ATR 值，数据不足返回 None

    使用示例:
        对于价格为 10 元的股票，ATR=0.3 → 波动率 3%
        1.5x ATR 止损 = 4.5% — 给正常波动留足空间
    """
    n = len(closes)
    if n < period + 1:
        return None

    # 取最近 period+1 个 bar
    h = highs[-(period + 1):]
    l = lows[-(period + 1):]
    c = closes[-(period + 1):]

    # 计算 True Range
    tr_list = []
    for i in range(1, len(h)):
        tr = max(
            h[i] - l[i],                     # 当日振幅
            abs(h[i] - c[i - 1]),            # 当日高 - 前收
            abs(l[i] - c[i - 1])             # 当日低 - 前收
        )
        tr_list.append(tr)

    return float(np.mean(tr_list))


def calc_atr_pct(highs, lows, closes, period=14):
    """
    计算 ATR 占价格的比例（波动率百分比）。

    返回:
        float | None  ATR / 当前价格，如 0.03 表示波动率 3%
    """
    atr = calc_atr(highs, lows, closes, period)
    if atr is None:
        return None
    price = closes[-1]
    if price <= 0:
        return None
    return atr / price


# =============================================================================
# SMA — 简单移动平均
# =============================================================================

def calc_sma(closes, period=20):
    """
    计算简单移动平均（SMA）。

    参数:
        closes : np.ndarray  收盘价序列
        period : int         均线周期

    返回:
        float | None  MA 值
    """
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))


# =============================================================================
# 成交量分析
# =============================================================================

def calc_volume_ratio(volumes, period=20):
    """
    计算量比: 当日成交量 / N 日均量。

    放量说明有资金介入，配合 RSI 超卖可能是反转信号。
    缩量反弹则可靠性较低。

    参数:
        volumes : np.ndarray  成交量序列
        period  : int         均量周期

    返回:
        float | None  量比，如 1.5 表示放量 50%
    """
    n = len(volumes)
    if n < period + 1:
        return None

    today_vol = float(volumes[-1])
    avg_vol   = float(np.mean(volumes[-(period + 1):-1]))

    if avg_vol <= 0:
        return 1.0

    return today_vol / avg_vol


# =============================================================================
# 跌幅分析
# =============================================================================

def calc_drawdown(closes, period=20):
    """
    计算近期最大回撤（从 N 日内最高点到当前价的跌幅）。

    均值回归策略的核心假设: 跌幅越大，反弹动力越强。
    但需要配合其他因子过滤持续下跌的"价值陷阱"。

    参数:
        closes : np.ndarray  收盘价序列
        period : int         回看窗口

    返回:
        float | None  回撤比例，如 0.15 表示从高点跌了 15%
    """
    if len(closes) < period:
        return None

    recent  = closes[-period:]
    peak    = np.max(recent)
    current = recent[-1]

    if peak <= 0:
        return None

    return (peak - current) / peak


# =============================================================================
# K线反转形态识别
# =============================================================================

def detect_bullish_engulfing(opens, highs, lows, closes):
    """
    识别看涨吞没形态。

    形态特征:
      - 前一日为阴线（close < open）
      - 当日为阳线（close > open）
      - 当日实体完全吞没前一日实体
        (当日开 ≤ 前日收 AND 当日收 ≥ 前日开)

    看涨吞没是强反转信号，尤其在下跌趋势末端出现时。

    返回:
        bool
    """
    if len(closes) < 2:
        return False

    prev_open  = float(opens[-2])
    prev_close = float(closes[-2])
    cur_open   = float(opens[-1])
    cur_close  = float(closes[-1])

    # 前日阴线
    if prev_close >= prev_open:
        return False
    # 当日阳线
    if cur_close <= cur_open:
        return False
    # 吞没条件
    if cur_open <= prev_close and cur_close >= prev_open:
        return True

    return False


def detect_hammer(opens, highs, lows, closes):
    """
    识别锤子线形态。

    形态特征:
      - 实体较小（实体 / 总振幅 < 0.3）
      - 下影线很长（下影线 ≥ 2 × 实体）
      - 上影线很短（上影线 ≤ 0.3 × 实体）
      - 出现在下跌趋势中（由调用方确认）

    锤子线表示卖方曾大幅打压但买方强势反击，
    是潜在的底部反转信号。

    返回:
        bool
    """
    if len(closes) < 1:
        return False

    op   = float(opens[-1])
    hi   = float(highs[-1])
    lo   = float(lows[-1])
    cl   = float(closes[-1])

    body   = abs(cl - op)
    total  = hi - lo
    upper  = hi - max(op, cl)
    lower  = min(op, cl) - lo

    if total <= 0 or body <= 0:
        return False

    # 实体占比小（< 30% 振幅）
    if body / total > 0.3:
        return False

    # 下影线至少 2 倍实体
    if lower < 2 * body:
        return False

    # 上影线短
    if upper > 0.3 * body:
        return False

    return True


def detect_reversal(opens, highs, lows, closes):
    """
    综合反转形态检测。

    返回:
        dict: {
            'bullish_engulfing': bool,
            'hammer': bool,
            'score': float (0~1),  反转信号强度
        }
    """
    engulfing = detect_bullish_engulfing(opens, highs, lows, closes)
    hammer    = detect_hammer(opens, highs, lows, closes)

    # 形态评分: 吞没 = 1.0, 锤子线 = 0.7, 普通阳线 = 0.3
    score = 0.0
    if engulfing:
        score = 1.0
    elif hammer:
        score = 0.7
    elif closes[-1] > opens[-1]:
        score = 0.3

    return {
        'bullish_engulfing': engulfing,
        'hammer': hammer,
        'score': score,
    }


# =============================================================================
# 市场状态分类
# =============================================================================

def classify_regime(closes, ma_period=60, bear_threshold=-0.08):
    """
    判断当前市场状态: 牛市 / 熊市 / 震荡。

    基于两个维度判断:
      1. 趋势方向: 价格 vs MA(ma_period)
      2. 近期动量: N 日涨跌幅

    参数:
        closes        : np.ndarray  指数收盘价序列
        ma_period     : int         趋势均线周期
        bear_threshold: float       熊市判定阈值（20日跌幅）

    返回:
        str: 'bull' | 'range' | 'bear'
    """
    if len(closes) < ma_period:
        return 'range'  # 数据不足，默认震荡

    current = closes[-1]
    ma      = calc_sma(closes, ma_period)

    if ma is None:
        return 'range'

    # 计算近期动量（用 MA_PERIOD 对应的时间窗口）
    n = len(closes)
    if n >= ma_period + 1:
        chg = (closes[-1] / closes[-(ma_period + 1)] - 1) if closes[-(ma_period + 1)] > 0 else 0
    elif n >= 22:
        chg = (closes[-1] / closes[-22] - 1) if closes[-22] > 0 else 0
    elif n >= 5:
        chg = (closes[-1] / closes[-5] - 1) if closes[-5] > 0 else 0
    else:
        chg = 0

    # 分类逻辑
    if chg <= bear_threshold:
        return 'bear'    # 近期跌幅超过阈值 → 熊市

    if current > ma:
        return 'bull'    # 价格在均线上方 → 牛市

    return 'range'       # 其余 → 震荡
