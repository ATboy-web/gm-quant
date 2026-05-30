"""
minute_backtest.py - V2 高性能5分钟K线回测引擎

核心优化:
1. 预计算所有技术指标为numpy数组
2. 按日期遍历而非按K线遍历
3. 每日只检查一次入场/出场
4. 向量化计算替代逐行循环
"""
import sys, os, json, traceback
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import sqlite3
import csv

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import indicators
import stock_pool
import sector_config
from trade_utils import calc_buy_fee, calc_sell_fee, apply_slippage, check_limit_status

# ============================================================
# 配置
# ============================================================
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "minute_bar", "minute_bar_5min.db")
INIT_CASH = 30000     # V2: 25000→30000
ENABLE_FEES = True
MAX_POSITIONS = 5
POSITION_PCT = 0.20
AGG_PERIOD = 6        # V2: 聚合6根5分钟K线 = 30分钟线

# 30分钟级别策略参数 (V2: 从5分钟聚合到30分钟)
BK_PERIOD = 10        # 突破窗口 (10根30分钟K线 = 5小时)
BK_VOL_SURGE = 2.5   # V2f: 2.0→2.5, 进一步提高量能门槛
BK_STOP_LOSS = 0.03  # 止损3%
BK_TAKE_PROFIT = 0.12 # V2i: 9%→12%, 优化止盈比例(4:1)
BK_TRAIL_STOP = 0.02 # 移动止盈2%
REQUIRE_TREND = True  # V2c: 要求MA20>MA40趋势确认
RSI_PERIOD = 14
RSI_BUY = 30
RSI_EXIT = 70
MAX_TRADES_PER_DAY = 4  # V2g: 3→4, 增加交易机会

# ============================================================
# 数据加载 + 30分钟聚合
# ============================================================
def aggregate_to_30min(df, agg_period=AGG_PERIOD):
    """将5分钟K线聚合为30分钟K线"""
    n = len(df)
    if n < agg_period:
        return df
    
    # 计算聚合后的行数
    n_agg = n // agg_period
    
    agg_data = []
    for i in range(n_agg):
        start_idx = i * agg_period
        end_idx = start_idx + agg_period
        
        chunk = df.iloc[start_idx:end_idx]
        agg_data.append({
            'datetime': chunk['datetime'].iloc[-1],  # 取最后一根K线的时间
            'open': float(chunk['open'].iloc[0]),
            'high': float(chunk['high'].max()),
            'low': float(chunk['low'].min()),
            'close': float(chunk['close'].iloc[-1]),
            'volume': float(chunk['volume'].sum()),
        })
    
    return pd.DataFrame(agg_data)


def load_minute_data(symbols, start_date=None, end_date=None):
    """从SQLite加载分钟数据，聚合到30分钟，预计算技术指标"""
    conn = sqlite3.connect(DB_FILE)
    data = {}
    
    for sym in symbols:
        query = "SELECT datetime, open, high, low, close, volume FROM minute_bar WHERE symbol = ?"
        params = [sym]
        if start_date:
            query += " AND datetime >= ?"
            params.append(start_date + " 09:30:00")
        if end_date:
            query += " AND datetime <= ?"
            params.append(end_date + " 15:00:00")
        query += " ORDER BY datetime"
        
        df = pd.read_sql_query(query, conn, params=params)
        if len(df) < 50:
            continue
        
        # 聚合到30分钟
        df = aggregate_to_30min(df, AGG_PERIOD)
        if len(df) < 30:
            continue
        
        # 预计算技术指标
        closes = df['close'].values.astype(float)
        highs = df['high'].values.astype(float)
        lows = df['low'].values.astype(float)
        vols = df['volume'].values.astype(float)
        
        # 滚动RSI
        rsi_arr = np.full(len(closes), 50.0)
        for i in range(RSI_PERIOD + 1, len(closes)):
            rsi_arr[i] = indicators.calc_rsi(closes[:i+1], RSI_PERIOD) or 50.0
        
        # 滚动均量
        vol_ma = np.ones(len(closes))
        for i in range(20, len(closes)):
            vol_ma[i] = np.mean(vols[i-20:i])
        
        # 滚动高点
        high_n = np.copy(closes)
        for i in range(BK_PERIOD, len(closes)):
            high_n[i] = np.max(closes[i-BK_PERIOD:i])
        
        # V2c: MA20和MA40
        ma20 = np.full(len(closes), np.nan)
        ma40 = np.full(len(closes), np.nan)
        for i in range(20, len(closes)):
            ma20[i] = np.mean(closes[i-20:i])
        for i in range(40, len(closes)):
            ma40[i] = np.mean(closes[i-40:i])
        
        df['rsi'] = rsi_arr
        df['vol_ma'] = vol_ma
        df['high_n'] = high_n
        df['ma20'] = ma20
        df['ma40'] = ma40
        df['date'] = df['datetime'].str[:10]
        
        data[sym] = df
    
    conn.close()
    return data


