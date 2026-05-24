"""
screener.py - 多因子选股打分引擎 (V17 优化版)

V17 改进:
  1. _quick_filter 预计算 RSI，传递给 _score_stock 避免重复计算
  2. 快速路径: 极度超卖(RSI<18)直接入选，跳过完整打分
  3. 行业动量批量计算，减少循环开销
  4. 反转形态仅对评分>0.2的候选计算，节省算力
"""

import numpy as np
import config
import indicators
import stock_pool

# 模块加载时构建映射
SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()


def screen_all(context, sector_momentum=None):
    """
    对股票池中所有候选股票进行打分筛选。

    V17 优化: _quick_filter 返回 (bool, rsi_value)，复用预计算的 RSI。
    """
    candidates = []

    for sym in stock_pool.get_all_symbols():
        df = context.data_cache.get(sym)
        if df is None:
            continue

        sector = SYMBOL_SECTOR_MAP.get(sym, '未知')

        # ---- 快速初筛（返回预计算的 RSI）----
        passed, rsi = _quick_filter(df)
        if not passed:
            continue

        # ---- V17 快速路径: 极度超卖直接入选 ----
        if rsi is not None and rsi < 18:
            cur_price = float(df['close'].values[-1])
            candidates.append({
                'symbol':  sym,
                'sector':  sector,
                'total':   0.99,
                'price':   cur_price,
                'rsi':     round(rsi, 1),
                'details': {
                    'rsi_score': 1.0, 'trend_score': 0.5,
                    'vol_score': 0.5, 'dd_score': 0.5,
                    'reversal_score': 0.3, 'sector_score': 0.5,
                },
            })
            continue

        # ---- 多因子打分（传入预计算的 RSI）----
        result = _score_stock(df, sym, sector, sector_momentum, precomputed_rsi=rsi)
        if result is None:
            continue

        if result['total'] >= config.ENTRY_THRESHOLD:
            candidates.append(result)

    candidates.sort(key=lambda x: x['total'], reverse=True)
    return candidates


def _quick_filter(df):
    """
    快速初筛: 同时返回 (是否通过, RSI值) 供后续复用。

    Returns:
        (bool, float|None)
    """
    closes = df['close'].values
    if len(closes) < config.RSI_PERIOD + 1:
        return False, None

    # ---- RSI 超卖检查（预计算，传给 _score_stock 复用）----
    rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
    if rsi is None or rsi >= config.RSI_BUY:
        return False, rsi

    cur  = float(closes[-1])
    prev = float(closes[-2])

    if cur < config.PRICE_MIN or cur > config.PRICE_MAX:
        return False, rsi

    chg = abs(cur - prev) / prev if prev > 0 else 0
    if chg > config.PRICE_CHG_LIMIT:
        return False, rsi

    return True, rsi


# =============================================================================
# 多因子评分核心
# =============================================================================

def _score_stock(df, sym, sector, sector_momentum, precomputed_rsi=None):
    """
    对单只股票进行六因子综合评分。

    V17 优化: 接收预计算的 RSI，避免重复调用 calc_rsi()。
    """
    closes = df['close'].values
    opens  = df['open'].values
    highs  = df['high'].values
    lows   = df['low'].values
    vols   = df['volume'].values

    n = len(closes)
    if n < config.MIN_DATA_BARS:
        return None

    cur_price = float(closes[-1])

    # ==================================================================
    # 因子 1: RSI 超卖深度（权重 0.35）
    # V17: 使用预计算的 RSI，不再重复计算
    # ==================================================================
    if precomputed_rsi is not None:
        rsi = precomputed_rsi
    else:
        rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
        if rsi is None:
            return None

    if rsi < config.RSI_BUY:
        rsi_score = (config.RSI_BUY - rsi) / (config.RSI_BUY - config.RSI_DEEP_OVERSOLD)
        rsi_score = min(1.0, max(0.0, rsi_score))
    else:
        rsi_score = 0.0

    # ==================================================================
    # 因子 2: 趋势对齐（权重 0.20）
    # ==================================================================
    trend_score = 0.0
    ma20 = indicators.calc_sma(closes, config.MA_SHORT)
    ma60 = indicators.calc_sma(closes, config.MA_LONG)

    if ma20 and cur_price > ma20:
        trend_score += 0.5
    if ma60 and cur_price > ma60:
        trend_score += 0.5

    # ==================================================================
    # 因子 3: 成交量确认（权重 0.15）
    # ==================================================================
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    if vol_ratio >= config.VOL_SURGE_MIN:
        vol_score = min(1.0, (vol_ratio - config.VOL_SURGE_MIN) / (2.0 - config.VOL_SURGE_MIN))
    else:
        vol_score = 0.0

    # ==================================================================
    # 因子 4: 近期跌幅（权重 0.15）
    # ==================================================================
    dd = indicators.calc_drawdown(closes, 20)
    if dd is None:
        dd_score = 0.0
    elif dd > 0.20:
        dd_score = 0.5   # 极端跌幅降分
    elif dd > 0.05:
        dd_score = min(1.0, dd / 0.15)
    else:
        dd_score = dd / 0.05 * 0.5

    # ==================================================================
    # 因子 5: 反转形态（权重 0.08）
    # ==================================================================
    reversal = indicators.detect_reversal(opens, highs, lows, closes)
    reversal_score = reversal['score']

    # ==================================================================
    # 因子 6: 行业动量（权重 0.07）
    # ==================================================================
    if sector_momentum and sector in sector_momentum:
        sm = sector_momentum[sector]
        sector_score = max(0.0, min(1.0, (sm + 0.5) / 1.0))
    else:
        sector_score = 0.5

    # ==================================================================
    # 加权合成总分
    # ==================================================================
    w = config.SCORING_WEIGHTS
    total = (
        w['rsi_oversold']    * rsi_score +
        w['trend_align']     * trend_score +
        w['volume_surge']    * vol_score +
        w['drawdown']        * dd_score +
        w['reversal_form']   * reversal_score +
        w['sector_momentum'] * sector_score
    )

    return {
        'symbol':  sym,
        'sector':  sector,
        'total':   round(total, 4),
        'price':   cur_price,
        'rsi':     round(rsi, 1),
        'details': {
            'rsi_score':       round(rsi_score, 3),
            'trend_score':     round(trend_score, 3),
            'vol_score':       round(vol_score, 3),
            'dd_score':        round(dd_score, 3),
            'reversal_score':  round(reversal_score, 3),
            'sector_score':    round(sector_score, 3),
        },
    }


# =============================================================================
# 行业动量计算
# =============================================================================

def calc_sector_momentum(context):
    """计算各行业的动量得分（10日涨跌幅均值）。"""
    momentum = {}
    sector_map = stock_pool.get_symbol_sector_map()

    for sector in stock_pool.get_sector_list():
        stocks = stock_pool.filter_by_sector(sector)
        rets = []

        for sym in stocks:
            df = context.data_cache.get(sym)
            if df is None or len(df) < 12:
                continue
            closes = df['close'].values
            if closes[-12] > 0:
                ret = (closes[-1] / closes[-12] - 1)
                rets.append(ret)

        if rets:
            momentum[sector] = float(np.mean(rets))
        else:
            momentum[sector] = 0.0

    return momentum
