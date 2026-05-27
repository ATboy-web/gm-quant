"""
standalone_backtest.py - V30.5 独立离线回测
完全零依赖GM SDK，仅使用本地SQLite数据 (C:/lainghua)
直接运行: python standalone_backtest.py
"""
import sys, os, json, traceback
import numpy as np
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import indicators
import stock_pool
import sector_config
import executor
import strategy_mr, strategy_momentum, strategy_vrc
import strategy_breakout, strategy_dividend, strategy_reversal
import fusion
from local_data_loader import preload_all
from trade_utils import calc_buy_fee, calc_sell_fee
from trade_utils import apply_slippage, check_limit_status
from indicators import calc_hurst, calc_adx
from risk_manager import RiskEngine  # V30.5: vnpy风控

# ============================================================
# 配置
# ============================================================
SYMBOLS       = stock_pool.get_all_symbols()
MARKET_INDEX  = config.MARKET_INDEX
START         = config.BACKTEST_START[:10]
END           = config.BACKTEST_END[:10]
INIT_CASH     = getattr(config, 'BACKTEST_CASH', 25000)
ENABLE_FEES   = True  # V30.5: 启用交易费用

print('=' * 60)
print('  V30.5 独立离线回测 (本地SQLite数据)')
print('  策略: MR+MOM+VRC+BK+DV+RT (6策略)')
print('  股票池: %d只 / %d行业 | 资金: ¥%d' % (len(SYMBOLS), len(stock_pool.get_sector_list()), INIT_CASH))
print('  区间: %s ~ %s' % (START, END))
print('=' * 60)
sector_config.print_summary()

