"""Unit-method NAV must be cash-flow immune: buys/redeems/deposits/withdrawals
must never cause a NAV jump (the whole point of the fund-of-funds unit method).
"""
from app.services.portfolio_nav import build_portfolio_nav, snap_date


def test_snap_date():
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    assert snap_date("2026-01-01", dates) == "2026-01-05"  # holiday -> next NAV day
    assert snap_date("2026-01-06", dates) == "2026-01-06"  # exact hit
    assert snap_date("2026-01-09", dates) == "2026-01-08"  # past window -> last
    assert snap_date("2025-12-31", dates) == "2026-01-05"


def _dates(n: int) -> list[str]:
    return [f"2026-01-{d:02d}" for d in range(1, n + 1)]


def _mk_assets(dates: list[str], fund_navs: dict, qty_by_date: dict, cash_by_date: dict,
               deposit_by_date: dict | None = None, withdrawal_by_date: dict | None = None) -> dict:
    return build_portfolio_nav(
        dates,
        {"A": fund_navs},
        {"A": qty_by_date},
        cash_by_date,
        deposit_by_date or {},
        withdrawal_by_date or {},
    )


def test_deposit_and_buy_do_not_jump_nav():
    dates = _dates(20)
    navs = {d: 1.0 + 0.001 * i for i, d in enumerate(dates)}  # fund drifts +0.1%/day
    # day1: deposit 10000; day2: buy 5000 @ 1.001; day3: buy 5000 @ 1.002
    qty = {}
    for i, d in enumerate(dates):
        qty[d] = 10000.0 if i >= 2 else 5000.0 if i >= 1 else 0.0
    cash = {}
    cum = 0.0
    for i, d in enumerate(dates):
        if i == 0:
            cum += 10000.0
        elif i == 1:
            cum -= 5000 * 1.001
        elif i == 2:
            cum -= 5000 * 1.002
        cash[d] = cum
    res = _mk_assets(dates, navs, qty, cash, {dates[0]: 10000.0})
    series = res["series"]
    assert len(series) == len(dates)
    assert series[0]["nav"] == 10000.0
    for prev, cur in zip(series, series[1:]):
        ratio = cur["nav"] / prev["nav"]
        # fund drift is 0.1%/day; a buy/sell day must stay inside 0.3%
        assert 0.997 <= ratio <= 1.003, f"NAV jumped: {prev['date']}->{cur['date']} {ratio}"


def test_negative_cash_must_not_jump_nav():
    # Same setup but the second buy overdraws the account (negative cash).
    # The old max(0, ...) clamp made NAV jump the moment deposits caught up.
    dates = _dates(20)
    navs = {d: 1.0 + 0.001 * i for i, d in enumerate(dates)}
    qty = {}
    for i, d in enumerate(dates):
        qty[d] = 10000.0 if i >= 2 else 5000.0 if i >= 1 else 0.0
    cash = {}
    cum = 0.0
    for i, d in enumerate(dates):
        if i == 0:
            cum += 10000.0
        elif i == 1:
            cum -= 5000 * 1.001
        elif i == 2:
            cum -= 5000 * 1.002
        elif i == 5:  # deposit catches up later
            cum += 10000.0
        cash[d] = cum
    res = _mk_assets(dates, navs, qty, cash, {dates[0]: 10000.0, dates[5]: 10000.0})
    series = res["series"]
    for prev, cur in zip(series, series[1:]):
        ratio = cur["nav"] / prev["nav"]
        assert 0.997 <= ratio <= 1.003, f"NAV jumped: {prev['date']}->{cur['date']} {ratio}"


def test_full_redeem_keeps_nav_continuous():
    dates = _dates(20)
    navs = {d: 1.0 + 0.001 * i for i, d in enumerate(dates)}
# buy all on day1, redeem everything on day10
    qty = {}
    for i, d in enumerate(dates):
        qty[d] = 10000.0 if 1 <= i < 10 else 0.0
    cash = {}
    cum = 10000.0  # deposit day0
    for i, d in enumerate(dates):
        if i == 1:
            cum -= 10000.0 * navs[d]
        elif i == 10:
            cum += 10000.0 * navs[d]
        cash[d] = cum
    res = _mk_assets(dates, navs, qty, cash, {dates[0]: 10000.0})
    series = res["series"]
    assert len(series) == len(dates)  # all days present, none skipped
    for prev, cur in zip(series, series[1:]):
        ratio = cur["nav"] / prev["nav"]
        assert 0.997 <= ratio <= 1.003, f"NAV jumped around redeem: {prev['date']}->{cur['date']} {ratio}"
    assert all(p["nav"] > 0 for p in series)


