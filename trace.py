"""
trace.py — 诊断日志 (V24)

记录格式(二进制紧凑):
  B|<策略>|<股票>|<价格>|<仓位%>|<票数>    (买入)
  S|<策略>|<股票>|<盈亏%>|<原因>            (卖出)
  E|错误信息                               (异常)
  H|市场状态|<情绪摘要>                     (心跳)

每条一行, 50-100字节, 576天约3-5MB
自动轮转: 最多保留10个文件
"""
import os
import time
import json
from datetime import datetime

TRACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'trace')
if not os.path.isabs(TRACE_DIR):
    TRACE_DIR = os.path.join(os.getcwd(), 'data', 'trace')
MAX_FILES = 10


def ensure_dir():
    os.makedirs(TRACE_DIR, exist_ok=True)


def _filepath():
    ensure_dir()
    today = datetime.now().strftime('%Y%m%d')
    return os.path.join(TRACE_DIR, f'{today}.log')


def _write(line):
    path = _filepath()
    ts = datetime.now().strftime('%H:%M:%S')
    with open(path, 'a', encoding='utf-8') as f:
        f.write(f'{ts}|{line}\n')


def rotate():
    """保持最多 MAX_FILES 个日志文件"""
    if not os.path.exists(TRACE_DIR):
        return
    files = sorted([f for f in os.listdir(TRACE_DIR) if f.endswith('.log')])
    while len(files) > MAX_FILES:
        os.remove(os.path.join(TRACE_DIR, files[0]))
        files.pop(0)


def buy(strategy, symbol, price, pct, votes, regime):
    """记录买入"""
    _write(f'B|{strategy}|{symbol}|{price:.2f}|{pct:.0%}|V{votes}|R{regime}')


def sell(strategy, symbol, pnl_pct, reason, regime):
    """记录卖出"""
    _write(f'S|{strategy}|{symbol}|{pnl_pct:+.2%}|{reason[:60]}|R{regime}')


def heartbeat(pos_count, cash, total_val, sentiment=None):
    """记录心跳 → 不写文件(太频繁), 仅内存计数"""
    pass  # 只在每天结束时由 status() 写一次


def error(msg):
    """记录错误"""
    _write(f'E|{msg[:200]}')


def status(msg):
    """记录状态"""
    _write(f'I|{msg[:200]}')


def dump_summary():
    """从日志提取摘要"""
    ensure_dir()
    stats = {'buys': 0, 'sells': 0, 'errors': 0, 'total_pnl': 0.0,
             'by_strategy': {}, 'by_sector': {}}
    today = datetime.now().strftime('%Y%m%d')
    path = os.path.join(TRACE_DIR, f'{today}.log')
    if not os.path.exists(path):
        return stats

    with open(path, encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 3:
                continue
            tag = parts[1]
            if tag == 'B':
                stats['buys'] += 1
            elif tag == 'S':
                stats['sells'] += 1
                try:
                    pnl = float(parts[3].rstrip('%')) / 100
                    stats['total_pnl'] += pnl
                except:
                    pass
                strat = parts[2]
                stats['by_strategy'][strat] = stats['by_strategy'].get(strat, 0) + 1
            elif tag == 'E':
                stats['errors'] += 1
    return stats
