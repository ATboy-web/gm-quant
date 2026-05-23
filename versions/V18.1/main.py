"""
main.py - V18 多策略融合框架

三策略并行:
  1. 均值回归 (MR) — RSI 超卖抄底
  2. 动量趋势 (MOM) — 均线多头追涨
  3. 量价背离 (VP) — 缩量止跌反转

融合引擎:
  - 投票融合: ≥2/3 策略同意 → 执行
  - 市场状态加权: 趋势市动量加倍 / 震荡市均值回归加倍
  - KNN 历史匹配: 分歧时通过历史相似度仲裁

出场:
  - 各策略独立管理自己的持仓出场
  - 出场信号也经过融合投票
"""

import sys
import os
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gm.api import *

import config
import indicators
import stock_pool
import screener
import strategy_mr
import strategy_momentum
import strategy_vp
import fusion

# =============================================================================
# 全局初始化
# =============================================================================

set_token(config.GM_TOKEN)

SYMBOLS       = stock_pool.get_all_symbols()
SYMBOL_SECTOR = stock_pool.get_symbol_sector_map()
MARKET_INDEX  = config.MARKET_INDEX

print('=' * 60)
print('  V18 多策略融合框架')
print('  策略: 均值回归 + 动量趋势 + 量价背离')
print('  融合: 投票制 (≥%d/3) | 市场状态加权'
      % config.VOTE_THRESHOLD)
print('  股票池: %d 只 / %d 行业'
      % (len(SYMBOLS), len(stock_pool.get_sector_list())))
print('=' * 60)


# =============================================================================
# init()
# =============================================================================

def init(context):
    context.pos_info   = {}  # {symbol: {cost, peak, entry_date, sector, strategy, ...}}
    context.sector_pos = {}  # {sector: symbol}
    context.data_cache = {}
    context.regime     = 'range'
    context.stats      = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0.0}
    context.strategy_stats = {'MR': {'wins': 0, 'total': 0},
                              'MOM': {'wins': 0, 'total': 0},
                              'VP': {'wins': 0, 'total': 0}}

    all_symbols = list(SYMBOLS) + [MARKET_INDEX]
    subscribe(symbols=all_symbols, frequency='1d', count=config.DATA_COUNT)
    schedule(schedule_func=on_bar, date_rule='1d', time_rule='14:50:00')
    context.on_backtest_finished = on_backtest_finished


# =============================================================================
# on_bar()
# =============================================================================

def on_bar(context, bars=None):
    try:
        _on_bar_impl(context, bars)
    except Exception as e:
        import traceback
        print('[异常] on_bar: %s' % e)
        traceback.print_exc()


def _on_bar_impl(context, bars=None):
    # ---- Step 0: 当前日期 ----
    try:
        if bars and len(bars) > 0:
            today = bars[0].bob.strftime('%Y-%m-%d')
        else:
            today = context.now.strftime('%Y-%m-%d')
    except Exception:
        today = str(datetime.now().strftime('%Y-%m-%d'))

    context.data_cache = {}
    context._today = today

    # ---- Step 1: 市场状态 ----
    context.regime = _detect_regime(context)
    regime = context.regime
    regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

    # ---- Step 2: 预加载数据 ----
    loaded_count = _preload_data(context)

    # ---- Step 3: 检查出场（各策略独立 + 融合仲裁） ----
    _check_exits_v18(context, regime_cfg)

    # ---- Step 4: 行业动量 ----
    sector_momentum = screener.calc_sector_momentum(context)

    # ---- Step 5: 多策略选股 + 融合投票 ----
    max_pos = regime_cfg['max_positions']
    if len(context.pos_info) < max_pos:
        _execute_entries_v18(context, sector_momentum, regime_cfg)

    # ---- 每日状态 ----
    pos_count = len(context.pos_info)
    print('[状态] %s | %s | 数据:%d只 | 持仓:%d/%d'
          % (today, regime, loaded_count, pos_count, max_pos))


# =============================================================================
# 数据获取
# =============================================================================

def _preload_data(context):
    all_symbols = list(SYMBOLS) + [MARKET_INDEX]
    loaded = 0
    for sym in all_symbols:
        df = _get_bar_data(context, sym)
        if df is not None:
            loaded += 1
    return loaded


def _get_bar_data(context, sym):
    if sym in context.data_cache:
        return context.data_cache[sym]

    try:
        df = context.data(symbol=sym, frequency='1d', count=config.DATA_COUNT)
        if df is not None and len(df) >= config.MIN_DATA_BARS:
            context.data_cache[sym] = df
            return df
        else:
            context.data_cache[sym] = None
    except Exception as e:
        context.data_cache[sym] = None

    return None


