"""
logger.py - 统一日志模块

双输出: 控制台 (INFO+) + 文件 (DEBUG+, ./logs/strategy_YYYYMMDD.log)
用法:
    from logger import log, setup_logger
    setup_logger()          # 模块级初始化
    log.info('...')         # 等同于 print + 写文件
"""

import logging
import os
import sys
from datetime import datetime

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
_logger = None
_initialized = False


def _ensure_log_dir():
    """确保日志目录存在"""
    if not os.path.exists(_LOG_DIR):
        os.makedirs(_LOG_DIR)


def setup_logger(name='strategy'):
    """
    初始化日志系统 (幂等).
    name: 日志名前缀, 生成 ./logs/{name}_YYYYMMDD.log
    """
    global _logger, _initialized
    if _initialized:
        return _logger

    _ensure_log_dir()
    _logger = logging.getLogger('gm_strategy')
    _logger.setLevel(logging.DEBUG)
    _logger.handlers.clear()

    fmt = logging.Formatter(
        '%(asctime)s | %(message)s',
        datefmt='%H:%M:%S'
    )

    # 控制台 handler (只输出 INFO+)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    _logger.addHandler(ch)

    # 文件 handler (输出所有 DEBUG+)
    today = datetime.now().strftime('%Y%m%d')
    log_path = os.path.join(_LOG_DIR, f'{name}_{today}.log')
    fh = logging.FileHandler(log_path, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    _logger.addHandler(fh)

    _initialized = True
    _logger.info('[日志] 启动 | 文件: %s', log_path)
    return _logger


def get_logger():
    """获取 logger 实例 (如未初始化则自动初始化)"""
    global _logger
    if _logger is None:
        setup_logger()
    return _logger


# 模块级快捷访问
log = get_logger()
