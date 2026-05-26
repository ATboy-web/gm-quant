# GM V30.3 — 六策略行业差异化量化交易系统

基于 [掘金量化（GoldMiner）](https://www.myquant.cn/)平台的 A 股量化交易策略，从 V1 迭代至 V30.3。

> **当前版本**：V30.3 · 六策略并行 + dict 工厂 + 行业参数注入  
> **离线回测**：+10.56%（2024-04-08 ~ 2025-05-30，初始资金 25,000 元）

---

## 策略概览

| 项目 | 说明 |
|------|------|
| 策略类型 | 六策略并行 + 投票融合（MR + MOM + VRC + BK + DV + RT） |
| 交易市场 | A 股主板（SHSE 600/601/603，SZSE 000/001/002） |
| 资金门槛 | 25,000 元（排除创业板/科创板） |
| 数据频率 | 日线 |
| 回测区间 | 2024-04-08 ~ 2025-05-30 |
| 初始资金 | 25,000 元 |
| SDK 版本 | GM 3.0.183（C SDK 3.8.15） |
| 回测 | **+10.56%**（最大回撤 -8.41%，157 笔交易） |

### 版本演进（关键里程碑）

| 版本 | 收益 | 回撤 | 交易 | 胜率 | 关键变化 |
|------|------|------|------|------|----------|
| V18.1 | +9.95% | -5.02% | 247 | 52.2% | 三策略 + MR投票融合 |
| V24 | +8.82% | -9.21% | 276 | 45.3% | dict工厂 + 行业参数注入 + 6策略 |
| V29 | +16.69% | -9.43% | 340 | 49.7% | VRC替换VP + 参数优化 |
| **V30.3** | **+10.56%** | **-8.41%** | 157 | 38.9% | 4 Bug修复 (见下文) |

> V30.3 区间更短(2024-04 ~ 2025-05, HS300 +8.6%)，V29 跑了更长的区间(至2026-05, HS300 +37%)

---

## V30.3 核心架构

```
                    ┌─────────────────────────────────┐
                    │         49 只股票候选池          │
                    │        (12 行业差异化配置)        │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │      StrategyFactory (dict)      │
                    │   每个行业注入差异化参数          │
                    └──┬───┬───┬───┬───┬───┬─────────┘
                       │   │   │   │   │   │
              MR  MOM  VRC  BK  DV  RT  — 六策略并行
                       │   │   │   │   │   │
                    ┌──▼───▼───▼───▼───▼───▼─────────┐
                    │   Executor 投票融合 + 配额制      │
                    │   V30.3: 6策略参加退出投票        │
                    └─────────────────────────────────┘
```

### 六策略矩阵

| 策略 | 代号 | 核心逻辑 | 收益贡献 | 交易数 |
|------|------|----------|----------|--------|
| 均值回归 | MR | RSI(14)超卖+六因子评分，ATR跟踪止盈 | +65.0% | 73 |
| 红利策略 | DV | 低波动+高股息+回调入场 | +41.1% | 22 |
| 反转确认 | RT | 双底/头肩底确认后入 | +22.5% | 17 |
| 成交量反转 | VRC | 下跌衰竭+放量阳线确认 | -5.2% | 19 |
| 动量趋势 | MOM | 多头排列+放量+金叉 | -25.8% | 6 |
| 突破策略 | BK | 放量突破N日新高 | -14.7% | 20 |

### 行业参数注入机制 (V24→V30.3 恢复)

每个行业的策略权重和参数（RSI买入、ATR止损倍数、时间止损天数等）通过 `sector_config.py` 配置，`strategy_factory.py` (dict架构) 自动注入到策略模块。12个行业独立配置，一行业一策略。

---

## V30.3 修复记录

V30 初始版本因三个复合Bug导致 -2.28% 亏损：

| Bug | 症状 | 修复 |
|-----|------|------|
| strategy_factory 从 dict→list 精简 | 丢失行业参数注入 | 恢复 V24 dict 架构 (315行) |
| Claw/ 多余 VP 策略 → 7策略双背离 | 信号互相稀释 | 移除 VP，回归6策略 |
| BK/DV/RT 退出信号被 executor 丢弃 | 非MR/MOM/VRC位置退出判断不全 | 扩展 fusion vote_exit 为6策略 |
| VRC 4% 止损过紧 | 杀死所有非VRC持仓 | VRC_STOP_LOSS → 6% |
| BK 在震荡市追高 | 虚假突破止损 | BK_VOL_SURGE 2.0, 门槛 0.65 |
| MOM 假动量信号 | 震荡市频繁触发 | MOM_SCORE_MIN 0.65 |

**修改的7个文件**：strategy_factory.py, sector_config.py, strategy_vrc.py, strategy_momentum.py, strategy_breakout.py, executor.py, fusion.py

---

## 项目结构

```
├── config.py              # V29.8 全局参数配置
├── sector_config.py       # 12行业差异化策略配置
├── strategy_factory.py    # V30.1 dict架构策略工厂（行业参数注入）
├── executor.py            # V30 交易执行引擎 + 策略配额
├── fusion.py              # V30 六策略退出投票
├── indicators.py          # 技术指标库 (RSI/ATR/MA/量比/形态识别)
├── stock_pool.py          # 49只精选股票池 (12行业)
├── screener.py            # 六因子选股打分引擎
├── strategy_mr.py         # 均值回归策略
├── strategy_momentum.py   # 动量趋势策略 (V29收紧)
├── strategy_vrc.py        # 成交量反转确认策略
├── strategy_breakout.py   # 突破策略 (V30.3收紧)
├── strategy_dividend.py   # 红利策略
├── strategy_reversal.py   # 反转确认策略
├── strategy_vp.py         # 量价背离(已弃用，VRC替换)
├── strategy_sr.py         # 支撑阻力策略(实验)
├── sentiment_engine.py    # 7源舆情爬虫+情绪分析
├── ai_assistant.py        # AI联网搜索+分析
├── advanced_factors.py    # 高级因子库
├── vibe_integration.py    # Vibe-Trading 集成
├── stats_validator.py     # Monte Carlo+Bootstrap验证
├── risk_manager.py        # 风控委员会
├── optimizer.py           # Grid Search优化器
├── live_monitor.py        # 实时监控窗口
├── visualizer.py          # tkinter回测可视化
├── gm_logger.py           # 统一日志模块
├── main.py                # GM终端主程序（仿真/回测）
├── offline_backtest.py    # 离线回测脚本
├── push_to_github.py      # GitHub REST API 推送
├── setup.py               # setup脚本
├── trace.py               # 诊断追踪
├── config.yaml            # 掘金终端配置
├── deploy/                # 部署同步脚本
├── versions/              # 历史版本归档
├── history/               # 废弃策略归档
├── vibe_source/           # Vibe-Trading 参考
└── logs/                  # 回测日志
```

---

## 使用方法

### 1. GM 终端回测

在掘金量化终端中打开 `main.py`，配置参数后点击"回测"。

### 2. 离线验证

```bash
python3 offline_backtest.py
```

不依赖掘金终端，直接用 `history()` API 拉取数据模拟回测。

### 3. 推送代码到 GitHub

```bash
python3 push_to_github.py
```

通过 GitHub REST API 推送文件。

---

## 技术依赖

| 依赖 | 版本 |
|------|------|
| GM Python SDK | 3.0.183 |
| GM C SDK | 3.8.15 |
| Python | ≥ 3.10 |

---

## License

Private — 个人量化研究用途。
