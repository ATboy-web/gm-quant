# CHANGELOG

All notable changes to the GM-Quant project will be documented in this file.

## [V29.4] - 2026-05-25

### Added
- **Strategy diversification**: `executor._diversify_candidates()` with per-strategy cap of 2 positions, preventing single strategy monopoly
- **Stock name mapping**: `stock_pool.get_symbol_name()` with full 96-stock Chinese name dictionary
- **Responsive visualizer**: Auto-detecting screen size, max 1600x900 with 90% width
- **Stock names in visualizer**: Trade table, signal log, CSV export all show Chinese names instead of codes

### Fixed
- **Critical: Missing strategies** — `sector_config.py` not synced to GM terminal, causing MR/BK/DV/RT to be disabled (0 trades). Root cause: GM terminal (`.goldminer3`) and Workspace (`Claw`) are independent filesystems.
- **UnicodeError**: `\u23ed` emoji in offline_backtest.py replaced with `[Skip]` for GBK compatibility
- **Non-interactive backtest**: `prompt_visual()` now detects non-TTY stdin, bypasses gracefully

### Changed
- `RSI_BUY`: 29 → 33 (adapting to 2024-2026 bull market)
- `ENTRY_THRESHOLD`: 0.42 → 0.36
- Executor confidence formula: Reverted to V29 `avg(confidences)` from V29.2 `max + consensus bonus`

### Performance
| Metric | V29 | V29.4 |
|--------|-----|-------|
| Total Return | +16.69% | +8.82% |
| Max Drawdown | -9.43% | -9.21% |
| Win Rate | 49.7% | 45.3% |
| Total Sells | 340 | 276 |

### Strategy Breakdown
| Strategy | Trades | Win Rate | PnL |
|----------|--------|----------|-----|
| MR | 122 | 49.2% | +84.2% |
| BK | 67 | 40.3% | +51.6% |
| RT | 12 | 50.0% | +28.6% |
| DV | 22 | 40.9% | +14.8% |
| MOM | 1 | 100% | +3.1% |
| VP | 52 | 42.3% | -28.2% |

---

## [V29] - 2026-05-25

### Added
- **MOM strategy overhaul**: 4 hard gates (MA spread >1.5%, volume >1.3, RSI 45-70, price >MA20), entry score 0.55
- **DV strategy overhaul**: AND low condition (60d<0% AND 20d<-4%), price <MA60, RSI 33-52, entry score 0.72
- **Trailing stop**: MOM/DV trigger at +5% profit, stop line tightens from 15% to 10%
- **Sector weight restructure**: MOM disabled in 8 non-trend sectors, reduced in 4; DV reduced ~30% globally; BK boosted

### Fixed
- **Bug**: `record_buy` missing in offline backtest → `MAX_TRADES_PER_SYMBOL` ineffective
- **Bug**: Circuit breaker state not reset on profit → permanent freeze after streak

### Performance
| Metric | V28 | V29 |
|--------|-----|-----|
| Total Return | +17.07% | +16.69% |
| Win Rate | 46.3% | **49.7%** |
| Sells | 471 | **340** |

### Strategy Breakdown
| Strategy | Trades | Win Rate | PnL |
|----------|--------|----------|-----|
| MR | 196 | 47.4% | +105.4% |
| BK | 64 | 53.1% | +95.8% |
| RT | 17 | 52.9% | +21.2% |
| MOM | 3 | 66.7% | +0.1% |
| DV | 7 | 42.9% | -1.4% |
| VP | 53 | 45.3% | -27.7% |

---

## [V28] - 2026-05-25

### Changed
- Parameters set to midpoint between V26 (aggressive) and V27 (conservative):
  - `ENTRY_THRESHOLD`: 0.42, `RSI_BUY`: 29, `ATR_STOP_MULT`: 1.4
  - `POSITION_PCT`: 0.14, `MAX_TRADES`: 10
  - Cooldown: 2 days, circuit breaker: 3 consecutive losses / 5 days

### Fixed
- **Bug**: `today` variable out of scope in `_do_sell()` → use `context._today`
- **Bug**: `record_buy` not called in `_do_buys()` → MAX_TRADES ineffective offline

### Performance
| Metric | V27 | V28 |
|--------|-----|-----|
| Total Return | +3.09% | **+17.07%** |
| Win Rate | 44.1% | **46.3%** |

### Strategy Ranking
| Strategy | Trades | Win Rate | PnL |
|----------|--------|----------|-----|
| BK | 42 | 59.5% | +162.3% |
| MR | 150 | 48.0% | +58.4% |
| RT | 12 | 58.3% | +41.4% |
| VP | 49 | 63.3% | +36.5% |
| DV | 153 | 39.9% | -32.2% |
| MOM | 65 | 33.8% | -65.9% |

---

## [V27] - 2026-05-25

### Added
- **Visualizer GUI**: tkinter + matplotlib backtest visualization with 8 cards, equity curve, strategy breakdown, trade records, CSV export
- **Performance optimizations**: Lazy data_cache construction, cached sector momentum, direct array indexing

### Changed
- Tightened all entry/exit parameters to reduce trade frequency:
  - `ENTRY_THRESHOLD`: 0.40→0.45, `RSI_BUY`: 30→28
  - `ATR_STOP_MULT`: 1.5→1.3, `STOP_LOSS_CAP`: 0.08→0.06
  - `POSITION_PCT`: 0.15→0.13

### Fixed
- **9 bugs** including:
  - Exit voting missing BK/DV/RT signals (critical)
  - Circuit breaker state persistence bug (critical)
  - BOM character in offline_backtest.py

### Performance
- Total Return: +3.09% (over-tightened, improved in V28)

---

## [V26] - 2026-05-25

### Added
- Position utilization optimization (47%→70%)
- Per-symbol trade count tracking (`MAX_TRADES_PER_SYMBOL`)
- Strategy RT toggle in config

### Changed
- Entry thresholds tightened globally +0.05
- Sector entry thresholds raised across all 12 sectors
- VP entry: 0.50→0.55, BK: 0.55→0.60, RT: 0.60→0.75

### Performance
- Total Return: +19.24%, 448 sells, 46.5% win rate

---

## [V25] - 2026-05-25

### Added
- File logging system (`gm_logger.py`) with dual output (console + file)
- `.gitignore` configuration

### Fixed
- Simulated account `get_cash()`/`get_position()` 1020 error
- `logger.py` → `gm_logger.py` rename (GM SDK conflict)

---

## [V24] - 2026-05-24

### Added
- **Six-strategy fusion framework** (MR + MOM + VP + BK + DV + RT)
- **Sentiment engine** (`sentiment_engine.py`): 7-source web scraping + sentiment analysis
- **AI assistant** (`ai_assistant.py`): DeepSeek API integration with web search
- **96-stock universe** across 12 sectors (8 stocks each)
- **12-sector differentiated config** with per-sector strategy weights

---

## V01-V20
Earlier versions archived in `versions/`. See individual version directories for details.
