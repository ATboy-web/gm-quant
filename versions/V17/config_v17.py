"""
config.py - V17 策略参数配置

V17 vs V16 核心差异:
  1. RSI_PERIOD: 14 → 6 (更敏感)
  2. MA60_EXIT_ENABLED: False → True (新增MA60趋势出场)
  3. RSI_BUY: 30 → 32 (更早入场)
  4. TIME_STOP_DAYS: 15 → 20 (延长持仓)
  5. ENTRY_THRESHOLD: 0.35 → 0.40 (更严格筛选)
"""

# 与 V16 相同的基础配置
GM_TOKEN = '5f7a56d57f3c71ee049bc7b291c8d7e7f0d5d353'

DATA_COUNT   = 80       # V17: 80（V18 改为 60）
MIN_DATA_BARS = 40

PRICE_MIN       = 2.0
PRICE_MAX       = 200.0
PRICE_CHG_LIMIT = 0.095

# 六因子评分权重 — 与 V16 相同
SCORING_WEIGHTS = {
    'rsi_oversold':   0.35,
    'trend_align':    0.20,
    'volume_surge':   0.15,
    'drawdown':       0.15,
    'reversal_form':  0.10,    # V17: 0.10（V18 改为 0.08）
    'sector_momentum': 0.10,   # V17: 0.10（V18 改为 0.07）
}

# ===== V17 关键参数差异 =====
RSI_PERIOD  = 6       # V17 改动: 14 → 6（更敏感，假信号增多）
RSI_BUY     = 32      # V17 改动: 30 → 32（更早入场）
RSI_EXIT    = 82      # V17: 82（V18 改为 80）

ATR_PERIOD      = 14
ATR_STOP_MULT   = 1.5
ATR_TRAIL_MULT  = 2.0   # V17: 2.0（V18 改为 2.5，让盈利更充分）

MA_SHORT = 20
MA_LONG  = 60

# ===== V17 新增: MA60 趋势出场 =====
MA60_EXIT_ENABLED    = True    # V17 核心改动！V18 改回 False
MA60_EXIT_GRACE_DAYS = 3
MA60_ENTRY_BUFFER    = 0.95

VOL_PERIOD    = 20
VOL_SURGE_MIN = 1.2

MAX_POSITIONS  = 4
POSITION_PCT   = 0.30

TIME_STOP_DAYS = 20      # V17 改动: 15 → 20（V18 改回 15）

ENTRY_THRESHOLD = 0.40  # V17 改动: 0.35 → 0.40

# 市场状态参数 — 与 V16 相同
MARKET_INDEX = 'SHSE.000001'
REGIME_MA_PERIOD      = 60
REGIME_BEAR_THRESHOLD = -0.08

REGIME_PARAMS = {
    'bull': {
        'max_positions': 4,
        'rsi_buy': 34,       # V17: 34（V18 改为 35）
        'entry_threshold': 0.30,
        'atr_stop_mult': 1.8,
    },
    'range': {
        'max_positions': 4,
        'rsi_buy': 30,
        'entry_threshold': 0.35,
        'atr_stop_mult': 1.5,
    },
    'bear': {
        'max_positions': 2,   # V17: 2（V18 改为 3）
        'rsi_buy': 28,
        'entry_threshold': 0.55,  # V17: 0.55（V18 改为 0.45）
        'atr_stop_mult': 1.2,
    },
}

# V17 没有 V18 的多策略融合参数
# FUSION_MODE = 'voting'  # V18 新增
# VOTE_THRESHOLD = 2       # V18 新增