def test_empty_portfolio_skipped():
    dates = _dates(5)
    res = build_portfolio_nav(dates, {}, {}, {}, {}, {})
    assert res["series"] == []


def test_withdrawal_redeems_units():
    dates = _dates(20)
    navs = {d: 1.0 + 0.001 * i for i, d in enumerate(dates)}
    qty = {}
    for i, d in enumerate(dates):
        qty[d] = 5000.0 if i >= 1 else 0.0
    cash = {}
    cum = 10000.0
    for i, d in enumerate(dates):
        if i == 1:
            cum -= 5000.0 * navs[d]
        elif i == 10:
            cum -= 2000.0  # withdrawal reduces available cash
        cash[d] = cum
    res = _mk_assets(dates, navs, qty, cash, {dates[0]: 10000.0}, {dates[10]: 2000.0})
    series = res["series"]
    for prev, cur in zip(series, series[1:]):
        ratio = cur["nav"] / prev["nav"]
        assert 0.997 <= ratio <= 1.003, f"NAV jumped at withdrawal: {prev['date']}->{cur['date']} {ratio}"


def test_weekend_nav_gap_must_not_jump():
    """Regression for the 2025-08-24 → 2025-08-25 production jump.

    A money-market fund publishes NAV on weekends (always 1.0), which keeps the
    calendar alive on Sat/Sun. A regular OTC fund held since BEFORE the window
    has no weekend NAV data point. Previously the holding was silently dropped
    on weekend dates (`if qty and nav` skipped it), then "appeared" on Monday,
    producing a ~+5000 NAV jump. Holdings must be valued at the fund's first
    known NAV on dates before its series starts.
    """
    dates = _dates(7)  # Mon..Sun
    # Fund A: money-market, NAV every day = 1.0
    # Fund B: OTC fund, NAV only on trading days (Mon..Fri), no Sat/Sun
    navs_b = {d: 2.0 for i, d in enumerate(dates) if i < 5}  # missing Sat(index5)/Sun(6)
    fund_navs = {"A": {d: 1.0 for d in dates}, "B": navs_b}
    qty_by_date = {"A": {d: 1000.0 for d in dates}, "B": {d: 1000.0 for d in dates}}
    cash_by_date = {d: 0.0 for d in dates}
    res = build_portfolio_nav(dates, fund_navs, qty_by_date, cash_by_date, {}, {})
    series = res["series"]
    assert len(series) == len(dates)
    for prev, cur in zip(series, series[1:]):
        ratio = cur["nav"] / prev["nav"]
        assert 0.997 <= ratio <= 1.003, f"NAV jumped over weekend: {prev['date']}->{cur['date']} {ratio}"


def test_fund_nav_starts_after_holding_appears():
    """Fund B's NAV series starts mid-window; holdings exist from day 0.
    The first dates must value B at its first known NAV, not drop it."""
    dates = _dates(6)
    fund_navs = {"A": {d: 1.0 for d in dates}, "B": {dates[2]: 3.0, dates[3]: 3.0, dates[4]: 3.0, dates[5]: 3.0}}
    qty_by_date = {"A": {d: 1000.0 for d in dates}, "B": {d: 2000.0 for d in dates}}
    cash_by_date = {d: 0.0 for d in dates}
    res = build_portfolio_nav(dates, fund_navs, qty_by_date, cash_by_date, {}, {})
    series = res["series"]
    # value[0] should already include B: 1000*1 + 2000*3 = 7000
    assert abs(series[0]["total_value"] - 7000.0) < 0.01, f"expected 7000, got {series[0]}"
    for prev, cur in zip(series, series[1:]):
        ratio = cur["nav"] / prev["nav"]
        assert 0.997 <= ratio <= 1.003, f"NAV jumped when B series starts: {prev['date']}->{cur['date']} {ratio}"