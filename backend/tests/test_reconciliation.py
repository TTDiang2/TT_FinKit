"""Reconciliation 纯计算逻辑测试（不依赖 DB）。"""
from app.routers.reconciliation import (
    map_bank_expected,
    calc_expected_balance,
    calc_unrecorded_months,
    resolve_bank_formula,
    normalize_bank_formula,
    formula_text,
    _formula_matches_preset,
)
from datetime import datetime


# ---- map_bank_expected（公式引擎）----

DIRECT = {"income": ["income"], "expense": ["expense_net"]}
COMPOSITE = {"income": ["transfer_in", "refund", "income"], "expense": ["expense_positive"]}


def test_direct_formula():
    out = map_bank_expected(
        DIRECT,
        income_total=18000.0,
        expense_net=5432.1, expense_positive=5612.9,
        refund_abs=180.8, transfer_in=3000.0,
    )
    assert out == {"income": 18000.0, "expense": 5432.1}


def test_composite_formula():
    out = map_bank_expected(
        COMPOSITE,
        income_total=20.5,
        expense_net=5432.1, expense_positive=5612.9,
        refund_abs=180.8, transfer_in=3000.0,
    )
    assert out == {"income": 3201.3, "expense": 5612.9}


def test_composite_no_income():
    out = map_bank_expected(
        COMPOSITE,
        income_total=0,
        expense_net=100.0, expense_positive=100.0,
        refund_abs=0, transfer_in=0,
    )
    assert out == {"income": 0.0, "expense": 100.0}


def test_custom_formula():
    custom = {"income": ["transfer_in", "income"], "expense": ["expense_positive"]}
    out = map_bank_expected(
        custom,
        income_total=500.0,
        expense_net=100.0, expense_positive=200.0,
        refund_abs=50.0, transfer_in=1000.0,
    )
    assert out == {"income": 1500.0, "expense": 200.0}


# ---- 公式解析/清洗 ----

class _FakeAccount:
    def __init__(self, mode="direct", formula=None):
        self.bank_statement_mode = mode
        self.bank_formula = formula


def test_resolve_preset_by_mode():
    assert resolve_bank_formula(_FakeAccount("composite")) == COMPOSITE
    assert resolve_bank_formula(_FakeAccount("direct")) == DIRECT
    assert resolve_bank_formula(_FakeAccount("unknown")) == DIRECT
    assert resolve_bank_formula(_FakeAccount(None)) == DIRECT


def test_resolve_custom_formula():
    import json
    custom = {"income": ["transfer_in"], "expense": ["expense_net"]}
    acc = _FakeAccount(formula=json.dumps(custom))
    assert resolve_bank_formula(acc) == custom


def test_resolve_invalid_json_falls_back():
    acc = _FakeAccount("composite", formula="not-json")
    assert resolve_bank_formula(acc) == COMPOSITE


def test_resolve_unknown_components_stripped():
    acc = _FakeAccount(formula='{"income": ["transfer_in", "hack"], "expense": ["expense_net"]}')
    assert resolve_bank_formula(acc) == {"income": ["transfer_in"], "expense": ["expense_net"]}


def test_normalize_valid_and_invalid():
    assert normalize_bank_formula({"income": ["income"], "expense": ["expense_net"]}) == {
        "income": ["income"], "expense": ["expense_net"]}
    assert normalize_bank_formula({"income": [], "expense": []}) is None
    assert normalize_bank_formula(None) is None
    assert normalize_bank_formula({"income": ["bogus"], "expense": ["expense_net"]}) is None


def test_formula_matches_preset():
    assert _formula_matches_preset(DIRECT) == "direct"
    assert _formula_matches_preset(COMPOSITE) == "composite"
    assert _formula_matches_preset({"income": ["transfer_in"], "expense": ["expense_net"]}) == "custom"


def test_formula_text():
    assert "银行收入" in formula_text(COMPOSITE)
    assert "转入转账" in formula_text(COMPOSITE)
    assert "正支出合计" in formula_text(COMPOSITE)


# ---- calc_expected_balance（转账计入余额）----

def test_expected_balance_formula():
    assert calc_expected_balance(1000.0, 5000.0, 3200.0) == 2800.0
    assert calc_expected_balance(0.0, 0.0, 0.0) == 0.0
    assert calc_expected_balance(1000.0, 5000.0, 3200.0 - 180.8) == 2980.8


def test_expected_balance_with_transfers():
    assert calc_expected_balance(1000.0, 5000.0, 3200.0, transfer_in=2000.0, transfer_out=500.0) == 4300.0


# ---- calc_unrecorded_months ----

def test_unrecorded_last_in_current_month():
    now = datetime(2026, 8, 12)
    assert calc_unrecorded_months("2026-08-05", now) == []


def test_unrecorded_last_previous_month():
    now = datetime(2026, 8, 12)
    assert calc_unrecorded_months("2026-07-31", now) == ["2026-08"]


def test_unrecorded_several_months():
    now = datetime(2026, 8, 12)
    assert calc_unrecorded_months("2026-06-30", now) == ["2026-07", "2026-08"]


def test_unrecorded_none():
    assert calc_unrecorded_months(None) == []


def test_unrecorded_cross_year():
    now = datetime(2026, 2, 5)
    assert calc_unrecorded_months("2025-12-20", now) == ["2026-01", "2026-02"]
