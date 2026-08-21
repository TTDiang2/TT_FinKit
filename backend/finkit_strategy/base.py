"""Strategy base class and data access context."""
from dataclasses import dataclass, field
from typing import Any

@dataclass
class StrategyContext:
    """Unified data access for backtesting and live signals.
    
    All data is read-only. Strategies access price/factor data ONLY through
    these methods - no DB connection, no network access in subprocess.
    """
    # list of asset dicts: [{"id": str, "type": str, "name": str, ...}, ...]
    pool: list[dict] = field(default_factory=list)
    # nav/prices: asset_id -> {date: value}
    prices: dict[str, dict[str, float]] = field(default_factory=dict)
    # daily returns: asset_id -> {date: return_rate}
    returns: dict[str, dict[str, float]] = field(default_factory=dict)
    # factor values: factor_name -> {date: value}
    factor_values: dict[str, dict[str, float]] = field(default_factory=dict)
    # factor betas: asset_id -> factor_name -> beta
    factor_exposures: dict[str, dict[str, float]] = field(default_factory=dict)
    # current portfolio weights: {asset_id: weight}
    current_weights: dict[str, float] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    now: str = ""

    def nav_history(self, asset_ids: list[str], begin: str, end: str) -> dict[str, list[tuple[str, float]]]:
        """Return nav/cum return series for assets in date range.
        
        Returns: {asset_id: [(date, value), ...]} sorted by date ascending.
        """
        result = {}
        for aid in asset_ids:
            series = []
            asset_prices = self.prices.get(aid, {})
            for date, val in sorted(asset_prices.items()):
                if begin <= date <= end:
                    series.append((date, val))
            result[aid] = series
        return result

    def get_returns(self, asset_ids: list[str], begin: str, end: str) -> dict[str, list[tuple[str, float]]]:
        """Return daily return series for assets in date range."""
        result = {}
        for aid in asset_ids:
            series = []
            asset_rets = self.returns.get(aid, {})
            for date, val in sorted(asset_rets.items()):
                if begin <= date <= end:
                    series.append((date, val))
            result[aid] = series
        return result

    def momentum(self, asset_ids: list[str], lookback: int = 120) -> dict[str, float]:
        """Compute cumulative return over lookback period for each asset."""
        result = {}
        for aid in asset_ids:
            rets = self.returns.get(aid, {})
            if not rets:
                result[aid] = 0.0
                continue
            sorted_dates = sorted(rets.keys())
            lookback = min(lookback, len(sorted_dates))
            if lookback <= 0:
                result[aid] = 0.0
                continue
            recent = sorted_dates[-lookback:]
            cum = 1.0
            for d in recent:
                cum *= (1 + rets[d])
            result[aid] = cum - 1.0
        return result

    def volatility(self, asset_ids: list[str], lookback: int = 120) -> dict[str, float]:
        """Compute annualized volatility over lookback period."""
        import math
        result = {}
        for aid in asset_ids:
            rets = self.returns.get(aid, {})
            if not rets:
                result[aid] = 0.0
                continue
            sorted_dates = sorted(rets.keys())
            lookback = min(lookback, len(sorted_dates))
            if lookback <= 1:
                result[aid] = 0.0
                continue
            recent = sorted_dates[-lookback:]
            daily_rets = [rets[d] for d in recent]
            mean = sum(daily_rets) / len(daily_rets)
            var = sum((r - mean) ** 2 for r in daily_rets) / len(daily_rets)
            ann_vol = math.sqrt(var * 252)
            result[aid] = ann_vol
        return result

    def factor_value(self, factor_name: str, begin: str, end: str) -> list[tuple[str, float]]:
        """Return factor value series in date range."""
        series = []
        fv = self.factor_values.get(factor_name, {})
        for date, val in sorted(fv.items()):
            if begin <= date <= end:
                series.append((date, val))
        return series

    def factor_exposure(self, asset_id: str, factor_name: str) -> float:
        """Return latest beta/exposure of asset to factor."""
        return self.factor_exposures.get(asset_id, {}).get(factor_name, 0.0)


class Strategy:
    """Base class for all FinKit strategies.
    
    Subclass must define:
      name, description, rebalance_freq, params_schema
    and implement:
      universe(ctx), target_weights(ctx, date)
    """
    name: str = ""
    description: str = ""
    rebalance_freq: str = "monthly"  # monthly / weekly
    params_schema: dict = field(default_factory=dict)

    def __init__(self, **params):
        self.params = {}
        for key, spec in self.params_schema.items():
            self.params[key] = params.get(key, spec.get("default", None))
        for key, val in params.items():
            if key in self.params_schema:
                self.params[key] = val

    def universe(self, ctx: StrategyContext) -> list[str]:
        """Return list of asset_ids in the investment universe."""
        return [a["id"] for a in ctx.pool]

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        """Return {asset_id: weight} for the given rebalance date.
        
        Return None to skip rebalancing (maintain current weights).
        """
        raise NotImplementedError
