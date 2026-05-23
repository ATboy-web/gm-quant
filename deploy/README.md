# V20 实盘部署版

## 快速开始

1. 打开掘金终端，进入策略研究页
2. 将本目录下所有 .py 文件复制到策略项目目录
3. 修改 config.py 中的 ACCOUNT_ID（实盘账户）
4. 在掘金终端运行 main.py

## 回测验证
- 离线回测: `python offline_backtest.py`
- 结果: +16.05% / -1.47% / 161笔 / 57.8%胜率

## 文件清单 (18个.py)
config.py, indicators.py, stock_pool.py, screener.py,
strategy_base.py, strategy_mr.py, strategy_momentum.py,
strategy_vp.py, strategy_breakout.py, strategy_dividend.py,
strategy_reversal.py, strategy_factory.py, sector_config.py,
executor.py, fusion.py, knn_matcher.py, main.py, offline_backtest.py

## 关键参数
- 初始资金: 25000
- 最大持仓: 4
- 冷却期: 3天
- 止损: 行业差异化(1.5%-12%)
