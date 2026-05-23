"""
main.py - V16 多因子自适应均值回归策略

================================================================================
策略核心理念
================================================================================
不是简单的 "RSI < 32 就买"，而是一个完整的量化决策系统:

  1. 市场状态判断   → 判断现在是牛/熊/震荡，自适应调整参数
  2. 多因子选股     → 六因子综合评分，自动分辨"有机会"和"该沉淀"
  3. ATR 动态风控   → 每只股票使用自身波动率计算止损，而非固定 5%
  4. 行业分散       → 同行业最多 1 只，优选强势行业中的超卖股
  5. 波动率仓位     → 低波动股票仓位加成，高波动股票仓位打折

================================================================================
策略流程（每日 14:50）
================================================================================
  Step 1: 标记市场状态（牛/熊/震荡），应用自适应参数
  Step 2: 预加载所有股票数据到缓存
  Step 3: 检查所有持仓的出场条件（ATR止损/跟踪止盈/RSI过热/时间止损）
  Step 4: 计算行业动量
  Step 5: 多因子筛选 + 评分排序
  Step 6: 按评分从高到低买入，行业分散，仓位自适应

================================================================================
模块架构
================================================================================
  config.py      → 所有可调参数（多因子权重、ATR倍数、市场状态参数等）
  indicators.py  → 纯函数技术指标（RSI、ATR、MA、量比、形态识别、市场分类）
  stock_pool.py  → 35 只精选股票候选池（12 个行业）
  screener.py    → 六因子选股打分引擎
  main.py        → 策略主程序（状态管理、交易执行、日志输出）
================================================================================
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gm.api import *

import config
import indicators
import stock_pool
import screener

# =============================================================================
# 全局初始化
# =============================================================================

set_token(config.GM_TOKEN)

# 股票池
SYMBOLS       = stock_pool.get_all_symbols()
SYMBOL_SECTOR = stock_pool.get_symbol_sector_map()

# 大盘指数符号
MARKET_INDEX = config.MARKET_INDEX

print('╔' + '═' * 58 + '╗')
print('║  V16 多因子自适应均值回归策略')
print('║  股票池: %d 只 / %d 个行业' % (len(SYMBOLS), len(stock_pool.get_sector_list())))
print('║  六因子选股 + ATR动态风控 + 市场状态自适应 + 行业波动率仓位')
print('╚' + '═' * 58 + '╝')


# =============================================================================
# init() — GM 框架初始化
# =============================================================================

def init(context):
    """
    策略初始化:
      - 创建持仓跟踪结构
      - 订阅股票 + 大盘指数数据
      - 注册每日 14:50 调度
    """
    # ---- 持仓跟踪 ----
    # pos_info: {symbol: {'cost': 成本价, 'peak': 最高价,
    #                     'entry_date': 入场日期, 'sector': 行业}}
    context.pos_info = {}

    # sector_pos: {sector: symbol} — 行业占用情况
    context.sector_pos = {}

    # data_cache: 同 bar 数据缓存
    context.data_cache = {}

    # regime: 当前市场状态 'bull' / 'range' / 'bear'
    context.regime = 'range'

    # ---- 统计 ----
    context.stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0.0}

    # ---- 订阅数据 ----
    # 全部股票 + 大盘指数
    all_symbols = list(SYMBOLS) + [MARKET_INDEX]
    subscribe(symbols=all_symbols, frequency='1d', count=config.DATA_COUNT)

    # ---- 调度 ----
    schedule(schedule_func=on_bar, date_rule='1d', time_rule='14:50:00')

    # ---- 回测完成回调 ----
    context.on_backtest_finished = on_backtest_finished


# =============================================================================
# on_bar() — 每日交易主逻辑
# =============================================================================

def on_bar(context, bars=None):
    try:
        _on_bar_impl(context, bars)
    except Exception as e:
        import traceback
        print('[异常] on_bar 出错: %s' % e)
        traceback.print_exc()


def _on_bar_impl(context, bars=None):
    """
    每日 14:50 触发一次（schedule 回调）。
    GM 框架有时会额外传入 bars 参数，因此保留 bars 以兼容两种调用方式。

    完整流程：
      市场状态 → 数据预加载 → 出场检查 → 行业动量 → 选股打分 → 入场执行
    """
    # ---- Step 0: 清缓存 ----
    context.data_cache = {}

    # ---- Step 1: 市场状态判断 ----
    context.regime = _detect_regime(context)
    regime_cfg = config.REGIME_PARAMS.get(context.regime, config.REGIME_PARAMS['range'])

    # ---- Step 2: 预加载全部股票数据 ----
    loaded_count = _preload_data(context)

    # ---- Step 3: 检查出场 ----
    _check_exits(context, regime_cfg)

    # ---- Step 4: 行业动量计算 ----
    sector_momentum = screener.calc_sector_momentum(context)

    # ---- Step 5: 多因子选股打分 ----
    candidates = screener.screen_all(context, sector_momentum)

    # ---- Step 6: 执行入场 ----
    taken = 0
    if len(context.pos_info) < regime_cfg['max_positions']:
        taken = _execute_entries(context, candidates, regime_cfg)

    # ---- 每日状态日志（始终输出，方便监控）----
    pos_count = len(context.pos_info)
    # 尝试获取当前日期
    try:
        if bars and len(bars) > 0:
            date_str = bars[0].bob.strftime('%Y-%m-%d')
        else:
            date_str = str(context.now.strftime('%Y-%m-%d'))
    except Exception:
        date_str = '--'
    print('[状态] %s | %s | 数据:%d只 | 候选:%d只 | 买入:%d | 持仓:%d/%d | RSI阈值:%d'
          % (date_str, context.regime, loaded_count, len(candidates), taken,
             pos_count, regime_cfg['max_positions'], regime_cfg.get('rsi_buy', config.RSI_BUY)))


# =============================================================================
# 数据获取（带缓存）
# =============================================================================

def _preload_data(context):
    """预加载所有股票 + 大盘指数的历史数据到缓存。返回成功加载的股票数。"""
    all_symbols = list(SYMBOLS) + [MARKET_INDEX]
    loaded = 0
    for sym in all_symbols:
        df = _get_bar_data(context, sym)
        if df is not None:
            loaded += 1
    return loaded


def _get_bar_data(context, sym):
    """获取股票日线 DataFrame，同 bar 内缓存。"""
    if sym in context.data_cache:
        return context.data_cache[sym]

    try:
        # ⚠️ context.data() 只有 4 个参数: symbol, frequency, count, fields
        # skip_suspended/fill_missing 是 history() 的参数，context.data() 不支持！
        df = context.data(
            symbol=sym,
            frequency='1d',
            count=config.DATA_COUNT,
        )
        if df is not None and len(df) >= config.MIN_DATA_BARS:
            context.data_cache[sym] = df
            return df
        elif df is not None:
            context.data_cache[sym] = None  # 数据条数不足
        else:
            context.data_cache[sym] = None
    except Exception as e:
        # 第一个失败的标的打印异常信息用于排查
        if not hasattr(context, '_data_error_printed'):
            context._data_error_printed = True
            import traceback
            print('[错误] context.data(%s) 异常: %s' % (sym, e))
            traceback.print_exc()
        context.data_cache[sym] = None

    return None


# =============================================================================
# 市场状态判断
# =============================================================================

def _detect_regime(context):
    """
    基于大盘指数（上证综指）判断当前市场状态。

    使用 indicators.classify_regime():
      - bull:  价格 > MA60 且近 20 日跌幅 < 8%
      - bear:  近 20 日跌幅 > 8%（严重下跌）
      - range: 其余情况

    返回:
        str: 'bull' | 'range' | 'bear'
    """
    df = _get_bar_data(context, MARKET_INDEX)
    if df is None:
        return 'range'

    closes = df['close'].values
    regime = indicators.classify_regime(
        closes,
        ma_period=config.REGIME_MA_PERIOD,
        bear_threshold=config.REGIME_BEAR_THRESHOLD
    )
    return regime


# =============================================================================
# 出场逻辑
# =============================================================================

def _check_exits(context, regime_cfg):
    """
    遍历所有持仓，按优先级检查出场条件。

    出场条件:
      1. ATR 固定止损: 亏损 > min(STOP_LOSS_CAP, ATR_STOP_MULT × ATR)
      2. ATR 跟踪止盈: 从高点回撤 > ATR_TRAIL_MULT × ATR
      3. RSI 过热: RSI > RSI_EXIT
      4. 时间止损: 持仓 > TIME_STOP_DAYS 且未盈利
    """
    for sym in list(context.pos_info.keys()):
        info = context.pos_info[sym]
        df    = _get_bar_data(context, sym)
        if df is None:
            continue

        closes = df['close'].values
        highs  = df['high'].values
        lows   = df['low'].values
        opens  = df['open'].values

        if len(closes) < 2:
            continue

        cur_price = float(closes[-1])

        # ---- 更新最高价 ----
        if cur_price > info['peak']:
            info['peak'] = cur_price

        # ---- 计算 ATR 和波动率 ----
        atr = indicators.calc_atr(highs, lows, closes, config.ATR_PERIOD)
        if atr is None:
            atr = cur_price * 0.03  # 默认 3% 波动率

        # ---- 盈亏 ----
        pnl = (cur_price - info['cost']) / info['cost']

        # ---- 出场判定 ----
        reason = None

        # 条件 1: ATR 固定止损
        stop_mult = regime_cfg.get('atr_stop_mult', config.ATR_STOP_MULT)
        stop_loss_pct = atr / cur_price * stop_mult
        stop_loss_pct = min(stop_loss_pct, config.STOP_LOSS_CAP)  # 上限保护
        stop_loss_pct = max(stop_loss_pct, 0.03)                   # 下限 3%

        if pnl <= -stop_loss_pct:
            reason = 'ATR止损(%.1f%%)' % (stop_loss_pct * 100)

        # 条件 2: ATR 跟踪止盈（仅盈利状态）
        elif info['peak'] > info['cost']:
            trail_pct = atr / cur_price * config.ATR_TRAIL_MULT
            trail_pct = max(trail_pct, 0.04)  # 至少 4% 回撤才触发
            if cur_price <= info['peak'] * (1.0 - trail_pct):
                reason = 'ATR跟踪(%.1f%%)' % (trail_pct * 100)

        # 条件 3: RSI 过热
        if reason is None:
            rsi = indicators.calc_rsi(closes, period=config.RSI_PERIOD)
            if rsi is not None and rsi > config.RSI_EXIT:
                reason = 'RSI过热(%.0f)' % rsi

        # 条件 4: 时间止损
        if reason is None:
            days_held = _count_holding_days(info)
            if days_held >= config.TIME_STOP_DAYS and pnl < 0.02:
                reason = '时间止损(%dd)' % days_held

        # ---- 执行卖出 ----
        if reason:
            _execute_sell(context, sym, cur_price, reason, info, atr / cur_price)


def _count_holding_days(info):
    """估算持仓天数（基于 bar 计数）。"""
    if 'bar_count' not in info:
        info['bar_count'] = 0
    info['bar_count'] += 1
    return info['bar_count']


def _execute_sell(context, sym, price, reason, info, vol_pct):
    """执行卖出操作。"""
    # 查询实际持仓
    vol = 0
    all_positions = get_position()
    if all_positions:
        for pos in all_positions:
            if pos.symbol == sym:
                vol = int(pos.volume)
                break

    # 清理记录
    context.pos_info.pop(sym, None)
    sector = info.get('sector', SYMBOL_SECTOR.get(sym, '未知'))
    if sector in context.sector_pos:
        del context.sector_pos[sector]

    # 计算盈亏
    pnl_pct = (price - info['cost']) / info['cost'] * 100
    days = info.get('bar_count', 0)

    # 下单
    if vol > 0:
        order_volume(
            symbol=sym,
            volume=vol,
            side=OrderSide_Sell,
            order_type=OrderType_Market,
            position_effect=PositionEffect_Close
        )

    # 日志
    print('[卖出] %s | %s | %s | 价%.2f | %+.2f%% | %dd | 波动%.1f%%'
          % (sym, sector, reason, price, pnl_pct, days, vol_pct * 100))

    # 更新统计
    context.stats['total_trades'] += 1
    context.stats['total_pnl'] += pnl_pct
    if pnl_pct > 0:
        context.stats['wins'] += 1
    else:
        context.stats['losses'] += 1


# =============================================================================
# 入场逻辑
# =============================================================================

def _execute_entries(context, candidates, regime_cfg):
    """
    按评分从高到低执行买入。

    规则:
      - 每行业最多买入 1 只
      - 总买入数 ≤ max_positions - 当前持仓数
      - 高波动行业仓位打折，低波动行业仓位加成
      - ATR 动态止损在入场时记录

    返回:
        int: 实际买入的股票数量
    """
    occupied_sectors = set(context.sector_pos.keys())
    remaining = regime_cfg['max_positions'] - len(context.pos_info)
    if remaining <= 0:
        return 0

    taken_sectors = set(occupied_sectors)
    taken_count   = 0

    # 查询可用资金（GM 下单是异步的，这里用 snapshot）
    cash_info = get_cash()
    available_cash = float(cash_info.available)
    initial_cash = available_cash  # 记录初始资金，用于计算每笔分配

    for c in candidates:
        if taken_count >= remaining:
            break

        sym    = c['symbol']
        sector = c['sector']
        price  = c['price']
        rsi    = c['rsi']
        score  = c['total']

        # 已持仓
        if sym in context.pos_info:
            continue

        # 该行业本轮已买入
        if sector in taken_sectors:
            continue

        # ---- 波动率仓位调整 ----
        vol_group = stock_pool.get_sector_volatility_group(sector)
        if vol_group == 'high':
            pos_pct = config.POSITION_PCT * config.VOL_ADJ_HIGH
        elif vol_group == 'low':
            pos_pct = config.POSITION_PCT * config.VOL_ADJ_LOW
        else:
            pos_pct = config.POSITION_PCT

        # ---- 计算买入数量（基于当前可用资金，不做递减假设）----
        # GM 异步下单，cash.available 在本 bar 内不会变
        # 用 remaining 计数限制，实际仓位由 POSITION_PCT 控制
        allocated = initial_cash * pos_pct / max(remaining - taken_count, 1)
        if allocated < price * 100:
            continue  # 资金不足 1 手

        qty = int(allocated / (price * 100)) * 100
        if qty < 100:
            continue

        # ---- 下单 ----
        order_volume(
            symbol=sym,
            volume=qty,
            side=OrderSide_Buy,
            order_type=OrderType_Market,
            position_effect=PositionEffect_Open
        )

        # ---- 记录持仓 ----
        context.pos_info[sym] = {
            'cost':       price,
            'peak':       price,
            'bar_count':  0,
            'sector':     sector,
            'entry_rsi':  rsi,
            'vol_group':  vol_group,
            'score':      score,
        }
        context.sector_pos[sector] = sym
        taken_sectors.add(sector)
        taken_count += 1
        # 不再递减 available_cash，GM 异步下单 cash 不会立即更新

        # 详细日志
        details = c['details']
        print('[买入] %s | %s(%s) | 评分%.3f | RSI%.1f | %.2f×%d | 余资%.0f'
              % (sym, sector, vol_group, score, rsi, price, qty, available_cash))
        print('       因子: RSI=%.2f 趋势=%.2f 量=%.2f 跌幅=%.2f 形态=%.2f 行业=%.2f'
              % (details['rsi_score'], details['trend_score'],
                 details['vol_score'], details['dd_score'],
                 details['reversal_score'], details['sector_score']))

    return taken_count


# =============================================================================
# 回测完成回调
# =============================================================================

def on_backtest_finished(context, indicator):
    """回测结束时的总结日志。"""
    s = context.stats
    pos_count = len(context.pos_info)

    print()
    print('=' * 56)
    print('  回测结束 — V16 多因子自适应均值回归策略')
    print('=' * 56)
    print('  总交易次数: %d  |  胜: %d  |  负: %d  |  胜率: %.1f%%'
          % (s['total_trades'], s['wins'], s['losses'],
             (s['wins'] / s['total_trades'] * 100) if s['total_trades'] > 0 else 0))
    print('  累计盈亏 : %+.2f%%' % s['total_pnl'])
    print('  剩余持仓 : %d 只' % pos_count)
    try:
        nav = context.account().nav
        print('  最终净值 : %.2f  |  资金: %.0f'
              % (nav, float(get_cash().nav)))
    except Exception:
        pass
    print('=' * 56)


# =============================================================================
# 错误处理
# =============================================================================

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
