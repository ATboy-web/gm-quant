"""
offline_backtest.py - V29.4 离线回测脚本

V29.4 改进（全策略激活 + 策略配额制）:
  根因: sector_config.py 未同步 → MR/BK/DV/RT 未启用 → VP 垄断
  修复: 全面同步所有 .py 文件 + executor 策略配额制 (每策略≤2只)
  config: RSI_BUY 29→33, ENTRY_THRESHOLD 0.42→0.36 (适配2024-2026牛市)
  VP: 保留 V29.2 趋势硬门移除

V29.2 改进（修复多策略竞争中的单策略歧视）:
  executor: 置信度改用 max(confidences)×(1+共识加成), 不再用 avg
            仓位比例下限提升: 双确认0.60→0.75, 单0.40→0.55
  VP: 移除 V29.1 趋势硬门(单策略测试证实有害 +8.29%→+0.75%)
  根因: VP独立运行 +8.29%, 多策略 -27.7%, 差距来自投票机制而非策略逻辑

V29 改进（MOM/DV 策略优化）:
  MOM: 入场门槛0.35→0.55, 量能硬门1.1→1.3, RSI下限45, 均线分离>1.5%
  DV: 低位 AND(原OR), 60d<0%, 20d<-4%, RSI 33-52, 门槛0.72, 价<MA60
  MOM权重: 8行业禁用, 4行业降权40-60%, BK补偿提权
  DV权重: 全行业降权~30%
  1. 入场适中: ENTRY_THRESHOLD 0.42, RSI_BUY 29
  2. 止损适中: ATR_STOP_MULT 1.4, STOP_LOSS_CAP 0.07
  3. 仓位适中: POSITION_PCT 0.14, MAX_TRADES 10
  4. 熔断回退: 连亏3笔/冷却5天, cooldown 2天
  5. 各行业 entry_threshold 降低 ~0.02
  6. Bug修复: record_buy 缺失(MAX_TRADES失效), 熔断状态持久化修复

V27 改进:
  1. 收紧参数: RSI买入28, 入场阈值0.45, 止损1.3倍ATR/6%硬止损
  2. 延长冷却期: 1天→3天, 减少Whipsaw
  3. 提高买入门槛: 投票≥0.8(原0.5), 减少单策略弱信号
  4. 降低交易频率: 单股最多8次(原12), 连亏2笔熔断
  5. 性能优化: 延迟构建data_cache, 行业动量缓存化, 减少切片

V20 改进:
  1. 新增反转确认策略(RT)
  2. 6策略体系: MR + MOM + VP + BK + DV + RT
  3. 化工/新能源/煤炭行业针对性优化

V19.2 改进:
  1. 新增突破策略(BK)和红利策略(DV)
  2. 新能源/公用事业参数优化
  3. 策略工厂支持5策略

V19 改进:
  1. 行业差异化策略参数
  2. 策略工厂动态创建
  3. executor 执行器复用
  4. 与 GM 终端解耦，纯 Python 回测
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import time
from datetime import datetime, timedelta
from gm.api import *

import config
import indicators
import stock_pool
import screener
import sector_config
import executor
import trace
import gm_logger as logger
import strategy_mr
import strategy_momentum
import strategy_vp
import strategy_breakout
import strategy_dividend
import strategy_reversal
import fusion
import visualizer

# =============================================================================
# 全局设置
# =============================================================================

set_token(config.GM_TOKEN)

SYMBOLS = stock_pool.get_all_symbols()
MARKET_INDEX = config.MARKET_INDEX
SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()

logger.setup_logger(name='offline_backtest')
log = logger.log

log.info('=' * 56)
log.info('  V28 \u79bb\u7ebf\u56de\u6d4b \u2014 \u516d\u7b56\u7565\u884c\u4e1a\u5dee\u5f02\u5316\u878d\u5408\u6846\u67b6')
log.info('  策略: MR + MOM + VP + BK + DV + RT')
log.info('  股票池: %d 只 / %d 行业', len(SYMBOLS), len(stock_pool.get_sector_list()))
log.info('=' * 56)
sector_config.print_summary()


# =============================================================================
# 数据获取
# =============================================================================

def fetch_history(symbol, start, end, freq='1d'):
    try:
        df = history(
            symbol=symbol, frequency=freq,
            start_time=start, end_time=end,
            adjust=ADJUST_PREV, df=True
        )
        if df is not None and len(df) > 0:
            df = df.sort_values('bob').reset_index(drop=True)
            return df
    except Exception:
        pass
    return None


def preload_all_data(start, end):
    log.info('[数据] 正在下载历史数据...')
    data = {}
    all_syms = list(SYMBOLS) + [MARKET_INDEX]

    for i, sym in enumerate(all_syms):
        df = fetch_history(sym, start, end)
        if df is not None and len(df) >= config.MIN_DATA_BARS:
            data[sym] = df
        if (i + 1) % 10 == 0 or (i + 1) == len(all_syms):
            log.info('  进度: %d/%d', i + 1, len(all_syms))

    log.info('[数据] 完成: 成功 %d/%d', len(data), len(all_syms))
    return data


# =============================================================================
# V19 回测引擎
# =============================================================================

class V19BacktestEngine:

    def __init__(self, data, start_cash=25000):
        self.data = data
        self.cash = float(start_cash)
        self.initial_cash = float(start_cash)
        self.positions = {}
        self.trades = []
        self.daily_values = []

        # V19 执行器
        self.exec_engine = executor.TradeExecutor()

        if MARKET_INDEX in data:
            self.bar_dates = list(data[MARKET_INDEX]['bob'].dt.strftime('%Y-%m-%d'))

        log.info('[引擎] 交易日数: %d | 初始资金: %.0f',
                 len(self.bar_dates), start_cash)

        # V27: 性能优化 — 预计算每个bar_idx的slice边界，避免重复iloc
        self._slices_cache = {}
        self._sector_momentum_cache = {}

        # 策略统计
        self.strategy_stats = {
            'MR':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'MOM': {'wins': 0, 'total': 0, 'pnl': 0.0},
            'VP':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'BK':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'DV':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'RT':  {'wins': 0, 'total': 0, 'pnl': 0.0},
        }
        # 行业统计
        self.sector_stats = {}

    def run(self, progress_callback=None):
        """运行回测。V29.4: 支持 progress_callback 用于实时可视化。"""
        log.info('[引擎] 开始回测 (V29 优化)...')
        for i, date_str in enumerate(self.bar_dates):
            self._daily_bar(date_str, i)
            self._record_daily_value(date_str, i)

            if (i + 1) % 50 == 0:
                total_val = self.daily_values[-1]['total'] if self.daily_values else 0
                pos_count = len(self.positions)
                ret = (total_val - self.initial_cash) / self.initial_cash * 100
                log.info('  [%s] 进度 %d/%d | 净值 %.0f (%+.1f%%) | 持仓 %d',
                         date_str, i + 1, len(self.bar_dates), total_val, ret, pos_count)
                # V29.4: 更新可视化加载窗口
                if progress_callback:
                    progress_callback(i + 1, len(self.bar_dates), total_val, ret, pos_count)

        self._print_summary()

    def _daily_bar(self, date_str, bar_idx):
        if bar_idx < config.DATA_COUNT:
            return

        # V19.2: 清理过期冷却期
        self.exec_engine.cleanup_cooldowns(date_str)

        regime = self._detect_regime(bar_idx)
        regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

        # V27: 只构建持仓数据用于出场检查
        pos_info_copy = {sym: dict(pos) for sym, pos in self.positions.items()}
        data_cache = {}
        for sym in self.positions:
            df = self._get_df_slice(sym, bar_idx)
            if df is not None:
                data_cache[sym] = df

        sells = self.exec_engine.check_exits(
            pos_info_copy, data_cache, regime, today_str=date_str
        )

        for sym, price, vote, info in sells:
            if sym in self.positions:
                self._execute_sell(sym, price, vote['reason'], date_str)
                self.exec_engine.record_sell(sym, date_str)

        # 行业动量 (V27: 缓存化)
        sector_momentum = self._calc_sector_momentum_cached(bar_idx)
        sentiment = {}
        for sec, mom in sector_momentum.items():
            sentiment[sec] = max(-1.0, min(1.0, mom * 5))
        self.exec_engine._sentiment = sentiment

        # 入场: 检查是否还有空间
        max_pos = regime_cfg['max_positions']
        if len(self.positions) < max_pos:
            # V27: 补充构建候选股数据
            for sym in SYMBOLS:
                if sym not in data_cache:
                    df = self._get_df_slice(sym, bar_idx)
                    if df is not None:
                        data_cache[sym] = df

            occupied = set(p.get('sector') for p in self.positions.values())
            candidates = self.exec_engine.find_buy_candidates(
                SYMBOLS, occupied, self.positions,
                data_cache, sector_momentum, regime, today_str=date_str
            )
            self._do_buys(candidates, max_pos, date_str)

    def _do_buys(self, candidates, max_pos, date_str):
        remaining = max_pos - len(self.positions)
        if remaining <= 0:
            return

        taken_sectors = set(p.get('sector') for p in self.positions.values())
        taken_count = 0

        for c in candidates:
            if taken_count >= remaining:
                break
            sector = c['sector']
            if sector in taken_sectors:
                continue

            sym = c['symbol']
            price = c['price']

            qty = self.exec_engine.calc_position_size(
                c, self.cash, remaining - taken_count
            )
            if qty < 100:
                continue

            self.cash -= price * qty
            self.positions[sym] = {
                'vol': qty, 'cost': price, 'peak': price,
                'entry_date': date_str, 'sector': sector,
                'strategy': c['best_strategy'],
                'voters': c.get('voters', []),
                'confidence': c['confidence'],
            }
            taken_sectors.add(sector)
            taken_count += 1

            # V28: 追踪单只股票交易次数（V27遗漏，导致MAX_TRADES_PER_SYMBOL在离线回测中失效）
            self.exec_engine.record_buy(sym)

            rsi_str = ' RSI=%.0f' % c['rsi'] if c.get('rsi') else ''
            log.info('[买入] %s | %s | %s | 策略:%s | %.2f×%d%s',
                     date_str, sym, c['reason'],
                     c['best_strategy'], price, qty, rsi_str)

            # V27: 记录买入交易
            self.trades.append({
                'date': date_str, 'symbol': sym, 'side': 'BUY',
                'price': price, 'vol': qty, 'pnl_pct': 0,
                'reason': c['reason'], 'sector': sector,
                'strategy': c['best_strategy'],
            })

    def _get_df_slice(self, symbol, bar_idx):
        if symbol not in self.data:
            return None
        df = self.data[symbol]
        if bar_idx >= len(df):
            return None
        return df.iloc[:bar_idx + 1]

    def _detect_regime(self, bar_idx):
        df = self._get_df_slice(MARKET_INDEX, bar_idx)
        if df is None:
            return 'range'
        closes = df['close'].values
        return indicators.classify_regime(
            closes,
            ma_period=config.REGIME_MA_PERIOD,
            bear_threshold=config.REGIME_BEAR_THRESHOLD
        )

    def _execute_sell(self, sym, price, reason, date_str):
        if sym not in self.positions:
            return
        pos = self.positions[sym]
        vol = pos['vol']
        cost_price = pos['cost']
        pnl_pct = (price - cost_price) / cost_price * 100
        sector = pos.get('sector', '未知')
        strat = pos.get('strategy', '?')
        entry_date = pos.get('entry_date', '')

        # 算持仓天数
        hold_days = 0
        if entry_date:
            try:
                from datetime import datetime as dt
                hold_days = (dt.strptime(date_str, '%Y-%m-%d') -
                             dt.strptime(entry_date, '%Y-%m-%d')).days
            except Exception:
                pass

        self.cash += price * vol

        self.trades.append({
            'date': date_str, 'symbol': sym, 'side': 'SELL',
            'price': price, 'vol': vol, 'pnl_pct': pnl_pct,
            'reason': reason, 'sector': sector, 'strategy': strat,
            'cost_price': cost_price, 'hold_days': hold_days,
            'entry_date': entry_date,
        })

        # 行业统计
        if sector not in self.sector_stats:
            self.sector_stats[sector] = {'wins': 0, 'total': 0, 'pnl': 0.0}
        self.sector_stats[sector]['total'] += 1
        self.sector_stats[sector]['pnl'] += pnl_pct
        if pnl_pct > 0:
            self.sector_stats[sector]['wins'] += 1

        del self.positions[sym]

        # 策略统计
        if strat in self.strategy_stats:
            self.strategy_stats[strat]['total'] += 1
            self.strategy_stats[strat]['pnl'] += pnl_pct
            if pnl_pct > 0:
                self.strategy_stats[strat]['wins'] += 1

        log.info('[卖出] %s | %s | %s | 价%.2f | %+.2f%% | %s',
                 date_str, sym, reason, price, pnl_pct, strat)

        # V27: 通知执行器记录交易结果，触发连亏熔断
        self.exec_engine.note_trade_result(pnl_pct / 100, date_str)

    def _calc_sector_momentum_cached(self, bar_idx):
        """V27: 缓存化行业动量计算。每10个bar才重算一次提高速度。"""
        cache_key = bar_idx // 10
        if cache_key in self._sector_momentum_cache:
            return self._sector_momentum_cache[cache_key]
        result = self._calc_sector_momentum(bar_idx)
        self._sector_momentum_cache[cache_key] = result
        return result

    def _calc_sector_momentum(self, bar_idx):
        momentum = {}
        for sector in stock_pool.get_sector_list():
            stocks = stock_pool.filter_by_sector(sector)
            rets = []
            for sym in stocks:
                df = self._get_df_slice(sym, bar_idx)
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

    def _record_daily_value(self, date_str, bar_idx):
        """V27: 优化 — 直接计算含仓市值，减少重复切片。"""
        market_value = 0.0
        for sym, pos in self.positions.items():
            df = self.data.get(sym)
            if df is not None and bar_idx < len(df):
                cur_price = float(df['close'].values[bar_idx])
                market_value += cur_price * pos['vol']

        total_value = self.cash + market_value
        self.daily_values.append({
            'date': date_str, 'cash': self.cash,
            'market': market_value, 'total': total_value,
        })

    def _print_summary(self):
        if not self.daily_values:
            log.info('[结果] 无交易记录')
            return

        df = pd.DataFrame(self.daily_values)
        final_value = df['total'].iloc[-1]
        initial = self.initial_cash
        total_return = (final_value - initial) / initial * 100

        df['cummax'] = df['total'].cummax()
        df['drawdown'] = (df['total'] - df['cummax']) / df['cummax']
        max_dd = df['drawdown'].min() * 100

        sell_trades = [t for t in self.trades if t['side'] == 'SELL']
        win_trades = [t for t in sell_trades if t['pnl_pct'] > 0]
        win_rate = len(win_trades) / len(sell_trades) * 100 if sell_trades else 0

        log.info('=' * 56)
        log.info('  V20 六策略行业差异化回测结果摘要')
        log.info('=' * 56)
        log.info('  初始资金:   %.0f', initial)
        log.info('  最终净值:   %.0f', final_value)
        log.info('  总收益率:   %+.2f%%', total_return)
        log.info('  最大回撤:   %.2f%%', max_dd)
        log.info('  交易次数:   %d (卖出%d)', len(self.trades), len(sell_trades))
        log.info('  胜率:       %.1f%% (%d/%d)',
                 win_rate, len(win_trades), len(sell_trades))
        if sell_trades:
            log.info('  平均盈亏:   %+.2f%%',
                     np.mean([t['pnl_pct'] for t in sell_trades]))

        # ---- 策略分项 ----
        log.info('  ---- 策略分项 ----')
        for name in ['MR', 'MOM', 'VP', 'BK', 'DV', 'RT']:
            ss = self.strategy_stats[name]
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                log.info('  %s: 交易%d 胜率%.1f%% 累计盈亏%+.1f%%',
                         name, ss['total'], wr, ss['pnl'])

        # ---- 行业分项 ----
        log.info('  ---- 行业分项 ----')
        for sector in sorted(self.sector_stats.keys()):
            ss = self.sector_stats[sector]
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                log.info('  %-6s: 交易%d 胜率%.1f%% 累计%+.1f%%',
                         sector, ss['total'], wr, ss['pnl'])

        log.info('=' * 56)

        # 最近 10 笔交易
        if sell_trades:
            log.info('  最近 10 笔卖出:')
            for t in sell_trades[-10:]:
                log.info('  %s %s %-6s %+.2f%% %s %s',
                         t['date'], t['symbol'], t.get('strategy', '?'),
                         t['pnl_pct'], t.get('reason', ''), t.get('sector', ''))


# =============================================================================
# 主程序
# =============================================================================

def run_backtest(enable_visual=False, skip_prompt=False):
    """
    运行离线回测，可选择打开可视化窗口。
    
    V29.4: 抽取为独立函数，无论从命令行 python offline_backtest.py 还是
    掘金终端 IDE 的回测按钮调用，都能正确触发可视化。
    
    用法:
        python offline_backtest.py              # 交互式
        python offline_backtest.py --visual     # 跳过交互，直接打开可视化
        python offline_backtest.py --no-visual  # 跳过交互，不打开可视化
    """
    global _engine_ref
    if skip_prompt:
        visualizer.VISUAL_ENABLED = enable_visual
    else:
        visualizer.prompt_visual()

    start_date = config.BACKTEST_START[:10]
    end_date   = config.BACKTEST_END[:10]

    all_data = preload_all_data(start_date, end_date)

    if MARKET_INDEX not in all_data:
        log.error('[错误] 无法获取大盘指数数据，退出')
        return

    if len(all_data) < 5:
        log.error('[错误] 有效股票数据不足，退出')
        return

    _t0 = time.time()
    engine = V19BacktestEngine(all_data, start_cash=config.BACKTEST_CASH)

    # V29.4: 回测前立即弹出加载窗口
    if visualizer.VISUAL_ENABLED:
        title = f'gm-quant V29.4 | {start_date[:10]} ~ {end_date[:10]}'
        visualizer.open_loading_window(title)

        def _update_vis(step, total, nav, ret_pct, positions):
            visualizer.update_loading(
                f'回测进行中... {step}/{total}\n'
                f'净值: {nav:,.0f} ({ret_pct:+.1f}%) | 持仓: {positions}只'
            )

        engine.run(progress_callback=_update_vis)
    else:
        engine.run()

    _elapsed = time.time() - _t0

    log.info('[耗时] 回测总耗时: %.1f 分钟 (%.1f 秒)', _elapsed / 60, _elapsed)

    # V29.4: 关闭加载窗口，打开完整可视化
    if visualizer.VISUAL_ENABLED:
        visualizer.update_loading('回测完成，加载可视化...')
        print('[Vis] 数据转换中...', flush=True)
        viz_data = visualizer.from_backtest_engine(engine)
        print(f'[Vis] 加载 {len(viz_data.trades)} 笔交易, {len(viz_data.daily_values)} 日净值', flush=True)
        visualizer.close_loading_window()
        visualizer.launch_visualizer(viz_data, _elapsed)

    _engine_ref = engine
    return engine


_engine_ref = None  # V29.4: 方便外部获取引擎引用


if __name__ == '__main__':
    if '--visual' in sys.argv:
        run_backtest(enable_visual=True, skip_prompt=True)
    elif '--no-visual' in sys.argv:
        run_backtest(enable_visual=False, skip_prompt=True)
    else:
        run_backtest()