# ============================================================
# 回测引擎
# ============================================================
class StandaloneBacktest:
    def __init__(self, data, start_cash=25000):
        self.data = data
        self.initial_cash = start_cash
        self.cash = start_cash
        self.positions = {}
        self.trades = []
        self.daily_values = []
        self.stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0.0}
        self.strategy_stats = {s: {'wins': 0, 'total': 0, 'pnl': 0.0}
                               for s in ['MR', 'MOM', 'VRC', 'BK', 'DV', 'RT']}
        self.sector_stats = {}
        self.exec_engine = executor.TradeExecutor()
        self.fee_stats = {'total_fees': 0.0, 'buy_fees': 0.0, 'sell_fees': 0.0}
        self.risk_engine = RiskEngine(start_cash)  # V30.5: 风控

        if MARKET_INDEX in data:
            df_idx = data[MARKET_INDEX]
            if 'date' in df_idx.columns:
                self.bar_dates = sorted(df_idx['date'].unique().tolist())
            elif 'bob' in df_idx.columns:
                self.bar_dates = sorted(set(
                    d.strftime('%Y-%m-%d') for d in pd.to_datetime(df_idx['bob'])
                ))
        if not self.bar_dates:
            first_sym = list(data.keys())[0] if data else None
            if first_sym and 'date' in data[first_sym]:
                self.bar_dates = sorted(data[first_sym]['date'].unique().tolist())

        print('[引擎] 交易日: %d | 初始资金: ¥%d' % (len(self.bar_dates), start_cash))

    def _get_df_slice(self, symbol, bar_idx):
        df = self.data.get(symbol)
        if df is None:
            return None
        end = min(bar_idx + 1, len(df))
        start = max(0, end - config.DATA_COUNT)
        if end - start < config.MIN_DATA_BARS:
            return None
        return df.iloc[start:end].reset_index(drop=True)

    def _detect_regime(self, bar_idx):
        """V30.5: 市场状态检测 — MA分类 + Hurst指数 + ADX趋势强度"""
        df = self.data.get(MARKET_INDEX)
        if df is None or bar_idx >= len(df):
            return 'range'
        closes = df['close'].values[:bar_idx + 1]

        # MA分类
        regime = indicators.classify_regime(closes, config.REGIME_MA_PERIOD, config.REGIME_BEAR_THRESHOLD)

        # Hurst指数微调 (每20个bar计算一次)
        if bar_idx >= 60 and bar_idx % 20 == 0:
            self._hurst_cache = calc_hurst(closes[-100:].tolist() if len(closes) >= 100 else closes.tolist())
        hurst = getattr(self, '_hurst_cache', 0.5)

        # ADX趋势确认
        if bar_idx >= 60 and len(df) >= 30:
            h = df['high'].values[-30:]
            l = df['low'].values[-30:]
            c = df['close'].values[-30:]
            self._adx_cache = calc_adx(h, l, c)
        adx = getattr(self, '_adx_cache', {})
        is_trending = adx.get('is_trending', False)

        # Huurst修正: H>0.6偏趋势, H<0.4偏回归
        if hurst > 0.6 and is_trending and regime == 'range':
            regime = 'bull'  # 持续趋势+高ADX=偏牛
        elif hurst < 0.4 and regime != 'bear':
            regime = 'range'  # 均值回归+非熊=震荡

        return regime

    def _calc_sector_momentum(self, bar_idx):
        # 从 symbol→sector 映射反推 sector→symbols
        sym_sec = stock_pool.get_symbol_sector_map()
        momentum = {}
        for sym, sec in sym_sec.items():
            if sec not in momentum:
                momentum[sec] = []
            df = self.data.get(sym)
            if df is not None and bar_idx >= 5:
                c = df['close'].values[:bar_idx + 1]
                if len(c) >= 6:
                    momentum[sec].append((c[-1] - c[-6]) / max(c[-6], 0.01))
        return {sec: float(np.mean(rets)) for sec, rets in momentum.items() if rets}

    def run(self):
        print('[引擎] 开始回测...')
        first_err = True
        for i, date_str in enumerate(self.bar_dates):
            if i < config.DATA_COUNT:
                continue
            # V30.5: 日风控重置
            self.risk_engine.reset_daily(date_str)
            try:
                self._daily_bar(date_str, i)
                self._record_daily(date_str)
            except Exception as e:
                if first_err:
                    print('[首次异常] %s bar_idx=%d: %s' % (date_str, i, e))
                    traceback.print_exc()
                    first_err = False
                continue

            if (i + 1) % 50 == 0:
                tv = self.daily_values[-1]['total'] if self.daily_values else INIT_CASH
                r = (tv - INIT_CASH) / INIT_CASH * 100
                print('  [%s] %d/%d | ¥%.0f (%+.1f%%) | 持仓%d' %
                      (date_str, i+1, len(self.bar_dates), tv, r, len(self.positions)))

        self._print_summary()

    def _daily_bar(self, date_str, bar_idx):
        self.exec_engine.cleanup_cooldowns(date_str)
        regime = self._detect_regime(bar_idx)
        regime_cfg = config.REGIME_PARAMS.get(regime, config.REGIME_PARAMS['range'])

        # 出场
        pos_copy = {s: dict(p) for s, p in self.positions.items()}
        data_cache = {}
        syms_to_check = set(list(self.positions.keys()) + list(SYMBOLS))
        for sym in syms_to_check:
            df = self._get_df_slice(sym, bar_idx)
            if df is not None:
                data_cache[sym] = df

        sells = self.exec_engine.check_exits(pos_copy, data_cache, regime, today_str=date_str)
        for sym, price, vote, info in sells:
            if sym in self.positions:
                self._execute_sell(sym, price, vote['reason'], date_str)
                self.exec_engine.record_sell(sym, date_str)

        # 入场 (V30.5: 风控熔断检查)
        if self.risk_engine.is_halted:
            return  # 风控熔断，暂停买入

        sector_momentum = self._calc_sector_momentum(bar_idx)
        sentiment = {sec: max(-1.0, min(1.0, mom * 5)) for sec, mom in sector_momentum.items()}
        self.exec_engine._sentiment = sentiment

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
        taken_sectors = set(p.get('sector') for p in self.positions.values())
        taken = 0
        for c in candidates:
            if taken >= remaining:
                break
            if c['sector'] in taken_sectors:
                continue
            qty = self.exec_engine.calc_position_size(c, self.cash, remaining - taken)
            if qty < 100:
                continue

            price = apply_slippage(c['price'], 'buy')  # V30.5: 买入滑点

            # V30.5: 涨跌停检查
            df = self.data.get(c['symbol'])
            if df is not None and len(df) >= 2:
                o = float(df['open'].iloc[-1])
                h = float(df['high'].iloc[-1])
                l = float(df['low'].iloc[-1])
                cl = float(df['close'].iloc[-1])
                prev = float(df['close'].iloc[-2])
                lim = check_limit_status(prev, h, l, cl)
                if not lim['can_buy']:
                    continue  # 涨停无法买入

            # 费用
            # V30.5: 买入费用
            if ENABLE_FEES:
                market = 'SHSE' if c['symbol'].startswith('SHSE') else 'SZSE'
                fee = calc_buy_fee(price * qty, market)['total']
                total_cost = price * qty + fee
                self.cash -= total_cost
                self.fee_stats['total_fees'] += fee
                self.fee_stats['buy_fees'] += fee
            else:
                self.cash -= price * qty
            self.positions[c['symbol']] = {
                'vol': qty, 'cost': price, 'peak': price,
                'entry_date': date_str, 'sector': c['sector'],
                'strategy': c['best_strategy'],
                'confidence': c['confidence'],
            }
            taken_sectors.add(c['sector'])
            taken += 1
            print('[买入] %s | %s | %s | 策略:%s | %.2f×%d' %
                  (date_str, c['symbol'], c['reason'], c['best_strategy'], price, qty))

    def _execute_sell(self, sym, price, reason, date_str):
        pos = self.positions.pop(sym)
        price = apply_slippage(price, 'sell')  # V30.5: 卖出滑点

        # V30.5: 跌停检查 — 跌停无法卖出, 持仓保留
        df = self.data.get(sym)
        if df is not None and len(df) >= 2:
            o = float(df['open'].iloc[-1])
            h = float(df['high'].iloc[-1])
            l = float(df['low'].iloc[-1])
            cl = float(df['close'].iloc[-1])
            prev = float(df['close'].iloc[-2])
            lim = check_limit_status(prev, h, l, cl)
            if not lim['can_sell']:
                self.positions[sym] = pos  # 恢复持仓
                return

        # V30.5: 扣除卖出费用
        gross_pnl_pct = (price - pos['cost']) / pos['cost'] * 100
        sector = pos.get('sector', '未知')
        strat = pos.get('strategy', '?')
        sell_amt = price * pos['vol']

        if ENABLE_FEES:
            market = 'SHSE' if sym.startswith('SHSE') else 'SZSE'
            buy_fee = calc_buy_fee(pos['cost'] * pos['vol'], market)['total']
            sell_fee = calc_sell_fee(sell_amt, market)['total']
            total_fee = buy_fee + sell_fee
            self.fee_stats['total_fees'] += total_fee
            self.fee_stats['sell_fees'] += sell_fee
            net_cash = sell_amt - sell_fee
            pnl_pct = (net_cash - (pos['cost'] * pos['vol'] + buy_fee)) / (pos['cost'] * pos['vol'] + buy_fee) * 100
            self.cash += net_cash
        else:
            self.cash += sell_amt
            pnl_pct = gross_pnl_pct

        self.trades.append({
            'date': date_str, 'symbol': sym, 'side': 'SELL',
            'price': price, 'vol': pos['vol'], 'pnl_pct': pnl_pct,
            'reason': reason, 'sector': sector, 'strategy': strat,
        })
        # 统计
        self.stats['total_trades'] += 1
        if pnl_pct > 0:
            self.stats['wins'] += 1
        else:
            self.stats['losses'] += 1
        self.stats['total_pnl'] += pnl_pct
        if strat in self.strategy_stats:
            self.strategy_stats[strat]['total'] += 1
            if pnl_pct > 0:
                self.strategy_stats[strat]['wins'] += 1
            self.strategy_stats[strat]['pnl'] += pnl_pct
        if sector not in self.sector_stats:
            self.sector_stats[sector] = {'wins': 0, 'total': 0, 'pnl': 0.0}
        self.sector_stats[sector]['total'] += 1
        if pnl_pct > 0:
            self.sector_stats[sector]['wins'] += 1
        self.sector_stats[sector]['pnl'] += pnl_pct
        print('[卖出] %s | %s | %s | 价%.2f | %+.2f%% | %s' %
              (date_str, sym, reason, price, pnl_pct, strat))

        # V30.5: 账户风控监控
        total_val = self.cash
        for s, p in self.positions.items():
            df = self.data.get(s)
            if df is not None and len(df) > 0:
                total_val += float(df['close'].iloc[-1]) * p['vol']
            else:
                total_val += p['cost'] * p['vol']
        halted, halt_reason = self.risk_engine.check_account(total_val, pnl_pct)
        if halted:
            print('[风控] 暂停交易: %s' % halt_reason)

    def _record_daily(self, date_str):
        mv = 0.0
        for s, p in self.positions.items():
            df = self.data.get(s)
            if df is not None and len(df) > 0:
                price = float(df['close'].values[-1])
            else:
                price = p['cost']
            mv += price * p['vol']
        self.daily_values.append({'date': date_str, 'total': self.cash + mv})

    def _print_summary(self):
        d = self.daily_values
        if not d:
            print('[错误] 无数据'); return

        final = d[-1]['total']
        total_ret = (final - INIT_CASH) / INIT_CASH * 100
        peaks = np.maximum.accumulate([v['total'] for v in d])
        dd = (np.array([v['total'] for v in d]) - peaks) / peaks * 100
        max_dd = float(np.min(dd))
        sells = [t for t in self.trades if t['side'] == 'SELL']
        wins_s = [t for t in sells if t['pnl_pct'] > 0]
        wr = len(wins_s) / len(sells) * 100 if sells else 0
        avg_pnl = np.mean([t['pnl_pct'] for t in sells]) if sells else 0

        # Profit factor
        wins_pnl = [t['pnl_pct'] for t in sells if t['pnl_pct'] > 0]
        loss_pnl = [abs(t['pnl_pct']) for t in sells if t['pnl_pct'] < 0]
        pf = sum(wins_pnl) / sum(loss_pnl) if loss_pnl else 0

        print('\n' + '=' * 60)
        print('  独立离线回测结果摘要')
        print('=' * 60)
        print('  初始资金:   ¥%d' % INIT_CASH)
        print('  最终净值:   ¥%.0f' % final)
        print('  总收益率:   %+.2f%%' % total_ret)
        print('  最大回撤:   %.2f%%' % max_dd)
        print('  交易次数:   %d (卖出%d)' % (len(self.trades), len(sells)))
        print('  胜率:       %.1f%% (%d/%d)' % (wr, len(wins_s), len(sells)))
        print('  平均盈亏:   %+.2f%%' % avg_pnl)
        print('  盈利因子:   %.2f' % pf)
        if self.fee_stats['total_fees'] > 0:
            print('  交易费用:   ¥%.0f (买¥%.0f 卖¥%.0f)' %
                  (self.fee_stats['total_fees'], self.fee_stats['buy_fees'], self.fee_stats['sell_fees']))
        print('  ---- 策略分项 ----')
        for name in ['MR', 'MOM', 'VRC', 'BK', 'DV', 'RT']:
            s = self.strategy_stats[name]
            t = s['total']
            w = s['wins']
            r = w / t * 100 if t else 0
            print('  %s: 交易%d 胜率%.1f%% 累计%+.1f%%' % (name, t, r, s['pnl']))
        print('  ---- 行业分项 ----')
        for sec, s in sorted(self.sector_stats.items()):
            t = s['total']
            w = s['wins']
            r = w / t * 100 if t else 0
            print('  %s: 交易%d 胜率%.1f%% 累计%+.1f%%' % (sec, t, r, s['pnl']))
        print('=' * 60)


