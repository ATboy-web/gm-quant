# Changelog

## V30.3 (2026-05-26)

### 修复
- 恢复 strategy_factory.py dict架构(315行), 行业参数注入机制
- 移除 Claw 多余 VP 策略(7→6策略)
- VRC_STOP_LOSS 4%→6% 减少跨策略误杀
- BK_VOL_SURGE 1.5→2.0, BK门槛 0.60→0.65
- MOM_SCORE_MIN 0.55→0.65
- fusion.py 扩展 vote_exit 为6策略 (BK/DV/RT退出信号不再丢弃)
- executor.py 传递全部6策略退出信号到fusion
- BACKTEST_END 修正为 2025-05-30

### 回测
- 总收益: +10.56%, 回撤 -8.41%, 157笔, 年化 +7.75%
- MR +65.0%, DV +41.1%, RT +22.5%

## V29.8 (2026-05-25)

### 新增
- VRC成交量反转确认策略 (替换VP)
- 行业权重重构
- Vibe-Trading 高级指标集成
- advanced_factors.py, live_monitor.py, vibe_integration.py

## V29 (2026-05-25)

### 优化
- MOM/DV策略全面重构
- 移动止盈机制
- stats_validator.py 统计验证

### 回测
- +16.69%, -9.43%回撤, 340笔

## V24 (2026-05-24)

### 新增
- dict架构 strategy_factory (行业参数注入)
- 6策略体系: MR/MOM/VP/BK/DV/RT
- sector_config.py 12行业差异化配置

### 回测
- +8.82%, -9.21%回撤, 276笔

## V18.1 (2026-05-22)

### 新增
- 三策略并行: MR + MOM + VP
- 投票融合引擎
- KNN历史匹配引擎

### 回测
- +9.95%, -5.02%回撤, 247笔
