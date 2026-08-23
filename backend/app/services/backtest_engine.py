"""Backtest engine — pure simulation + subprocess execution.

The heavy lifting (price loading, weight simulation, metrics) runs in an
isolated subprocess so long-running backtests never block the API event loop.
The subprocess reads prices directly from SQLite (``research_prices``) and
imports only ``finkit_strategy.base`` plus this module's pure functions.

Pure functions (``generate_rebalance_dates``, ``compute_trade_cost``,
``compute_metrics``, ``run_simulation``) are dependency-free and unit-tested.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date
from typing import Any

INITIAL_CAPITAL = 100_000.0
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.02

# Default tiered redemption fee schedule (holding days → fee rate).
# First matching tier wins; ``max_days=None`` is the catch-all.
DEFAULT_REDEEM_RULES: list[dict] = [
    {"max_days": 7, "fee_rate": 0.015},   # < 7 days  → 1.5%
    {"max_days": 30, "fee_rate": 0.005},  # < 30 days → 0.5%
    {"max_days": None, "fee_rate": 0.0},  # >= 30 days → 0
]

# ---------------------------------------------------------------------------
# Pure computation helpers
# ---------------------------------------------------------------------------

def generate_rebalance_dates(trading_days: list[str], freq: str = "monthly") -> list[str]:
    """Pick rebalance dates from a sorted trading-day calendar.

    ``daily``  → every trading day.
    ``monthly`` → the last trading day of each calendar month present.
    ``weekly``  → every Friday present.
    """
    if freq == "daily":
        return list(trading_days)
    if freq == "weekly":
        return [d for d in trading_days if date.fromisoformat(d).weekday() == 4]
    # monthly: group by YYYY-MM, take the last trading day in each group
    by_month: dict[str, list[str]] = {}
    for d in trading_days:
        by_month.setdefault(d[:7], []).append(d)
    return [by_month[m][-1] for m in sorted(by_month)]


def redeem_fee_rate(rules: list[dict], holding_days: int) -> float:
    """Tiered redemption fee rate for a holding period (days).

    ``rules`` is a list of ``{"max_days": int|None, "fee_rate": float}``.
    The first tier whose ``max_days`` is not None and greater than
    ``holding_days`` applies; otherwise the last rule's rate is the fallback.
    """
    if not rules:
        return 0.0
    for rule in sorted(
        rules, key=lambda r: (r.get("max_days") is None, r.get("max_days") or float("inf"))
    ):
        max_days = rule.get("max_days")
        if max_days is not None and holding_days < max_days:
            return float(rule.get("fee_rate", 0.0))
    return float(rules[-1].get("fee_rate", 0.0))


def compute_trade_cost(
    side: str,
    amount: float,
    purchase_fee_rate: float,
    redeem_rules: list[dict],
    holding_days: int,
) -> tuple[float, float]:
    """Return (fee, rate_applied) for a trade notional ``amount``.

    Buys  → flat ``purchase_fee_rate``.
    Sells → tiered redemption fee by holding period.
    """
    if side == "buy":
        return amount * purchase_fee_rate, purchase_fee_rate
    rate = redeem_fee_rate(redeem_rules, holding_days)
    return amount * rate, rate


def _max_drawdown(navs: list[float]) -> float:
    if len(navs) < 2:
        return 0.0
    peak = navs[0]
    mdd = 0.0
    for v in navs:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < mdd:
                mdd = dd
    return mdd


def compute_metrics(
    nav_series: list[dict], total_cost: float = 0.0, turnover: float = 0.0,
    initial_capital: float = INITIAL_CAPITAL,
) -> dict[str, float | None]:
    """Risk/return metrics from the nav series (navs[0] > 0 required).

    Returns: ann_return, ann_volatility, sharpe, max_drawdown, calmar,
    sortino, total_cost, turnover_annual (ratio = annual turnover / capital).
    """
    navs = [p["nav"] for p in nav_series]
    n = len(navs)
    if n < 2 or navs[0] <= 0 or navs[-1] <= 0:
        return {
            "ann_return": 0.0, "ann_volatility": 0.0, "sharpe": 0.0,
            "max_drawdown": 0.0, "calmar": 0.0, "sortino": 0.0,
            "total_cost": round(total_cost, 4),
            "total_cost_ratio": round(total_cost / initial_capital, 6) if initial_capital > 0 else 0.0,
            "turnover_annual": 0.0,
        }

    daily_rets = [
        navs[i] / navs[i - 1] - 1.0 for i in range(1, n) if navs[i - 1] > 0
    ]
    periods = len(daily_rets)
    years = periods / TRADING_DAYS_PER_YEAR

    ann_return = (navs[-1] / navs[0]) ** (TRADING_DAYS_PER_YEAR / max(1, periods)) - 1.0

    if periods >= 2:
        mean = sum(daily_rets) / periods
        var = sum((r - mean) ** 2 for r in daily_rets) / (periods - 1)
        ann_vol = math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        ann_vol = 0.0

    sharpe = (ann_return - RISK_FREE_RATE) / ann_vol if ann_vol > 0 else 0.0

    mdd = _max_drawdown(navs)
    calmar = ann_return / abs(mdd) if mdd < 0 else 0.0

    # Sortino: downside deviation over negative daily returns only
    neg = [r for r in daily_rets if r < 0]
    if len(neg) >= 2:
        d_mean = sum(neg) / len(neg)
        d_var = sum((r - d_mean) ** 2 for r in neg) / (len(neg) - 1)
        d_dev = math.sqrt(d_var) * math.sqrt(TRADING_DAYS_PER_YEAR)
        sortino = (ann_return - RISK_FREE_RATE) / d_dev if d_dev > 0 else 0.0
    else:
        sortino = 0.0

    # Annual turnover RATIO: traded amount per year / portfolio capital.
    # (The frontend displays this as a percentage.)
    turnover_annual = (turnover / years / initial_capital) if years > 0 and initial_capital > 0 else 0.0

    return {
        "ann_return": round(ann_return, 6),
        "ann_volatility": round(ann_vol, 6),
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(mdd, 6),
        "calmar": round(calmar, 6),
        "sortino": round(sortino, 6),
        "total_cost": round(total_cost, 4),
        "total_cost_ratio": round(total_cost / initial_capital, 6) if initial_capital > 0 else 0.0,
        "turnover_annual": round(turnover_annual, 6),
    }


# ---------------------------------------------------------------------------
# View builders (best-effort portfolio analytics)
# ---------------------------------------------------------------------------

def _avg_weights(weight_history: list[dict]) -> dict[str, float]:
    avg: dict[str, float] = {}
    for wh in weight_history:
        for aid, w in wh["weights"].items():
            avg[aid] = avg.get(aid, 0.0) + w
    denom = max(1, len(weight_history))
    return {aid: v / denom for aid, v in avg.items()}


def _factor_view(prices: dict[str, dict[str, float]], weight_history: list[dict]) -> dict:
    """Target/realized exposure + per-asset return contribution.

    Contribution is the average weight times the full-period asset return —
    a simple first-order attribution.
    """
    avg_w = _avg_weights(weight_history)
    contribution: dict[str, float] = {}
    for aid, series in prices.items():
        vals = [v for _, v in sorted(series.items())]
        if len(vals) >= 2 and vals[0] > 0:
            contribution[aid] = round(avg_w.get(aid, 0.0) * (vals[-1] / vals[0] - 1.0), 6)
        else:
            contribution[aid] = 0.0
    exposure = round(sum(avg_w.values()), 6)
    return {
        "target_exposure": exposure,
        "realized_exposure": exposure,
        "contribution": contribution,
    }


def _risk_view(
    nav_series: list[dict],
    weight_history: list[dict],
    metrics: dict,
) -> dict:
    """Drawdown series, historical VaR95 / CVaR95 and average risk weights."""
    dd_series: list[dict] = []
    peak = None
    for p in nav_series:
        v = p["nav"]
        peak = v if peak is None or v > peak else peak
        dd = (v - peak) / peak if peak and peak > 0 else 0.0
        dd_series.append({"date": p["date"], "drawdown": round(dd, 6)})

    navs = [p["nav"] for p in nav_series]
    daily_rets = sorted(
        navs[i] / navs[i - 1] - 1.0 for i in range(1, len(navs)) if navs[i - 1] > 0
    )

    var95: float | None = None
    cvar95: float | None = None
    if daily_rets:
        idx = max(0, int(round(0.05 * len(daily_rets))) - 1)
        var95 = daily_rets[idx]
        cutoff = daily_rets[idx]
        below = [r for r in daily_rets if r <= cutoff]
        if below:
            cvar95 = sum(below) / len(below)

    return {
        "max_drawdown_series": dd_series,
        "var_95": round(var95, 6) if var95 is not None else None,
        "cvar_95": round(cvar95, 6) if cvar95 is not None else None,
        "risk_contrib": {aid: round(v, 6) for aid, v in _avg_weights(weight_history).items()},
    }


# ---------------------------------------------------------------------------
# Simulation core
# ---------------------------------------------------------------------------

def run_simulation(
    strategy: Any,
    ctx: Any,
    trading_days: list[str],
    rebalance_dates: list[str],
    prices: dict[str, dict[str, float]],
    fee_terms: dict[str, dict],
    redeem_rules: list[dict],
    initial_capital: float = INITIAL_CAPITAL,
) -> dict:
    """Simulate the strategy over a trading calendar.

    Between rebalance dates weights drift with prices; a daily
    (mgmt+custody)/365 fee is deducted from total value. On rebalance days the
    strategy is asked for target weights (``None`` = maintain current) and the
    diff is traded, with purchase fee on buys and tiered redeem fee on sells.
    """
    rebalance_set = set(rebalance_dates)
    universe = list(prices.keys())
    eps = 1e-6

    holdings: dict[str, float] = {}   # asset_id -> shares
    buy_dates: dict[str, str] = {}    # asset_id -> first buy date (tiered fee)
    cash = float(initial_capital)
    portfolio_value = float(initial_capital)
    total_cost = 0.0
    total_turnover = 0.0

    nav_series: list[dict] = []
    weight_history: list[dict] = []
    rebalance_records: list[dict] = []

    def _price(aid: str, day: str) -> float:
        return prices.get(aid, {}).get(day, 0.0)

    def _invested(day: str) -> float:
        return sum(sh * _price(aid, day) for aid, sh in holdings.items())

    def _daily_fee_rate() -> float:
        """Weighted-average (mgmt+custody)/year over held assets."""
        total_v = sum(sh * _price(aid, day) for aid, sh in holdings.items())
        if total_v <= 0:
            return 0.0
        weighted = sum(
            sh * _price(aid, day)
            * (fee_terms.get(aid, {}).get("mgmt_fee", 0.0)
               + fee_terms.get(aid, {}).get("custody_fee", 0.0))
            for aid, sh in holdings.items()
        )
        return weighted / total_v

    for day in trading_days:
        invested = _invested(day)

        trades: list[dict] = []
        if day in rebalance_set:
            ctx.now = day
            target = strategy.target_weights(ctx, day)
            if target is not None:
                gross = sum(max(0.0, v) for v in target.values())
                if gross <= 0:
                    target = {aid: 0.0 for aid in universe}
                else:
                    target = {aid: max(0.0, w) / gross for aid, w in target.items()}

                portfolio_value = cash + invested
                for aid in sorted(set(holdings) | set(target)):
                    px = _price(aid, day)
                    if px <= 0:
                        continue
                    current_value = holdings.get(aid, 0.0) * px
                    target_value = portfolio_value * target.get(aid, 0.0)
                    diff = target_value - current_value
                    if diff > eps:
                        fee = diff * fee_terms.get(aid, {}).get("purchase_fee", 0.0)
                        bought = diff / px
                        was_empty = holdings.get(aid, 0.0) <= eps
                        holdings[aid] = holdings.get(aid, 0.0) + bought
                        if was_empty:
                            buy_dates[aid] = day
                        cash -= diff + fee
                        total_cost += fee
                        total_turnover += diff
                        trades.append({
                            "symbol": aid, "side": "buy",
                            "amount": round(diff, 4), "fee": round(fee, 4),
                        })
                    elif diff < -eps:
                        amount = -diff
                        holding_days = max(
                            0,
                            (date.fromisoformat(day)
                             - date.fromisoformat(buy_dates.get(aid, day))).days,
                        )
                        fee, _rate = compute_trade_cost(
                            "sell", amount, 0.0, redeem_rules, holding_days
                        )
                        sold = amount / px
                        holdings[aid] = holdings.get(aid, 0.0) - sold
                        if holdings[aid] <= eps:
                            holdings.pop(aid, None)
                            buy_dates.pop(aid, None)
                        cash += amount - fee
                        total_cost += fee
                        total_turnover += amount
                        trades.append({
                            "symbol": aid, "side": "sell",
                            "amount": round(amount, 4), "fee": round(fee, 4),
                        })
                if trades:
                    rebalance_records.append({"date": day, "trades": trades})

        # day-end: mark to market + daily fee deducted PRO-RATA from cash and
        # holdings (like fund NAV accrual). Deducting only from cash would drive
        # cash negative when fully invested, causing phantom sell trades on the
        # next rebalance day (turnover explosion).
        invested = _invested(day)
        portfolio_value = cash + invested
        daily_fee = portfolio_value * _daily_fee_rate() / 365.0
        if daily_fee > 0 and portfolio_value > 0:
            ratio = daily_fee / portfolio_value
            cash -= cash * ratio
            for aid in list(holdings.keys()):
                holdings[aid] -= holdings[aid] * ratio
                if holdings[aid] <= eps:
                    holdings.pop(aid, None)
            portfolio_value -= daily_fee
            total_cost += daily_fee

        nav = portfolio_value / initial_capital if initial_capital > 0 else 0.0
        nav_series.append({
            "date": day,
            "nav": round(nav, 8),
            "portfolio_value": round(portfolio_value, 4),
        })

        weights = {
            aid: (holdings.get(aid, 0.0) * _price(aid, day)) / portfolio_value
            for aid in universe
            if holdings.get(aid, 0.0) and _price(aid, day) > 0
        }
        weight_history.append({
            "date": day,
            "weights": {k: round(v, 6) for k, v in weights.items() if v > 1e-9},
        })

    metrics = compute_metrics(nav_series, total_cost, total_turnover, initial_capital)
    return {
        "nav_series": nav_series,
        "metrics": metrics,
        "weight_history": weight_history,
        "rebalance_records": rebalance_records,
        "factor_view": _factor_view(prices, weight_history),
        "risk_view": _risk_view(nav_series, weight_history, metrics),
    }


# ---------------------------------------------------------------------------
# Data loading (runs inside the subprocess, stdlib sqlite3 only)
# ---------------------------------------------------------------------------

def load_price_data(
    db_path: str,
    universe: list[str],
    start_date: str,
    end_date: str,
) -> tuple[
    dict[str, dict[str, float]],
    dict[str, dict[str, float]],
    list[dict],
    dict[str, dict],
]:
    """Read close series, daily returns, asset metadata and fee terms.

    ``universe`` is a list of asset SYMBOLS (e.g. "000300", "511010"). All
    returned price/return/fee data is keyed by symbol so strategies never
    deal with internal UUIDs. Prices come from the ``research_prices``
    warehouse (asset_id, date, close).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in universe)

    # Resolve symbols → internal asset ids, and build the symbol-keyed pool
    pool: list[dict] = []
    symbol_to_id: dict[str, str] = {}
    fee_terms: dict[str, dict] = {}
    arows = conn.execute(
        "SELECT id, symbol, exchange, name, asset_type, mgmt_fee, custody_fee, purchase_fee "
        f"FROM research_assets WHERE symbol IN ({placeholders})",
        list(universe),
    ).fetchall()
    for a in arows:
        symbol_to_id[a["symbol"]] = a["id"]
        pool.append({
            "id": a["id"], "symbol": a["symbol"], "exchange": a["exchange"],
            "name": a["name"], "type": a["asset_type"] or "fund",
        })
        fee_terms[a["symbol"]] = {
            # DB stores fees as PERCENTAGE numbers (e.g. 0.5 = 0.5%/year);
            # the engine uses decimal rates, so divide by 100.
            "purchase_fee": float(a["purchase_fee"] or 0.0) / 100.0,
            "mgmt_fee": float(a["mgmt_fee"] or 0.0) / 100.0,
            "custody_fee": float(a["custody_fee"] or 0.0) / 100.0,
        }

    # Load prices by internal ids, then re-key by symbol
    ids = [symbol_to_id[s] for s in universe if s in symbol_to_id]
    prices: dict[str, dict[str, float]] = {s: {} for s in universe}
    if ids:
        id_placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            "SELECT asset_id, date, close FROM research_prices "
            f"WHERE asset_id IN ({id_placeholders}) AND date >= ? AND date <= ? "
            "ORDER BY asset_id, date",
            [*ids, start_date, end_date],
        ).fetchall()
        id_to_symbol = {v: k for k, v in symbol_to_id.items()}
        for r in rows:
            sym = id_to_symbol.get(r["asset_id"])
            if sym is not None:
                prices[sym][r["date"]] = float(r["close"])

    returns: dict[str, dict[str, float]] = {}
    for sym, series in prices.items():
        rets: dict[str, float] = {}
        prev: float | None = None
        for d in sorted(series):
            if prev is not None and prev > 0:
                rets[d] = series[d] / prev - 1.0
            prev = series[d]
        returns[sym] = rets

    conn.close()
    return prices, returns, pool, fee_terms


