"""Tests for fund_classify module.

TDD: these tests are written FIRST (RED phase) before fund_classify.py exists.
They cover:
  - exact-match classification by underlying_asset_type
  - keyword-match classification by fund name fallback
  - unknown → "其他"
  - default benchmark (symbol, exchange) per asset class
"""
from app.services.fund_classify import classify_asset_class, default_benchmark


def test_classify_by_underlying():
    assert classify_asset_class("黄金", "") == "黄金"
    assert classify_asset_class("原油", "") == "原油"
    assert classify_asset_class("美股", "") == "美股"
    assert classify_asset_class("股票", "") == "A股"  # A股股票基金


def test_classify_by_name_fallback():
    assert classify_asset_class("", "华安黄金ETF联接C") == "黄金"
    assert classify_asset_class("", "广发道琼斯石油指数") == "原油"
    assert classify_asset_class("", "汇添富纳斯达克生物科") == "美股"
    assert classify_asset_class("", "诺安油气能源") == "油气"


def test_classify_unknown():
    assert classify_asset_class("", "某不知名基金") == "其他"


def test_default_benchmark():
    assert default_benchmark("黄金") == ("AU8888.SH", "SH")
    assert default_benchmark("原油") == ("", "")
    assert default_benchmark("美股") == (".IXIC", "US")
    assert default_benchmark("A股") == ("000300.SH", "SH")
    assert default_benchmark("其他") == ("", "")