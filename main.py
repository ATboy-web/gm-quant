"""
main.py - V29.8 (VRC, 双账户仿真+回测)
"""

import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gm.api import *
import config
import indicators
import stock_pool
import screener
import sector_config
import executor
import trace
import trace as logger  # V30.5: gm_logger merged into trace

set_token(config.GM_TOKEN)

SYMBOLS       = stock_pool.get_all_symbols()[:49]  # GM limit 50
SYMBOL_SECTOR = stock_pool.get_symbol_sector_map()
MARKET_INDEX  = config.MARKET_INDEX

exec_engine = executor.TradeExecutor()
logger.setup_logger()
log = logger.log

log.info('=' * 56)
log.info('  V29.8 VRC+双账户 | MR+MOM+VRC+BK+DV+RT')
log.info('  %d stocks / %d sectors', len(SYMBOLS), len(stock_pool.get_sector_list()))
log.info('  SIM: %s', config.SIM_ACCOUNT_ID[:8] + '...')
log.info('=' * 56)
sector_config.print_summary()

# AI toggle
_ai_choice = ''
try:
    _ai_choice = input('\n[AI] 1=on 2=off (default 2): ').strip()
except Exception:
    pass
config.AI_ENABLED = (_ai_choice == '1')
print('  AI: %s' % ('on' if config.AI_ENABLED else 'off'))
print()


# =============================================================================
# init()
# =============================================================================

def init(context):
    context.pos_info   = {}
    context.sector_pos = {}
    context.data_cache = {}
    context.regime     = 'range'
    context.stats      = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0.0}
    context.strategy_stats = {'MR':  {'wins': 0, 'total': 0},
                              'MOM': {'wins': 0, 'total': 0},
                              'VRC': {'wins': 0, 'total': 0},
                              'BK':  {'wins': 0, 'total': 0},
                              'DV':  {'wins': 0, 'total': 0},
                              'RT':  {'wins': 0, 'total': 0}}
    context.trades = []
    context.daily_values = []

    # ---- Mode detection ----
    try:
        is_bt = (context.mode == MODE_BACKTEST)
    except Exception:
        is_bt = True
    context.is_backtest = is_bt

    if is_bt:
        log.info('[Mode] BACKTEST')
        schedule(schedule_func=on_bar, date_rule='1d', time_rule='14:50:00')
    else:
        log.info('[Mode] SIM | account=%s', config.SIM_ACCOUNT_ID[:8] + '...')
        # Launch live monitor in background
        try:
            import subprocess, os
            subprocess.Popen(
                ['python', os.path.join(os.path.dirname(__file__), 'live_monitor.py')],
                creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0
            )
            log.info('[Monitor] live window launched')
        except Exception as e:
            log.warning('[Monitor] failed: %s', e)
        # 10-sec schedule (AM 9:31-11:30, PM 13:01-15:00)
        times = []
        for h in range(9, 12):
            ms = 31 if h == 9 else 0
            me = 60 if h < 11 else 31
            for m in range(ms, me):
                for s in range(0, 60, 10):
                    times.append('%02d:%02d:%02d' % (h, m, s))
        for h in range(13, 15):
            for m in range(1 if h == 13 else 0, 60):
                for s in range(0, 60, 10):
                    times.append('%02d:%02d:%02d' % (h, m, s))
        log.info('[Schedule] registering %d slots...', len(times))
        for t in times:
            schedule(schedule_func=on_bar, date_rule='1d', time_rule=t)
        log.info('[Schedule] done')

    # Subscribe 49 stocks + 1 index = 50
    all_syms = list(SYMBOLS) + [MARKET_INDEX]
    subscribe(symbols=all_syms, frequency='1d', count=config.DATA_COUNT)
    context.SYMBOLS = all_syms[:-1]

    context.on_backtest_finished = on_backtest_finished


# =============================================================================
# on_bar()
# =============================================================================

