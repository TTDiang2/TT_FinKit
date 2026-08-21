"""Pure portfolio NAV index construction (no DB / async / network).

Builds a time-weighted portfolio NAV series from per-fund daily NAVs,
per-fund share counts, and cash events — the same "fund of funds" unit
method used by fund apps: deposits subscribe units at the previous NAV,
withdrawals redeem units, so the resulting NAV series is cash-flow-free
and its daily returns are valid for volatility / Sharpe.
"""
from __future__ import annotations

from .indicators import (
    annualized_return,
    annualized_volatility,
    max_drawdown,
    sharpe_ratio,
)


def forward_fill(dates: list[str], nav_by_date: dict[str, float]) -> dict[str, float]:
    """Map every date in ``dates`` to the latest known NAV at or before it."""
    out: dict[str, float] = {}
    last: float | None = None
    for d in dates:
        v = nav_by_date.get(d)
        if v is not None:
            last = v
        if last is not None:
            out[d] = last
    return out


def snap_date(d: str, dates: list[str]) -> str:
    """Earliest NAV date at or after ``d``; the last date if past the window.

    Cash events (deposits, buys) on non-trading days must be booked on the
    next NAV date, otherwise the share book gains shares while the cash
    ledger never records the outflow, and the portfolio NAV jumps.
    """
    for x in dates:
        if x >= d:
            return x
    return dates[-1]


def build_portfolio_nav(
    dates: list[str],
    fund_navs: dict[str, dict[str, float]],
    fund_qty: dict[str, dict[str, float]],
    cash_by_date: dict[str, float],
    deposit_by_date: dict[str, float],
    withdrawal_by_date: dict[str, float],
) -> dict:
    """Args:
    dates:            sorted ascending trading-calendar dates (union of fund NAVs)
    fund_navs:        {fund_id: {date: nav}} — will be forward-filled internally
    fund_qty:         {fund_id: {date: cumulative shares held at that date}}
    cash_by_date:     {date: cumulative idle cash at that date}
    deposit_by_date / withdrawal_by_date: {date: flow amount on that exact date}

    Returns {series: [{date, nav, total_value}], metrics: {...}}.
    """
    filled = {fid: forward_fill(dates, nav) for fid, nav in fund_navs.items()}

    units = 0.0
    prev_nav = 1.0
    series: list[dict] = []
    for d in dates:
        flow = deposit_by_date.get(d, 0.0) - withdrawal_by_date.get(d, 0.0)
        if flow and units > 0:
            units += flow / prev_nav
        value = cash_by_date.get(d, 0.0)
        for fid, navs in filled.items():
            qty = fund_qty.get(fid, {}).get(d)
            nav = navs.get(d)
            if qty and nav:
                value += qty * nav
        if value <= 0:
            # fully deleveraged (all cash spent, no holdings) — nothing to value
            continue
        if units <= 0:
            units = 1.0
        nav = value / units
        series.append({"date": d, "nav": round(nav, 6), "total_value": round(value, 2)})
        prev_nav = nav

    nav_series = [p["nav"] for p in series]
    return {
        "series": series,
        "metrics": {
            "points": len(series),
            "ann_return": annualized_return(nav_series),
            "ann_volatility": annualized_volatility(nav_series),
            "sharpe": sharpe_ratio(nav_series),
            "max_drawdown": max_drawdown(nav_series),
        },
    }


def compute_pnl_by_period(
    series: list[dict],
    deposit_by_date: dict[str, float],
    withdrawal_by_date: dict[str, float],
    granularity: str,
) -> list[dict]:
    """Daily P&L → grouped series by ``granularity`` (day/month/year).

    Daily P&L = Δtotal_value − net cash flow that day. Internal cash-leg events
    (buy/sell) cancel out in the total, so the residual is the market move.
    Returns [{date, pnl}, ...] sorted ascending; ``date`` is YYYY-MM-DD for
    granularity=="day", YYYY-MM for "month", YYYY for "year".
    """
    daily: list[dict] = []
    prev_value: float | None = None
    for p in series:
        d = p["date"]
        flow = deposit_by_date.get(d, 0.0) - withdrawal_by_date.get(d, 0.0)
        pnl = 0.0 if prev_value is None else p["total_value"] - prev_value - flow
        daily.append({"date": d, "pnl": round(pnl, 2)})
        prev_value = p["total_value"]

    if granularity == "day":
        return daily
    buckets: dict[str, float] = {}
    for it in daily:
        key = it["date"][:7] if granularity == "month" else it["date"][:4]
        buckets[key] = buckets.get(key, 0.0) + it["pnl"]
    return [{"date": k, "pnl": round(v, 2)} for k, v in sorted(buckets.items())]