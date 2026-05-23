# V18.1 三策略融合 + MR主导 (2026-05)

## 回测结果
- 总收益: +9.95%, 最大回撤: -5.02%
- 247笔, 胜率52.2%

## 架构
- 三策略并行: MR(均值回归) + MOM(动量趋势) + VP(量价背离)
- 投票融合: >=2/3策略同意才执行
- MR主导: 权重x2
- 出场: 归属策略优先 + 止损安全阀 + 交叉验证

## 策略详解
- MR: RSI超卖+六因子打分, ATR跟踪止盈+止损+RSI过热+时间止损 (176笔,51.1%,+68.2%)
- MOM: MA20>MA60多头排列+放量突破追涨, 跌破MA20/死叉出场 (43笔,51.2%,+92.0%)
- VP: 价新低+缩量=抛压耗尽, 放量反弹/放量滞涨出场 (28笔,60.7%,+11.2%)

## 文件
config.py, indicators.py, stock_pool.py, screener.py, strategy_mr.py, strategy_momentum.py, strategy_vp.py, fusion.py, knn_matcher.py, main.py, offline_backtest.py
