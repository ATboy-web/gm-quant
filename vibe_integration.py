"""
vibe_integration.py - V29.8 Vibe-Trading-inspired modules
P0: Factor IC/IR Analysis
P1: Risk Committee (multi-angle exit review)
P2: Risk Parity Portfolio Optimization
"""

import numpy as np
from scipy import stats
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')


# =============================================================================
# P0: Factor IC/IR Analysis
# =============================================================================

class FactorICAnalyzer:
    """
    Factor Information Coefficient (IC) and Information Ratio (IR) analysis.
    Evaluates which strategy signals actually predict future returns.
    """

    def __init__(self):
        self.history = defaultdict(list)  # {strategy_name: [(ic, date), ...]}

    def compute_ic(self, signals: list, forward_returns: list) -> float:
        """
        Spearman rank IC between strategy signals and forward returns.
        Args:
            signals: [(symbol, score), ...]
            forward_returns: [(symbol, return_5d), ...]
        Returns: IC value [-1, 1]
        """
        if len(signals) < 5 or len(forward_returns) < 5:
            return 0.0
        scores = [s[1] for s in signals]
        rets = [r[1] for r in forward_returns]
        if np.std(scores) < 0.001 or np.std(rets) < 0.001:
            return 0.0
        ic, _ = stats.spearmanr(scores, rets)
        return float(np.clip(ic, -1, 1)) if not np.isnan(ic) else 0.0

    def record(self, strategy_name: str, ic: float, date_str: str = ""):
        self.history[strategy_name].append((ic, date_str))

    def get_ir(self, strategy_name: str) -> float:
        """Information Ratio = mean(IC) / std(IC)"""
        ics = [h[0] for h in self.history[strategy_name]]
        if len(ics) < 3:
            return 0.0
        mean_ic = np.mean(ics)
        std_ic = np.std(ics)
        if std_ic < 0.001:
            return mean_ic * 10 if mean_ic > 0 else mean_ic * 5
        return float(mean_ic / std_ic)

    def get_strategy_quality(self, strategy_name: str) -> dict:
        ics = [h[0] for h in self.history.get(strategy_name, [])]
        if len(ics) < 5:
            return {"ic_mean": 0.0, "ir": 0.0, "ic_positive_ratio": 0.5, "grade": "C"}
        ic_mean = np.mean(ics)
        ir = self.get_ir(strategy_name)
        pos_ratio = sum(1 for ic in ics if ic > 0) / len(ics)

        # Grade: A (strong), B (good), C (neutral), D (weak), F (harmful)
        if ir > 0.8 and ic_mean > 0.05:
            grade = "A"
        elif ir > 0.4 and ic_mean > 0.02:
            grade = "B"
        elif ir > 0 and ic_mean > 0:
            grade = "C"
        elif ir > -0.3:
            grade = "D"
        else:
            grade = "F"

        return {"ic_mean": round(float(ic_mean), 4), "ir": round(float(ir), 2),
                "ic_positive_ratio": round(float(pos_ratio), 3), "grade": grade,
                "samples": len(ics)}

    def adjust_weight(self, base_weight: float, strategy_name: str) -> float:
        """Adjust strategy weight based on IC quality"""
        q = self.get_strategy_quality(strategy_name)
        grade_mult = {"A": 1.3, "B": 1.1, "C": 1.0, "D": 0.6, "F": 0.2}
        return base_weight * grade_mult.get(q["grade"], 1.0)

    def summary(self) -> str:
        lines = ["=== Factor IC/IR Report ==="]
        lines.append(f"{'Strategy':<8} {'IC':<8} {'IR':<8} {'Pos%':<8} {'N':<5} {'Grade':<6}")
        lines.append("-" * 48)
        for name in sorted(self.history.keys()):
            q = self.get_strategy_quality(name)
            lines.append(f"{name:<8} {q['ic_mean']:<8.4f} {q['ir']:<8.2f} "
                         f"{q['ic_positive_ratio']:<8.3f} {q['samples']:<5} {q['grade']:<6}")
        return '\n'.join(lines)


# =============================================================================
# P1: Risk Committee - Multi-angle Exit Review
# =============================================================================