# ============================================================
# 主入口
# ============================================================
if __name__ == '__main__':

    # 加载数据
    all_syms = list(SYMBOLS) + [MARKET_INDEX]
    data = preload_all(START, END, all_syms)

    if MARKET_INDEX not in data or len(data.get(MARKET_INDEX, {})) < 60:
        print('[错误] 大盘指数数据不足, 请确认 C:/lainghua 数据完整')
        sys.exit(1)

    # 运行
    engine = StandaloneBacktest(data, INIT_CASH)
    engine.run()

    # V30.5: 可视窗口
    try:
        import visualizer
        bt_data = visualizer.BacktestData()
        bt_data.initial_cash = INIT_CASH
        for t in engine.trades:
            rec = visualizer.TradeRecord(
                t['date'], t['symbol'], t['side'], t['price'],
                vol=t.get('vol', 0), pnl_pct=t.get('pnl_pct', 0),
                strategy=t.get('strategy', '?'), sector=t.get('sector', '?'),
                reason=t.get('reason', '')
            )
            bt_data.trades.append(rec)
        bt_data.daily_values = engine.daily_values
        bt_data.strategy_stats = engine.strategy_stats
        bt_data.sector_stats = engine.sector_stats
        visualizer.launch_visualizer(bt_data)
    except Exception as e:
        print('[Vis] 跳过可视化:', e)