# ---------------------------------------------------------------------------
# Subprocess orchestration
# ---------------------------------------------------------------------------

_RUNNER_CODE = r'''
import sys, json, traceback
from finkit_strategy.base import Strategy, StrategyContext
from app.services.backtest_engine import (
    generate_rebalance_dates, run_simulation, load_price_data,
    DEFAULT_REDEEM_RULES,
)

input_path = sys.argv[1]
output_path = sys.argv[2]

with open(input_path, "r", encoding="utf-8") as f:
    data = json.load(f)

result = None
try:
    namespace = {}
    exec(data["strategy_code"], namespace)
    strat_classes = [
        v for v in namespace.values()
        if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
    ]
    if not strat_classes:
        raise ValueError("No Strategy subclass found in code")
    strategy = strat_classes[0](**data.get("params", {}))

    prices, returns, pool, fee_terms = load_price_data(
        data["db_path"], data["universe"], data["start_date"], data["end_date"]
    )
    trading_days = sorted(set().union(*(set(p) for p in prices.values()))) if prices else []
    if not trading_days:
        raise ValueError("No price data found for universe in date range")

    ctx = StrategyContext(
        pool=pool,
        prices=prices,
        returns=returns,
        factor_values=data.get("factor_values", {}),
        factor_exposures=data.get("factor_exposures", {}),
        current_weights={},
        params=data.get("params", {}),
        now=trading_days[0],
    )

    rebalance_dates = generate_rebalance_dates(trading_days, data["rebalance_freq"])
    cost_config = data.get("cost_config") or {}
    redeem_rules = cost_config.get("redeem_rules") or DEFAULT_REDEEM_RULES
    initial_capital = float(cost_config.get("initial_capital", 100000.0))

    out = run_simulation(
        strategy=strategy,
        ctx=ctx,
        trading_days=trading_days,
        rebalance_dates=rebalance_dates,
        prices=prices,
        fee_terms=fee_terms,
        redeem_rules=redeem_rules,
        initial_capital=initial_capital,
    )
    out["status"] = "ok"
    out["error"] = None
    result = out

except Exception as e:
    result = {
        "status": "error",
        "error": f"{type(e).__name__}: {e}",
        "nav_series": [], "metrics": {}, "weight_history": [],
        "rebalance_records": [], "factor_view": {}, "risk_view": {},
    }
    try:
        result["traceback"] = traceback.format_exc()
    except Exception:
        pass

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False)
'''


