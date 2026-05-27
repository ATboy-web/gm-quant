# GM V30.5 — 六策略行业差异化量化交易系统

基于 [掘金量化（GoldMiner）](https://www.myquant.cn/)平台的 A 股量化交易策略。借鉴 7 个顶级量化仓库，独立离线回测零 GM 依赖。

> **当前版本**：V30.5 · UMP裁判系统 + 分层风控 + 真实费用  
> **独立回测**：+9.30%（2025-01-01 ~ 2026-05-26，¥25,000 初始资金）

---

## 快速开始

```bash
# 独立离线回测 (零 GM SDK 依赖)
python standalone_backtest.py

# 掘金终端回测/仿真
# 在掘金终端 IDE 中打开 main.py
```

---

## 回测结果

| 区间 | 收益 | 回撤 | 胜率 | 盈利因子 |
|------|------|------|------|----------|
| 2024-2025 | -4.53% | -13.4% | 34.8% | 0.73 |
| **2025-2026** | **+9.30%** | **-19.2%** | **50.5%** | **1.87** |

### 2025-2026 策略分项

| 策略 | 交易 | 胜率 | 累计 |
|------|------|------|------|
| MR 均值回归 | 62 | 43.5% | +19.1% |
| VRC 成交量反转 | 14 | 71.4% | +71.7% |
| BK 突破 | 15 | 66.7% | +61.5% |
| RT 反转确认 | 4 | 25.0% | +0.7% |

---

## 核心架构

```
本地SQLite数据 (C:/lainghua)
        ↓
standalone_backtest.py (独立回测引擎)
  ├── local_data_loader.py   数据加载
  ├── trade_utils.py          交易日历+费用+滑点+通知
  ├── risk_manager.py         分层风控 (订单/持仓/账户)
  ├── fusion.py (UMP)         6边裁+主裁决策
  ├── executor.py             交易执行
  ├── indicators.py           技术指标+Hurst+ADX+因子处理
  ├── screener.py             六因子选股
  ├── sector_config.py        12行业差异化配置
  ├── stock_pool.py           股票池管理
  └── strategy_factory.py     dict架构策略工厂
       ├── strategy_mr.py       均值回归
       ├── strategy_momentum.py 动量趋势
       ├── strategy_vrc.py      成交量反转
       ├── strategy_breakout.py 突破
       ├── strategy_dividend.py 红利
       └── strategy_reversal.py 反转确认
```

---

## 项目结构 (26 个 py 文件)

```
config.py              全局参数
indicators.py           技术指标 (Hurst/ADX/RSRS/K线/因子处理)
stock_pool.py           股票池管理 + 名称映射
sector_config.py        12行业差异化配置
screener.py             六因子选股打分

strategy_factory.py     策略工厂 (dict架构)
strategy_mr.py          均值回归策略
strategy_momentum.py    动量趋势策略
strategy_vrc.py         成交量反转确认
strategy_breakout.py    突破策略
strategy_dividend.py    红利策略
strategy_reversal.py    反转确认策略

executor.py             交易执行引擎
fusion.py               UMP裁判系统 (6边裁+主裁)
trade_utils.py          交易日历 + 费用 + 滑点 + 通知
risk_manager.py         分层风控 + 组合风险管理

standalone_backtest.py  独立离线回测 (零GM依赖)
local_data_loader.py    SQLite本地数据 + yfinance备用
offline_backtest.py     GM终端回测 (历史保留)

visualizer.py           tkinter+matplotlib可视化
main.py                 掘金终端主程序
trace.py                日志+诊断追踪
push_to_github.py       GitHub REST API推送
sentiment_engine.py     舆情爬虫+情绪分析
stats_validator.py      统计验证 (Monte Carlo)
vibe_integration.py     Vibe高级指标
```

---

## 借鉴来源

| 仓库 | ⭐ | 借鉴 |
|------|-----|------|
| vnpy | 40.9k | 分层风控引擎, 策略模板 |
| abu | 17.3k | UMP裁判系统, 仓位管理, 滑点 |
| Qbot | 17.5k | RSRS指标, 多渠通知 |
| QUANTAXIS | 10.6k | Hurst/ADX/CHO 高级指标 |
| Vibe-Trading | 8.7k | 本地数据加载, K线形态 |
| ai_quant_trade | 5.7k | 交易日历, 真实费用 |
| panda_factor | 2.7k | 因子标准化/中性化/IC分析 |

---

## License

Private — 个人量化研究用途。