def on_bar(context, bars=None):
    try:
        _on_bar_impl(context, bars)
    except Exception as e:
        import traceback
        log.error('[ERR] on_bar: %s', e)
        traceback.print_exc()


def _on_bar_impl(context, bars=None):
    try:
        if bars and len(bars) > 0:
            today = bars[0].bob.strftime('%Y-%m-%d')
        else:
            today = context.now.strftime('%Y-%m-%d')
    except Exception:
        today = str(datetime.now().strftime('%Y-%m-%d'))

    context.data_cache = {}
    context._today = today

    loaded = _preload_data(context)
    context.regime = _detect_regime(context)
    regime = context.regime
    regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

    # Step 3: Check exits
    sells = exec_engine.check_exits(
        context.pos_info, context.data_cache, regime, context, today
    )
    for sym, price, vote, info in sells:
        _do_sell(context, sym, price, vote['reason'], info)
        exec_engine.record_sell(sym, today)

    exec_engine.cleanup_cooldowns(today)

    # Step 4: Sector momentum
    sector_momentum = screener.calc_sector_momentum(context)

    # Step 5: Find buy candidates
    try:
        acct = config.SIM_ACCOUNT_ID if not context.is_backtest else None
        cash = get_cash(account_id=acct)
        trace.heartbeat(len(context.pos_info), cash.available, cash.nav, None)
    except Exception:
        trace.heartbeat(len(context.pos_info), 0, 0, None)

    max_pos = regime_cfg['max_positions']
    occupied = set(context.sector_pos.keys())
    if len(context.pos_info) < max_pos:
        candidates = exec_engine.find_buy_candidates(
            context.SYMBOLS, occupied, context.pos_info,
            context.data_cache, sector_momentum, regime
        )
        _do_buys(context, candidates, max_pos)

    pos_count = len(context.pos_info)
    _prev = getattr(context, '_last_pos_count', -1)
    if pos_count != _prev:
        log.info('[State] %s | %s | loaded:%d | pos:%d/%d',
                 today, regime, loaded, pos_count, max_pos)
        context._last_pos_count = pos_count


# =============================================================================
# Data helpers
# =============================================================================

def _preload_data(context, symbols=None):
    if symbols is None:
        symbols = list(SYMBOLS) + [MARKET_INDEX]
    loaded = 0
    for sym in symbols:
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
        context.data_cache[sym] = None
    except Exception:
        context.data_cache[sym] = None
    return None


def _detect_regime(context):
    df = _get_bar_data(context, MARKET_INDEX)
    if df is None:
        return 'range'
    return indicators.classify_regime(
        df['close'].values,
        ma_period=config.REGIME_MA_PERIOD,
        bear_threshold=config.REGIME_BEAR_THRESHOLD
    )


# =============================================================================
# Trade execution
# =============================================================================

def _do_buys(context, candidates, max_pos):
    remaining = max_pos - len(context.pos_info)
    if remaining <= 0:
        return

    try:
        acct = config.SIM_ACCOUNT_ID if not context.is_backtest else None
        cash_info = get_cash(account_id=acct)
        available_cash = float(cash_info.available)
    except Exception as e:
        log.warning('[Cash] get_cash failed, skip buys: %s', e)
        return

    taken_sectors = set(context.sector_pos.keys())
    taken_count = 0

    for c in candidates:
        if taken_count >= remaining:
            break
        sector = c['sector']
        if sector in taken_sectors:
            continue

        sym   = c['symbol']
        price = c['price']
        qty = exec_engine.calc_position_size(c, available_cash, remaining - taken_count)
        if qty < 100:
            continue

        order_volume(symbol=sym, volume=qty, side=OrderSide_Buy,
                     order_type=OrderType_Market, position_effect=PositionEffect_Open,
                     account=acct if acct else "")
        try:
            trace.buy(c.get('best_strategy','?'), sym, price,
                      c.get('position_pct',0), len(c.get('voters',[])), context.regime)
        except Exception:
            pass

        entry_date = getattr(context, '_today', str(context.now.strftime('%Y-%m-%d')))
        vol_group = stock_pool.get_sector_volatility_group(sector)
        context.pos_info[sym] = {
            'cost': price, 'peak': price, 'bar_count': 0,
            'entry_date': entry_date, 'sector': sector,
            'vol_group': vol_group,
            'strategy': c['best_strategy'],
            'voters': c['voters'],
            'confidence': c['confidence'],
        }
        context.sector_pos[sector] = sym
        taken_sectors.add(sector)
        taken_count += 1

        rsi_str = ' RSI=%.0f' % c['rsi'] if c.get('rsi') else ''
        log.info('[BUY] %s | %s(%s) | %s | %s | %.2f x %d%s',
                 sym, sector, vol_group, c['reason'],
                 c['best_strategy'], price, qty, rsi_str)


