"""
visualizer.py - V29 回测可视化窗口

功能面板:
  1. 概览面板 — 总收益/胜率/夏普率/最大回撤/交易次数/盈亏比
  2. 净值曲线 — 含回撤阴影区域 + 基准对比
  3. 交易记录表 — 买卖明细（股票/日期/价格/数量/盈亏/策略/行业）
  4. 策略统计 — 六策略胜率/盈亏柱状图
  5. 持仓历史 — 每日持仓变化折线图
  6. 月度收益 — 热力图
  7. 盈亏分布 — 直方图

终端控制: --visual 或交互式选择
日志保存: 自动写入 logs/visualizer_YYYYMMDD_HHMMSS.csv
"""

import os
import sys
import csv
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import pandas as pd

# matplotlib
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.ticker import FuncFormatter, PercentFormatter
import matplotlib.pyplot as plt

# 中文字体
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from config import BACKTEST_START, BACKTEST_END, BACKTEST_CASH
import stock_pool  # V29.4: 股票名称映射

# =============================================================================
# 配色方案 (中国股市: 红涨绿跌)
# =============================================================================
COLORS = {
    'bg':           '#1a1a2e',
    'panel_bg':     '#16213e',
    'card_bg':      '#0f3460',
    'accent':       '#e94560',
    'text':         '#e0e0e0',
    'text_dim':     '#8899aa',
    'green':        '#00b894',   # 跌 (中国习惯)
    'red':          '#e17055',   # 涨 (中国习惯)
    'buy_color':    '#e17055',   # 买入标记
    'sell_color':   '#00b894',   # 卖出标记
    'profit':       '#e17055',   # 盈利
    'loss':         '#00b894',   # 亏损
    'grid':         '#2d3436',
    'highlight':    '#fdcb6e',
    'white':        '#ffffff',
    'chart_bg':     '#16213e',
}

# =============================================================================
# 数据模型
# =============================================================================

class TradeRecord:
    """单笔交易记录"""
    __slots__ = ('date', 'symbol', 'side', 'price', 'vol', 'cost_price',
                 'pnl_pct', 'pnl_amount', 'sector', 'strategy', 'reason',
                 'confidence', 'hold_days')

    def __init__(self, date, symbol, side, price, vol=0, cost_price=0,
                 pnl_pct=0, pnl_amount=0, sector='', strategy='',
                 reason='', confidence=0, hold_days=0):
        self.date = date
        self.symbol = symbol
        self.side = side         # BUY / SELL
        self.price = price
        self.vol = vol
        self.cost_price = cost_price
        self.pnl_pct = pnl_pct
        self.pnl_amount = pnl_amount
        self.sector = sector
        self.strategy = strategy
        self.reason = reason
        self.confidence = confidence
        self.hold_days = hold_days


class BacktestData:
    """回测结果数据集"""
    def __init__(self):
        self.trades = []              # TradeRecord 列表
        self.daily_values = []        # [{date, cash, market, total}, ...]
        self.strategy_stats = {}      # {name: {wins, total, pnl}}
        self.sector_stats = {}        # {name: {wins, total, pnl}}
        self.signals = []             # [{date, symbol, strategy, action, score}, ...]
        self.positions_history = []   # [{date, count, symbols}, ...]
        self.initial_cash = BACKTEST_CASH
        self.total_elapsed = 0        # 回测耗时 (秒)

    @property
    def equity_curve(self):
        if not self.daily_values:
            return np.array([]), np.array([])
        dates = [d['date'] for d in self.daily_values]
        totals = np.array([d['total'] for d in self.daily_values])
        return dates, totals

    @property
    def total_return(self):
        if not self.daily_values:
            return 0
        final = self.daily_values[-1]['total']
        return (final - self.initial_cash) / self.initial_cash * 100

    @property
    def max_drawdown(self):
        if not self.daily_values:
            return 0
        totals = np.array([d['total'] for d in self.daily_values])
        cummax = np.maximum.accumulate(totals)
        dd = (totals - cummax) / cummax
        return float(dd.min()) * 100

    @property
    def win_rate(self):
        sells = [t for t in self.trades if t.side == 'SELL']
        if not sells:
            return 0
        wins = [t for t in sells if t.pnl_pct > 0]
        return len(wins) / len(sells) * 100

    @property
    def sharpe_ratio(self):
        """简化夏普比率 (年化, 无风险利率=2%)"""
        if not self.daily_values:
            return 0
        totals = np.array([d['total'] for d in self.daily_values])
        if len(totals) < 2:
            return 0
        daily_returns = np.diff(totals) / totals[:-1]
        mean_r = np.mean(daily_returns) - 0.02 / 252
        std_r = np.std(daily_returns)
        if std_r == 0:
            return 0
        return float(mean_r / std_r * np.sqrt(252))

    @property
    def avg_profit(self):
        sells = [t for t in self.trades if t.side == 'SELL']
        if not sells:
            return 0
        return float(np.mean([t.pnl_pct for t in sells]))

    @property
    def avg_hold_days(self):
        sells = [t for t in self.trades if t.side == 'SELL']
        if not sells:
            return 0
        return float(np.mean([t.hold_days for t in sells if t.hold_days > 0]))


# =============================================================================
# 主窗口
# =============================================================================