class RiskCommittee:
    """
    Multi-agent risk review.
    Only VETO a sell when ALL agents agree to hold.
    """

    def __init__(self):
        self.stats = {"vetoed": 0, "approved": 0, "total": 0}

    def review(self, df, pos_info: dict, regime: str = 'range') -> dict:
        data = self._extract_data(df)
        votes = {
            "tech": self._technical_vote(data, pos_info),
            "vol": self._volume_vote(data, pos_info),
            "regime": self._regime_vote(data, regime, pos_info),
        }
        sell_votes = sum(1 for v in votes.values() if v)
        self.stats["total"] += 1

        # Only veto when ALL 3 agents say HOLD (0 sell votes)
        # Any 1 agent saying SELL is enough to proceed
        if sell_votes >= 1:
            self.stats["approved"] += 1
            return {"action": "SELL", "votes": votes,
                    "reason": f"Committee {sell_votes}/3 approve"}
        else:
            self.stats["vetoed"] += 1
            return {"action": "HOLD", "reason": "Vetoed: all agents hold", "votes": votes}

    @staticmethod
    def _extract_data(df):
        if df is None or len(df) < 20:
            return None
        return {
            "close": df["close"].values[-20:],
            "volume": df["volume"].values[-20:],
            "high": df["high"].values[-20:],
            "low": df["low"].values[-20:],
        }

    def _technical_vote(self, data, pos_info) -> bool:
        """Vote SELL=True if technicals confirm breakdown"""
        if data is None:
            return True  # No data = sell (safety)
        closes = data["close"]
        if len(closes) < 5:
            return True

        # Check: price accelerating downward (3-day slope steeper than 5-day)
        ret_3d = (closes[-1] - closes[-4]) / max(closes[-4], 0.01)
        ret_5d = (closes[-1] - closes[-6]) / max(closes[-6], 0.01)
        accelerating_down = (ret_3d < ret_5d * 1.2) and ret_3d < -0.02

        # Check: below recent low
        recent_low = np.min(data["low"][-10:-1])
        breaking_low = closes[-1] < recent_low * 0.97
        breaking_support = closes[-1] < np.min(closes[-5:])

        sell = accelerating_down or breaking_low or breaking_support
        return sell

    def _volume_vote(self, data, pos_info) -> bool:
        """Vote SELL=True if volume confirms distribution"""
        if data is None:
            return True
        volumes = data["volume"]
        if len(volumes) < 10:
            return True

        # Check: selling on rising volume (distribution)
        vol_ratio = volumes[-3:].mean() / max(volumes[-10:].mean(), 1)
        high_vol_sell = vol_ratio > 1.3  # 30% above avg volume

        # Check: volume drying up (no interest = dead cat)
        vol_drying = volumes[-5:].mean() < volumes[-10:-5].mean() * 0.5

        sell = high_vol_sell or vol_drying
        return sell

    def _regime_vote(self, data, regime, pos_info) -> bool:
        """Vote SELL=True if regime context supports selling"""
        # In bear market: always sell (cut losses fast)
        if regime == 'bear':
            return True
        # In bull market: hold unless clearly broken
        if regime == 'bull':
            return False
        # In range: sell if position is old (>10 days in loss)
        days = pos_info.get('bar_count', 0)
        cost = pos_info.get('cost', 0)
        if data and len(data["close"]) > 0:
            pnl = (data["close"][-1] - cost) / max(cost, 0.01)
            if days > 10 and pnl < -0.03:
                return True
        return False


# =============================================================================
# P2: Risk Parity Portfolio Optimization
# =============================================================================

class RiskParityOptimizer:
    """
    Risk parity position sizing: allocate capital inversely proportional to
    each position's volatility contribution.
    """

    def __init__(self, max_leverage: float = 1.0):
        self.max_leverage = max_leverage

    def allocate(self, candidates: list, data_cache: dict,
                 available_cash: float, max_positions: int = 5) -> list:
        """
        Args:
            candidates: [{'symbol': ..., 'confidence': ..., 'price': ..., ...}, ...]
            data_cache: {symbol: DataFrame}
            available_cash: float
            max_positions: int
        Returns: [{'symbol': ..., 'shares': int, 'weight': float}, ...]
        """
        if not candidates or available_cash <= 0:
            return []

        candidates = candidates[:max_positions]
        vols = []
        for c in candidates:
            df = data_cache.get(c['symbol'])
            vol = self._estimate_volatility(df)
            vols.append(max(vol, 0.005))  # Floor at 0.5% daily vol

        # Risk parity: weight = 1/vol / sum(1/vol)
        inv_vols = [1.0 / v for v in vols]
        total_inv = sum(inv_vols)
        weights = [iv / total_inv for iv in inv_vols]

        # Confidence adjustment: blend risk-parity with confidence
        confs = [c.get('confidence', 0.5) for c in candidates]
        conf_weight = 0.3  # 30% confidence, 70% risk parity
        for i in range(len(weights)):
            weights[i] = weights[i] * (1 - conf_weight) + confs[i] * conf_weight
        weights = self._normalize(weights)

        # Allocate shares
        allocations = []
        for i, c in enumerate(candidates):
            cash_for_stock = available_cash * weights[i] / max_positions
            shares = int(cash_for_stock / c['price'] / 100) * 100
            shares = max(shares, 100)  # Min 100 shares (A-share rule)
            allocations.append({
                "symbol": c['symbol'],
                "shares": shares,
                "weight": round(weights[i], 3),
                "vol": round(vols[i], 4)
            })

        return allocations

    @staticmethod
    def _estimate_volatility(df) -> float:
        if df is None or len(df) < 20:
            return 0.02  # Default 2% daily
        returns = np.diff(df["close"].values[-21:]) / df["close"].values[-21:-1]
        return float(np.std(returns))

    @staticmethod
    def _normalize(weights: list) -> list:
        total = sum(weights)
        return [w / total for w in weights] if total > 0 else [1.0 / len(weights)] * len(weights)


