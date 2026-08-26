"""market_data middleware 行为测试：回退链/超时/全败/收益计算。"""
import time

import pytest

from app.services import market_data


def _install_chain(monkeypatch, chain):
    monkeypatch.setattr(market_data, "CHAINS", {"test": chain})


def test_fetch_closes_falls_back_until_first_success(monkeypatch):
    calls: list[str] = []

    def boom(code: str):
        calls.append("boom")
        raise RuntimeError("down")

    def empty(code: str):
        calls.append("empty")
        return []

    def ok(code: str):
        calls.append("ok")
        return [("2026-01-02", 2.0), ("2026-01-03", 2.1)]

    _install_chain(monkeypatch, [("boom", boom), ("empty", empty), ("ok", ok)])
    series = market_data.fetch_closes("X", chain="test")

    assert series == [("2026-01-02", 2.0), ("2026-01-03", 2.1)]
    assert calls == ["boom", "empty", "ok"]
    assert market_data.last_provider_report().get("X") == "ok"


def test_fetch_closes_all_fail_raises_with_reasons(monkeypatch):
    def boom(code: str):
        raise RuntimeError("down")

    _install_chain(monkeypatch, [("boom", boom)])
    with pytest.raises(RuntimeError, match="所有数据源均失败.*boom"):
        market_data.fetch_closes("X", chain="test")


def test_fetch_closes_timeout_skips_provider(monkeypatch):
    def slow(code: str):
        time.sleep(2)
        return [("2026-01-02", 9.9)]

    def ok(code: str):
        return [("2026-01-02", 1.0)]

    monkeypatch.setattr(market_data, "_PROVIDER_TIMEOUT_S", 0.1)
    _install_chain(monkeypatch, [("slow", slow), ("ok", ok)])

    series = market_data.fetch_closes("X", chain="test")
    assert series == [("2026-01-02", 1.0)]
    assert market_data.last_provider_report().get("X") == "ok"


def test_fetch_returns_computes_pct(monkeypatch):
    def ok(code: str):
        return [("2026-01-02", 2.0), ("2026-01-03", 2.1), ("2026-01-04", 2.0)]

    _install_chain(monkeypatch, [("ok", ok)])
    rets = market_data.fetch_returns("X", chain="test")

    assert len(rets) == 2
    assert rets[0][0] == "2026-01-03"
    assert rets[0][1] == pytest.approx(0.05)
    assert rets[1][1] == pytest.approx(2.0 / 2.1 - 1.0)


def test_yf_symbol_mapping():
    assert market_data.yf_symbol_for("日经225") == "^N225"
    assert market_data.yf_symbol_for("恒生指数") == "^HSI"
    assert market_data.yf_symbol_for("000300") == "000300.SS"
    assert market_data.yf_symbol_for("399006") == "399006.SZ"
    assert market_data.yf_symbol_for("^GSPC") == "^GSPC"
    assert market_data.yf_symbol_for("不存在指数") is None