class BacktestVisualizer:
    """回测可视化主窗口"""

    def __init__(self, data: BacktestData, title="量化回测可视化"):
        self.data = data
        self.root = tk.Tk()
        self.root.title(title)

        # V29.4: 自适应窗口 — 取屏幕 90% 但不超过 1600×900
        _sw = self.root.winfo_screenwidth()
        _sh = self.root.winfo_screenheight()
        _w = min(1600, int(_sw * 0.9))
        _h = min(900, int(_sh * 0.88))
        self.root.geometry(f"{_w}x{_h}+{int((_sw-_w)/2)}+{int((_sh-_h)/2)}")
        self.root.configure(bg=COLORS['bg'])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 样式
        self._setup_style()

        # 构建界面
        self._build_ui()

        # 实时时钟
        self._update_clock()

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('Dark.TFrame', background=COLORS['bg'])
        style.configure('Panel.TFrame', background=COLORS['panel_bg'])
        style.configure('Card.TFrame', background=COLORS['card_bg'])

        style.configure('Header.TLabel',
                        background=COLORS['panel_bg'],
                        foreground=COLORS['highlight'],
                        font=('Microsoft YaHei', 10, 'bold'))

        style.configure('StatBig.TLabel',
                        background=COLORS['card_bg'],
                        foreground=COLORS['white'],
                        font=('Consolas', 20, 'bold'))

        style.configure('StatLabel.TLabel',
                        background=COLORS['card_bg'],
                        foreground=COLORS['text_dim'],
                        font=('Microsoft YaHei', 8))

        style.configure('Positive.TLabel',
                        background=COLORS['card_bg'],
                        foreground=COLORS['red'],
                        font=('Consolas', 13, 'bold'))

        style.configure('Negative.TLabel',
                        background=COLORS['card_bg'],
                        foreground=COLORS['green'],
                        font=('Consolas', 13, 'bold'))

        style.configure('Clock.TLabel',
                        background=COLORS['bg'],
                        foreground=COLORS['text_dim'],
                        font=('Consolas', 10))

        # Treeview 样式
        style.configure('Trade.Treeview',
                        background=COLORS['panel_bg'],
                        foreground=COLORS['text'],
                        fieldbackground=COLORS['panel_bg'],
                        rowheight=24,
                        font=('Consolas', 9))
        style.configure('Trade.Treeview.Heading',
                        background=COLORS['card_bg'],
                        foreground=COLORS['highlight'],
                        font=('Microsoft YaHei', 9, 'bold'))
        style.map('Trade.Treeview',
                  background=[('selected', COLORS['card_bg'])],
                  foreground=[('selected', COLORS['white'])])

    def _build_ui(self):
        # 顶部标题栏
        self._build_header()

        # 主内容区 (左右分栏)
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # 左侧: 图表区
        left_frame = ttk.Frame(main_paned, style='Dark.TFrame')
        main_paned.add(left_frame, weight=65)

        # 右侧: 信息面板区
        right_frame = ttk.Frame(main_paned, style='Dark.TFrame')
        main_paned.add(right_frame, weight=35)

        self._build_charts(left_frame)
        self._build_info_panels(right_frame)

    def _build_header(self):
        header = ttk.Frame(self.root, style='Panel.TFrame', height=50)
        header.pack(fill=tk.X, padx=8, pady=(8, 0))
        header.pack_propagate(False)

        title_lbl = ttk.Label(header, text='📊 量化回测可视化',
                              style='Header.TLabel')
        title_lbl.pack(side=tk.LEFT, padx=15, pady=10)

        # 耗时
        self.elapsed_lbl = ttk.Label(header, text='', style='StatLabel.TLabel')
        self.elapsed_lbl.pack(side=tk.LEFT, padx=20)

        # 时钟
        self.clock_lbl = ttk.Label(header, text='', style='Clock.TLabel')
        self.clock_lbl.pack(side=tk.RIGHT, padx=15)

        # 导出按钮
        self.export_btn = ttk.Button(header, text='导出报告 CSV',
                                     command=self._export_csv,
                                     style='TButton')
        self.export_btn.pack(side=tk.RIGHT, padx=5)

        # 保存日志按钮
        self.save_log_btn = ttk.Button(header, text='保存完整日志',
                                       command=self._save_full_log,
                                       style='TButton')
        self.save_log_btn.pack(side=tk.RIGHT, padx=5)

        # V30.4: HTML报告导出
        self.html_btn = ttk.Button(header, text='导出HTML报告',
                                   command=self._export_html,
                                   style='TButton')
        self.html_btn.pack(side=tk.RIGHT, padx=5)

    def _build_charts(self, parent):
        """构建图表区 — 净值曲线 + 策略统计 + 盈亏分布 + 相关性"""
        cards_frame = ttk.Frame(parent, style='Dark.TFrame')
        cards_frame.pack(fill=tk.X, padx=2, pady=2)
        overview_card = ttk.Frame(cards_frame, style='Panel.TFrame')
        overview_card.pack(fill=tk.X, padx=2, pady=2)
        self._build_overview_cards(overview_card)

        # 净值曲线图
        self._build_equity_chart(parent)

        # 底部: 策略统计 + 盈亏分布 + 相关性 (三格)
        bottom_frame = ttk.Frame(parent, style='Dark.TFrame')
        bottom_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        bottom_paned = ttk.PanedWindow(bottom_frame, orient=tk.HORIZONTAL)
        bottom_paned.pack(fill=tk.BOTH, expand=True)

        strat_frame = ttk.Frame(bottom_paned, style='Dark.TFrame')
        bottom_paned.add(strat_frame, weight=40)
        self._build_strategy_chart(strat_frame)

        corr_frame = ttk.Frame(bottom_paned, style='Dark.TFrame')
        bottom_paned.add(corr_frame, weight=30)
        self._build_correlation_chart(corr_frame)

        dist_frame = ttk.Frame(bottom_paned, style='Dark.TFrame')
        bottom_paned.add(dist_frame, weight=30)
        self._build_distribution_chart(dist_frame)

    def _build_overview_cards(self, parent):
        """概览统计卡片 (V30.4: 添加盈亏比和盈利因子)"""
        d = self.data
        # 计算高级指标
        sell_trades = [t for t in d.trades if t.side == 'SELL']
        buys = [t.pnl for t in sell_trades if hasattr(t, 'pnl') and t.pnl > 0]
        losses = [t.pnl for t in sell_trades if hasattr(t, 'pnl') and t.pnl < 0]
        profit_factor = sum(buys) / abs(sum(losses)) if losses else 0
        avg_win = np.mean(buys) if buys else 0
        avg_loss = abs(np.mean(losses)) if losses else 0.01
        pl_ratio = avg_win / avg_loss if avg_loss > 0.01 else 0

        cards_data = [
            ('总收益率', f'{d.total_return:+.2f}%',
             'Positive.TLabel' if d.total_return >= 0 else 'Negative.TLabel'),
            ('交易胜率', f'{d.win_rate:.1f}%',
             'Positive.TLabel' if d.win_rate >= 50 else 'StatBig.TLabel'),
            ('最大回撤', f'{d.max_drawdown:.2f}%', 'Negative.TLabel'),
            ('夏普比率', f'{d.sharpe_ratio:.2f}',
             'Positive.TLabel' if d.sharpe_ratio >= 0 else 'Negative.TLabel'),
            ('盈利因子', f'{profit_factor:.2f}',
             'Positive.TLabel' if profit_factor >= 1 else 'Negative.TLabel'),
            ('P/L比', f'{pl_ratio:.2f}',
             'Positive.TLabel' if pl_ratio >= 1 else 'Negative.TLabel'),
            ('交易次数', f'{len(d.trades)}',
             'StatBig.TLabel'),
            ('平均盈亏', f'{d.avg_profit:+.2f}%',
             'Positive.TLabel' if d.avg_profit >= 0 else 'Negative.TLabel'),
            ('卖出笔数', f'{len([t for t in d.trades if t.side == "SELL"])}',
             'StatBig.TLabel'),
            ('均持天数', f'{d.avg_hold_days:.1f}天',
             'StatBig.TLabel'),
        ]

        for i, (label, value, style) in enumerate(cards_data):
            card = ttk.Frame(parent, style='Card.TFrame')
            card.pack(side=tk.LEFT, padx=4, pady=4, ipadx=8, ipady=2)

            ttk.Label(card, text=label, style='StatLabel.TLabel').pack(pady=(4, 0))
            ttk.Label(card, text=value, style=style).pack(pady=(0, 4))

    def _build_equity_chart(self, parent):
        """净值曲线 + 回撤"""
        chart_frame = ttk.Frame(parent, style='Panel.TFrame')
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        ttk.Label(chart_frame, text='净值曲线 & 回撤',
                  style='Header.TLabel').pack(anchor=tk.W, padx=10, pady=(5, 0))

        fig = Figure(figsize=(10, 4.5), dpi=100, facecolor=COLORS['panel_bg'])
        gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.05)

        # 上图: 净值曲线
        ax1 = fig.add_subplot(gs[0], facecolor=COLORS['chart_bg'])
        # 下图: 回撤
        ax2 = fig.add_subplot(gs[1], facecolor=COLORS['chart_bg'], sharex=ax1)

        dates, totals = self.data.equity_curve
        if len(totals) > 0:
            dates_dt = pd.to_datetime(dates, errors='coerce')
            # 净值曲线
            ax1.plot(dates_dt, totals, color=COLORS['red'], linewidth=1.5,
                     label='策略净值')
            ax1.axhline(y=self.data.initial_cash, color=COLORS['text_dim'],
                        linestyle='--', linewidth=0.8, alpha=0.6, label='初始资金')
            ax1.fill_between(dates_dt, self.data.initial_cash, totals,
                             where=(totals >= self.data.initial_cash),
                             color=COLORS['red'], alpha=0.1)
            ax1.fill_between(dates_dt, self.data.initial_cash, totals,
                             where=(totals < self.data.initial_cash),
                             color=COLORS['green'], alpha=0.1)

            # 标注最终值
            ax1.annotate(f'¥{totals[-1]:,.0f}\n({self.data.total_return:+.1f}%)',
                         xy=(dates_dt[-1], totals[-1]),
                         xytext=(15, 10), textcoords='offset points',
                         fontsize=9, color=COLORS['red' if totals[-1] >= self.data.initial_cash else 'green'],
                         fontweight='bold')

            ax1.legend(loc='upper left', fontsize=8, facecolor=COLORS['panel_bg'],
                       edgecolor=COLORS['grid'], labelcolor=COLORS['text'])

            # 回撤
            cummax = np.maximum.accumulate(totals)
            drawdown = (totals - cummax) / cummax * 100
            ax2.fill_between(dates_dt, drawdown, 0,
                             color=COLORS['green'], alpha=0.3)
            ax2.plot(dates_dt, drawdown, color=COLORS['green'], linewidth=0.8)
            ax2.axhline(y=0, color=COLORS['text_dim'], linewidth=0.5, alpha=0.5)

            # 标注最大回撤
            min_idx = np.argmin(drawdown)
            ax2.annotate(f'Max DD: {drawdown[min_idx]:.1f}%',
                         xy=(dates_dt[min_idx], drawdown[min_idx]),
                         xytext=(10, -15), textcoords='offset points',
                         fontsize=8, color=COLORS['green'],
                         arrowprops=dict(arrowstyle='->', color=COLORS['green'], lw=0.8))

        # 样式
        for ax in [ax1, ax2]:
            ax.tick_params(colors=COLORS['text_dim'], labelsize=8)
            ax.grid(True, alpha=0.15, color=COLORS['grid'])
            for spine in ax.spines.values():
                spine.set_color(COLORS['grid'])

        ax1.set_ylabel('资产 (¥)', color=COLORS['text_dim'], fontsize=9)
        ax2.set_ylabel('回撤 %', color=COLORS['text_dim'], fontsize=9)
        ax2.set_xlabel('日期', color=COLORS['text_dim'], fontsize=9)
        ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'¥{x/1000:.0f}k'))

        plt.setp(ax1.get_xticklabels(), visible=False)

        canvas = FigureCanvasTkAgg(fig, chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _build_strategy_chart(self, parent):
        """策略分项统计柱状图"""
        ttk.Label(parent, text='策略分项胜率 & 累计盈亏',
                  style='Header.TLabel').pack(anchor=tk.W, padx=10, pady=(5, 0))

        fig = Figure(figsize=(4.5, 3), dpi=100, facecolor=COLORS['panel_bg'])
        ax1 = fig.add_subplot(111, facecolor=COLORS['chart_bg'])

        strategies = list(self.data.strategy_stats.keys())
        stats = self.data.strategy_stats

        win_rates = []
        pnls = []
        totals = []
        labels = []
        for s in strategies:
            ss = stats[s]
            if ss['total'] > 0:
                labels.append(s)
                win_rates.append(ss['wins'] / ss['total'] * 100)
                pnls.append(ss['pnl'])
                totals.append(ss['total'])

        x = np.arange(len(labels))
        width = 0.35

        bars1 = ax1.bar(x - width/2, win_rates, width, color=COLORS['accent'],
                        alpha=0.8, label='胜率 %')
        bars2 = ax1.bar(x + width/2, pnls, width, color=COLORS['highlight'],
                        alpha=0.8, label='累计盈亏 %')

        # 标注值
        for bar, val in zip(bars1, win_rates):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                     f'{val:.0f}%', ha='center', fontsize=8, color=COLORS['text'])
        for bar, val in zip(bars2, pnls):
            y_pos = bar.get_height() + 1 if val >= 0 else bar.get_height() - 3
            color = COLORS['red'] if val >= 0 else COLORS['green']
            ax1.text(bar.get_x() + bar.get_width()/2, y_pos,
                     f'{val:+.1f}%', ha='center', fontsize=8, color=color)

        ax1.set_xticks(x)
        ax1.set_xticklabels(labels, fontsize=9, color=COLORS['text'])
        ax1.legend(fontsize=8, facecolor=COLORS['panel_bg'],
                   edgecolor=COLORS['grid'], labelcolor=COLORS['text'])
        ax1.tick_params(colors=COLORS['text_dim'], labelsize=8)
        ax1.grid(True, alpha=0.15, color=COLORS['grid'], axis='y')
        for spine in ax1.spines.values():
            spine.set_color(COLORS['grid'])

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _build_distribution_chart(self, parent):
        """盈亏分布直方图"""
        ttk.Label(parent, text='盈亏分布',
                  style='Header.TLabel').pack(anchor=tk.W, padx=10, pady=(5, 0))

        fig = Figure(figsize=(4.5, 3), dpi=100, facecolor=COLORS['panel_bg'])
        ax = fig.add_subplot(111, facecolor=COLORS['chart_bg'])

        sells = [t for t in self.data.trades if t.side == 'SELL']
        if sells:
            pnl_list = [t.pnl_pct for t in sells]
            bins = np.linspace(min(pnl_list) - 1, max(pnl_list) + 1, 20)
            n, bins_out, patches = ax.hist(pnl_list, bins=bins, edgecolor=COLORS['panel_bg'],
                                           alpha=0.8)

            # 着色: 盈利红, 亏损绿
            for i, patch in enumerate(patches):
                if bins_out[i] >= 0:
                    patch.set_facecolor(COLORS['red'])
                else:
                    patch.set_facecolor(COLORS['green'])

            ax.axvline(x=0, color=COLORS['text_dim'], linestyle='--', linewidth=0.8)
            ax.axvline(x=np.mean(pnl_list), color=COLORS['highlight'],
                       linestyle='--', linewidth=1, label=f'均值 {np.mean(pnl_list):+.2f}%')
            ax.legend(fontsize=8, facecolor=COLORS['panel_bg'],
                      edgecolor=COLORS['grid'], labelcolor=COLORS['text'])

        ax.set_xlabel('盈亏 %', color=COLORS['text_dim'], fontsize=9)
        ax.set_ylabel('笔数', color=COLORS['text_dim'], fontsize=9)
        ax.tick_params(colors=COLORS['text_dim'], labelsize=8)
        ax.grid(True, alpha=0.15, color=COLORS['grid'], axis='y')
        for spine in ax.spines.values():
            spine.set_color(COLORS['grid'])

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _build_correlation_chart(self, parent):
        """V30.4: 策略日收益相关性热力图"""
        chart_frame = ttk.Frame(parent, style='Panel.TFrame')
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        ttk.Label(chart_frame, text='策略相关性',
                  style='Header.TLabel').pack(anchor=tk.W, padx=10, pady=(5, 0))

        # 按策略分组每日收益
        strat_returns = {}
        dates_set = set()
        for t in self.data.trades:
            if hasattr(t, 'strategy') and hasattr(t, 'pnl') and hasattr(t, 'date'):
                s = t.strategy
                if s not in strat_returns:
                    strat_returns[s] = defaultdict(float)
                strat_returns[s][t.date] += t.pnl
                dates_set.add(t.date)

        strategies = sorted(strat_returns.keys())
        if len(strategies) < 2:
            ttk.Label(chart_frame, text='策略数不足',
                      style='StatLabel.TLabel').pack(pady=20)
            return

        # 构建日收益矩阵
        all_dates = sorted(dates_set)
        df = pd.DataFrame(index=all_dates)
        for s in strategies:
            df[s] = pd.Series(strat_returns[s], index=all_dates).fillna(0)

        # 相关性矩阵
        corr = df.corr()
        n = len(strategies)

        fig = Figure(figsize=(3.5, 3), dpi=100, facecolor=COLORS['panel_bg'])
        ax = fig.add_subplot(111)

        im = ax.imshow(corr.values, cmap='RdYlGn', vmin=-1, vmax=1, aspect='auto')
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels(strategies, fontsize=7, rotation=45)
        ax.set_yticklabels(strategies, fontsize=7)

        for i in range(n):
            for j in range(n):
                v = corr.values[i, j]
                ax.text(j, i, f'{v:.2f}', ha='center', va='center',
                        fontsize=8, fontweight='bold',
                        color='white' if abs(v) > 0.5 else 'black')

        ax.set_title('策略日收益相关性', color=COLORS['text'], fontsize=10, pad=10)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _build_info_panels(self, parent):
        """右侧信息面板"""
        # Notebok (标签页)
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # 标签1: 交易记录
        trade_tab = ttk.Frame(notebook, style='Dark.TFrame')
        notebook.add(trade_tab, text='交易记录')
        self._build_trade_table(trade_tab)

        # 标签2: 行业统计
        sector_tab = ttk.Frame(notebook, style='Dark.TFrame')
        notebook.add(sector_tab, text='行业统计')
        self._build_sector_table(sector_tab)

        # 标签3: 持仓历史
        pos_tab = ttk.Frame(notebook, style='Dark.TFrame')
        notebook.add(pos_tab, text='持仓历史')
        self._build_positions_chart(pos_tab)

        # 标签4: 月度收益
        month_tab = ttk.Frame(notebook, style='Dark.TFrame')
        notebook.add(month_tab, text='月度收益')
        self._build_monthly_table(month_tab)

        # 标签5: 信号日志
        signal_tab = ttk.Frame(notebook, style='Dark.TFrame')
        notebook.add(signal_tab, text='信号日志')
        self._build_signal_log(signal_tab)

    def _build_trade_table(self, parent):
        """交易记录表格"""
        # 筛选栏
        filter_frame = ttk.Frame(parent, style='Panel.TFrame')
        filter_frame.pack(fill=tk.X, padx=2, pady=2)

        ttk.Label(filter_frame, text='筛选:',
                  style='StatLabel.TLabel').pack(side=tk.LEFT, padx=5)

        self.trade_filter_var = tk.StringVar(value='全部')
        filter_combo = ttk.Combobox(filter_frame, textvariable=self.trade_filter_var,
                                    values=['全部', '买入', '卖出', '盈利', '亏损'],
                                    state='readonly', width=8)
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo.bind('<<ComboboxSelected>>', lambda e: self._refresh_trade_table())

        ttk.Label(filter_frame, text=f'共 {len(self.data.trades)} 笔',
                  style='StatLabel.TLabel').pack(side=tk.RIGHT, padx=5)

        # 表格
        tree_frame = ttk.Frame(parent, style='Panel.TFrame')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        columns = ('日期', '方向', '股票', '价格', '数量', '成本价',
                   '盈亏%', '盈亏¥', '策略', '行业', '理由')
        self.trade_tree = ttk.Treeview(tree_frame, columns=columns,
                                       show='headings', style='Trade.Treeview',
                                       height=20)

        col_widths = [85, 40, 75, 55, 45, 55, 55, 60, 50, 65, 120]
        for col, w in zip(columns, col_widths):
            self.trade_tree.heading(col, text=col)
            self.trade_tree.column(col, width=w, anchor='center')

        # 滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                                  command=self.trade_tree.yview)
        self.trade_tree.configure(yscrollcommand=scrollbar.set)

        self.trade_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._refresh_trade_table()

    def _refresh_trade_table(self):
        """刷新交易表格"""
        for item in self.trade_tree.get_children():
            self.trade_tree.delete(item)

        filter_val = self.trade_filter_var.get()

        for t in self.data.trades:
            # 筛选
            if filter_val == '买入' and t.side != 'BUY':
                continue
            if filter_val == '卖出' and t.side != 'SELL':
                continue
            if filter_val == '盈利' and t.pnl_pct <= 0:
                continue
            if filter_val == '亏损' and t.pnl_pct >= 0:
                continue

            pnl_str = f'{t.pnl_pct:+.2f}%'
            pnl_amt = f'{t.pnl_amount:+.0f}'

            # 颜色标记
            tags = []
            if t.side == 'BUY':
                tags.append('buy')
            elif t.pnl_pct > 0:
                tags.append('profit')
            else:
                tags.append('loss')

            self.trade_tree.insert('', tk.END, values=(
                t.date, '买入' if t.side == 'BUY' else '卖出',
                stock_pool.get_symbol_name(t.symbol),
                f'{t.price:.2f}', str(t.vol),
                f'{t.cost_price:.2f}' if t.cost_price else '-',
                pnl_str if t.side == 'SELL' else '-',
                pnl_amt if t.side == 'SELL' else '-',
                t.strategy, t.sector, t.reason[:20] if t.reason else '-'
            ), tags=tags)

        # 标签颜色
        self.trade_tree.tag_configure('buy', foreground=COLORS['red'])
        self.trade_tree.tag_configure('profit', foreground=COLORS['red'])
        self.trade_tree.tag_configure('loss', foreground=COLORS['green'])

    def _build_sector_table(self, parent):
        """行业统计"""
        columns = ('行业', '交易数', '胜率', '累计盈亏')
        tree = ttk.Treeview(parent, columns=columns,
                            show='headings', style='Trade.Treeview')

        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=80, anchor='center')

        for sector, ss in sorted(self.data.sector_stats.items(),
                                  key=lambda x: x[1]['pnl'], reverse=True):
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                pnl_str = f'{ss["pnl"]:+.1f}%'
                tags = ('profit',) if ss['pnl'] >= 0 else ('loss',)
                tree.insert('', tk.END, values=(sector, ss['total'],
                            f'{wr:.1f}%', pnl_str), tags=tags)

        tree.tag_configure('profit', foreground=COLORS['red'])
        tree.tag_configure('loss', foreground=COLORS['green'])

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_positions_chart(self, parent):
        """持仓数量变化图"""
        fig = Figure(figsize=(4, 3), dpi=100, facecolor=COLORS['panel_bg'])
        ax = fig.add_subplot(111, facecolor=COLORS['chart_bg'])

        if self.data.positions_history:
            dates = [p['date'] for p in self.data.positions_history]
            counts = [p['count'] for p in self.data.positions_history]
            ax.fill_between(range(len(dates)), counts, alpha=0.3,
                            color=COLORS['highlight'])
            ax.plot(range(len(dates)), counts, color=COLORS['highlight'],
                    linewidth=1.5)

            # 标注最大持仓
            max_idx = np.argmax(counts)
            ax.annotate(f'  Max: {counts[max_idx]}',
                        xy=(max_idx, counts[max_idx]),
                        fontsize=9, color=COLORS['text'])

        ax.set_ylabel('持仓数', color=COLORS['text_dim'], fontsize=9)
        ax.tick_params(colors=COLORS['text_dim'], labelsize=8)
        ax.grid(True, alpha=0.15, color=COLORS['grid'])
        for spine in ax.spines.values():
            spine.set_color(COLORS['grid'])
        ax.set_ylim(bottom=0)

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _build_monthly_table(self, parent):
        """月度收益表"""
        columns = ('月份', '收益%', '交易数', '胜率')
        tree = ttk.Treeview(parent, columns=columns,
                            show='headings', style='Trade.Treeview')

        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=75, anchor='center')

        # 按月汇总
        monthly = defaultdict(lambda: {'pnl': 0, 'total': 0, 'wins': 0})
        for t in self.data.trades:
            if t.side != 'SELL':
                continue
            month = t.date[:7]
            monthly[month]['pnl'] += t.pnl_pct
            monthly[month]['total'] += 1
            if t.pnl_pct > 0:
                monthly[month]['wins'] += 1

        for month in sorted(monthly.keys()):
            m = monthly[month]
            wr = m['wins'] / m['total'] * 100 if m['total'] > 0 else 0
            pnl_str = f'{m["pnl"]:+.1f}%'
            tags = ('profit',) if m['pnl'] >= 0 else ('loss',)
            tree.insert('', tk.END, values=(month, pnl_str, m['total'],
                        f'{wr:.0f}%'), tags=tags)

        tree.tag_configure('profit', foreground=COLORS['red'])
        tree.tag_configure('loss', foreground=COLORS['green'])

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_signal_log(self, parent):
        """信号日志"""
        text_frame = ttk.Frame(parent, style='Panel.TFrame')
        text_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        text_widget = tk.Text(text_frame, bg=COLORS['chart_bg'],
                              fg=COLORS['text'], font=('Consolas', 9),
                              wrap=tk.WORD, insertbackground=COLORS['white'])
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                  command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 写入内容
        text_widget.insert(tk.END, '=' * 50 + '\n')
        text_widget.insert(tk.END, f'  回测信号日志\n')
        text_widget.insert(tk.END, f'  回测区间: {BACKTEST_START[:10]} ~ {BACKTEST_END[:10]}\n')
        text_widget.insert(tk.END, f'  初始资金: ¥{BACKTEST_CASH:,}\n')
        text_widget.insert(tk.END, '=' * 50 + '\n\n')

        # 策略统计
        text_widget.insert(tk.END, '--- 策略分项 ---\n')
        for name, ss in self.data.strategy_stats.items():
            if ss['total'] > 0:
                wr = ss['wins'] / ss['total'] * 100
                text_widget.insert(tk.END,
                    f'  {name:5s}: {ss["total"]:3d}笔  胜率{wr:5.1f}%  盈亏{ss["pnl"]:+7.1f}%\n')

        text_widget.insert(tk.END, '\n--- 交易明细 ---\n')
        for t in self.data.trades:
            side = '买' if t.side == 'BUY' else '卖'
            line = f'  [{t.date}] {side} {stock_pool.get_symbol_name(t.symbol):8s} @{t.price:8.2f}'
            if t.side == 'SELL':
                line += f' | 成本{t.cost_price:8.2f} | 盈亏{t.pnl_pct:+6.2f}%'
            line += f' | {t.strategy:4s} | {t.sector}'
            if t.reason:
                line += f' | {t.reason[:30]}'
            line += '\n'
            text_widget.insert(tk.END, line)

        text_widget.insert(tk.END, '\n' + '=' * 50 + '\n')
        text_widget.insert(tk.END, f'  总收益: {self.data.total_return:+.2f}%\n')
        text_widget.insert(tk.END, f'  最大回撤: {self.data.max_drawdown:.2f}%\n')
        text_widget.insert(tk.END, f'  胜率: {self.data.win_rate:.1f}%\n')
        text_widget.insert(tk.END, '=' * 50 + '\n')

        text_widget.configure(state='disabled')

    def _update_clock(self):
        """实时时钟"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.clock_lbl.config(text=f'[Clock] {now}')

        # 耗时显示
        if self.data.total_elapsed > 0:
            mins = int(self.data.total_elapsed // 60)
            secs = int(self.data.total_elapsed % 60)
            self.elapsed_lbl.config(text=f'[Time] 回测耗时: {mins}分{secs}秒')

        self.root.after(1000, self._update_clock)

    def _export_csv(self):
        """导出交易记录CSV"""
        filepath = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('CSV', '*.csv')],
            initialfile=f'trades_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
        if not filepath:
            return

        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['日期', '方向', '股票', '价格', '数量', '成本价',
                             '盈亏%', '盈亏金额', '策略', '行业', '理由', '置信度', '持仓天数'])
            for t in self.data.trades:
                writer.writerow([
                    t.date,
                    '买入' if t.side == 'BUY' else '卖出',
                    stock_pool.get_symbol_name(t.symbol),
                    f'{t.price:.2f}',
                    t.vol,
                    f'{t.cost_price:.2f}' if t.cost_price else '',
                    f'{t.pnl_pct:.2f}' if t.side == 'SELL' else '',
                    f'{t.pnl_amount:.2f}' if t.side == 'SELL' else '',
                    t.strategy, t.sector, t.reason,
                    f'{t.confidence:.2f}', t.hold_days
                ])

        messagebox.showinfo('导出成功', f'已导出到:\n{filepath}')

    def _save_full_log(self):
        """保存完整日志到 logs/ 目录"""
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(log_dir, f'visualizer_{timestamp}.csv')

        # 交易日志
        with open(log_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['=' * 20 + ' 回测可视化完整日志 ' + '=' * 20])
            writer.writerow([f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
            writer.writerow([f'回测区间: {BACKTEST_START[:10]} ~ {BACKTEST_END[:10]}'])
            writer.writerow([f'初始资金: ¥{BACKTEST_CASH:,}'])
            writer.writerow([f'总收益率: {self.data.total_return:+.2f}%'])
            writer.writerow([f'最大回撤: {self.data.max_drawdown:.2f}%'])
            writer.writerow([f'交易胜率: {self.data.win_rate:.1f}%'])
            writer.writerow([f'夏普比率: {self.data.sharpe_ratio:.2f}'])
            writer.writerow([])
            writer.writerow(['--- 交易明细 ---'])
            writer.writerow(['日期', '方向', '股票', '价格', '数量', '成本价',
                             '盈亏%', '盈亏金额', '策略', '行业', '理由'])
            for t in self.data.trades:
                writer.writerow([
                    t.date,
                    '买入' if t.side == 'BUY' else '卖出',
                    stock_pool.get_symbol_name(t.symbol),
                    f'{t.price:.2f}',
                    t.vol,
                    f'{t.cost_price:.2f}' if t.cost_price else '',
                    f'{t.pnl_pct:.2f}' if t.side == 'SELL' else '',
                    f'{t.pnl_amount:.2f}' if t.side == 'SELL' else '',
                    t.strategy, t.sector, t.reason
                ])

        messagebox.showinfo('保存成功', f'日志已保存到:\n{log_path}')

    def _export_html(self):
        """V30.4: 导出独立HTML报告 (借鉴Vibe-Trading)"""
        from tkinter import filedialog as fd
        filename = fd.asksaveasfilename(
            defaultextension='.html',
            filetypes=[('HTML', '*.html')],
            initialfile=f'gm_quant_report_{datetime.now():%Y%m%d}.html'
        )
        if not filename:
            return

        d = self.data
        # 计算指标
        sells = [t for t in d.trades if t.side == 'SELL']
        wins = [t.pnl for t in sells if hasattr(t, 'pnl') and hasattr(t, 'pnl_pct') for t in [t]][:0]

        # --- HTML模板 ---
        html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>gm-quant V30.4 回测报告</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;background:#1a1a2e;color:#e0e0e0;margin:40px}}
h1{{color:#e94560;border-bottom:2px solid #0f3460;padding-bottom:10px}}
.card{{background:#16213e;border-radius:12px;padding:20px;margin:10px;display:inline-block;min-width:140px}}
.card .val{{font-size:32px;font-weight:bold;margin:5px 0}}
.card .lbl{{font-size:13px;color:#888}}
.pos{{color:#e94560}}.neg{{color:#4ecca3}}
table{{border-collapse:collapse;width:100%;margin:10px 0}}
th{{background:#0f3460;padding:10px;text-align:left}}
td{{padding:8px;border-bottom:1px solid #0f3460}}
tr:hover{{background:#1a1a3e}}
.summary{{display:flex;flex-wrap:wrap;margin:20px 0}}
</style></head><body>
<h1>gm-quant V30.4 回测报告</h1>
<p>{datetime.now():%Y-%m-%d %H:%M} | 区间: {d.trades[0].date if d.trades else 'N/A'} ~ {d.trades[-1].date if d.trades else 'N/A'}</p>

<div class="summary">
<div class="card"><div class="lbl">总收益率</div><div class="val {'pos' if d.total_return>=0 else 'neg'}">{d.total_return:+.2f}%</div></div>
<div class="card"><div class="lbl">最大回撤</div><div class="val neg">{d.max_drawdown:.2f}%</div></div>
<div class="card"><div class="lbl">胜率</div><div class="val {'pos' if d.win_rate>=50 else ''}">{d.win_rate:.1f}%</div></div>
<div class="card"><div class="lbl">夏普比率</div><div class="val">{d.sharpe_ratio:.2f}</div></div>
<div class="card"><div class="lbl">交易次数</div><div class="val">{len(d.trades)}</div></div>
<div class="card"><div class="lbl">平均盈亏</div><div class="val {'pos' if d.avg_profit>=0 else 'neg'}">{d.avg_profit:+.2f}%</div></div>
</div>

<h2>策略分项</h2>
<table><tr><th>策略</th><th>交易</th><th>胜率</th><th>累计盈亏</th></tr>'''
        for name, stats in sorted(d.strategy_stats.items()):
            total = stats.get('total', 0)
            wins_s = stats.get('wins', 0)
            wr = wins_s/total*100 if total else 0
            pnl = stats.get('pnl', 0)
            html += f'<tr><td>{name}</td><td>{total}</td><td>{wr:.1f}%</td><td class="{"pos" if pnl>=0 else "neg"}">{pnl:+.1f}%</td></tr>'
        html += '</table>'

        html += '<h2>行业分项</h2><table><tr><th>行业</th><th>交易</th><th>胜率</th><th>累计</th></tr>'
        for sec, stats in sorted(d.sector_stats.items()):
            total = stats.get('total', 0)
            wins_s = stats.get('wins', 0)
            wr = wins_s/total*100 if total else 0
            pnl = stats.get('pnl', 0)
            html += f'<tr><td>{sec}</td><td>{total}</td><td>{wr:.1f}%</td><td class="{"pos" if pnl>=0 else "neg"}">{pnl:+.1f}%</td></tr>'
        html += '</table>'

        # 最近10笔
        html += '<h2>最近卖出</h2><table><tr><th>日期</th><th>股票</th><th>策略</th><th>盈亏</th></tr>'
        recent = [t for t in sells if hasattr(t, 'pnl_pct')][-10:]
        for t in reversed(recent):
            html += f'<tr><td>{t.date}</td><td>{getattr(t,"symbol","")}</td><td>{getattr(t,"strategy","")}</td><td class="{"pos" if t.pnl_pct>=0 else "neg"}">{t.pnl_pct:+.2f}%</td></tr>'
        html += '</table><p style="color:#888;text-align:center;margin-top:40px">gm-quant V30.4 · Powered by local_data_loader</p></body></html>'

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
        messagebox.showinfo('导出成功', f'HTML报告已保存到:\n{filename}')

    def _on_close(self):
        """关闭窗口"""
        self.root.quit()
        self.root.destroy()

    def run(self):
        """启动 GUI 主循环"""
        self.root.mainloop()


# =============================================================================
# 数据转换: 回测引擎 → 可视化数据
# =============================================================================

def from_backtest_engine(engine) -> BacktestData:
    """从 V19BacktestEngine 提取数据"""
    data = BacktestData()

    # 日净值
    data.daily_values = list(engine.daily_values)

    # 转换 trades
    for t in engine.trades:
        if t['side'] == 'SELL':
            cost = t.get('cost_price', 0)
            record = TradeRecord(
                date=t['date'],
                symbol=t['symbol'],
                side='SELL',
                price=t['price'],
                vol=t['vol'],
                cost_price=cost,
                pnl_pct=t['pnl_pct'],
                pnl_amount=t['pnl_pct'] / 100 * cost * t['vol'] if cost else 0,
                sector=t.get('sector', ''),
                strategy=t.get('strategy', ''),
                reason=t.get('reason', ''),
                hold_days=t.get('hold_days', 0),
            )
        else:
            record = TradeRecord(
                date=t.get('date', ''),
                symbol=t.get('symbol', ''),
                side='BUY',
                price=t.get('price', 0),
                vol=t.get('vol', 0),
                cost_price=t.get('price', 0),
                sector=t.get('sector', ''),
                strategy=t.get('strategy', ''),
                reason=t.get('reason', ''),
            )
        data.trades.append(record)

    # 策略统计
    data.strategy_stats = dict(engine.strategy_stats)
    data.sector_stats = dict(engine.sector_stats)

    # 持仓历史
    data.positions_history = []
    # (从 daily_values 无法直接获知每日持仓数，但这个可以从 trades 推算)

    return data


def from_csv_files(nav_csv: str, trade_csv: str) -> BacktestData:
    """从 CSV 文件加载回测结果"""
    data = BacktestData()

    # 净值
    try:
        nav = pd.read_csv(nav_csv)
        data.daily_values = [
            {'date': str(r['date']), 'cash': 0, 'market': 0,
             'total': float(r['total_asset_value'])}
            for _, r in nav.iterrows()
        ]
    except Exception:
        pass

    # 交易
    try:
        trades_df = pd.read_csv(trade_csv)
        for _, r in trades_df.iterrows():
            side = 'BUY' if '买入' in str(r.get('btype', '')) else 'SELL'
            record = TradeRecord(
                date=str(r.get('date', '')),
                symbol=str(r.get('symbol', '')),
                side=side,
                price=float(r.get('price', 0)),
                vol=int(r.get('volume', 0)),
                cost_price=float(r.get('cost_price', 0)) if side == 'SELL' else float(r.get('price', 0)),
                pnl_pct=float(r.get('pnl_pct', 0)),
                pnl_amount=0,
                sector='',
                strategy='',
                reason=str(r.get('btype', '')),
            )
            data.trades.append(record)
    except Exception:
        pass

    return data


# =============================================================================
# 终端入口
# =============================================================================

VISUAL_ENABLED = True   # V29.4: 默认启用可视化（GM终端无stdin也生效）

# =============================================================================
# V29.4: 实时加载窗口 — 回测前即弹出，显示进度
# =============================================================================

_loading_root = None
_loading_label = None
_loading_title_text = ''


def open_loading_window(title_text='gm-quant'):
    """回测开始前立即弹出轻量窗口，显示加载状态。"""
    global _loading_root, _loading_label, _loading_title_text
    _loading_title_text = title_text

    try:
        _loading_root = tk.Tk()
    except Exception:
        _loading_root = None
        return

    _loading_root.title(title_text)
    _loading_root.configure(bg=COLORS['bg'])
    _loading_root.protocol("WM_DELETE_WINDOW", lambda: None)  # 禁止关闭

    sw = _loading_root.winfo_screenwidth()
    sh = _loading_root.winfo_screenheight()
    w, h = 520, 320
    _loading_root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # 标题
    tk.Label(_loading_root, text=title_text,
             font=('Microsoft YaHei', 16, 'bold'),
             fg=COLORS['highlight'], bg=COLORS['bg']).pack(pady=(50, 10))

    # 副标题
    tk.Label(_loading_root, text='六策略行业差异化回测框架',
             font=('Microsoft YaHei', 10),
             fg=COLORS['text_dim'], bg=COLORS['bg']).pack()

    # 进度标签
    _loading_label = tk.Label(_loading_root, text='初始化...',
                              font=('Microsoft YaHei', 12),
                              fg=COLORS['text'], bg=COLORS['bg'],
                              wraplength=480, justify='center')
    _loading_label.pack(pady=(30, 10))

    # 进度条
    try:
        style = ttk.Style()
        style.configure('Load.Horizontal.TProgressbar',
                        background=COLORS['highlight'],
                        troughcolor=COLORS['panel_bg'])
        _progress_bar = ttk.Progressbar(_loading_root, mode='indeterminate',
                                        length=400, style='Load.Horizontal.TProgressbar')
        _progress_bar.pack(pady=(10, 30))
        _progress_bar.start(10)
    except Exception:
        pass

    _loading_root.update()


def update_loading(text):
    """回测引擎调用 -- 更新加载文本。"""
    global _loading_root, _loading_label
    if _loading_root and _loading_label:
        try:
            _loading_label.config(text=text)
            _loading_root.update()
        except Exception:
            pass


def close_loading_window():
    """回测完成后关闭加载窗口，准备打开完整可视化。"""
    global _loading_root, _loading_label
    if _loading_root:
        try:
            _loading_root.destroy()
        except Exception:
            pass
        _loading_root = None
        _loading_label = None


def prompt_visual():
    """终端交互: 是否打开可视化窗口。

    V29.4: 移除 isatty() 检测 — GM终端IDE中 stdin 可能不是tty但支持input()。
    改用 try/except EOFError 兜底，非交互环境自动跳过。
    """
    global VISUAL_ENABLED
    print()
    print('=' * 50)
    print('  [Vis] 可视化窗口')
    print('  1 = 打开可视化窗口 (GUI)')
    print('  2 = 跳过 (仅命令行输出)')
    print('=' * 50)
    try:
        choice = input('  请选择 [1/2] (默认=2): ').strip()
        if choice == '1':
            VISUAL_ENABLED = True
            print('  [OK] 回测完成后将打开可视化窗口')
        else:
            VISUAL_ENABLED = False
            print('  [Skip] 仅命令行输出')
    except (EOFError, OSError, KeyboardInterrupt):
        # 非交互环境 (后台/管道/重定向) → 默认跳过
        print('  [Skip] 非交互环境，仅命令行输出')
    print()


def launch_visualizer(data: BacktestData, elapsed_seconds: float = 0):
    """启动可视化窗口"""
    if not VISUAL_ENABLED:
        return

    data.total_elapsed = elapsed_seconds
    data.initial_cash = BACKTEST_CASH

    print('\n[Vis] 正在启动可视化窗口...')
    try:
        viz = BacktestVisualizer(data, title=f'gm-quant V29.4 | {BACKTEST_START[:10]} ~ {BACKTEST_END[:10]}')
        viz.run()
    except Exception as e:
        print(f'[Vis] 启动失败: {e}')
        import traceback
        traceback.print_exc()


# =============================================================================
# 测试入口
# =============================================================================

if __name__ == '__main__':
    # 测试: 从CSV加载
    import sys
    if len(sys.argv) >= 3:
        data = from_csv_files(sys.argv[1], sys.argv[2])
    else:
        # 造一些测试数据
        data = BacktestData()
        np.random.seed(42)
        n = 500
        cum_ret = np.cumsum(np.random.randn(n) * 0.02)
        for i in range(n):
            total = 25000 * (1 + cum_ret[i] / 10)
            data.daily_values.append({
                'date': f'2024-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}',
                'cash': 5000, 'market': total - 5000, 'total': total,
            })
        data.strategy_stats = {
            'MR': {'wins': 15, 'total': 25, 'pnl': 8.5},
            'MOM': {'wins': 18, 'total': 30, 'pnl': 12.3},
            'VP': {'wins': 10, 'total': 20, 'pnl': -2.1},
            'BK': {'wins': 8, 'total': 15, 'pnl': 5.2},
            'DV': {'wins': 12, 'total': 18, 'pnl': 3.8},
            'RT': {'wins': 6, 'total': 12, 'pnl': -1.5},
        }
        data.sector_stats = {
            '科技': {'wins': 10, 'total': 20, 'pnl': 15.0},
            '消费': {'wins': 8, 'total': 15, 'pnl': 6.0},
            '金融': {'wins': 5, 'total': 10, 'pnl': 2.0},
        }

    VISUAL_ENABLED = True
    launch_visualizer(data)
