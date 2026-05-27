"""
local_data_loader.py - V30.4 本地数据加载器
从 GM 终端 SQLite 数据文件直接读取 OHLCV，无需终端运行。

数据目录: C:/lainghua/basic_data/day_bar/
表结构: dists_day_bar(symbol, trade_date, open, high, low, close, volume)
"""
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import os
import glob

DATA_DIR = "C:/lainghua/basic_data/day_bar"


def _get_db_files():
    """获取所有日线数据文件。"""
    return sorted(glob.glob(os.path.join(DATA_DIR, "*.dat")))


def _symbol_to_db(symbol):
    """根据股票代码确定属于哪个数据库文件。"""
    if symbol.startswith("SHSE."):
        # 上交所股票: SHSE_YYYY.dat
        return [f for f in _get_db_files() if "SHSE" in f and f.endswith(".dat")]
    elif symbol.startswith("SZSE."):
        # 深交所股票
        return [f for f in _get_db_files() if "SZSE" in f and f.endswith(".dat")]
    else:
        # 指数等: 尝试所有文件
        return _get_db_files()


def load_symbol(symbol, start, end):
    """
    加载单只股票的历史数据。

    Args:
        symbol: 'SHSE.600000' 格式
        start: '2024-01-01' 格式
        end: '2025-05-30' 格式

    Returns:
        DataFrame with columns [symbol, trade_date, open, high, low, close, volume]
        或 None
    """
    db_files = _symbol_to_db(symbol)
    dfs = []

    for db_path in db_files:
        try:
            conn = sqlite3.connect(db_path)
            query = """
                SELECT symbol, trade_date, open, high, low, close, volume
                FROM dists_day_bar
                WHERE symbol = ? AND trade_date >= ? AND trade_date <= ?
                ORDER BY trade_date
            """
            df = pd.read_sql_query(query, conn, params=(symbol, start, end))
            conn.close()
            if len(df) > 0:
                dfs.append(df)
        except Exception as e:
            pass

    if not dfs:
        return None
    result = pd.concat(dfs, ignore_index=True)
    # GM API返回的是bob/eob格式,这里保持一致
    result['bob'] = pd.to_datetime(result['trade_date']) + pd.Timedelta(hours=9, minutes=30)
    result['eob'] = pd.to_datetime(result['trade_date']) + pd.Timedelta(hours=15)
    result.rename(columns={'trade_date': 'date'}, inplace=True)
    return result.sort_values('bob')


def preload_all(start: str, end: str, symbols: list, verbose=True):
    """
    批量加载所有股票数据（替代GM的preload_all_data）。

    Args:
        start: '2024-01-01'
        end: '2025-05-30'
        symbols: ['SHSE.600000', ...]
        verbose: 打印进度

    Returns:
        dict: {symbol: DataFrame}
    """
    data = {}
    total = len(symbols)

    if verbose:
        print('[本地数据] 正在加载 %d 只股票...' % total)

    for i, sym in enumerate(symbols):
        df = load_symbol(sym, start, end)
        if df is not None and len(df) > 0:
            data[sym] = df
        if verbose and (i + 1) % 20 == 0:
            print('  进度: %d/%d' % (i + 1, total))

    if verbose:
        print('[本地数据] 完成: %d/%d 只股票有数据' % (len(data), total))

    return data


# ====== V30.5 ======
"""
yf_data_loader.py - V30.4 yfinance数据源 (参考runoob教程)
作为GM本地数据的备用数据源，自动回退。
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime


# GM symbol → yfinance symbol 映射
def gm_to_yf(symbol: str) -> str:
    """GM格式转yfinance格式: SHSE.600000 → 600000.SS"""
    if symbol.startswith('SHSE.'):
        return symbol.replace('SHSE.', '') + '.SS'
    elif symbol.startswith('SZSE.'):
        return symbol.replace('SZSE.', '') + '.SZ'
    return symbol


def load_symbol(symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """
    从yfinance加载单只股票数据。

    Args:
        symbol: GM格式如 'SHSE.600000'
        start: '2024-01-01'
        end: '2025-05-30'

    Returns:
        DataFrame with GM兼容格式 或 None
    """
    try:
        yf_sym = gm_to_yf(symbol)
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(start=start, end=end)

        if df.empty:
            return None

        # 转换为GM格式
        df = df.reset_index()
        df.rename(columns={
            'Date': 'bob',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
        }, inplace=True)

        # GM格式: bob必须有时间
        df['bob'] = pd.to_datetime(df['bob']) + pd.Timedelta(hours=9, minutes=30)
        df['eob'] = df['bob'] + pd.Timedelta(hours=5, minutes=30)
        df['date'] = df['bob'].dt.strftime('%Y-%m-%d')
        df['symbol'] = symbol

        return df[['symbol', 'date', 'bob', 'eob', 'open', 'high', 'low', 'close', 'volume']]
    except Exception:
        return None


def preload_all(start: str, end: str, symbols: list, verbose=True) -> dict:
    """
    批量加载所有股票数据 (yfinance备用)。

    自动跳过失败，返回能加载的股票。
    """
    data = {}
    total = len(symbols)
    if verbose:
        print('[yfinance] 正在下载 %d 只股票...' % total)

    for i, sym in enumerate(symbols):
        df = load_symbol(sym, start, end)
        if df is not None and len(df) >= 20:
            data[sym] = df
        if verbose and (i + 1) % 10 == 0:
            print('  进度: %d/%d (成功 %d)' % (i + 1, total, len(data)))

    if verbose:
        print('[yfinance] 完成: %d/%d' % (len(data), total))
    return data
