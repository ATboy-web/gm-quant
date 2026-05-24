"""
main.py - V24 六策略行业差异化融合框架

  1. 新增反转确认策略(RT)
  2. 6策略体系: MR + MOM + VP + BK + DV + RT
  3. 化工/新能源/煤炭行业针对性优化（RT反转确认替代MR左侧抄底）

  1. 新增突破策略(BK)和红利策略(DV)
  2. 新能源/公用事业参数大幅优化
  3. 高波动行业添加BK，低波动行业添加DV

  1. 行业差异化: 12个行业各自配置策略参数（不再一套参数走天下）
  2. 策略工厂: 根据行业+市场状态动态创建策略实例
  3. 代码模块化: 交易逻辑抽离到 executor.py，主程序只做初始化+回调

文件结构:
  main.py          ← 你在这里（初始化+回调，~100行）
  executor.py      ← 交易执行器（入场/出场/仓位）
  sector_config.py ← 12个行业差异化策略配置
  strategy_factory.py ← 策略工厂
  strategy_base.py ← 策略基类
  strategy_mr.py   ← 均值回归策略
  strategy_momentum.py ← 动量趋势策略
  strategy_vp.py   ← 量价背离策略
  strategy_breakout.py ← 突破策略 
  strategy_dividend.py ← 红利策略 
  strategy_reversal.py ← 反转确认策略 (V20)
  fusion.py        ← 投票融合引擎
  config.py        ← 全局参数
  indicators.py    ← 技术指标
  stock_pool.py    ← 股票池
  screener.py      ← 选股引擎
  knn_matcher.py   ← KNN匹配
"""

import sys
import os
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

# =============================================================================
# 全局初始化
# =============================================================================

set_token(config.GM_TOKEN)

SYMBOLS       = stock_pool.get_all_symbols()
SYMBOL_SECTOR = stock_pool.get_symbol_sector_map()
MARKET_INDEX  = config.MARKET_INDEX

exec_engine = executor.TradeExecutor()

print('=' * 60)
print('  V24 六策略行业差异化融合框架')
print('  策略: MR + MOM + VP + BK + DV + RT(反转确认)')
print('  V21: GM主程序同步 + CSV分析针对性优化')
print('  股票池: %d 只 / %d 行业'
      % (len(SYMBOLS), len(stock_pool.get_sector_list())))
print('=' * 60)
sector_config.print_summary()

# ===== AI辅助开关 (终端启动时选择) =====
_ai_choice = ''
try:
    _ai_choice = input('\n[AI辅助] 1=开启  2=关闭 (默认2): ').strip()
except Exception:
    pass
if _ai_choice == '1':
    config.AI_ENABLED = True
    print('  AI辅助: %s | 供应商:%s | 模型:%s' % (
        '在线' if config.AI_API_KEY else '离线(无Key)',
        config.AI_PROVIDER, config.AI_MODEL))
else:
    config.AI_ENABLED = False
    print('  AI辅助: 已关闭')
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
                              'VP':  {'wins': 0, 'total': 0},
                              'BK':  {'wins': 0, 'total': 0},
                              'DV':  {'wins': 0, 'total': 0},
                              'RT':  {'wins': 0, 'total': 0}}

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
    # Step 0: 当前日期
    try:
        if bars and len(bars) > 0:
            today = bars[0].bob.strftime('%Y-%m-%d')
        else:
            today = context.now.strftime('%Y-%m-%d')
    except Exception:
        today = str(datetime.now().strftime('%Y-%m-%d'))

    context.data_cache = {}
    context._today = today

    # Step 1: 预加载数据
    loaded = _preload_data(context)

    # Step 2: 市场状态
    context.regime = _detect_regime(context)
    regime = context.regime
    regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

    # Step 3: 检查出场（使用 executor）
    sells = exec_engine.check_exits(
        context.pos_info, context.data_cache, regime, context, today
    )
    for sym, price, vote, info in sells:
        _do_sell(context, sym, price, vote['reason'], info)
        exec_engine.record_sell(sym, today)

    exec_engine.cleanup_cooldowns(today)

    # Step 4: 行业动量
    sector_momentum = screener.calc_sector_momentum(context)

    # Step 5: 选股入场（使用 executor）
    try:
        cash = get_cash()
        trace.heartbeat(len(context.pos_info), cash.available, cash.nav, getattr(context, '_sentiment', None))
    except Exception:
        trace.heartbeat(len(context.pos_info), 0, 0, None)
    max_pos = regime_cfg['max_positions']
    occupied = set(context.sector_pos.keys())
    if len(context.pos_info) < max_pos:
        candidates = exec_engine.find_buy_candidates(
            SYMBOLS, occupied, context.pos_info,
            context.data_cache, sector_momentum, regime
        )
        _do_buys(context, candidates, max_pos)

    # 状态
    pos_count = len(context.pos_info)
    print('[状态] %s | %s | 数据:%d只 | 持仓:%d/%d'
          % (today, regime, loaded, pos_count, max_pos))


# =============================================================================
# 数据获取辅助
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
    closes = df['close'].values
    return indicators.classify_regime(
        closes,
        ma_period=config.REGIME_MA_PERIOD,
        bear_threshold=config.REGIME_BEAR_THRESHOLD
    )


# =============================================================================
# 交易执行
# =============================================================================

def _do_buys(context, candidates, max_pos):
    """执行买入。"""
    remaining = max_pos - len(context.pos_info)
    if remaining <= 0:
        return

    cash_info = get_cash()
    available_cash = float(cash_info.available)
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

        order_volume(
            symbol=sym, volume=qty,
            side=OrderSide_Buy,
            order_type=OrderType_Market,
            position_effect=PositionEffect_Open
        )
        try: trace.buy(c.get('best_strategy','?'), sym, price, c.get('position_pct',0), len(c.get('voters',[])), context.regime)
        except: pass

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
        print('[买入] %s | %s(%s) | %s | 策略:%s | %.2f×%d%s'
              % (sym, sector, vol_group, c['reason'],
                 c['best_strategy'], price, qty, rsi_str))


def _do_sell(context, sym, price, reason, info):
    """执行卖出。"""
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
    try: trace.sell(strat, sym, pnl_pct/100, reason, context.regime)
    except: pass

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
    print('  回测结束 — V24 六策略行业差异化融合框架')
    print('=' * 56)
    print('  总交易: %d | 胜: %d | 负: %d | 胜率: %.1f%%'
          % (s['total_trades'], s['wins'], s['losses'],
             (s['wins'] / s['total_trades'] * 100) if s['total_trades'] > 0 else 0))
    print('  累计盈亏: %+.2f%%' % s['total_pnl'])
    print('  剩余持仓: %d 只' % pos_count)
    print('  ---- 策略分项 ----')
    for name in ['MR', 'MOM', 'VP', 'BK', 'DV', 'RT']:
        ss = context.strategy_stats[name]
        if ss['total'] > 0:
            print('  %s: 交易%d 胜率%.1f%%' %
                  (name, ss['total'], ss['wins'] / ss['total'] * 100))
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