def _detect_regime(context):
    df = _get_bar_data(context, MARKET_INDEX)
    if df is None:
        return 'range'
    closes = df['close'].values
    return indicators.classify_regime(
        closes,
        ma_period=config.REGIME_MA_PERIOD,
        bear_threshold=config.REGIME_BEAR_THRESHOLD
    )


# =============================================================================
# V18: 多策略入场
# =============================================================================

def _execute_entries_v18(context, sector_momentum, regime_cfg):
    """
    对每只候选股票，运行三个策略获取信号，融合投票决定是否买入。
    """
    occupied_sectors = set(context.sector_pos.keys())
    remaining = regime_cfg['max_positions'] - len(context.pos_info)
    if remaining <= 0:
        return 0

    # 收集所有候选及其策略投票
    buy_candidates = []

    for sym in SYMBOLS:
        if sym in context.pos_info:
            continue

        sector = SYMBOL_SECTOR.get(sym, '未知')
        if sector in occupied_sectors:
            continue

        df = _get_bar_data(context, sym)
        if df is None:
            continue

        # ---- 三个策略各自打分 ----
        mr_sig  = strategy_mr.get_signal(df, sector, sector_momentum, context.regime) \
                  if config.STRATEGY_MR_ENABLED else None
        mom_sig = strategy_momentum.get_signal(df, sector, sector_momentum, context.regime) \
                  if config.STRATEGY_MOM_ENABLED else None
        vp_sig  = strategy_vp.get_signal(df, sector, sector_momentum, context.regime) \
                  if config.STRATEGY_VP_ENABLED else None

        # ---- 融合投票 ----
        vote_result = fusion.vote_entry(mr_sig, mom_sig, vp_sig, context.regime)

        if vote_result['action'] == 'BUY':
            cur_price = float(df['close'].values[-1])
            highest_score = 0
            best_strategy = 'MR'
            for sig, name in [(mr_sig, 'MR'), (mom_sig, 'MOM'), (vp_sig, 'VP')]:
                if sig and sig.get('action') == 'BUY':
                    if sig.get('score', 0) > highest_score:
                        highest_score = sig['score']
                        best_strategy = name

            buy_candidates.append({
                'symbol': sym,
                'sector': sector,
                'price': cur_price,
                'confidence': vote_result['confidence'],
                'position_pct': vote_result['position_pct'],
                'voters': vote_result['voters'],
                'reason': vote_result['reason'],
                'best_strategy': best_strategy,
                'mr_sig': mr_sig,
                'mom_sig': mom_sig,
                'vp_sig': vp_sig,
            })

    # 按置信度排序
    buy_candidates.sort(key=lambda x: x['confidence'], reverse=True)

    # 执行买入
    cash_info = get_cash()
    available_cash = float(cash_info.available)
    initial_cash = available_cash
    taken_sectors = set(occupied_sectors)
    taken_count = 0

    for c in buy_candidates:
        if taken_count >= remaining:
            break

        sym    = c['symbol']
        sector = c['sector']
        price  = c['price']

        if sector in taken_sectors:
            continue

        vol_group = stock_pool.get_sector_volatility_group(sector)
        if vol_group == 'high':
            base_pct = config.POSITION_PCT * config.VOL_ADJ_HIGH
        elif vol_group == 'low':
            base_pct = config.POSITION_PCT * config.VOL_ADJ_LOW
        else:
            base_pct = config.POSITION_PCT

        pos_pct = base_pct * c['position_pct']

        allocated = initial_cash * pos_pct / max(remaining - taken_count, 1)
        if allocated < price * 100:
            continue

        qty = int(allocated / (price * 100)) * 100
        if qty < 100:
            continue

        order_volume(
            symbol=sym, volume=qty,
            side=OrderSide_Buy,
            order_type=OrderType_Market,
            position_effect=PositionEffect_Open
        )

        entry_date = getattr(context, '_today',
                             str(context.now.strftime('%Y-%m-%d')))
        context.pos_info[sym] = {
            'cost':       price,
            'peak':       price,
            'bar_count':  0,
            'entry_date': entry_date,
            'sector':     sector,
            'vol_group':  vol_group,
            'strategy':   c['best_strategy'],
            'voters':     c['voters'],
            'confidence': c['confidence'],
        }
        context.sector_pos[sector] = sym
        taken_sectors.add(sector)
        taken_count += 1

        rsi_str = ''
        if c['mr_sig'] and 'rsi' in c['mr_sig']:
            rsi_str = ' RSI=%.0f' % c['mr_sig']['rsi']

        print('[买入] %s | %s(%s) | %s | 策略:%s | %.2f×%d%s'
              % (sym, sector, vol_group, c['reason'],
                 c['best_strategy'], price, qty, rsi_str))

    return taken_count


