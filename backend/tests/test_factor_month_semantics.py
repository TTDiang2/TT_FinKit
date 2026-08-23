"""P0 regression tests — as_of month semantics (YYYY-MM) + recompute skipped reasons."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

from app.routers.factors import _expand_month_bound
from app.services.factor_engine import compute_exposure, _month_ends


class TestExpandMonthBound:
    def test_month_input_expands_to_first_and_last_day(self):
        first, last = _expand_month_bound("2026-08")
        assert first == "2026-08-01"
        assert last == "2026-08-31"

    def test_leap_february(self):
        first, last = _expand_month_bound("2024-02")
        assert first == "2024-02-01"
        assert last == "2024-02-29"

    def test_full_date_passthrough(self):
        assert _expand_month_bound("2026-08-20") == ("2026-08-20", "2026-08-20")

    def test_month_end_as_of_matches_month_semantics(self):
        """The core bug: stored as_of is the last TRADING day (e.g. 2026-08-20),
        which must fall inside the month window expanded from '2026-08'."""
        first, last = _expand_month_bound("2026-08")
        assert first <= "2026-08-20" <= last

    def test_contribution_end_semantics(self):
        """Contribution compares as_of <= end; month '2026-07' must include
        any July month-end like 2026-07-31 (or earlier trading day)."""
        _, end = _expand_month_bound("2026-07")
        assert end >= "2026-07-31" or end == "2026-07-31"


class TestMonthEndsHelper:
    def test_last_trading_day_per_month(self):
        dates = ["2026-06-01", "2026-06-30", "2026-07-01", "2026-07-15", "2026-08-20"]
        assert _month_ends(dates) == ["2026-06-30", "2026-07-15", "2026-08-20"]


class TestComputeExposure:
    def test_min_samples_gate(self):
        """< min_samples (400 for 500-day window) returns None."""
        dates = [f"2025-01-{i:02d}" for i in range(2, 21)]  # 20 days
        asset = list(zip(dates, np.random.RandomState(0).normal(0, 0.01, 20)))
        factors = {"f1": list(zip(dates, np.random.RandomState(1).normal(0, 0.01, 20)))}
        assert compute_exposure(asset, factors, window_days=500) is None

    def test_recovers_known_beta(self):
        rs = np.random.RandomState(42)
        n = 450
        f1 = rs.normal(0, 0.01, n)
        f2 = rs.normal(0, 0.01, n)
        asset_ret = 0.3 + 1.5 * f1 + (-0.7) * f2 + rs.normal(0, 1e-6, n)
        from datetime import date, timedelta
        d0 = date(2024, 1, 1)
        dates = [(d0 + timedelta(days=i)).isoformat() for i in range(n)]
        res = compute_exposure(
            list(zip(dates, asset_ret)),
            {"f1": list(zip(dates, f1)), "f2": list(zip(dates, f2))},
            window_days=500,
        )
        assert res is not None
        assert abs(res["betas"]["f1"] - 1.5) < 0.05
        assert abs(res["betas"]["f2"] - (-0.7)) < 0.05
        assert res["as_of"] == dates[-1]
