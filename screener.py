"""
screener.py - 多因子选股打分引擎 (V16 核心模块)

每天对所有候选股票进行量化打分，自动识别"有机会"和"该沉淀"的股票。

六因子模型:
  1. RSI 超卖深度   (30%) — 均值回归核心信号
  2. 趋势对齐       (20%) — 顺势而为，不抄下跌股
  3. 成交量确认     (15%) — 放量反弹才有诚意
  4. 近期跌幅       (15%) — 跌得越多反弹空间越大
  5. 反转形态       (10%) — K线组合确认底部
  6. 行业动量       (10%) — 优选强势行业中的超卖股

评分输出:
  总分 ∈ [0, 1]，只买入总分 ≥ ENTRY_THRESHOLD 的股票。
  按总分降序排列，优先买入得分最高的标的。
"""

import numpy as np
import config
import indicators
import stock_pool


def screen_all(context, sector_momentum=None):
    """
    对股票池中所有候选股票进行打分筛选。

    参数:
        context          : GM 策略上下文
        sector_momentum  : dict {sector: momentum_score} 或 None

    返回:
        list[dict]: 通过筛选的股票列表，按总分降序排列
        每项包含: symbol, score, price, rsi, sector, details
    """
    candidates = []

    for sym in stock_pool.get_all_symbols():
        # 已持仓的跳过（在 main.py 中处理，这里不重复）
        df = context.data_cache.get(sym)
        if df is None:
            continue

        # 获取行业
        sector = SYMBOL_SECTOR_MAP.get(sym, '未知')

        # ---- 快速初筛 ----
        if not _quick_filter(df, sym):
            continue

        # ---- 多因子打分 ----
        result = _score_stock(df, sym, sector, sector_momentum)
        if result is None:
            continue  # 数据不足

        if result['total'] >= config.ENTRY_THRESHOLD:
            candidates.append(result)

    # 按总分降序排列（得分高的优先）
    candidates.sort(key=lambda x: x['total'], reverse=True)

    return candidates


def _quick_filter(df, sym):
    """
    快速初筛: 用最低成本排除明显不符合条件的股票。

    过滤条件（按优先级）:
      1. RSI 必须处于超卖区（核心条件，不过此关一律跳过）
      2. 数据不足
      3. 股价异常（仙股或天价股）
      4. 涨跌停板
    """
    closes = df['close'].values
    if len(closes) < config.RSI_PERIOD + 1:
        return False

    # ---- 条件 0: RSI 超卖硬性检查（均值回归策略的核心）----
    # 无论其他因子多好，RSI 不超卖就不买
    rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
    if rsi is None or rsi >= config.RSI_BUY:
        return False

    cur  = float(closes[-1])
    prev = float(closes[-2])

    # 价格区间
    if cur < config.PRICE_MIN or cur > config.PRICE_MAX:
        return False

    # 涨跌幅过滤
    chg = abs(cur - prev) / prev if prev > 0 else 0
    if chg > config.PRICE_CHG_LIMIT:
        return False

    return True


# =============================================================================
# 多因子评分核心
# =============================================================================

def _score_stock(df, sym, sector, sector_momentum):
    """
    对单只股票进行六因子综合评分。

    参数:
        df              : pd.DataFrame  日线数据
        sym             : str           股票代码
        sector          : str           所属行业
        sector_momentum : dict | None   行业动量数据

    返回:
        dict | None: {
            'symbol': str,
            'sector': str,
            'total': float,      总分 (0~1)
            'price': float,      当前价
            'rsi': float,        RSI 值
            'details': {         各因子得分明细
                'rsi_score': ...,
                'trend_score': ...,
                ...
            }
        }
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
    # 因子 1: RSI 超卖深度（权重 0.30）
    #
    # RSI 越低 → 超卖越严重 → 得分越高
    # RSI < RSI_BUY 才给分，RSI >= RSI_BUY 得 0 分
    # ==================================================================
    rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
    if rsi is None:
        return None

    if rsi < config.RSI_BUY:
        # 线性映射: RSI=RIS_BUY → 0, RSI=RSI_DEEP_OVERSOLD → 1
        # RSI 低于 DEEP_OVERSOLD 时奖励最高 1.0（不再额外溢出）
        rsi_score = (config.RSI_BUY - rsi) / (config.RSI_BUY - config.RSI_DEEP_OVERSOLD)
        rsi_score = min(1.0, max(0.0, rsi_score))  # 钳制在 0~1
    else:
        rsi_score = 0.0

    # ==================================================================
    # 因子 2: 趋势对齐（权重 0.20）
    #
    # 价格在 MA20 上方 → +0.5
    # 价格在 MA60 上方 → +0.5
    # 全部在上方 = 1.0，全部在下方 = 0.0
    # 均值回归 + 上行趋势 = 胜率更高的组合
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
    #
    # 量比 = 当日量 / 20日均量
    # 量比越大说明资金介入越积极，反弹信号越可靠
    # ==================================================================
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0

    if vol_ratio >= config.VOL_SURGE_MIN:
        # 线性映射: 1.2x → 0.0, 2.0x → 1.0
        vol_score = min(1.0, (vol_ratio - config.VOL_SURGE_MIN) / (2.0 - config.VOL_SURGE_MIN))
    else:
        # 量能不足，线性映射: 0 → 0.0, VOL_SURGE_MIN → 0.0（不给分）
        vol_score = 0.0

    # ==================================================================
    # 因子 4: 近期跌幅（权重 0.15）
    #
    # 从 20 日内最高点跌了多少
    # 跌幅越大 → 均值回归潜力越大 → 得分越高
    # 但 > 20% 的极端跌幅可能有问题（基本面恶化），给分降低
    # ==================================================================
    dd = indicators.calc_drawdown(closes, 20)
    if dd is None:
        dd_score = 0.0
    elif dd > 0.20:
        # 极端跌幅 → 可能是基本面问题，降分
        dd_score = 0.5
    elif dd > 0.05:
        # 中等跌幅（5%~20%）: 最佳反弹区间
        dd_score = dd / 0.15  # 15% 跌幅 = 1.0 分
        dd_score = min(1.0, dd_score)
    else:
        # 跌幅 < 5%: 反弹空间有限
        dd_score = dd / 0.05 * 0.5

    # ==================================================================
    # 因子 5: 反转形态（权重 0.10）
    #
    # K 线形态确认底部反转
    # ==================================================================
    reversal = indicators.detect_reversal(opens, highs, lows, closes)
    reversal_score = reversal['score']

    # ==================================================================
    # 因子 6: 行业动量（权重 0.10）
    #
    # 如果行业整体走强，该行业的超卖反弹更可靠
    # 如果行业持续走弱，即使个股超卖也可能是行业性问题
    # ==================================================================
    if sector_momentum and sector in sector_momentum:
        sm = sector_momentum[sector]
        # 动量从 -1 到 +1，映射到 0~1
        sector_score = max(0.0, min(1.0, (sm + 0.5) / 1.0))
    else:
        sector_score = 0.5  # 无数据时给中性分

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
    """
    计算各行业的动量得分。

    对每个行业，取所有成分股的平均 10 日涨跌幅作为行业动量。
    正值 = 行业走强，负值 = 行业走弱。

    返回:
        dict: {sector: momentum_score}
    """
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


# =============================================================================
# 预加载: 确保 stock_pool 的映射可用
# =============================================================================

# 在模块加载时构建的映射，供 screen_all 快速查询
SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()
