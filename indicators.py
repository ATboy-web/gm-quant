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


def calc_ma_crossover(closes, fast=20, slow=60):
    """V30.4: MA金叉/死叉检测 (借鉴runoob教程)"""
    n = len(closes)
    if n < slow + 2:
        return {'golden_cross': False, 'dead_cross': False, 'bullish': False, 'spread': 0}
    import numpy as np
    fast_ma = float(np.mean(closes[-fast:]))
    slow_ma = float(np.mean(closes[-slow:]))
    prev_fast = float(np.mean(closes[-(fast+1):-1]))
    prev_slow = float(np.mean(closes[-(slow+1):-1]))
    golden_cross = (prev_fast <= prev_slow) and (fast_ma > slow_ma)
    dead_cross = (prev_fast >= prev_slow) and (fast_ma < slow_ma)
    spread = (fast_ma - slow_ma) / slow_ma * 100 if slow_ma > 0 else 0
    return {'golden_cross': golden_cross, 'dead_cross': dead_cross,
            'bullish': fast_ma > slow_ma, 'spread': round(spread, 2)}

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


# =============================================================================
# V30.4: 增强K线形态识别 (借鉴 Vibe-Trading pattern_tool)
# =============================================================================

def detect_candlestick(open_, high, low, close, prev_open=None, prev_close=None):
    """
    综合K线形态检测: doji, hammer, bullish/bearish engulfing。

    Args:
        open_: 当日开盘价 (float)
        high:  当日最高价
        low:   当日最低价
        close: 当日收盘价
        prev_open:  前日开盘价 (engulfing需要)
        prev_close: 前日收盘价 (engulfing需要)

    Returns:
        dict: {'doji': bool, 'hammer': bool, 'engulf_bull': bool, 'engulf_bear': bool}
    """
    body = abs(close - open_)
    total_range = high - low
    upper_shadow = high - max(open_, close)
    lower_shadow = min(open_, close) - low

    result = {'doji': False, 'hammer': False, 'engulf_bull': False, 'engulf_bear': False}

    if total_range <= 0:
        return result

    # Doji: 实体/总幅度 < 10%
    if body / total_range < 0.10:
        result['doji'] = True

    # Hammer: 下影线 > 2x实体, 上影线 < 实体
    if lower_shadow > 2 * body and upper_shadow < body and body > 0:
        result['hammer'] = True

    # Engulfing (需要前日数据)
    if prev_open is not None and prev_close is not None:
        prev_body = abs(prev_close - prev_open)
        # Bullish engulfing: 前日阴线 + 今日阳线 + 吞噬
        if (prev_close < prev_open and close > open_
                and open_ <= prev_close and close >= prev_open
                and body > prev_body):
            result['engulf_bull'] = True
        # Bearish engulfing: 前日阳线 + 今日阴线 + 吞噬
        if (prev_open < prev_close and close < open_
                and open_ >= prev_close and close <= prev_open
                and body > prev_body):
            result['engulf_bear'] = True

    return result


def detect_peaks_valleys(closes, window=5):
    """
    检测价格序列中的峰点和谷点 (借鉴 Vibe-Trading)。

    Args:
        closes: np.ndarray or list of close prices
        window: 半窗口大小

    Returns:
        dict: {'peaks': [indices], 'valleys': [indices]}
    """
    n = len(closes)
    if n < 2 * window + 1:
        return {'peaks': [], 'valleys': []}

    peaks, valleys = [], []
    for i in range(window, n - window):
        seg = closes[i - window:i + window + 1]
        if closes[i] == max(seg):
            peaks.append(i)
        if closes[i] == min(seg):
            valleys.append(i)

    return {'peaks': peaks, 'valleys': valleys}


# ====== V30.5 高级指标 ======

