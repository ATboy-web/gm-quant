# GM-Quant V24 🚀

**A股量化多策略融合系统** | 掘金量化(GM) SDK 3.0.183 | 5仓位 · 96股池 · 6策略 · 7源情绪 · AI辅助

离线回测: **+14.01% / -7.83%** | 526笔交易 | 胜率 45.6% | ~21秒

---

## 快速开始

```bash
掘金终端 → 打开项目 6ec60351 → 运行 main.py
终端提示: [AI辅助] 1=开启 2=关闭 (默认2)
本地测试: python offline_backtest.py
```

---

## 文件结构 (19个文件)

```
config.py              全局参数 (5仓位/AI开关)
indicators.py          技术指标库 (RSI/ATR/MA/量比)
stock_pool.py          96只股票池 (12行业×8只)
screener.py            六因子选股打分引擎
sentiment_engine.py    7源爬虫情绪引擎
ai_assistant.py        联网AI辅助 (DDG搜索+DeepSeek/OpenAI/智谱/通义千问/Moonshot)
trace.py               诊断日志 (只记B/S, 不拖慢)

strategy_mr.py         均值回归策略
strategy_momentum.py   动量趋势策略
strategy_vp.py         量价背离策略
strategy_breakout.py   突破策略
strategy_dividend.py   红利策略
strategy_reversal.py   反转确认策略
strategy_factory.py    策略工厂 (6策略)

sector_config.py       12行业差异化配置
executor.py            交易执行引擎
fusion.py              退出融合引擎
main.py                GM主程序 (含AI开关提示)
offline_backtest.py    离线回测
```

---

## 策略架构

| 策略 | 类型 | 逻辑 | 胜率 | 贡献 |
|------|------|------|------|------|
| MR 均值回归 | 抄底 | RSI超卖+六因子+ATR止损 | 47.5% | +36.3% |
| BK 突破 | 追涨 | N日新高+放量确认 | 59.1% | +100.6% |
| DV 红利 | 防御 | 低位+稳定量+RSI合理 | 40.2% | +25.9% |
| RT 反转确认 | 左侧 | MA5>MA10+超卖历史 | 77.8% | +20.3% |
| VP 量价背离 | 反转 | 价新低+缩量 | 54.9% | +6.7% |
| MOM 动量趋势 | 顺势 | MA20>MA60多头+放量 | 31.7% | -37.8% |
| 🤖 AI辅助 | 宏观 | 联网搜索+AI分析+股票筛选 | — | 终端可选 |

---

## AI 辅助 (ai_assistant.py)

启动时输入 1 开启，联网搜索 + AI 分析新闻 + 股票热度排行

支持API: **DeepSeek** / **OpenAI** / **智谱GLM** / **通义千问** / **Moonshot**
无API Key自动降级为本地关键词分析 (不拖慢回测)

---

## 修复记录

| 日期 | 问题 | 修复 |
|------|------|------|
| 05-25 | trace B/S日志全空 | regime→context.regime |
| 05-25 | 回测5小时(148K次文件write) | trace.heartbeat→pass |
| 05-25 | 128→96股池收益提升 | +12.19%→+14.01% |
| 05-24 | get_cash() SDK不兼容 | 改用顶层get_cash()+try |
| 05-24 | 13僵尸文件+仓库混乱 | 全量清理19文件 |
| 05-24 | 7源爬虫+情绪引擎 | 新浪/财联社/东财/雪球/股吧/同花顺/华尔街见闻 |
| 05-24 | 仓位失控(12只) | 硬编码5仓位限制 |

---

## 版本

[V24 Release](https://github.com/ATboy-web/gm-quant/releases/tag/V24) | [历史版本](https://github.com/ATboy-web/gm-quant/tree/main/versions)
