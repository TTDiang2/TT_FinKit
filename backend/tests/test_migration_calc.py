"""Tests for migration_calc module - fund position migration reverse-calculation.

The migration algorithm converts user-recorded amount-only entries into real share
quantity entries by reverse-engineering shares from historical NAV (Net Asset Value).
"""
from app.services.migration_calc import compute_shares, pick_nearest_nav, build_migration_entries


def test_compute_shares():
    # Normal case: 5000 / 1.25 = 4000
    assert compute_shares(5000.0, 1.25) == 4000.0
    # Zero amount -> zero shares
    assert compute_shares(0, 1.25) == 0.0
    # Zero NAV -> division-by-zero protection
    assert compute_shares(5000.0, 0) == 0.0


def test_pick_nearest_nav_exact():
    s = [{"date": "2024-01-02", "close": 1.1},
         {"date": "2024-01-03", "close": 1.2},
         {"date": "2024-01-04", "close": 1.3}]
    # Exact match returns that point
    assert pick_nearest_nav("2024-01-03", s) == ("2024-01-03", 1.2)


def test_pick_nearest_nav_before_market_open():
    s = [{"date": "2024-01-02", "close": 1.1},
         {"date": "2024-01-03", "close": 1.2}]
    # Target 2024-01-01 is earlier than the earliest data point
    # -> None (cannot reverse-calculate, no historical data available)
    assert pick_nearest_nav("2024-01-01", s) is None


def test_pick_nearest_nav_weekend():
    s = [{"date": "2024-01-05", "close": 1.1},
         {"date": "2024-01-08", "close": 1.2}]  # 6/7 weekend, no data
    # Target 2024-01-06 (Saturday) -> nearest preceding trading day 01-05
    assert pick_nearest_nav("2024-01-06", s) == ("2024-01-05", 1.1)


def test_build_migration_entries():
    inputs = [{"date": "2024-01-03", "amount": 5000.0},
              {"date": "2024-01-10", "amount": 3000.0}]
    fake_series = [{"date": "2024-01-03", "close": 1.25},
                   {"date": "2024-01-10", "close": 1.30}]
    # nav_fetcher is an injected callable; here it ignores its argument
    out = build_migration_entries(inputs, lambda dates: fake_series)
    assert out[0] == {"date": "2024-01-03", "amount": 5000.0, "nav": 1.25, "shares": 4000.0}
    # 3000 / 1.30 = 2307.6923... rounded to 2 decimal places -> 2307.69
    assert out[1]["shares"] == 2307.69