# =============================================================================
# V18: 多策略出场
# =============================================================================

def _check_exits_v18(context, regime_cfg):
    """
    对每个持仓：
      1. 识别持仓归属策略
      2. 三个策略各自检查是否该出场
      3. 融合投票决定最终是否卖出
    """
    for sym in list(context.pos_info.keys()):
        info = context.pos_info[sym]
        df = _get_bar_data(context, sym)
        if df is None:
            continue

        closes = df['close'].values
        highs  = df['high'].values
        lows   = df['low'].values

        if len(closes) < 2:
            continue

        cur_price = float(closes[-1])

        if cur_price > info['peak']:
            info['peak'] = cur_price

        # ---- 三个策略各自检查出场 ----
        today = ''
        if hasattr(context, '_today'):
            today = context._today
        if not today:
            import datetime
            today = datetime.datetime.now().strftime('%Y-%m-%d')

        mr_exit  = strategy_mr.check_exit(df, info, context.regime, context, today_str=today) \
                   if config.STRATEGY_MR_ENABLED else None
        mom_exit = strategy_momentum.check_exit(df, info, context.regime, context) \
                   if config.STRATEGY_MOM_ENABLED else None
        vp_exit  = strategy_vp.check_exit(df, info, context.regime, context, today_str=today) \
                   if config.STRATEGY_VP_ENABLED else None

        # ---- 融合投票（传入归属策略）----
        owner_strategy = info.get('strategy', 'MR')
        vote_result = fusion.vote_exit(mr_exit, mom_exit, vp_exit, context.regime,
                                       owner_strategy=owner_strategy)

        if vote_result['action'] == 'SELL':
            _execute_sell_v18(context, sym, cur_price, vote_result['reason'],
                              info, df)


def _execute_sell_v18(context, sym, price, reason, info, df):
    """V18 卖出执行。"""
    vol = 0
    all_positions = get_position()
    if all_positions:
        for pos in all_positions:
            if pos.symbol == sym:
                vol = int(pos.volume)
                break

    context.pos_info.pop(sym, None)
    sector = info.get('sector', SYMBOL_SECTOR.get(sym, '未知'))
    if sector in context.sector_pos:
        del context.sector_pos[sector]

    pnl_pct = (price - info['cost']) / info['cost'] * 100

    if vol > 0:
        order_volume(
            symbol=sym, volume=vol,
            side=OrderSide_Sell,
            order_type=OrderType_Market,
            position_effect=PositionEffect_Close
        )

    strat = info.get('strategy', '?')
    print('[卖出] %s | %s | %s | 价%.2f | %+.2f%% | %s'
          % (sym, sector, reason, price, pnl_pct, strat))

    context.stats['total_trades'] += 1
    context.stats['total_pnl'] += pnl_pct
    if pnl_pct > 0:
        context.stats['wins'] += 1
        context.strategy_stats[strat]['wins'] += 1
    else:
        context.stats['losses'] += 1
    context.strategy_stats[strat]['total'] += 1


# =============================================================================
# 回测完成
# =============================================================================

def on_backtest_finished(context, indicator):
    s = context.stats
    pos_count = len(context.pos_info)
    print()
    print('=' * 56)
    print('  回测结束 — V18 多策略融合框架')
    print('=' * 56)
    print('  总交易: %d | 胜: %d | 负: %d | 胜率: %.1f%%'
          % (s['total_trades'], s['wins'], s['losses'],
             (s['wins'] / s['total_trades'] * 100) if s['total_trades'] > 0 else 0))
    print('  累计盈亏: %+.2f%%' % s['total_pnl'])
    print('  剩余持仓: %d 只' % pos_count)
    # 各策略表现
    print('  ---- 策略分项 ----')
    for name in ['MR', 'MOM', 'VP']:
        ss = context.strategy_stats[name]
        if ss['total'] > 0:
            print('  %s: 交易%d 胜率%.1f%%' %
                  (name, ss['total'],
                   ss['wins'] / ss['total'] * 100))
    try:
        nav = context.account().nav
        print('  最终净值: %.2f' % nav)
    except Exception:
        pass
    print('=' * 56)


def handle_error(context, error_code, error_msg, **kwargs):
    print('[错误] code=%s msg=%s' % (error_code, error_msg))


# =============================================================================
# 回测入口
# =============================================================================

if __name__ == '__main__':
    run(
        filename='main.py',
        backtest_start_time=config.BACKTEST_START,
        backtest_end_time=config.BACKTEST_END,
        backtest_initial_cash=config.BACKTEST_CASH,
        backtest_adjust=ADJUST_PREV,
    )