# ============================================================
# 回测引擎
# ============================================================
class MinuteBacktest:
    def __init__(self, data, start_cash=INIT_CASH):
        self.data = data
        self.initial_cash = start_cash
        self.cash = start_cash
        self.positions = {}
        self.trades = []
        self.daily_values = []
        self.stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0.0}
        self.fee_stats = {'total_fees': 0.0, 'buy_fees': 0.0, 'sell_fees': 0.0}
        
        # 获取所有交易日
        all_dates = set()
        for sym, df in self.data.items():
            all_dates.update(df['date'].unique().tolist())
        self.trading_dates = sorted(all_dates)
        
        print(f'[引擎] 交易日: {len(self.trading_dates)} | 股票: {len(data)} | 资金: {start_cash}')
    
    def run(self):
        """按日期遍历回测"""
        print('[引擎] 开始回测...')
        
        for day_idx, date in enumerate(self.trading_dates):
            # 获取当日数据
            day_data = {}
            for sym, df in self.data.items():
                mask = df['date'] == date
                if mask.sum() > 0:
                    day_data[sym] = df[mask].copy()
            
            if not day_data:
                continue
            
            # 出场检查 (开盘时)
            self._check_exits(day_data, date)
            
            # 入场检查 (盘中，取最后一根K线的指标)
            if len(self.positions) < MAX_POSITIONS:
                self._check_entries(day_data, date)
            
            # 记录每日净值
            self._record_daily(day_data, date)
            
            # 进度报告
            if (day_idx + 1) % 20 == 0:
                total_val = self._calc_total_value(day_data)
                ret = (total_val - self.initial_cash) / self.initial_cash * 100
                print(f'  [{date}] {day_idx+1}/{len(self.trading_dates)} | {total_val:.0f} ({ret:+.1f}%) | 持仓{len(self.positions)}')
        
        self._print_summary()
    
    def _calc_total_value(self, day_data):
        """计算总资产"""
        total = self.cash
        for sym, pos in self.positions.items():
            if sym in day_data:
                price = float(day_data[sym]['close'].iloc[-1])
                total += price * pos['vol']
        return total
    
    def _check_exits(self, day_data, date):
        """检查出场"""
        to_sell = []
        
        for sym, pos in self.positions.items():
            if sym not in day_data:
                continue
            
            df = day_data[sym]
            cur_price = float(df['close'].iloc[-1])
            rsi = float(df['rsi'].iloc[-1])
            
            # 更新峰值
            if cur_price > pos['peak']:
                pos['peak'] = cur_price
            
            pnl = (cur_price - pos['cost']) / pos['cost']
            days_held = pos.get('days_held', 0) + 1
            pos['days_held'] = days_held
            
            # T+1检查
            if days_held < 1:
                continue
            
            # 止损
            if pnl <= -BK_STOP_LOSS:
                to_sell.append((sym, cur_price, f'止损{pnl*100:.1f}%'))
                continue
            
            # 止盈
            if pnl >= BK_TAKE_PROFIT:
                to_sell.append((sym, cur_price, f'止盈{pnl*100:.1f}%'))
                continue
            
            # 移动止盈
            if pos['peak'] > pos['cost']:
                trail_pct = (pos['peak'] - cur_price) / pos['peak']
                if pnl > 0.02 and trail_pct >= BK_TRAIL_STOP:
                    to_sell.append((sym, cur_price, f'移动止盈'))
                    continue
            
            # RSI过热
            if rsi > RSI_EXIT and pnl > 0:
                to_sell.append((sym, cur_price, f'RSI过热{rsi:.0f}'))
                continue
            
            # 时间止损 (5天)
            if days_held >= 5:
                to_sell.append((sym, cur_price, f'时间止损{days_held}天'))
                continue
        
        for sym, price, reason in to_sell:
            self._execute_sell(sym, price, reason, date)
    
    def _check_entries(self, day_data, date):
        """检查入场 - 使用完整历史数据计算指标，每日限制交易次数"""
        # V2: 每日交易次数限制
        today_trades = sum(1 for t in self.trades if t['date'] == date)
        if today_trades >= MAX_TRADES_PER_DAY:
            return
        
        candidates = []
        
        for sym in self.data.keys():
            if sym in self.positions:
                continue
            
            # 使用完整历史数据（包含今天）
            df = self.data[sym]
            mask = df['date'] <= date
            if mask.sum() < BK_PERIOD + 5:
                continue
            
            df_hist = df[mask]
            
            if len(df_hist) < BK_PERIOD + 5:
                continue
            
            cur_price = float(df_hist['close'].iloc[-1])
            if cur_price < 2.0 or cur_price > 200.0:
                continue
            
            rsi = float(df_hist['rsi'].iloc[-1])
            vol_ratio = float(df_hist['volume'].iloc[-1]) / float(df_hist['vol_ma'].iloc[-1]) if float(df_hist['vol_ma'].iloc[-1]) > 0 else 1.0
            recent_high = float(df_hist['high_n'].iloc[-1])
            
            # V2c: 趋势过滤
            ma20_val = float(df_hist['ma20'].iloc[-1]) if not np.isnan(df_hist['ma20'].iloc[-1]) else 0
            ma40_val = float(df_hist['ma40'].iloc[-1]) if not np.isnan(df_hist['ma40'].iloc[-1]) else 0
            trend_ok = (ma20_val > ma40_val) if REQUIRE_TREND else True
            
            # BK突破信号 (V2f: 趋势过滤+收窄RSI)
            if cur_price > recent_high and vol_ratio >= BK_VOL_SURGE and 30 <= rsi <= 70 and trend_ok:
                score = 0.50 + min(0.30, (vol_ratio - 1.0) * 0.30)
                if 35 <= rsi <= 65:
                    score += 0.20
                if score >= 0.60:  # V2: 0.65→0.60
                    candidates.append({
                        'symbol': sym, 'price': cur_price, 'confidence': score,
                        'reason': f'BK突破|放量{vol_ratio:.1f}|RSI{rsi:.0f}',
                        'strategy': 'BK',
                    })
            
            # MR超卖信号 (V2b: 禁用，MR亏损-237%)
            # if rsi < RSI_BUY:
            #     ...
        
        # 按置信度排序
        candidates.sort(key=lambda x: x['confidence'], reverse=True)
        
        remaining = MAX_POSITIONS - len(self.positions)
        for c in candidates[:remaining]:
            qty = self._calc_position_size(c['price'])
            if qty >= 100:
                self._execute_buy(c['symbol'], c['price'], qty, c['reason'], c['strategy'], date)
    
    def _calc_position_size(self, price):
        allocated = self.cash * POSITION_PCT
        if allocated < price * 100:
            return 0
        return int(allocated / (price * 100)) * 100
    
    def _execute_buy(self, symbol, price, qty, reason, strategy, date):
        price = apply_slippage(price, 'buy')
        if ENABLE_FEES:
            market = 'SHSE' if symbol.startswith('SHSE') else 'SZSE'
            fee = calc_buy_fee(price * qty, market)['total']
            self.cash -= (price * qty + fee)
            self.fee_stats['total_fees'] += fee
            self.fee_stats['buy_fees'] += fee
        else:
            self.cash -= price * qty
        
        self.positions[symbol] = {
            'vol': qty, 'cost': price, 'peak': price,
            'entry_date': date, 'strategy': strategy, 'days_held': 0,
        }
        print(f'[买入] {date} | {symbol} | {reason} | {price:.2f}x{qty}')
    
    def _execute_sell(self, symbol, price, reason, date):
        if symbol not in self.positions:
            return
        pos = self.positions.pop(symbol)
        price = apply_slippage(price, 'sell')
        sell_amt = price * pos['vol']
        
        if ENABLE_FEES:
            market = 'SHSE' if symbol.startswith('SHSE') else 'SZSE'
            buy_fee = calc_buy_fee(pos['cost'] * pos['vol'], market)['total']
            sell_fee = calc_sell_fee(sell_amt, market)['total']
            self.fee_stats['total_fees'] += (buy_fee + sell_fee)
            self.fee_stats['sell_fees'] += sell_fee
            pnl_pct = (sell_amt - sell_fee - pos['cost'] * pos['vol'] - buy_fee) / (pos['cost'] * pos['vol'] + buy_fee) * 100
            self.cash += (sell_amt - sell_fee)
        else:
            pnl_pct = (price - pos['cost']) / pos['cost'] * 100
            self.cash += sell_amt
        
        self.trades.append({
            'date': date, 'symbol': symbol, 'price': price, 'vol': pos['vol'],
            'pnl_pct': pnl_pct, 'reason': reason, 'strategy': pos['strategy'],
        })
        self.stats['total_trades'] += 1
        if pnl_pct > 0: self.stats['wins'] += 1
        else: self.stats['losses'] += 1
        self.stats['total_pnl'] += pnl_pct
        print(f'[卖出] {date} | {symbol} | {reason} | {pnl_pct:+.2f}%')
    
    def _record_daily(self, day_data, date):
        total_val = self.cash
        for sym, pos in self.positions.items():
            if sym in day_data:
                price = float(day_data[sym]['close'].iloc[-1])
                total_val += price * pos['vol']
        self.daily_values.append({'date': date, 'total': total_val})
    
    def _print_summary(self):
        if not self.daily_values:
            print('无交易数据')
            return
        
        final = self.daily_values[-1]['total']
        total_ret = (final - self.initial_cash) / self.initial_cash * 100
        
        peak = self.initial_cash
        max_dd = 0
        for dv in self.daily_values:
            if dv['total'] > peak: peak = dv['total']
            dd = (peak - dv['total']) / peak * 100
            if dd > max_dd: max_dd = dd
        
        wr = self.stats['wins'] / self.stats['total_trades'] * 100 if self.stats['total_trades'] > 0 else 0
        avg_pnl = self.stats['total_pnl'] / self.stats['total_trades'] if self.stats['total_trades'] > 0 else 0
        wins_total = sum(t['pnl_pct'] for t in self.trades if t['pnl_pct'] > 0)
        losses_total = abs(sum(t['pnl_pct'] for t in self.trades if t['pnl_pct'] < 0))
        pf = wins_total / losses_total if losses_total > 0 else 999
        
        print('=' * 60)
        print('  5分钟K线回测摘要')
        print('=' * 60)
        print(f'  初始资金: {self.initial_cash}')
        print(f'  最终净值: {final:.0f}')
        print(f'  总收益率: {total_ret:+.2f}%')
        print(f'  年化收益: {total_ret * 365 / max(len(self.trading_dates), 1):+.2f}%')
        print(f'  最大回撤: {max_dd:.2f}%')
        print(f'  交易次数: {self.stats["total_trades"]} (胜{self.stats["wins"]} 负{self.stats["losses"]})')
        print(f'  胜率:     {wr:.1f}%')
        print(f'  平均盈亏: {avg_pnl:+.2f}%')
        print(f'  盈利因子: {pf:.2f}')
        print(f'  交易费用: {self.fee_stats["total_fees"]:.0f}')
        
        # 策略分项
        strat_stats = {}
        for t in self.trades:
            s = t['strategy']
            if s not in strat_stats:
                strat_stats[s] = {'count': 0, 'wins': 0, 'pnl': 0.0}
            strat_stats[s]['count'] += 1
            if t['pnl_pct'] > 0: strat_stats[s]['wins'] += 1
            strat_stats[s]['pnl'] += t['pnl_pct']
        
        print('  ---- 策略分项 ----')
        for s, st in sorted(strat_stats.items(), key=lambda x: -x[1]['pnl']):
            wr_s = st['wins'] / st['count'] * 100 if st['count'] > 0 else 0
            print(f'  {s}: {st["count"]}笔 {wr_s:.0f}%WR 累计{st["pnl"]:+.1f}%')
        
        print('=' * 60)
        
        # 保存日志
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f'minute_backtest_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        
        with open(log_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['日期', '股票', '价格', '数量', '盈亏%', '策略', '理由'])
            for t in self.trades:
                w.writerow([t['date'], t['symbol'], f"{t['price']:.2f}", t['vol'],
                           f"{t['pnl_pct']:+.2f}", t['strategy'], t['reason']])
        
        print(f'  日志已保存: {log_path}')


# ============================================================
# 主入口
# ============================================================
if __name__ == '__main__':
    print('=' * 60)
    print('  V2 高性能5分钟K线回测引擎')
    print('=' * 60)
    
    symbols = stock_pool.get_all_symbols()
    print(f'[数据] 加载 {len(symbols)} 只股票...')
    data = load_minute_data(symbols, start_date='2024-06-01', end_date='2026-05-26')
    print(f'[数据] 成功加载 {len(data)} 只')
    
    if len(data) == 0:
        print('无数据，退出')
        sys.exit(1)
    
    engine = MinuteBacktest(data, INIT_CASH)
    engine.run()
