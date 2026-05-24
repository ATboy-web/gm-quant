# deploy/ — 实盘部署版本

## 当前版本: V24

## 回测 (GM终端)
+41.79% / -10.50% | 253买/237卖 | 70品种 | ~54分钟

## 配置
- 128只股票 / 12行业
- 5仓位 / 18%仓位比例
- 6策略：MR + MOM + VP + BK + DV + RT
- 7源情绪引擎
- 冷却期：1天
- 无行业排他
- 投票门槛：≥2票(100%) ≥1票(70%) ≥0.5票(40%)

## 文件清单 (18个)
```
config.py · indicators.py · stock_pool.py · screener.py
sentiment_engine.py · trace.py
strategy_mr.py · strategy_momentum.py · strategy_vp.py
strategy_breakout.py · strategy_dividend.py · strategy_reversal.py
strategy_factory.py · sector_config.py · executor.py · fusion.py
main.py · offline_backtest.py
```

## 使用
掘金终端导入 `main.py` 直接运行

## 注意事项
- GM SDK 3.0.183
- `trace.py` 自动记录每笔交易到 `data/trace/`
- `sentiment_engine.py` 爬虫数据缓存 `data/news/`
- 如需调整行业参数，用 `safe_config.py`（workspace中）
