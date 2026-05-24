# 贡献指南

## 提交 Issue

- Bug: 附上 CSV 回测数据 + trace 日志
- 建议: 说清楚期望收益/回撤目标

## 提交 PR

1. Fork + clone
2. `python offline_backtest.py` 确保基线通过
3. 修改代码
4. 再次回测确认收益不受影响
5. 提交 PR，附回测对比结果

## 分支

- `main` — 稳定版
- `dev/*` — 实验性修改

## 代码风格

- Python 3.11+
- 注释用中文
- 所有 #noqa 标注必须有原因
- 新增策略需同时更新 `sector_config.py` 和 `strategy_factory.py`
