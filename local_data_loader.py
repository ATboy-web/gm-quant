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
# yfinance/economy data sources - lazy imports to avoid import errors


# GM symbol → yfinance symbol 映射
def gm_to_yf(symbol: str) -> str:
    """GM格式转yfinance格式: SHSE.600000 → 600000.SS"""
    if symbol.startswith('SHSE.'):
        return symbol.replace('SHSE.', '') + '.SS'
    elif symbol.startswith('SZSE.'):
        return symbol.replace('SZSE.', '') + '.SZ'
    return symbol


def load_symbol_from_yfinance(symbol: str, start: str, end: str) -> pd.DataFrame | None:
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
        import yfinance as yf
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


def preload_from_yfinance(start: str, end: str, symbols: list, verbose=True) -> dict:
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

# ====== V30.5 efinance 数据源 (东方财富免费API) ======
def preload_from_efinance(start: str, end: str, symbols: list, verbose=True) -> dict:
    """从东方财富 API 批量加载数据（免费，无需终端）。"""
    import efinance as ef
    data = {}
    total = len(symbols)
    if verbose:
        print('[efinance] 正在下载 %d 只股票...' % total)
    for i, sym in enumerate(symbols):
        try:
            # GM格式 → 纯代码: SHSE.600000 → 600000
            code = sym.split('.')[-1] if '.' in sym else sym
            df = ef.stock.get_quote_history(code, beg=start.replace('-',''), end=end.replace('-',''))
            if df is not None and len(df) > 0:
                import pandas as pd
                df = df.rename(columns={
                    '日期': 'date', '开盘': 'open', '收盘': 'close',
                    '最高': 'high', '最低': 'low', '成交量': 'volume', '股票名称': 'name'
                })
                df['symbol'] = sym
                df['bob'] = pd.to_datetime(df['date']) + pd.Timedelta(hours=9, minutes=30)
                df['eob'] = df['bob'] + pd.Timedelta(hours=5, minutes=30)
                data[sym] = df[['symbol','date','bob','eob','open','high','low','close','volume']]
        except Exception:
            pass
        if verbose and (i+1) % 20 == 0:
            print('  进度: %d/%d (成功 %d)' % (i+1, total, len(data)))
    if verbose:
        print('[efinance] 完成: %d/%d' % (len(data), total))
    return data


# ====== V30.5 zhituapi (东方财富免费API, 支持分钟线) ======
# Token: BA4E703D-D6A3-445E-BC76-E5857CCF0441
# 接口: /hs/history/{code}.{SH|SZ}/{level}/{adjust}
# 周期: 5,15,30,60,d,w,m,y  复权: n(否),f(前),b(后)

def preload_from_zhituapi(start: str, end: str, symbols: list,
                          freq='d', adjust='f', token=None, verbose=True) -> dict:
    """从 zhituapi 加载数据。默认前复权日线。"""
    if token is None:
        token = 'BA4E703D-D6A3-445E-BC76-E5857CCF0441'
    data = {}
    total = len(symbols)
    start_fmt = start.replace('-', '')[:8]
    end_fmt = end.replace('-', '')[:8]
    if verbose:
        print('[zhituapi] 加载 %d 只 (%s/%s)...' % (total, freq, adjust))
    import requests as _req
    for i, sym in enumerate(symbols):
        try:
            code = sym.split('.')[-1]
            market = 'SH' if sym.startswith('SHSE') else 'SZ'
            full_code = f'{code}.{market}'
            url = f'https://api.zhituapi.com/hs/history/{full_code}/{freq}/{adjust}?token={token}&st={start_fmt}&et={end_fmt}'
            resp = _req.get(url, timeout=15)
            rows = resp.json()
            if isinstance(rows, list) and len(rows) > 0:
                import pandas as pd
                df = pd.DataFrame(rows)
                df = df.rename(columns={'t':'date','o':'open','c':'close','h':'high','l':'low','v':'volume'})
                df['symbol'] = sym
                df['bob'] = pd.to_datetime(df['date'])
                df['eob'] = df['bob']
                data[sym] = df[['symbol','date','bob','eob','open','high','low','close','volume']]
        except Exception:
            pass
        if verbose and (i+1) % 10 == 0:
            print('  进度: %d/%d (成功 %d)' % (i+1, total, len(data)))
    if verbose:
        print('[zhituapi] 完成: %d/%d' % (len(data), total))
    return data

# ====== V30.5 AKShare 数据源 (开源免费) ======
def preload_from_akshare(start: str, end: str, symbols: list, adjust='qfq', verbose=True) -> dict:
    """从 AKShare 加载数据（前复权日线，免费开源）。"""
    try:
        import akshare as ak
        import pandas as pd
    except ImportError:
        print('[akshare] 未安装, pip install akshare')
        return {}
    data = {}
    total = len(symbols)
    if verbose:
        print('[akshare] 加载 %d 只...' % total)
    for i, sym in enumerate(symbols):
        try:
            code = sym.split('.')[-1]
            df = ak.stock_zh_a_hist(symbol=code, period='daily', start_date=start.replace('-',''), end_date=end.replace('-',''), adjust=adjust)
            if df is not None and len(df) > 0:
                df = df.rename(columns={'日期':'date','开盘':'open','收盘':'close','最高':'high','最低':'low','成交量':'volume'})
                df['symbol'] = sym
                df['bob'] = pd.to_datetime(df['date']) + pd.Timedelta(hours=9, minutes=30)
                df['eob'] = df['bob'] + pd.Timedelta(hours=5, minutes=30)
                data[sym] = df[['symbol','date','bob','eob','open','high','low','close','volume']]
        except Exception:
            pass
        if verbose and (i+1) % 20 == 0:
            print('  进度: %d/%d (成功 %d)' % (i+1, total, len(data)))
    if verbose:
        print('[akshare] 完成: %d/%d' % (len(data), total))
    return data