def _do_sell(context, sym, price, reason, info):
    vol = 0
    acct = config.SIM_ACCOUNT_ID if not context.is_backtest else None
    try:
        all_positions = get_position(account_id=acct)
        if all_positions:
            for pos in all_positions:
                if pos.symbol == sym:
                    vol = int(pos.volume)
                    break
    except Exception as e:
        log.warning('[Sell] get_position failed: %s', e)

    context.pos_info.pop(sym, None)
    sector = info.get('sector', SYMBOL_SECTOR.get(sym, 'unknown'))
    if sector in context.sector_pos:
        del context.sector_pos[sector]

    pnl_pct = (price - info['cost']) / info['cost'] * 100

    if vol > 0:
        order_volume(symbol=sym, volume=vol, side=OrderSide_Sell,
                     order_type=OrderType_Market, position_effect=PositionEffect_Close,
                     account=acct if acct else "")

    strat = info.get('strategy', '?')
    log.info('[SELL] %s | %s | %s | %.2f | %+.2f%% | %s',
             sym, sector, reason, price, pnl_pct, strat)
    try:
        trace.sell(strat, sym, pnl_pct/100, reason, context.regime)
    except Exception:
        pass

    exec_engine.note_trade_result(pnl_pct / 100, getattr(context, '_today', ''))

    context.stats['total_trades'] += 1
    context.stats['total_pnl'] += pnl_pct
    if pnl_pct > 0:
        context.stats['wins'] += 1
        if strat in context.strategy_stats:
            context.strategy_stats[strat]['wins'] += 1
    else:
        context.stats['losses'] += 1
    if strat in context.strategy_stats:
        context.strategy_stats[strat]['total'] += 1


# =============================================================================
# Backtest finished
# =============================================================================

def on_backtest_finished(context, indicator):
    s = context.stats
    pos_count = len(context.pos_info)
    log.info('=' * 56)
    log.info('  Backtest Done - V29.8 VRC')
    log.info('=' * 56)
    log.info('  Trades: %d | Win: %d | Loss: %d | WR: %.1f%%',
             s['total_trades'], s['wins'], s['losses'],
             (s['wins']/s['total_trades']*100) if s['total_trades']>0 else 0)
    log.info('  Cum PnL: %+.2f%%', s['total_pnl'])
    log.info('  Remaining: %d pos', pos_count)
    log.info('  ---- By Strategy ----')
    for name in ['MR','MOM','VRC','BK','DV','RT']:
        ss = context.strategy_stats[name]
        if ss['total'] > 0:
            log.info('  %s: %d trades WR %.1f%%',
                     name, ss['total'], ss['wins']/ss['total']*100)
    log.info('=' * 56)


def handle_error(context, error_code, error_msg, **kwargs):
    log.error('[Error] code=%s msg=%s', error_code, error_msg)


# =============================================================================
# Entry
# =============================================================================

if __name__ == '__main__':
    run(
        filename='main.py',
        backtest_start_time=config.BACKTEST_START,
        backtest_end_time=config.BACKTEST_END,
        backtest_initial_cash=config.BACKTEST_CASH,
        backtest_adjust=ADJUST_PREV,
    )
