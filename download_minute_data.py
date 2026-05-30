"""
download_minute_data.py - 下载5分钟K线数据
使用baostock下载所有股票的5分钟数据，保存到本地SQLite
"""
import baostock as bs
import sqlite3
import pandas as pd
import os
import sys
from datetime import datetime

# 配置 — 使用workspace内的目录避免沙箱限制
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "minute_bar")
DB_FILE = os.path.join(DATA_DIR, "minute_bar_5min.db")
START_DATE = "2024-01-01"
END_DATE = "2026-05-26"

# 股票池
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stock_pool


def init_db():
    """初始化数据库"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS minute_bar (
            symbol TEXT,
            datetime TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            PRIMARY KEY (symbol, datetime)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON minute_bar(symbol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_datetime ON minute_bar(datetime)")
    conn.commit()
    return conn


def gm_to_bs(symbol):
    """GM格式转baostock格式: SHSE.600036 → sh.600036"""
    if symbol.startswith('SHSE.'):
        return 'sh.' + symbol.split('.')[-1]
    elif symbol.startswith('SZSE.'):
        return 'sz.' + symbol.split('.')[-1]
    return symbol


def download_symbol(bs_symbol, gm_symbol, conn, max_retries=3):
    """下载单只股票的5分钟数据，带重试"""
    for retry in range(max_retries):
        try:
            rs = bs.query_history_k_data_plus(
                bs_symbol,
                "date,time,code,open,high,low,close,volume",
                start_date=START_DATE,
                end_date=END_DATE,
                frequency="5",
                adjustflag="2"  # 前复权
            )
            
            if rs.error_code != '0':
                return 0
            break
        except Exception as e:
            if retry < max_retries - 1:
                import time
                time.sleep(2)
                # 重新登录
                try:
                    bs.logout()
                except:
                    pass
                bs.login()
            else:
                return 0
    
    rows = []
    while rs.next():
        row = rs.get_row_data()
        # row: [date, time, code, open, high, low, close, volume]
        dt_str = row[1]  # 20250506093500000
        # 转换为标准格式: 2025-05-06 09:35:00
        dt_formatted = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]} {dt_str[8:10]}:{dt_str[10:12]}:{dt_str[12:14]}"
        
        try:
            open_p = float(row[3])
            high_p = float(row[4])
            low_p = float(row[5])
            close_p = float(row[6])
            vol = float(row[7])
        except (ValueError, IndexError):
            continue
        
        rows.append((gm_symbol, dt_formatted, open_p, high_p, low_p, close_p, vol))
    
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO minute_bar VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows
        )
        conn.commit()
    
    return len(rows)


def main():
    print("=" * 60)
    print("  5分钟K线数据下载器")
    print(f"  区间: {START_DATE} ~ {END_DATE}")
    print("=" * 60)
    
    # 初始化数据库
    conn = init_db()
    
    # 登录baostock
    lg = bs.login()
    if lg.error_code != '0':
        print(f"登录失败: {lg.error_msg}")
        return
    print(f"baostock登录成功")
    
    # 获取股票池
    symbols = stock_pool.get_all_symbols()
    
    # 跳过已下载的股票
    cursor = conn.execute("SELECT DISTINCT symbol FROM minute_bar")
    downloaded = set(row[0] for row in cursor.fetchall())
    symbols = [s for s in symbols if s not in downloaded]
    print(f"待下载: {len(symbols)} 只 (已下载: {len(downloaded)})")
    print(f"股票池: {len(symbols)} 只")
    
    # 下载数据
    success = 0
    total_rows = 0
    for i, gm_sym in enumerate(symbols):
        bs_sym = gm_to_bs(gm_sym)
        try:
            rows = download_symbol(bs_sym, gm_sym, conn)
            if rows > 0:
                success += 1
                total_rows += rows
        except Exception as e:
            pass
        
        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{len(symbols)} | 成功: {success} | 总行数: {total_rows}")
    
    # 登出
    bs.logout()
    conn.close()
    
    print("=" * 60)
    print(f"  下载完成!")
    print(f"  成功: {success}/{len(symbols)} 只股票")
    print(f"  总行数: {total_rows}")
    print(f"  数据库: {DB_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
