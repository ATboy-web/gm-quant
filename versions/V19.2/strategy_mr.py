"""
strategy_mr.py - 均值回归策略 (V18)

继承 V17 六因子打分核心，去掉 MA60 趋势出场。
作为 V18 多策略融合中的「抄底选手」。

信号格式:
  get_signal(df, sector, sector_momentum, regime) -> {
      'action': 'BUY' | 'HOLD',
      'confidence': 0.0 ~ 1.0,
      'score': float,
      'rsi': float,
      'reason': str,
  }

  check_exit(df, pos_info, regime, context=None) -> {
      'action': 'SELL' | 'HOLD',
      'confidence': 0.0 ~ 1.0,
      'reason': str,
  }
"""

import numpy as np
import config
import indicators
import stock_pool

SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()


def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    """
    均值回归买入信号。

    使用六因子综合评分:
      RSI超卖(35%) + 趋势对齐(20%) + 量能确认(15%)
      + 跌幅(15%) + 反转形态(8%) + 行业动量(7%)

    参数:
        df: DataFrame with columns [open, high, low, close, volume]
        sector: 行业名称
        sector_momentum: 行业动量字典 {sector: momentum}
        regime: 'bull' | 'range' | 'bear'

    返回:
        dict: {'action', 'confidence', 'score', 'rsi', 'reason'} 或 None
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

    # ---- 快速过滤 ----
    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None

    regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])
    rsi_buy_threshold = regime_cfg.get('rsi_buy', config.RSI_BUY)
    entry_threshold = regime_cfg.get('entry_threshold', config.ENTRY_THRESHOLD)

    # ---- RSI ----
    rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
    if rsi is None:
        return None

    if rsi >= rsi_buy_threshold:
        return {'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
                'rsi': round(rsi, 1), 'reason': 'RSI=%.0f >= %d' % (rsi, rsi_buy_threshold)}

    # ---- 极度超卖快速路径 ----
    if rsi < 18:
        return {'action': 'BUY', 'confidence': 0.95, 'score': 0.99,
                'rsi': round(rsi, 1), 'reason': '极度超卖 RSI=%.0f' % rsi}

    # ---- 六因子打分 ----
    w = config.SCORING_WEIGHTS

    # 因子1: RSI超卖深度
    if rsi < rsi_buy_threshold:
        rsi_score = (rsi_buy_threshold - rsi) / (rsi_buy_threshold - config.RSI_DEEP_OVERSOLD)
        rsi_score = min(1.0, max(0.0, rsi_score))
    else:
        rsi_score = 0.0

    # 因子2: 趋势对齐
    trend_score = 0.0
    ma20 = indicators.calc_sma(closes, config.MA_SHORT)
    ma60 = indicators.calc_sma(closes, config.MA_LONG)
    if ma20 and cur_price > ma20:
        trend_score += 0.5
    if ma60 and cur_price > ma60:
        trend_score += 0.5

    # 因子3: 量能确认
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None:
        vol_ratio = 1.0
    if vol_ratio >= config.VOL_SURGE_MIN:
        vol_score = min(1.0, (vol_ratio - config.VOL_SURGE_MIN) / (2.0 - config.VOL_SURGE_MIN))
    else:
        vol_score = 0.0

    # 因子4: 跌幅
    dd = indicators.calc_drawdown(closes, 20)
    if dd is None:
        dd_score = 0.0
    elif dd > 0.20:
        dd_score = 0.5
    elif dd > 0.05:
        dd_score = min(1.0, dd / 0.15)
    else:
        dd_score = dd / 0.05 * 0.5

    # 因子5: 反转形态
    reversal = indicators.detect_reversal(opens, highs, lows, closes)
    reversal_score = reversal['score']

    # 因子6: 行业动量
    if sector_momentum and sector and sector in sector_momentum:
        sm = sector_momentum[sector]
        sector_score = max(0.0, min(1.0, (sm + 0.5) / 1.0))
    else:
        sector_score = 0.5

    total = (
        w['rsi_oversold']    * rsi_score +
        w['trend_align']     * trend_score +
        w['volume_surge']    * vol_score +
        w['drawdown']        * dd_score +
        w['reversal_form']   * reversal_score +
        w['sector_momentum'] * sector_score
    )

    if total >= entry_threshold:
        confidence = min(1.0, total)
        return {
            'action': 'BUY',
            'confidence': confidence,
            'score': round(total, 4),
            'rsi': round(rsi, 1),
            'reason': '多因子评分%.3f RSI=%.0f' % (total, rsi),
        }

    return {'action': 'HOLD', 'confidence': 0.0, 'score': 0.0,
            'rsi': round(rsi, 1), 'reason': '评分%.3f < %.2f' % (total, entry_threshold)}


def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    """
    均值回归策略的出场逻辑。

    出场优先级:
      1. ATR 跟踪止盈
      2. ATR 固定止损
      3. RSI 过热
      4. 时间止损（无盈利则出场）

    V18: 去除 MA60 趋势出场，减少过早止损。
    """
    closes = df['close'].values
    highs  = df['high'].values
    lows   = df['low'].values

    if len(closes) < 2:
        return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}

    cur_price = float(closes[-1])
    cost = pos_info['cost']
    peak = pos_info.get('peak', cost)
    entry_date = pos_info.get('entry_date', '')

    # 更新峰值
    if cur_price > peak:
        peak = cur_price

    # ---- ATR ----
    atr = indicators.calc_atr(highs, lows, closes, config.ATR_PERIOD)
    if atr is None:
        atr = cur_price * 0.03

    pnl = (cur_price - cost) / cost
    regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

    # 1. ATR 跟踪止盈
    if peak > cost:
        trail_pct = atr / cur_price * config.ATR_TRAIL_MULT
        trail_pct = max(trail_pct, 0.04)
        if cur_price <= peak * (1.0 - trail_pct):
            return {
                'action': 'SELL',
                'confidence': 0.9,
                'reason': 'MR_ATR跟踪止盈(%.1f%%)' % (trail_pct * 100),
            }

    # 2. ATR 止损
    stop_mult = regime_cfg.get('atr_stop_mult', config.ATR_STOP_MULT)
    stop_loss_pct = min(atr / cur_price * stop_mult, config.STOP_LOSS_CAP)
    stop_loss_pct = max(stop_loss_pct, 0.04)  # V19.1: 3%→4%，避免正常波动触发
    if pnl <= -stop_loss_pct:
        return {
            'action': 'SELL',
            'confidence': 1.0,
            'reason': 'MR_ATR止损(%.1f%%)' % (stop_loss_pct * 100),
        }

    # 3. RSI 过热
    rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
    if rsi is not None and rsi > config.RSI_EXIT:
        return {
            'action': 'SELL',
            'confidence': 0.8,
            'reason': 'MR_RSI过热(%.0f)' % rsi,
        }

    # 4. 时间止损
    days_held = _count_days(entry_date, context, today_str)
    if days_held >= config.TIME_STOP_DAYS and pnl < 0.03:  # V19.1: 2%→3%
        return {
            'action': 'SELL',
            'confidence': 0.7,
            'reason': 'MR_时间止损(%dd)' % days_held,
        }

    return {'action': 'HOLD', 'confidence': 0.0, 'reason': ''}


def _count_days(entry_date, context=None, today_str=None):
    """计算持仓天数。优先使用传入的 today_str，其次 context._today，最后 datetime.now()。"""
    if not entry_date:
        return 0
    try:
        if not today_str:
            if context and hasattr(context, '_today'):
                today_str = context._today
        if not today_str:
            from datetime import datetime
            today_str = datetime.now().strftime('%Y-%m-%d')

        from datetime import datetime as dt
        entry = dt.strptime(entry_date, '%Y-%m-%d')
        today = dt.strptime(today_str, '%Y-%m-%d')
        return (today - entry).days
    except Exception:
        return 0