# =============================================================================
# Integration Engine
# =============================================================================

class VibeIntegration:
    """Master integration of all three Vibe-Trading-inspired modules."""

    def __init__(self):
        self.ic_analyzer = FactorICAnalyzer()
        self.risk_committee = RiskCommittee()
        self.risk_parity = RiskParityOptimizer()

    # ---- Factor IC ----
    def record_ic(self, strategy_name, ic, date_str=""):
        self.ic_analyzer.record(strategy_name, ic, date_str)

    def get_ic_report(self):
        return self.ic_analyzer.summary()

    def ic_adjust_weight(self, base_weight, strategy_name):
        return self.ic_analyzer.adjust_weight(base_weight, strategy_name)

    # ---- Risk Committee ----
    def review_exit(self, df, pos_info, regime='range'):
        return self.risk_committee.review(df, pos_info, regime)

    # ---- Risk Parity ----
    def allocate_positions(self, candidates, data_cache, cash, max_pos=5):
        return self.risk_parity.allocate(candidates, data_cache, cash, max_pos)


# =============================================================================
# P3: Advanced Performance Metrics (from Vibe-Trading metrics.py)
# =============================================================================

class AdvancedMetrics:
    """
    Sharpe, Sortino, Calmar, Profit Factor, Max Consecutive Loss.
    Adapted from Vibe-Trading's metrics.py (MIT license).
    """

    @staticmethod
    def calc_all(equity_curve: list, trades: list, initial_cash: float,
                 bench_returns: list = None) -> dict:
        """
        Args:
            equity_curve: [value, ...] daily NAV sequence
            trades: [{'pnl': float, 'type': 'SELL', ...}, ...]
            initial_cash: starting capital
            bench_returns: [ret, ...] benchmark daily returns (optional)
        """
        if len(equity_curve) < 2:
            return AdvancedMetrics._empty(initial_cash)

        import numpy as np
        ec = np.array(equity_curve, dtype=float)
        n = len(ec)

        # Returns
        rets = np.diff(ec) / ec[:-1]
        total_ret = (ec[-1] - initial_cash) / initial_cash

        # Annualized (252 trading days)
        ann_ret = (1 + total_ret) ** (252.0 / max(n, 1)) - 1

        # Vol & Sharpe
        vol = float(np.std(rets))
        sharpe = float(np.mean(rets) / (vol + 1e-10) * np.sqrt(252))

        # Drawdown
        peak = np.maximum.accumulate(ec)
        dd = (ec - peak) / np.where(peak == 0, 1, peak)
        max_dd = float(np.min(dd))

        # Calmar
        calmar = ann_ret / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0

        # Sortino
        downside = rets[rets < 0]
        d_std = float(np.std(downside)) if len(downside) > 1 else 1e-10
        sortino = float(np.mean(rets) / (d_std + 1e-10) * np.sqrt(252))

        # Trade stats
        sell_trades = [t for t in trades if t.get('type') == 'SELL' or t.get('pnl') is not None]
        pnls = [t.get('pnl', 0) for t in sell_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        win_rate = len(wins) / len(pnls) if pnls else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 1e-10
        profit_factor = sum(wins) / abs(sum(losses)) if losses else 0

        # Max consecutive loss
        max_cl, cur = 0, 0
        for p in pnls:
            if p < 0:
                cur += 1
                max_cl = max(max_cl, cur)
            else:
                cur = 0

        # Benchmark
        bench_ret = 0.0
        excess = 0.0
        ir = 0.0
        if bench_returns and len(bench_returns) > 0:
            br = np.array(bench_returns[:n-1])
            bench_ret = float(np.prod(1 + br) - 1)
            excess = total_ret - bench_ret
            active = rets - br[:len(rets)]
            ir = float(np.mean(active) / (np.std(active) + 1e-10) * np.sqrt(252))

        return {
            "total_return": round(total_ret * 100, 2),
            "annual_return": round(ann_ret * 100, 2),
            "max_drawdown": round(max_dd * 100, 2),
            "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2),
            "calmar": round(calmar, 2),
            "volatility": round(vol * 100, 2),
            "win_rate": round(win_rate * 100, 1),
            "profit_factor": round(profit_factor, 2),
            "max_consecutive_loss": max_cl,
            "trade_count": len(pnls),
            "benchmark_return": round(bench_ret * 100, 2),
            "excess_return": round(excess * 100, 2),
            "information_ratio": round(ir, 2),
        }

    @staticmethod
    def _empty(cash):
        return {"total_return": 0, "annual_return": 0, "max_drawdown": 0,
                "sharpe": 0, "sortino": 0, "calmar": 0, "volatility": 0,
                "win_rate": 0, "profit_factor": 0, "max_consecutive_loss": 0,
                "trade_count": 0, "benchmark_return": 0, "excess_return": 0,
                "information_ratio": 0}


# =============================================================================
# P4: Cross-Asset Correlation (from Vibe-Trading correlation.py)
# =============================================================================

class CorrelationAnalyzer:
    """
    Pairwise correlation of daily returns over configurable lookback.
    Adapted from Vibe-Trading's correlation.py (MIT license).
    """

    @staticmethod
    def compute_stock_correlation(price_data: dict, window: int = 60,
                                   method: str = "pearson") -> dict:
        """
        Args:
            price_data: {symbol: DataFrame with 'close' column}
            window: lookback days
            method: 'pearson' or 'spearman'
        Returns:
            {labels: [...], matrix: [[...], ...], high_pairs: [(a,b,r), ...]}
        """
        import numpy as np
        symbols = sorted(price_data.keys())
        if len(symbols) < 2:
            return {"labels": symbols, "matrix": [], "high_pairs": []}

        # Build returns matrix
        n = len(symbols)
        returns = {}
        for sym in symbols:
            df = price_data[sym]
            if df is None or len(df) < window:
                continue
            closes = df['close'].values[-window:]
            rets = np.diff(closes) / closes[:-1]
            if len(rets) > 0:
                returns[sym] = rets

        valid = list(returns.keys())
        if len(valid) < 2:
            return {"labels": valid, "matrix": [], "high_pairs": []}

        # Correlation matrix
        nv = len(valid)
        matrix = [[1.0] * nv for _ in range(nv)]
        high_pairs = []

        for i in range(nv):
            for j in range(i + 1, nv):
                ri = returns[valid[i]]
                rj = returns[valid[j]]
                min_len = min(len(ri), len(rj))
                if min_len < 5:
                    continue
                if method == "spearman":
                    from scipy.stats import spearmanr
                    corr, _ = spearmanr(ri[-min_len:], rj[-min_len:])
                else:
                    corr = float(np.corrcoef(ri[-min_len:], rj[-min_len:])[0, 1])
                if np.isnan(corr):
                    corr = 0.0
                corr = round(corr, 4)
                matrix[i][j] = corr
                matrix[j][i] = corr
                if abs(corr) > 0.7:
                    high_pairs.append((valid[i], valid[j], corr))

        high_pairs.sort(key=lambda x: -abs(x[2]))
        return {"labels": valid, "matrix": matrix, "high_pairs": high_pairs[:10]}


# =============================================================================
# P5: Benchmark Comparison (CSI 300 alignment)
# =============================================================================

class BenchmarkComparator:
    """Compare strategy returns against CSI 300 benchmark."""

    @staticmethod
    def compare(strategy_returns: list, bench_returns: list) -> dict:
        """
        Returns excess metrics: alpha, beta, tracking error, info ratio.
        """
        import numpy as np
        sr = np.array(strategy_returns)
        br = np.array(bench_returns)
        n = min(len(sr), len(br))
        sr, br = sr[:n], br[:n]

        if n < 5:
            return {"alpha": 0, "beta": 1, "tracking_error": 0, "info_ratio": 0}

        # Beta = Cov(s,b) / Var(b)
        cov = np.cov(sr, br)[0, 1]
        var_b = np.var(br)
        beta = cov / var_b if var_b > 1e-10 else 1.0

        # Alpha = mean(s - beta * b) * 252
        excess = sr - beta * br
        alpha = float(np.mean(excess) * 252)

        # Tracking error
        te = float(np.std(excess) * np.sqrt(252))

        # Info ratio
        ir = alpha / te if te > 1e-10 else 0.0

        return {
            "alpha": round(alpha * 100, 2),
            "beta": round(beta, 2),
            "tracking_error": round(te * 100, 2),
            "information_ratio": round(ir, 2),
        }


# Singleton
_vibe_instance = None


def get_vibe() -> VibeIntegration:
    global _vibe_instance
    if _vibe_instance is None:
        _vibe_instance = VibeIntegration()
    return _vibe_instance
