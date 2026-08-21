"""Money-market fund parsing — offline tests on synthetic payload snippets."""
import asyncio

from app.services import money_market_fund as mmf


def test_slice_pairs():
    text = 'Data_millionCopiesIncome=[[1739577600000,0.5442],[1739664000000,0.5531]];'
    pairs = mmf._slice_pairs(text, "Data_millionCopiesIncome")
    assert pairs == [(1739577600000, 0.5442), (1739664000000, 0.5531)]


def test_slice_pairs_missing_marker():
    assert mmf._slice_pairs("no marker here", "Data_whatever") == []


def test_slice_pairs_empty_array():
    assert mmf._slice_pairs('Data_x=[];', "Data_x") == []


def test_money_market_nav_series_filters_window():
    text = 'Data_millionCopiesIncome=[[1739577600000,0.5],[1739664000000,0.5],[1739750400000,0.5]];'
    series = mmf.money_market_nav_series(text, "2025-02-15", "2025-02-16")
    assert [p["date"] for p in series] == ["2025-02-15", "2025-02-16"]
    assert all(p["close"] == 1.0 for p in series)


def test_money_market_nav_series_empty_window():
    text = 'Data_millionCopiesIncome=[[1739577600000,0.5]];'
    assert mmf.money_market_nav_series(text, "2030-01-01", "2030-01-02") == []


def test_mmf_shares_by_date_no_events():
    assert asyncio.run(mmf.mmf_shares_by_date("163820", ["2026-01-01"], [])) == {}