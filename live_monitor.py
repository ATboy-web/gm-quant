"""
live_monitor.py - V29.8 实盘监控窗口
每2秒读取策略日志，实时显示持仓/交易/盈亏
"""

import tkinter as tk
from tkinter import ttk
import os
import re
import time
import threading

LOG_DIR = r"C:\Users\Administrator\.goldminer3\projects\6ec60351-55c6-11f1-9418-d843ae58f5f1\logs"


def find_latest_log():
    """找到最新的策略日志文件"""
    if not os.path.exists(LOG_DIR):
        return None
    logs = [f for f in os.listdir(LOG_DIR) if f.startswith("strategy_") and f.endswith(".log")]
    if not logs:
        return None
    logs.sort(reverse=True)
    return os.path.join(LOG_DIR, logs[0])


def parse_log(log_path):
    """解析日志，提取持仓/交易/状态"""
    if not log_path or not os.path.exists(log_path):
        return {"state": "等待启动...", "positions": [], "trades": [], "mode": "?", "account": "?"}

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    result = {
        "state": "运行中",
        "mode": "?",
        "account": "?",
        "positions": {},
        "trades": [],
        "last_state": "",
        "schedule": "",
        "total_buys": 0,
        "total_sells": 0,
    }

    for line in lines:
        line = line.strip()

        # Mode
        if "[Mode]" in line:
            m = re.search(r'\[Mode\]\s+(\w+)', line)
            if m:
                result["mode"] = m.group(1)
            m = re.search(r'account=(\w+)', line)
            if m:
                result["account"] = m.group(1)

        # Schedule
        if "[Schedule]" in line:
            result["schedule"] = line.split("[Schedule] ")[-1]

        # Buys
        if "[BUY]" in line:
            result["total_buys"] += 1
            parts = line.split("|")
            if len(parts) >= 6:
                sym = parts[1].strip()
                price_str = parts[4].strip().split(" x ")[0] if " x " in parts[4] else "?"
                qty_str = parts[4].strip().split(" x ")[1].split()[0] if " x " in parts[4] else "?"
                strat = parts[5].strip()[:8] if len(parts) > 5 else "?"
                result["positions"][sym] = {
                    "price": price_str,
                    "qty": qty_str,
                    "strategy": strat,
                    "time": line[0:8] if len(line) > 8 else ""
                }
                result["trades"].append({
                    "type": "BUY",
                    "symbol": sym,
                    "price": price_str,
                    "qty": qty_str,
                    "strategy": strat,
                    "time": line[0:8] if len(line) > 8 else ""
                })

        # Sells
        if "[SELL]" in line:
            result["total_sells"] += 1
            parts = line.split("|")
            if len(parts) >= 6:
                sym = parts[1].strip()
                pnl = parts[4].strip() if len(parts) > 4 else "?"
                result["positions"].pop(sym, None)
                result["trades"].append({
                    "type": "SELL",
                    "symbol": sym,
                    "pnl": pnl,
                    "time": line[0:8] if len(line) > 8 else ""
                })

        # State
        if "[State]" in line:
            result["last_state"] = line.split("[State] ")[-1][:100]

    return result


def parse_backtest_progress():
    """读取回测进度文件"""
    progress_file = os.path.join(LOG_DIR, "bt_progress.json")
    if not os.path.exists(progress_file):
        return None
    try:
        import json
        with open(progress_file, "r") as f:
            return json.load(f)
    except Exception:
        return None


class LiveMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GM-Quant Live Monitor V29.8")
        self.root.geometry("680x500")
        self.root.configure(bg="#1a1a2e")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#1a1a2e", foreground="#e0e0e0", font=("Consolas", 10))
        style.configure("Header.TLabel", font=("Consolas", 12, "bold"), foreground="#00d4aa")
        style.configure("Buy.TLabel", foreground="#ff4444")
        style.configure("Sell.TLabel", foreground="#44ff44")
        style.configure("TFrame", background="#16213e")
        style.configure("TLabelFrame.Label", background="#1a1a2e", foreground="#00d4aa", font=("Consolas", 11, "bold"))

        # Header
        self.header = ttk.Label(self.root, text="GM-Quant Live Monitor", style="Header.TLabel")
        self.header.pack(pady=5)

        # Status bar
        self.status_frame = ttk.Frame(self.root, style="TFrame")
        self.status_frame.pack(fill=tk.X, padx=10, pady=2)
        self.status_label = ttk.Label(self.status_frame, text="等待数据...", font=("Consolas", 9))
        self.status_label.pack(side=tk.LEFT, padx=5)

        # Main content area
        self.main_frame = ttk.Frame(self.root, style="TFrame")
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Positions table (left)
        pos_frame = ttk.LabelFrame(self.main_frame, text="持仓", style="TLabelFrame")
        pos_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.pos_text = tk.Text(pos_frame, bg="#0f3460", fg="#e0e0e0", font=("Consolas", 9),
                                height=12, width=30, state=tk.DISABLED, wrap=tk.NONE)
        self.pos_text.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

        # Trade log (right)
        trade_frame = ttk.LabelFrame(self.main_frame, text="最近交易", style="TLabelFrame")
        trade_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        self.trade_text = tk.Text(trade_frame, bg="#0f3460", fg="#e0e0e0", font=("Consolas", 9),
                                  height=12, width=35, state=tk.DISABLED, wrap=tk.NONE)
        self.trade_text.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

        # State bar at bottom
        self.state_label = ttk.Label(self.root, text="", font=("Consolas", 9))
        self.state_label.pack(fill=tk.X, padx=10, pady=2)

        # Tag colors
        self.pos_text.tag_configure("header", foreground="#00d4aa", font=("Consolas", 9, "bold"))
        self.pos_text.tag_configure("profit", foreground="#44ff44")
        self.pos_text.tag_configure("buy", foreground="#ff6363")
        self.pos_text.tag_configure("sell", foreground="#44ff44")

        self.running = True
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh()

    def refresh(self):
        if not self.running:
            return

        # Check for backtest progress first
        bt = parse_backtest_progress()
        if bt and bt.get("total", 0) > 0:
            self._render_backtest(bt)
        else:
            data = parse_log(find_latest_log())
            self._render_sim(data)

        self.root.after(2000, self.refresh)

    def _render_backtest(self, bt):
        self.status_label.config(text="  BACKTEST | %s / %s bars" % (bt["current"], bt["total"]))
        self.state_label.config(text="  %s | NAV %.0f (%+.1f%%) | pos %s | trades %s"
                                 % (bt["date"], bt["nav"], bt["ret"], bt["positions"], bt["trades"]))

        # Progress bar
        self.pos_text.config(state=tk.NORMAL)
        self.pos_text.delete(1.0, tk.END)
        pct = bt["current"] / max(bt["total"], 1) * 100
        bar_len = int(pct / 3.3)
        bar = "=" * bar_len + ">" + " " * (30 - bar_len)
        self.pos_text.insert(tk.END, "Backtest Progress\n\n", "header")
        self.pos_text.insert(tk.END, "[%s] %s%%\n\n" % (bar, int(pct)))
        self.pos_text.insert(tk.END, "Date:  %s\n" % bt["date"])
        self.pos_text.insert(tk.END, "NAV:   %.0f (%+.1f%%)\n" % (bt["nav"], bt["ret"]))
        self.pos_text.insert(tk.END, "Pos:   %s\n" % bt["positions"])
        self.pos_text.insert(tk.END, "Trades: %s\n" % bt["trades"])
        self.pos_text.insert(tk.END, "Win:   %s | Loss: %s\n" % (bt["wins"], bt["losses"]))
        self.pos_text.config(state=tk.DISABLED)

        self.trade_text.config(state=tk.NORMAL)
        self.trade_text.delete(1.0, tk.END)
        self.trade_text.insert(tk.END, "回测进行中...\n\n", "header")
        self.trade_text.insert(tk.END, "等待完成后显示\n完整可视化结果")
        self.trade_text.config(state=tk.DISABLED)

    def _render_sim(self, data):

        # Status bar
        self.status_label.config(
            text=f"  {data['mode']} | {data['account']} | 调度: {data['schedule']}")

        # State
        self.state_label.config(text=f"  {data['last_state']}")

        # Positions
        self.pos_text.config(state=tk.NORMAL)
        self.pos_text.delete(1.0, tk.END)
        if data["positions"]:
            self.pos_text.insert(tk.END, f"{'代码':<10}{'价':<8}{'量':<6}{'策略':<8}\n", "header")
            self.pos_text.insert(tk.END, "-" * 32 + "\n")
            for sym, info in sorted(data["positions"].items()):
                self.pos_text.insert(tk.END,
                    f"{sym:<10}{info['price']:<8}{info['qty']:<6}{info['strategy']:<8}\n")
            self.pos_text.insert(tk.END, f"\n共 {len(data['positions'])} 只持仓")
        else:
            self.pos_text.insert(tk.END, "暂无持仓\n", "profit")
        self.pos_text.config(state=tk.DISABLED)

        # Trades (last 20)
        self.trade_text.config(state=tk.NORMAL)
        self.trade_text.delete(1.0, tk.END)
        recent = data["trades"][-20:]
        self.trade_text.insert(tk.END, f"{'时间':<10}{'类型':<6}{'代码':<10}{'价格/盈亏':<12}\n", "header")
        self.trade_text.insert(tk.END, "-" * 38 + "\n")
        for t in reversed(recent):
            tag = "buy" if t["type"] == "BUY" else "sell"
            detail = f"{t.get('price', '')} x {t.get('qty', '')}" if t["type"] == "BUY" else t.get("pnl", "")
            self.trade_text.insert(tk.END,
                f"{t['time']:<10}{t['type']:<6}{t['symbol']:<10}{detail:<12}\n", tag)
        self.trade_text.insert(tk.END, f"\n买入: {data['total_buys']}  卖出: {data['total_sells']}")
        self.trade_text.config(state=tk.DISABLED)

        self.root.after(2000, self.refresh)

    def on_close(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = LiveMonitor()
    app.run()