def calc_rsrs(high, low, N=18, M=400):
    """
    计算 RSRS 指标。

    Args:
        high: 最高价序列 (list or np.ndarray)
        low: 最低价序列
        N: 回归窗口 (默认18日)
        M: 历史斜率参考窗口 (默认400日)

    Returns:
        {
            'slope': float (当前斜率),
            'zscore': float (标准化得分),
            'r2': float (拟合优度),
            'signal': 'bullish' | 'bearish' | 'neutral'
        }
    """
    n = len(high)
    if n < N + 1:
        return {'slope': 0, 'zscore': 0, 'r2': 0, 'signal': 'neutral'}

    high_arr = np.array(high[-N:])
    low_arr = np.array(low[-N:])

    # OLS: high = slope * low + intercept
    try:
        slope, intercept = np.polyfit(low_arr, high_arr, 1)
        # R^2
        predicted = slope * low_arr + intercept
        ss_res = np.sum((high_arr - predicted) ** 2)
        ss_tot = np.sum((high_arr - np.mean(high_arr)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    except Exception:
        return {'slope': 0, 'zscore': 0, 'r2': 0, 'signal': 'neutral'}

    # 计算历史斜率序列 (滑动窗口)
    if n >= M + N:
        historical_slopes = []
        for i in range(min(M, n - N)):
            h = high[i:i + N]
            l = low[i:i + N]
            try:
                s, _ = np.polyfit(l, h, 1)
                historical_slopes.append(s)
            except Exception:
                pass

        if len(historical_slopes) >= 60:
            mean_slope = np.mean(historical_slopes)
            std_slope = np.std(historical_slopes)
            if std_slope > 0.001:
                zscore = (slope - mean_slope) / std_slope
            else:
                zscore = 0
        else:
            zscore = 0
    else:
        zscore = 0

    # 信号判断
    if zscore > 0.7 and r2 > 0.6:
        signal = 'bullish'
    elif zscore < -0.7 and r2 > 0.6:
        signal = 'bearish'
    else:
        signal = 'neutral'

    return {
        'slope': round(float(slope), 4),
        'zscore': round(float(zscore), 2),
        'r2': round(float(r2), 3),
        'signal': signal
    }


def calc_rsrs_score(closes, highs, lows, N=18):
    """
    简化版 RSRS 评分 — 用于选股打分。
    基于斜率标准化+动量修正。

    返回 0~1 之间的分数，越高越看涨。
    """
    n = len(closes)
    if n < N + 10:
        return 0.5

    rsrs = calc_rsrs(highs, lows, N, min(200, n))

    # 基础分: Z-score 映射到 [0,1]
    z = np.clip(rsrs['zscore'], -2, 2)
    base_score = (z + 2) / 4  # [-2,2] → [0,1]

    # R² 加权: 低R² = 噪声大 = 降权
    r2_weight = min(1.0, max(0.3, rsrs['r2']))

    # 价格动量修正
    ret_5d = (closes[-1] - closes[-6]) / closes[-6] if closes[-6] > 0 else 0
    momentum_bonus = np.clip(ret_5d * 2, -0.15, 0.15)

    score = base_score * r2_weight + momentum_bonus
    return round(max(0.0, min(1.0, score)), 3)


# ====== V30.5 高级指标 (merged) ======
def calc_hurst(series, max_lag=20):
    """
    计算 Hurst 指数 — 判断市场价格行为特征。

    H < 0.5: 均值回归 (利于 MR 策略)
    H ≈ 0.5: 随机游走
    H > 0.5: 趋势持续 (利于 MOM 策略)

    使用 R/S 分析方法 (Rescaled Range Analysis)

    Args:
        series: 价格序列 (list or np.ndarray)
        max_lag: 最大滞后阶数

    Returns:
        float: Hurst指数 (0~1)
    """
    if len(series) < 30:
        return 0.5  # 样本不足，默认随机游走

    log_returns = np.diff(np.log(series))
    if len(log_returns) < 20:
        return 0.5

    lags = range(2, min(max_lag, len(log_returns) // 2))
    tau = []
    for lag in lags:
        # 分割为多个子序列
        n_splits = len(log_returns) // lag
        if n_splits < 2:
            break
        rs_values = []
        for i in range(n_splits):
            chunk = log_returns[i * lag:(i + 1) * lag]
            mean_chunk = np.mean(chunk)
            dev = chunk - mean_chunk
            Z = np.cumsum(dev)
            R = np.max(Z) - np.min(Z)
            S = np.std(chunk)
            if S > 0:
                rs_values.append(R / S)

        if rs_values:
            tau.append([lag, np.mean(rs_values)])

    if len(tau) < 4:
        return 0.5

    # 线性回归 log(RS) = H * log(lag)
    log_lag = np.log([t[0] for t in tau])
    log_rs = np.log([t[1] for t in tau])

    # 简单线性回归
    n = len(log_lag)
    x_mean = np.mean(log_lag)
    y_mean = np.mean(log_rs)
    num = sum((log_lag[i] - x_mean) * (log_rs[i] - y_mean) for i in range(n))
    den = sum((log_lag[i] - x_mean) ** 2 for i in range(n))

    if den == 0:
        return 0.5
    H = num / den
    return max(0.01, min(0.99, H))


# ============================================================
# ADX 趋势强度 (借鉴 QUANTAXIS)
# ============================================================

def calc_adx(high, low, close, period=14):
    """
    计算 ADX (Average Directional Index) — 趋势强度指标。

    ADX < 20: 无趋势 (震荡市)
    ADX 20-30: 趋势形成中
    ADX > 30: 强趋势市场
    ADX > 50: 极强趋势 (极端)

    Returns:
        {
            'adx': float (当前ADX值),
            'plus_di': float (正向指标),
            'minus_di': float (负向指标),
            'is_trending': bool (是否有趋势),
            'direction': 'up' | 'down' | 'none'
        }
    """
    n = len(close)
    if n < period + 1:
        return {'adx': 20, 'plus_di': 0, 'minus_di': 0, 'is_trending': False, 'direction': 'none'}

    # True Range
    tr = []
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr.append(max(hl, hc, lc))

    # Directional Movement
    plus_dm = []
    minus_dm = []
    for i in range(1, n):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        if up > down and up > 0:
            plus_dm.append(up)
        else:
            plus_dm.append(0)
        if down > up and down > 0:
            minus_dm.append(down)
        else:
            minus_dm.append(0)

    # 平滑 (Wilder's smoothing)
    atr_val = np.mean(tr[-period:])
    plus_di = 100 * np.mean(plus_dm[-period:]) / max(atr_val, 0.001)
    minus_di = 100 * np.mean(minus_dm[-period:]) / max(atr_val, 0.001)

    # ADX = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    di_sum = plus_di + minus_di
    dx = 100 * abs(plus_di - minus_di) / max(di_sum, 0.001)

    # 简单均值作为ADX
    adx = dx if n < period * 2 else np.mean([dx] + [0] * (period - 1))

    # 也可以使用简单平滑
    adx_smooth = float(dx)  # 简化为DX

    is_trending = adx_smooth > 20
    if plus_di > minus_di:
        direction = 'up'
    elif minus_di > plus_di:
        direction = 'down'
    else:
        direction = 'none'

    return {
        'adx': round(float(adx_smooth), 1),
        'plus_di': round(float(plus_di), 1),
        'minus_di': round(float(minus_di), 1),
        'is_trending': is_trending,
        'direction': direction
    }


# ============================================================
# CHO 佳庆指标 (借鉴 QUANTAXIS)
# ============================================================

def calc_cho(high, low, close, volume, short_period=3, long_period=10):
    """
    CHO (Chaikin Oscillator) — 量价确认指标。

    正 CHO: 资金流入 (积累)
    负 CHO: 资金流出 (分配)

    Returns:
        float: CHO值
    """
    n = len(close)
    if n < long_period + 1:
        return 0.0

    # A/D Line = sum((close-low)-(high-close))/(high-low) * volume
    ad = []
    for i in range(n):
        hl = high[i] - low[i]
        if hl > 0:
            clv = ((close[i] - low[i]) - (high[i] - close[i])) / hl
        else:
            clv = 0
        ad.append(clv * volume[i])

    # CHO = EMA(AD, short) - EMA(AD, long)
    ad_series = np.array(ad)
    ema_short = _ema(ad_series, short_period)
    ema_long = _ema(ad_series, long_period)

    if ema_short is None or ema_long is None:
        return 0.0
    return round(float(ema_short - ema_long), 2)


def _ema(data, period):
    """指数移动平均"""
    if len(data) < period:
        return None
    alpha = 2.0 / (period + 1)
    result = data[0]
    for x in data[1:]:
        result = alpha * x + (1 - alpha) * result
    return result

def calc_rsrs(high, low, N=18, M=400):
    """
    计算 RSRS 指标。

    Args:
        high: 最高价序列 (list or np.ndarray)
        low: 最低价序列
        N: 回归窗口 (默认18日)
        M: 历史斜率参考窗口 (默认400日)

    Returns:
        {
            'slope': float (当前斜率),
            'zscore': float (标准化得分),
            'r2': float (拟合优度),
            'signal': 'bullish' | 'bearish' | 'neutral'
        }
    """
    n = len(high)
    if n < N + 1:
        return {'slope': 0, 'zscore': 0, 'r2': 0, 'signal': 'neutral'}

    high_arr = np.array(high[-N:])
    low_arr = np.array(low[-N:])

    # OLS: high = slope * low + intercept
    try:
        slope, intercept = np.polyfit(low_arr, high_arr, 1)
        # R^2
        predicted = slope * low_arr + intercept
        ss_res = np.sum((high_arr - predicted) ** 2)
        ss_tot = np.sum((high_arr - np.mean(high_arr)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    except Exception:
        return {'slope': 0, 'zscore': 0, 'r2': 0, 'signal': 'neutral'}

    # 计算历史斜率序列 (滑动窗口)
    if n >= M + N:
        historical_slopes = []
        for i in range(min(M, n - N)):
            h = high[i:i + N]
            l = low[i:i + N]
            try:
                s, _ = np.polyfit(l, h, 1)
                historical_slopes.append(s)
            except Exception:
                pass

        if len(historical_slopes) >= 60:
            mean_slope = np.mean(historical_slopes)
            std_slope = np.std(historical_slopes)
            if std_slope > 0.001:
                zscore = (slope - mean_slope) / std_slope
            else:
                zscore = 0
        else:
            zscore = 0
    else:
        zscore = 0

    # 信号判断
    if zscore > 0.7 and r2 > 0.6:
        signal = 'bullish'
    elif zscore < -0.7 and r2 > 0.6:
        signal = 'bearish'
    else:
        signal = 'neutral'

    return {
        'slope': round(float(slope), 4),
        'zscore': round(float(zscore), 2),
        'r2': round(float(r2), 3),
        'signal': signal
    }


def calc_rsrs_score(closes, highs, lows, N=18):
    """
    简化版 RSRS 评分 — 用于选股打分。
    基于斜率标准化+动量修正。

    返回 0~1 之间的分数，越高越看涨。
    """
    n = len(closes)
    if n < N + 10:
        return 0.5

    rsrs = calc_rsrs(highs, lows, N, min(200, n))

    # 基础分: Z-score 映射到 [0,1]
    z = np.clip(rsrs['zscore'], -2, 2)
    base_score = (z + 2) / 4  # [-2,2] → [0,1]

    # R² 加权: 低R² = 噪声大 = 降权
    r2_weight = min(1.0, max(0.3, rsrs['r2']))

    # 价格动量修正
    ret_5d = (closes[-1] - closes[-6]) / closes[-6] if closes[-6] > 0 else 0
    momentum_bonus = np.clip(ret_5d * 2, -0.15, 0.15)

    score = base_score * r2_weight + momentum_bonus
    return round(max(0.0, min(1.0, score)), 3)


# ====== V30.5 ======
def winsorize_mad(series, n_mad=3.0):
    """
    MAD 去极值 — 中位数绝对偏差法。

    Args:
        series: 因子值序列
        n_mad: MAD 倍数阈值

    Returns:
        去极值后的序列
    """
    median = np.median(series)
    mad = np.median(np.abs(series - median))
    if mad < 0.001:
        return series

    upper = median + n_mad * mad * 1.4826  # 1.4826 = 正态化系数
    lower = median - n_mad * mad * 1.4826
    return np.clip(series, lower, upper)


def winsorize_percentile(series, lower_pct=1, upper_pct=99):
    """
    百分位去极值。

    Args:
        series: 因子值序列
        lower_pct: 下百分位
        upper_pct: 上百分位

    Returns:
        去极值后的序列
    """
    lo = np.percentile(series, lower_pct)
    hi = np.percentile(series, upper_pct)
    return np.clip(series, lo, hi)


def standardize(series):
    """
    Z-score 标准化: (x - μ) / σ。

    Returns:
        标准化后的序列，均值为 0 标准差为 1
    """
    std = np.std(series)
    if std < 0.001:
        return np.zeros_like(series)
    return (series - np.mean(series)) / std


def standardize_cross_sectional(factor_matrix):
    """
    截面标准化 — 每个交易日独立标准化各股票的因子值。

    Args:
        factor_matrix: (n_dates, n_stocks) 的因子矩阵

    Returns:
        截面标准化后的矩阵
    """
    result = np.zeros_like(factor_matrix, dtype=float)
    for i in range(factor_matrix.shape[0]):
        row = factor_matrix[i]
        mask = ~np.isnan(row)
        if mask.sum() > 1:
            result[i][mask] = standardize(row[mask])
    return result


def neutralize_by_sector(factor_values, sectors):
    """
    行业中性化 — 移除行业均值影响。

    Args:
        factor_values: 因子值数组 (n_stocks,)
        sectors: 行业标签数组 (n_stocks,)

    Returns:
        行业中性化后的因子值
    """
    result = np.array(factor_values, dtype=float)
    unique_sectors = set(sectors)
    for sec in unique_sectors:
        mask = np.array([s == sec for s in sectors])
        if mask.sum() > 1:
            sec_mean = np.mean(factor_values[mask])
            result[mask] = result[mask] - sec_mean
    return result


def neutralize_by_market_cap(factor_values, market_caps):
    """
    市值中性化 — 回归移除市值影响。

    Args:
        factor_values: 因子值
        market_caps: 市值 (对数)

    Returns:
        市值中性化后的残差
    """
    X = np.column_stack([np.ones(len(factor_values)), market_caps])
    mask = ~(np.isnan(factor_values) | np.isnan(market_caps).any() if isinstance(market_caps, np.ndarray) else np.isnan(factor_values))
    if mask.sum() < 3:
        return factor_values

    beta = np.linalg.lstsq(X[mask], factor_values[mask], rcond=None)[0]
    predicted = X @ beta
    return factor_values - predicted


def calc_factor_ic(factor_values, forward_returns):
    """
    计算因子 IC (Information Coefficient)。

    Args:
        factor_values: 因子值 (n_stocks,)
        forward_returns: 未来收益 (n_stocks,)

    Returns:
        {'ic': float, 'rank_ic': float}
    """
    mask = ~(np.isnan(factor_values) | np.isnan(forward_returns))
    if mask.sum() < 5:
        return {'ic': 0.0, 'rank_ic': 0.0}

    f = factor_values[mask]
    r = forward_returns[mask]

    try:
        ic, _ = stats.pearsonr(f, r)
    except Exception:
        ic = 0.0

    try:
        rank_ic, _ = stats.spearmanr(f, r)
    except Exception:
        rank_ic = 0.0

    return {
        'ic': round(float(ic) if not np.isnan(ic) else 0.0, 4),
        'rank_ic': round(float(rank_ic) if not np.isnan(rank_ic) else 0.0, 4)
    }


def process_factor_pipeline(factor_values, sectors=None, market_caps=None,
                             winsorize=True, standardize_out=True,
                             neutralize_sector=True, neutralize_mcap=False):
    """
    完整的因子处理流水线 (借鉴 panda_factor factor_analysis_workflow)。

    Args:
        factor_values: 原始因子值
        sectors: 行业标签 (可选)
        market_caps: 市值 (可选)
        winsorize: 是否去极值
        standardize_out: 是否标准化输出
        neutralize_sector: 是否行业中性化
        neutralize_mcap: 是否市值中性化

    Returns:
        处理后的因子值
    """
    result = np.array(factor_values, dtype=float)

    # 1. 去极值
    if winsorize:
        result = winsorize_mad(result, n_mad=3.0)

    # 2. 中性化
    if neutralize_sector and sectors is not None:
        result = neutralize_by_sector(result, sectors)
    if neutralize_mcap and market_caps is not None:
        result = neutralize_by_market_cap(result, market_caps)

    # 3. 标准化
    if standardize_out:
        result = standardize(result)

    return result
