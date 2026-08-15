"""Reconciliation 纯计算逻辑测试（不依赖 DB）。"""
from app.routers.reconciliation import (
    map_bank_expected,
    is_interest_category,
    calc_expected_balance,
    calc_unrecorded_months,
)
from datetime import datetime


# ---- map_bank_expected ----

def test_direct_mode():
    # 工资账户：银行收入 = 系统收入合计；银行支出 = 系统支出净额
    out = map_bank_expected(
        mode="direct",
        income_total=18000.0, interest=20.5,
        expense_net=5432.1, expense_positive=5612.9,
        refund_abs=180.8, transfer_in=3000.0,
    )
    assert out == {"income": 18000.0, "expense": 5432.1}


def test_composite_mode():
    # 消费账户：银行收入 = 转账 + 退款 + 利息；银行支出 = 毛消费（正支出合计）
    out = map_bank_expected(
        mode="composite",
        income_total=20.5, interest=20.5,
        expense_net=5432.1, expense_positive=5612.9,
        refund_abs=180.8, transfer_in=3000.0,
    )
    assert out == {"income": 3201.3, "expense": 5612.9}  # 3000 + 180.8 + 20.5


def test_composite_no_income():
    out = map_bank_expected(
        mode="composite",
        income_total=0, interest=0,
        expense_net=100.0, expense_positive=100.0,
        refund_abs=0, transfer_in=0,
    )
    assert out == {"income": 0.0, "expense": 100.0}


# ---- is_interest_category ----

def test_interest_detection():
    assert is_interest_category("利息")
    assert is_interest_category("银行利息")
    assert is_interest_category("建行利息")
    assert not is_interest_category("工资")
    assert not is_interest_category("退款")
    assert not is_interest_category(None)
    assert not is_interest_category("")


# ---- calc_expected_balance ----

def test_expected_balance_formula():
    assert calc_expected_balance(1000.0, 5000.0, 3200.0) == 2800.0
    assert calc_expected_balance(0.0, 0.0, 0.0) == 0.0
    # 退款（负支出）会减少支出合计
    assert calc_expected_balance(1000.0, 5000.0, 3200.0 - 180.8) == 2980.8


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
