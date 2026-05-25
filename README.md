# gm-quant — 六策略行业差异化量化交易框架

[![Version](https://img.shields.io/badge/version-V29.4-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![GM SDK](https://img.shields.io/badge/GM%20SDK-3.0.183-green)](https://www.myquant.cn/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

基于[掘金量化](https://www.myquant.cn/) SDK 的 A 股多策略融合交易系统。覆盖 **6 个策略**、**12 个行业**、**96 只股票**，通过行业差异化配置和策略配额制实现信号多元化。

---

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/ATboy-web/gm-quant.git
cd gm-quant

# 2. 安装掘金 SDK
pip install gm -U

# 3. 配置 Token
# 编辑 config.py，填入你的 GM_TOKEN

# 4. 运行离线回测
python offline_backtest.py
```

### 环境要求

- Python 3.8+ (推荐 3.13)
- 掘金量化 SDK >= 3.0.183
- 掘金终端后台运行 (回测模式)
- pandas, numpy

---

## 策略架构

```
                     ┌─────────────────────────┐
                     │     Strategy Factory     │
                     │   (行业差异化策略创建)      │
                     └───────────┬─────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
    ┌────▼────┐  ┌────────┐  ┌──▼───┐  ┌──────┐  ┌────▼───┐  ┌──────┐
    │   MR    │  │  MOM   │  │  VP  │  │  BK  │  │   DV   │  │  RT  │
    │均值回归  │  │动量趋势  │  │量价背离│  │ 突破  │  │ 红利   │  │反转确认│
    └────┬────┘  └───┬────┘  └──┬───┘  └──┬───┘  └───┬────┘  └───┬──┘
         │           │          │         │          │          │
         └───────────┴──────────┴─────────┴──────────┴──────────┘
                                 │
                     ┌───────────▼─────────────┐
                     │  Six-Strategy Fusion    │
                     │  (加权投票 + 行业权重)     │
                     └───────────┬─────────────┘
                                 │
                     ┌───────────▼─────────────┐
                     │    Trade Executor       │
                     │  (入场/出场/风险控制)      │
                     └─────────────────────────┘
```

| 策略 | 类型 | 核心逻辑 | RSI 区间 | 适用行业 |
|------|------|----------|----------|----------|
| **MR** 均值回归 | 左侧抄底 | 六因子超卖评分 + RSI < 33 | 全行业 | 12/12 |
| **VP** 量价背离 | 量价分析 | 价格新低 + 成交量萎缩 + 背离确认 | 底背离 | 12/12 |
| **BK** 突破 | 趋势跟随 | 价格突破 + 量能确认 + 均线多头 | 高波动 | 5/12 |
| **DV** 红利 | 防御配置 | 低位 AND 条件 + 价格 < MA60 | 低波动 | 6/12 |
| **RT** 反转确认 | 右侧确认 | 下跌后放量反弹 + 规则底确认 | 中波动 | 3/12 |
| **MOM** 动量 | 趋势加速 | 4 道硬门 + 金叉确认 (严厉限制) | 趋势 | 4/12 |

---

## V29.4 回测结果

**回测区间**: 2024-01-01 ~ 2026-05-22 | **初始资金**: ¥25,000 | **交易日**: 575

| 指标 | 数值 |
|------|------|
| 总收益率 | **+8.82%** |
| 最大回撤 | -9.21% |
| 胜率 | 45.3% |
| 总交易 | 553 笔 (276 卖出) |
| 平均盈亏 | +0.56% |

### 策略分项

| 策略 | 交易笔数 | 胜率 | 累计盈亏 | 状态 |
|------|----------|------|----------|------|
| MR 均值回归 | 122 | 49.2% | **+84.2%** | 核心盈利引擎 |
| BK 突破 | 67 | 40.3% | +51.6% | 稳定贡献 |
| RT 反转确认 | 12 | 50.0% | +28.6% | 低频高质量 |
| DV 红利 | 22 | 40.9% | +14.8% | 防御有效 |
| MOM 动量 | 1 | 100% | +3.1% | 严格限制中 |
| VP 量价背离 | 52 | 42.3% | **-28.2%** | 待修复 |

### 行业分项 (Top 5)

| 行业 | 交易 | 胜率 | 累计 |
|------|------|------|------|
| 科技 | 26 | 53.8% | +49.9% |
| 煤炭 | 43 | 48.8% | +36.4% |
| 金融 | 14 | 71.4% | +36.1% |
| 有色 | 33 | 42.4% | +31.7% |
| 消费 | 11 | 45.5% | +27.5% |

---

## 项目结构

```
gm-quant/
├── config.py                  # 全局参数 + 回测/仿真模式 + AI 配置
├── indicators.py              # 技术指标库 (RSI/ATR/MA/量比/形态识别)
├── stock_pool.py              # 96 只股票候选池 + 股票名称映射
├── screener.py                # 六因子选股打分引擎
├── sentiment_engine.py        # 7 源舆情爬虫 + 情绪分析
├── ai_assistant.py            # AI 联网搜索 + 股票排名
│
├── strategy_mr.py             # 均值回归策略 (六因子评分)
├── strategy_momentum.py       # 动量趋势策略 (4 道硬门)
├── strategy_vp.py             # 量价背离策略 (量价关系)
├── strategy_breakout.py       # 突破策略 (趋势跟随)
├── strategy_dividend.py       # 红利策略 (防御配置)
├── strategy_reversal.py       # 反转确认策略 (右侧确认)
├── strategy_factory.py        # 策略工厂 (行业差异化创建)
│
├── sector_config.py           # 12 行业差异化策略配置
├── fusion.py                  # 六策略投票融合引擎
├── executor.py                # 交易执行引擎 + 策略配额制
│
├── main.py                    # 策略主程序 (回测/仿真自适应)
├── offline_backtest.py        # 离线回测脚本
├── visualizer.py              # 回测可视化 GUI (tkinter+matplotlib)
├── gm_logger.py               # 统一日志模块
├── trace.py                   # 心跳 + 状态跟踪
├── push_to_github.py          # GitHub API 推送脚本
│
├── CHANGELOG.md               # 版本历史
├── README.md                  # 项目说明
├── LICENSE                    # MIT
├── SECURITY.md                # 安全策略
├── CONTRIBUTING.md            # 贡献指南
├── CODE_OF_CONDUCT.md         # 行为准则
│
├── versions/                  # 历史版本归档
├── deploy/                    # 部署脚本
├── .github/                   # Actions + Projects
├── logs/                      # 回测日志
└── .workbuddy/                # WorkBuddy 数据
```

---

## 历史版本对比

| 版本 | 总收益 | 回撤 | 胜率 | 卖出 | 关键改进 |
|------|--------|------|------|------|----------|
| V29.4 | +8.82% | -9.21% | 45.3% | 276 | 策略配额制 + 牛市适配 |
| V29 | +16.69% | -9.43% | 49.7% | 340 | MOM/DV 重构 + 权重重构 |
| V28 | +17.07% | -8.26% | 46.3% | 471 | V26/V27 参数中点 |
| V26 | +19.24% | -7.8% | ~47% | 448 | 仓位优化 + 入场收紧 |

完整版本历史见 [CHANGELOG.md](CHANGELOG.md)

---

## 已知问题

- [ ] **VP 策略持续亏损** (-28.2%) — 三个版本未改善，需策略逻辑层面重写
- [ ] **MR 收益未恢复到 V29 水平** — entry_threshold 可进一步放宽
- [ ] **MOM 过度限制** — 1 笔交易过于保守

---

## 贡献

欢迎提 Issue 或 PR！详见 [CONTRIBUTING.md](CONTRIBUTING.md)

## 许可

MIT License — 详见 [LICENSE](LICENSE)

---

*Built with [掘金量化 SDK](https://www.myquant.cn/) | Python 3.13 | 96 stocks × 6 strategies × 12 sectors*
