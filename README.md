# GM-Quant V24

**A股量化多策略融合系统** | 掘金GM SDK 3.0.183 | 6策略 | 情绪引擎 | AI辅助

离线回测: **+14.01% / -7.83%** | 526笔 | ~21s

---

## 快速开始
掘金终端打开项目 6ec60351 → 运行 main.py
启动提示: [AI辅助] 1=开启 2=关闭 (默认2)

## 策略
6策略融合: MR(均值回归) + MOM(动量) + VP(量价背离) + BK(突破) + DV(红利) + RT(反转确认)
49股池(12行业) | 5仓位 | 7源爬虫情绪 | AI辅助(可选)

## 文件 (19个)
config.py indicators.py stock_pool.py screener.py sentiment_engine.py ai_assistant.py trace.py
strategy_mr.py strategy_momentum.py strategy_vp.py strategy_breakout.py strategy_dividend.py strategy_reversal.py strategy_factory.py
sector_config.py executor.py fusion.py main.py offline_backtest.py

## AI辅助
联网搜索(DDG) + DeepSeek/OpenAI/智谱/通义千问/Moonshot
无API Key自动降级离线模式 | 终端【2】关闭

## 修复记录
05-25: 订阅超限→49+1=50 | trace日志恢复 | 96→49股池
05-24: get_cash()兼容 | 僵尸文件清理 | 7源爬虫
05-24: 仓位限制硬编码 | 注释清理V24

## License MIT