def _backend_root() -> str:
    # backend/app/services/backtest_engine.py -> backend/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _error_result(message: str) -> dict:
    return {
        "status": "error", "error": message,
        "nav_series": [], "metrics": {}, "weight_history": [],
        "rebalance_records": [], "factor_view": {}, "risk_view": {},
    }


def _run_backtest_sync(
    strategy_code: str,
    params: dict,
    universe: list[str],
    start_date: str,
    end_date: str,
    rebalance_freq: str,
    db_path: str,
    cost_config: dict | None = None,
    timeout: int = 120,
) -> dict:
    """Write input JSON, spawn the subprocess, read the output JSON.

    Same temp-JSON IPC pattern as ``finkit_strategy.runner``.
    """
    input_data = {
        "strategy_code": strategy_code,
        "params": params,
        "universe": universe,
        "start_date": start_date,
        "end_date": end_date,
        "rebalance_freq": rebalance_freq,
        "db_path": db_path,
        "cost_config": cost_config or {},
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(input_data, f)
        input_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(_RUNNER_CODE)
        runner_script = f.name
    output_path = tempfile.mktemp(suffix='.json')

    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _backend_root() + (os.pathsep + existing if existing else "")

    try:
        proc = subprocess.Popen(
            [sys.executable, runner_script, input_path, output_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return _error_result(f"Backtest execution timed out after {timeout}s")
        with open(output_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return _error_result(str(e))
    finally:
        for path in (runner_script, input_path, output_path):
            try:
                os.unlink(path)
            except OSError:
                pass


async def run_backtest_in_subprocess(
    strategy_code: str,
    params: dict,
    universe: list[str],
    start_date: str,
    end_date: str,
    rebalance_freq: str,
    db_path: str = "finkit.db",
    cost_config: dict | None = None,
    timeout: int = 120,
) -> dict:
    """Async wrapper: run the backtest subprocess off the event loop."""
    import asyncio
    return await asyncio.to_thread(
        _run_backtest_sync, strategy_code, params, universe, start_date,
        end_date, rebalance_freq, db_path, cost_config, timeout,
    )
