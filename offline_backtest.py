"""
offline_backtest.py - V20 离线回测脚本

V30 改进:
  1. 新增反转确认策略(RT)
  2. 7策略体系: MR + MOM + VP + VRC + BK + DV + RT
  3. VP策略引入多维度背离检测引擎(OBV/RSI/MACD)
  4. screener新增MultiDimensionScreener五维评分

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
from datetime import datetime, timedelta

import config
import indicators
import stock_pool
import screener
import sector_config
import executor
import trace
import strategy_mr
import strategy_momentum
import strategy_breakout
import strategy_dividend
import strategy_reversal
import fusion

# =============================================================================
# 全局设置
# =============================================================================


SYMBOLS = stock_pool.get_all_symbols()
MARKET_INDEX = config.MARKET_INDEX
SYMBOL_SECTOR_MAP = stock_pool.get_symbol_sector_map()

print('=' * 60)
print('  V30 离线回测 — 七策略多维度融合框架')
print('  策略: MR + MOM + VP + VRC + BK + DV + RT')
print('  V30: VP背离引擎 + 五维评分 + 风控委员会')
print('  股票池: %d 只 / %d 行业' % (len(SYMBOLS), len(stock_pool.get_sector_list())))
print('=' * 60)
sector_config.print_summary()


# =============================================================================
# 数据获取 (V30.4: 本地SQLite数据, 无需GM终端)
# =============================================================================

import local_data_loader


def preload_all_data(start, end):
    """使用本地SQLite数据加载 (C:/lainghua/basic_data/day_bar/)。"""
    print('[数据] 正在加载本地数据...')
    all_syms = list(SYMBOLS) + [MARKET_INDEX]
    data = local_data_loader.preload_all(start, end, all_syms, verbose=True)
    print('[数据] 完成: 成功 %d/%d' % (len(data), len(all_syms)))
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

        # V29.10: 风险委员会 (仿 Vibe-Trading)
        try:
            import risk_manager
            self.risk_manager = risk_manager.RiskCommittee(initial_capital=start_cash)
        except Exception as e:
            print('[Risk] 风控模块加载失败: %s' % e)
            self.risk_manager = None

        self.bar_dates = []
        if MARKET_INDEX in data:
            df_idx = data[MARKET_INDEX]
            if 'bob' in df_idx.columns:
                try:
                    self.bar_dates = sorted(set(
                        d.strftime('%Y-%m-%d') for d in pd.to_datetime(df_idx['bob'])
                    ))
                except Exception:
                    if 'date' in df_idx.columns:
                        self.bar_dates = sorted(df_idx['date'].unique().tolist())
            elif 'date' in df_idx.columns:
                self.bar_dates = sorted(df_idx['date'].unique().tolist())

        if not self.bar_dates:
            # Fallback: 从任意股票获取日期
            for sym, df in data.items():
                if 'date' in df.columns:
                    self.bar_dates = sorted(df['date'].unique().tolist())
                    break

        print('[引擎] 交易日数: %d | 初始资金: %.0f'
              % (len(self.bar_dates), start_cash))

        # 策略统计
        self.strategy_stats = {
            'MR':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'MOM': {'wins': 0, 'total': 0, 'pnl': 0.0},
            'VRC':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'VP':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'BK':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'DV':  {'wins': 0, 'total': 0, 'pnl': 0.0},
            'RT':  {'wins': 0, 'total': 0, 'pnl': 0.0},
        }
        # 行业统计
        self.sector_stats = {}

    def run(self):
        print('[引擎] 开始回测...')
        import traceback
        for i, date_str in enumerate(self.bar_dates):
            try:
                self._daily_bar(date_str, i)
                self._record_daily_value(date_str, i)
            except Exception as e:
                print('[异常] %s 交易日处理失败: %s' % (date_str, e))
                traceback.print_exc()
                # 继续下一个交易日，不中断回测
                continue

            if (i + 1) % 50 == 0:
                total_val = self.daily_values[-1]['total'] if self.daily_values else 0
                pos_count = len(self.positions)
                ret = (total_val - self.initial_cash) / self.initial_cash * 100
                print('  [%s] 进度 %d/%d | 净值 %.0f (%+.1f%%) | 持仓 %d'
                      % (date_str, i + 1, len(self.bar_dates), total_val, ret, pos_count))
                # Write progress file for live monitor
                self._write_progress(date_str, i + 1, len(self.bar_dates), total_val, ret, pos_count)

        # Progress file for live monitor
        import os as _os
        _log_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'logs')
        _os.makedirs(_log_dir, exist_ok=True)
        self._progress_file = _os.path.join(_log_dir, 'bt_progress.json')

        try:
            self._print_summary()
        except Exception as e:
            print('[错误] _print_summary 失败: %s' % e)
            traceback.print_exc()

    def _write_progress(self, date_str, current, total, nav, ret, positions):
        try:
            import json
            d = {"type":"backtest","date":str(date_str),"current":current,
                 "total":total,"nav":nav,"ret":round(ret,2),"positions":positions,
                 "trades":len(self.trades),"wins":self.stats.get("wins",0),
                 "losses":self.stats.get("losses",0)}
            with open(self._progress_file,'w') as f:
                json.dump(d,f)
        except Exception:
            pass

    def _daily_bar(self, date_str, bar_idx):
        if bar_idx < config.DATA_COUNT:
            return

        # V19.2: 清理过期冷却期
        self.exec_engine.cleanup_cooldowns(date_str)

        regime = self._detect_regime(bar_idx)
        regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

        # 出场检查（使用 executor）
        pos_info_copy = {sym: dict(pos) for sym, pos in self.positions.items()}
        data_cache = {}
        for sym in list(self.positions.keys()) + SYMBOLS:
            df = self._get_df_slice(sym, bar_idx)
            if df is not None:
                data_cache[sym] = df

        sells = self.exec_engine.check_exits(
            pos_info_copy, data_cache, regime, today_str=date_str
        )

        for sym, price, vote, info in sells:
            if sym in self.positions:
                self._execute_sell(sym, price, vote['reason'], date_str)
                # V19.2: 记录卖出，启动冷却期
                self.exec_engine.record_sell(sym, date_str)

        # 行业动量 → 模拟市场情绪 (软化映射)
        sector_momentum = self._calc_sector_momentum(bar_idx)
        sentiment = {}
        for sec, mom in sector_momentum.items():
            sentiment[sec] = max(-1.0, min(1.0, mom * 5))  # 5%动量=+1, -5%=-1
        self.exec_engine._sentiment = sentiment

        # 入场
        max_pos = regime_cfg['max_positions']
        occupied = set(p.get('sector') for p in self.positions.values())
        if len(self.positions) < max_pos:
            candidates = self.exec_engine.find_buy_candidates(
                SYMBOLS, occupied, self.positions,
                data_cache, sector_momentum, regime
            )
            self._do_buys(candidates, max_pos, date_str)

    def _do_buys(self, candidates, max_pos, date_str):
        remaining = max_pos - len(self.positions)
        if remaining <= 0:
            return

        taken_sectors = set(p.get('sector') for p in self.positions.values())
        taken_count = 0

        # V29.10: 计算行业持仓市值 (供风控审计)
        sector_positions = {}
        for p in self.positions.values():
            sec = p.get('sector', '未知')
            val = p.get('cost', 0) * p.get('vol', 0)
            sector_positions[sec] = sector_positions.get(sec, 0) + val

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

            # ---- V29.10: 风控委员会交易前审计 ----
            if self.risk_manager:
                candidate_for_audit = dict(c)
                candidate_for_audit['qty'] = qty
                # 波动率分组
                sec_cfg = sector_config.SECTOR_CONFIGS.get(sector, {})
                candidate_for_audit['vol_group'] = sec_cfg.get('vol_group', 'medium')

                audit = self.risk_manager.audit_buy(
                    candidate_for_audit,
                    list(self.positions.values()),
                    sector_positions,
                    today_str=date_str
                )
                if not audit['approved']:
                    print('[风控拒绝] %s | %s | %s' % (date_str, sym, audit['reason']))
                    continue
                # 调整仓位
                adj = audit.get('adjusted_size', 1.0)
                if adj != 1.0:
                    new_qty = int((qty * adj) / 100) * 100
                    if new_qty >= 100:
                        qty = new_qty
                        print('[风控调整] %s | %s | 仓位调整至 %.0f%% (%d股)'
                              % (date_str, sym, adj * 100, qty))

            self.cash -= price * qty
            self.positions[sym] = {
                'vol': qty, 'cost': price, 'peak': price,
                'entry_date': date_str, 'sector': sector,
                'strategy': c['best_strategy'],
                'voters': c.get('voters', []),
                'confidence': c['confidence'],
            }
            # 更新行业持仓市值
            sector_positions[sector] = sector_positions.get(sector, 0) + price * qty
            taken_sectors.add(sector)
            taken_count += 1

            rsi_str = ' RSI=%.0f' % c['rsi'] if c.get('rsi') else ''
            print('[买入] %s | %s | %s | 策略:%s | %.2f×%d%s'
                  % (date_str, sym, c['reason'],
                     c['best_strategy'], price, qty, rsi_str))

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
        pnl_pct = (price - pos['cost']) / pos['cost'] * 100
        sector = pos.get('sector', '未知')
        strat = pos.get('strategy', '?')

        self.cash += price * vol

        # V29.10: 更新风控状态
        if self.risk_manager:
            total_val = self.cash
            for s, p in self.positions.items():
                if s != sym:
                    total_val += p.get('cost', 0) * p.get('vol', 0)
            self.risk_manager.update_state(total_val, recent_trade_pnl=pnl_pct / 100)

        self.trades.append({
            'date': date_str, 'symbol': sym, 'side': 'SELL',
            'price': price, 'vol': vol, 'pnl_pct': pnl_pct,
            'reason': reason, 'sector': sector, 'strategy': strat,
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

        print('[卖出] %s | %s | %s | 价%.2f | %+.2f%% | %s'
              % (date_str, sym, reason, price, pnl_pct, strat))

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
        market_value = 0.0
        for sym, pos in self.positions.items():
            df = self._get_df_slice(sym, bar_idx)
            if df is not None and len(df) > 0:
                cur_price = float(df['close'].values[-1])
                market_value += cur_price * pos['vol']

        total_value = self.cash + market_value
        self.daily_values.append({
            'date': date_str, 'cash': self.cash,
            'market': market_value, 'total': total_value,
        })

        # V29.10: 每日重置风控日内状态
        if self.risk_manager and bar_idx > 0:
            self.risk_manager.reset_daily(total_value)

    def _print_summary(self):
        if not self.daily_values:
            print('[结果] 无交易记录')
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

        print()
        print('=' * 60)
        print('  V20 六策略行业差异化回测结果摘要')
        print('=' * 60)
        print('  初始资金:   %.0f' % initial)
        print('  最终净值:   %.0f' % final_value)
        print('  总收益率:   %+.2f%%' % total_return)
        print('  最大回撤:   %.2f%%' % max_dd)
        print('  交易次数:   %d (卖出%d)' % (len(self.trades), len(sell_trades)))
        print('  胜率:       %.1f%% (%d/%d)'
              % (win_rate, len(win_trades), len(sell_trades)))
        print('  平均盈亏:   %+.2f%%' %
              (np.mean([t['pnl_pct'] for t in sell_trades]) if sell_trades else 0))

        # ---- 策略分项 ----
        print('  ---- 策略分项 ----')
        for name in ['MR', 'MOM', 'VRC', 'VP', 'BK', 'DV', 'RT']:
            ss = self.strategy_stats[name]
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                print('  %s: 交易%d 胜率%.1f%% 累计盈亏%+.1f%%'
                      % (name, ss['total'], wr, ss['pnl']))

        # ---- 行业分项 ----
        print('  ---- 行业分项 ----')
        for sector in sorted(self.sector_stats.keys()):
            ss = self.sector_stats[sector]
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                print('  %-6s: 交易%d 胜率%.1f%% 累计%+.1f%%'
                      % (sector, ss['total'], wr, ss['pnl']))

        # ---- V29.8: Advanced Metrics (Vibe-Trading) ----
        try:
            from vibe_integration import AdvancedMetrics
            equity = [dv['total'] for dv in self.daily_values]
            trades = [{'pnl': t['pnl_pct'], 'type': t['side']} for t in self.trades]
            m = AdvancedMetrics.calc_all(equity, trades, self.initial_cash)
            print('  ---- 高级指标 (Vibe) ----')
            print('  年化收益率: %+.2f%%' % m['annual_return'])
            print('  夏普比率:   %.2f | 索提诺: %.2f | 卡玛: %.2f'
                  % (m['sharpe'], m['sortino'], m['calmar']))
            print('  盈利因子:   %.2f | 最大连亏: %d笔 | 年化波动: %.1f%%'
                  % (m['profit_factor'], m['max_consecutive_loss'], m['volatility']))
        except Exception:
            pass

        # ---- V29.10: 统计验证引擎 (仿 Vibe-Trading) ----
        try:
            import stats_validator
            report = stats_validator.comprehensive_validation(self.trades, self.daily_values)
            self.validation_report = report
        except Exception as e:
            print('[Validator] 统计验证失败: %s' % e)

        print('=' * 60)

        # 最近 10 笔交易
        if sell_trades:
            print()
            print('  最近 10 笔卖出:')
            for t in sell_trades[-10:]:
                print('  %s %s %-6s %+.2f%% %s %s'
                      % (t['date'], t['symbol'], t.get('strategy', '?'),
                         t['pnl_pct'], t.get('reason', ''), t.get('sector', '')))


# =============================================================================
# 主程序
# =============================================================================

if __name__ == '__main__':
    start_date = config.BACKTEST_START[:10]
    end_date   = config.BACKTEST_END[:10]

    all_data = preload_all_data(start_date, end_date)

    if MARKET_INDEX not in all_data:
        print('[错误] 无法获取大盘指数数据，退出')
        sys.exit(1)

    if len(all_data) < 5:
        print('[错误] 有效股票数据不足，退出')
        sys.exit(1)

    engine = V19BacktestEngine(all_data, start_cash=config.BACKTEST_CASH)
    engine.run()

    # Visualizer (V30.4: 传入 engine data, 自动转换)
    if '--no-visual' not in sys.argv:
        try:
            import visualizer
            bt_data = visualizer.from_backtest_engine(engine)
            elapsed = (engine.bar_dates[-1] - engine.bar_dates[0]).days if hasattr(engine, 'bar_dates') and engine.bar_dates else 0
            visualizer.launch_visualizer(bt_data, elapsed_seconds=elapsed)
        except Exception as e:
            print('[Visualizer] Failed to launch:', e)


def quick_eval(param_overrides=None, silent=True, all_data=None):
    """
    快速评估 — 供 optimizer.py 调用。
    修改 config 参数 → 运行轻量回测 → 返回 (return, maxdd, sharpe, trades)

    Args:
        param_overrides: {key: value} 参数覆盖
        silent: 是否静默输出
        all_data: 可选，已下载的数据字典(复用，避免重复下载)

    注意: 此函数不会修改全局 config, 使用参数覆盖运行回测。
    """
    import config as cfg
    original = {}

    if param_overrides:
        for k, v in param_overrides.items():
            attr = k.upper() if k.islower() else k
            if hasattr(cfg, attr):
                original[k] = getattr(cfg, attr)
                setattr(cfg, attr, v)

    try:
        if not silent:
            print('[QuickEval] 参数: %s' % (param_overrides or 'default'))

        if all_data is None:
            all_data = preload_all_data(cfg.BACKTEST_START[:10], cfg.BACKTEST_END[:10])

        if MARKET_INDEX not in all_data or len(all_data) < 5:
            return 0.0, -0.2, 0.0, 999

        engine = V19BacktestEngine(all_data, start_cash=cfg.BACKTEST_CASH)
        engine.run()

        if not engine.daily_values:
            return 0.0, -0.2, 0.0, 999

        df = pd.DataFrame(engine.daily_values)
        final_val = df['total'].iloc[-1]
        ret = (final_val - engine.initial_cash) / engine.initial_cash * 100

        df['cummax'] = df['total'].cummax()
        df['drawdown'] = (df['total'] - df['cummax']) / df['cummax']
        maxdd = float(df['drawdown'].min())

        sells = [t for t in engine.trades if t['side'] == 'SELL']
        if sells:
            daily_rets = np.array([t['pnl_pct'] / 100 for t in sells])
            sharpe = float(np.mean(daily_rets) / (np.std(daily_rets) + 1e-10) * np.sqrt(252))
        else:
            sharpe = 0.0

        return ret, maxdd, sharpe, len(sells)

    except Exception as e:
        if not silent:
            print('[QuickEval] Error: %s' % e)
        return 0.0, -0.3, 0.0, 999

    finally:
        # 恢复原始参数
        for k, v in original.items():
            attr = k.upper() if k.islower() else k
            setattr(cfg, attr, v)
