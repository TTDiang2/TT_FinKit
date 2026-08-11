"""migration_calc: Pure-computation reverse-calculation of fund share quantities.

This module is part of the FinKit investment-tab P0 migration feature. Users historically
tracked off-exchange fund purchases by amount only (quantity = 1.0). To migrate to a real
share-based ledger we reverse-calculate shares from historical NAV (Net Asset Value).

Design notes:
  * Pure standard library only (datetime). No DB / network / async / iFinD coupling.
  * nav_fetcher is INJECTED; production binds it to an iFinD query later. Tests pass a
    lambda that returns a fixed series.
  * All amounts and shares are floats; shares are rounded to 2 decimal places at the
    entry-construction boundary to keep ledger precision stable.

Public API:
  - compute_shares(amount, nav) -> float
  - pick_nearest_nav(target_date, nav_series) -> (str, float) | None
  - build_migration_entries(inputs, nav_fetcher) -> list[dict]
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional


def compute_shares(amount: float, nav: float) -> float:
    """Compute share quantity from a purchase amount and per-share NAV.

    Returns amount / nav. Guards against division by zero and non-positive inputs by
    returning 0.0; this matches ledger semantics where an entry with zero/negative
    amount or invalid NAV should not produce phantom share rows.
    """
    if amount <= 0 or nav <= 0:
        return 0.0
    return amount / nav


def pick_nearest_nav(
    target_date: str,
    nav_series: list[dict],
) -> Optional[tuple[str, float]]:
    """Pick the NAV point appropriate for ``target_date``.

    ``nav_series`` is a list of ``{"date": "YYYY-MM-DD", "close": float}`` entries
    assumed to be sorted ascending by date.

    Behaviour:
      * Exact match on date -> that point.
      * target earlier than the earliest series point -> ``None`` (cannot reverse-
        calculate, no historical data available).
      * target falls between two series points (e.g. weekend/holiday) -> the
        most-recent trading day on-or-before target. This avoids look-ahead bias
        and matches the convention that off-exchange subscriptions execute at the
        next-known NAV but are recorded against the previous published value.
    """
    if not nav_series:
        return None

    target = date.fromisoformat(target_date)
    earliest = date.fromisoformat(nav_series[0]["date"])
    if target < earliest:
        return None

    # Walk forward; the series is ascending so the first point whose date >= target
    # is the upper bound. If equal -> exact match. Otherwise the previous point is
    # the largest date <= target, which is what we want for weekend/holiday gaps.
    candidate: Optional[tuple[str, float]] = None
    for point in nav_series:
        point_date = date.fromisoformat(point["date"])
        if point_date == target:
            return (point["date"], float(point["close"]))
        if point_date > target:
            break
        candidate = (point["date"], float(point["close"]))

    return candidate


def build_migration_entries(
    inputs: list[dict],
    nav_fetcher: Callable[[list[str]], list[dict]],
) -> list[dict]:
    """Build migrated ledger entries from user-recorded amount-only purchases.

    ``inputs`` is a list of ``{"date": "YYYY-MM-DD", "amount": float}``.
    ``nav_fetcher`` is an injected callable: given a list of dates it returns the
    historical NAV series. In production this is bound to iFinD; tests substitute a
    lambda returning a fixed series.

    For each input the function:
      1. Calls ``nav_fetcher([date])`` to obtain the NAV series.
      2. Uses ``pick_nearest_nav`` to find the applicable NAV point.
      3. Computes shares with ``compute_shares`` and rounds to 2 decimals.
      4. Emits ``{"date", "amount", "nav", "shares"}``.

    If ``pick_nearest_nav`` returns ``None`` (target predates available data), the
    entry is emitted with ``nav=None``, ``shares=None`` and an ``error="no_nav"``
    field so callers can surface/handle it without dropping the user input.
    """
    entries: list[dict] = []
    for entry in inputs:
        target_date = entry["date"]
        amount = float(entry["amount"])
        series = nav_fetcher([target_date])
        picked = pick_nearest_nav(target_date, series)
        if picked is None:
            entries.append({
                "date": target_date,
                "amount": amount,
                "nav": None,
                "shares": None,
                "error": "no_nav",
            })
            continue
        nav_date, nav_value = picked
        raw_shares = compute_shares(amount, nav_value)
        entries.append({
            "date": target_date,
            "amount": amount,
            "nav": nav_value,
            "shares": round(raw_shares, 2),
        })
    return entries