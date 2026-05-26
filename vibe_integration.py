"""
vibe_integration.py - V30.4 精简版
  P1: Risk Committee (multi-angle exit review)
  P3: Advanced Performance Metrics
"""
import numpy as np
import warnings
warnings.filterwarnings('ignore')


# =============================================================================
# Risk Committee - Multi-angle Exit Review
# =============================================================================

class RiskCommittee:
    """Multi-agent risk review. Only VETO a sell when ALL agents agree to hold."""

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
        return {"close": df["close"].values[-20:], "volume": df["volume"].values[-20:],
                "high": df["high"].values[-20:], "low": df["low"].values[-20:]}

    def _technical_vote(self, data, pos_info) -> bool:
        if data is None: return True
        closes = data["close"]
        if len(closes) < 5: return True
        ret_3d = (closes[-1] - closes[-4]) / max(closes[-4], 0.01)
        ret_5d = (closes[-1] - closes[-6]) / max(closes[-6], 0.01)
        accelerating_down = (ret_3d < ret_5d * 1.2) and ret_3d < -0.02
        breaking_low = closes[-1] < np.min(data["low"][-10:-1]) * 0.97
        return accelerating_down or breaking_low

    def _volume_vote(self, data, pos_info) -> bool:
        if data is None: return True
        volumes = data["volume"]
        if len(volumes) < 10: return True
        vol_ratio = volumes[-3:].mean() / max(volumes[-10:].mean(), 1)
        vol_drying = volumes[-5:].mean() < volumes[-10:-5].mean() * 0.5
        return vol_ratio > 1.3 or vol_drying

    def _regime_vote(self, data, regime, pos_info) -> bool:
        if regime == 'bear': return True
        if regime == 'bull': return False
        days = pos_info.get('bar_count', 0)
        cost = pos_info.get('cost', 0)
        if data and len(data["close"]) > 0:
            pnl = (data["close"][-1] - cost) / max(cost, 0.01)
            if days > 10 and pnl < -0.03:
                return True
        return False


# =============================================================================
# Integration Engine
# =============================================================================

class VibeIntegration:
    def __init__(self):
        self.risk_committee = RiskCommittee()

    def review_exit(self, df, pos_info, regime='range'):
        return self.risk_committee.review(df, pos_info, regime)


# =============================================================================
# Advanced Performance Metrics
# =============================================================================

class AdvancedMetrics:
    """Sharpe, Sortino, Calmar, Profit Factor, Max Consecutive Loss."""

    @staticmethod
    def calc_all(equity_curve: list, trades: list, initial_cash: float,
                 bench_returns: list = None) -> dict:
        if len(equity_curve) < 2:
            return AdvancedMetrics._empty(initial_cash)
        ec = np.array(equity_curve, dtype=float)
        n = len(ec)
        rets = np.diff(ec) / ec[:-1]
        total_ret = (ec[-1] - initial_cash) / initial_cash
        ann_ret = (1 + total_ret) ** (252.0 / max(n, 1)) - 1
        vol = float(np.std(rets))
        sharpe = float(np.mean(rets) / (vol + 1e-10) * np.sqrt(252))
        peak = np.maximum.accumulate(ec)
        dd = (ec - peak) / np.where(peak == 0, 1, peak)
        max_dd = float(np.min(dd))
        calmar = ann_ret / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0
        downside = rets[rets < 0]
        d_std = float(np.std(downside)) if len(downside) > 1 else 1e-10
        sortino = float(np.mean(rets) / (d_std + 1e-10) * np.sqrt(252))
        sell_trades = [t for t in trades if t.get('type') == 'SELL' or t.get('pnl') is not None]
        pnls = [t.get('pnl', 0) for t in sell_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = len(wins) / len(pnls) if pnls else 0
        profit_factor = sum(wins) / abs(sum(losses)) if losses else 0
        max_cl, cur = 0, 0
        for p in pnls:
            if p < 0: cur += 1; max_cl = max(max_cl, cur)
            else: cur = 0
        bench_ret, excess, ir = 0.0, 0.0, 0.0
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
            "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
            "calmar": round(calmar, 2), "volatility": round(vol * 100, 2),
            "win_rate": round(win_rate * 100, 1), "profit_factor": round(profit_factor, 2),
            "max_consecutive_loss": max_cl, "trade_count": len(pnls),
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


# Singleton
_vibe_instance = None

def get_vibe() -> VibeIntegration:
    global _vibe_instance
    if _vibe_instance is None:
        _vibe_instance = VibeIntegration()
    return _vibe_instance
