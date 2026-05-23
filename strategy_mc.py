"""
strategy_mc.py - MA趋势突破策略 (V23)

与MR互补: MR做超卖反弹, MC做趋势延续。
买入: MA5>MA20>MA60 + 价格突破20日高 + 放量
卖出: MA5死叉MA20 或 ATR止损
"""
import numpy as np
import config
import indicators

MC_BUY_CONF = 0.65

def get_signal(df, sector=None, sector_momentum=None, regime='range'):
    closes = df['close'].values
    highs = df['high'].values
    vols = df['volume'].values
    n = len(closes)
    if n < 65:
        return None
    cur_price = float(closes[-1])
    if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
        return None
    # MA alignment
    ma5 = np.mean(closes[-5:])
    ma20 = np.mean(closes[-20:])
    ma60 = np.mean(closes[-60:])
    prev_ma5 = np.mean(closes[-6:-1])
    prev_ma20 = np.mean(closes[-21:-1])
    # Must be in uptrend
    if not (ma5 > ma20 > ma60):
        return {'action': 'HOLD', 'confidence': 0, 'score': 0, 'reason': 'MC_未多头排列'}
    # Price breaking above 20-day high
    high20 = max(highs[-21:-1])
    if cur_price <= high20 * 1.005:
        return {'action': 'HOLD', 'confidence': 0, 'score': 0, 'reason': 'MC_未突破20日高'}
    # Volume surge
    vol_ratio = indicators.calc_volume_ratio(vols, config.VOL_PERIOD)
    if vol_ratio is None or vol_ratio < 1.1:
        return {'action': 'HOLD', 'confidence': 0, 'score': 0, 'reason': 'MC_量不足'}
    # RSI not overbought
    rsi = indicators.calc_rsi(closes, 14)
    if rsi and rsi > 78:
        return {'action': 'HOLD', 'confidence': 0, 'score': 0, 'rsi': round(rsi,1), 'reason': 'MC_RSI过热'}
    score = 0.45 + vol_ratio * 0.15
    if prev_ma5 <= prev_ma20:  # fresh crossover
        score += 0.15
    score = min(1.0, score)
    if score >= 0.50:
        return {'action': 'BUY', 'confidence': MC_BUY_CONF, 'score': round(score,4), 'reason': 'MC_趋势突破(MA5/20/60多头)'}
    return {'action': 'HOLD', 'confidence': score, 'score': round(score,4), 'reason': 'MC_评分不足%.3f'%score}

def check_exit(df, pos_info, regime='range', context=None, today_str=None):
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    n = len(closes)
    if n < 6:
        return {'action': 'HOLD', 'confidence': 0, 'reason': ''}
    cur_price = float(closes[-1])
    cost = pos_info['cost']
    pnl = (cur_price - cost) / cost
    # MA5 death cross MA20
    ma5 = np.mean(closes[-5:])
    ma20 = np.mean(closes[-20:])
    prev_ma5 = np.mean(closes[-6:-1])
    prev_ma20 = np.mean(closes[-21:-1])
    if prev_ma5 >= prev_ma20 and ma5 < ma20:
        return {'action': 'SELL', 'confidence': 0.8, 'reason': 'MC_死叉(MA5<MA20)'}
    # ATR stop
    atr = indicators.calc_atr(highs, lows, closes, 14)
    if atr is None:
        atr = cur_price * 0.03
    stop = cost - 2.0 * atr
    if cur_price <= stop:
        return {'action': 'SELL', 'confidence': 1.0, 'reason': 'MC_ATR止损'}
    # Hard stop 6%
    if pnl <= -0.06:
        return {'action': 'SELL', 'confidence': 1.0, 'reason': 'MC_硬止损%.1f%%'%(pnl*100)}
    # Take profit 15%
    if pnl >= 0.15:
        return {'action': 'SELL', 'confidence': 0.8, 'reason': 'MC_止盈%.1f%%'%(pnl*100)}
    return {'action': 'HOLD', 'confidence': 0, 'reason': ''}
