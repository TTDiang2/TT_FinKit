"""校验（Reconciliation）模块路由。

按账户 + 月份做银行口径映射核对（第 1 层），以及今日余额核对（第 3 层）。
银行口径映射公式见 docs/BOOKKEEPING.md §3。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_private_db
from ..models.account import Account
from ..models.transaction import Transaction
from ..models.reconciliation import ReconciliationRecord
from ..middleware.auth import get_current_user_id

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])


# --------------------------------------------------------------------------- #
# 校验口径公式引擎（银行收支换算）
# --------------------------------------------------------------------------- #

# 每个账户可自定义：银行收入/支出 各由哪些系统口径分项求和组成。
# 分项（收入侧）：transfer_in=转入转账，refund=退款绝对值，income=收入合计
# 分项（支出侧）：expense_positive=正支出合计（毛支出），expense_net=支出净额（含退款冲销）
VALID_INCOME_COMPONENTS = {"transfer_in", "refund", "income"}
VALID_EXPENSE_COMPONENTS = {"expense_positive", "expense_net"}

BANK_FORMULA_PRESETS = {
    "direct": {"income": ["income"], "expense": ["expense_net"]},
    "composite": {"income": ["transfer_in", "refund", "income"], "expense": ["expense_positive"]},
}

COMPONENT_LABELS = {
    "transfer_in": "转入转账",
    "refund": "退款（负支出绝对值）",
    "income": "收入合计",
    "expense_positive": "正支出合计（毛支出）",
    "expense_net": "支出净额（正支出−退款）",
}


def _formula_matches_preset(formula: dict) -> Optional[str]:
    for name, preset in BANK_FORMULA_PRESETS.items():
        if (sorted(formula.get("income", [])) == sorted(preset["income"])
                and sorted(formula.get("expense", [])) == sorted(preset["expense"])):
            return name
    return "custom"


def resolve_bank_formula(account: Account) -> dict:
    """返回账户的校验口径公式 {income: [...], expense: [...]}。

    优先用自定义 bank_formula（JSON，非法则忽略）；否则按 bank_statement_mode 预设回退。
    """
    if getattr(account, "bank_formula", None):
        try:
            f = json.loads(account.bank_formula)
            inc = [c for c in f.get("income", []) if c in VALID_INCOME_COMPONENTS]
            exp = [c for c in f.get("expense", []) if c in VALID_EXPENSE_COMPONENTS]
            if inc and exp:
                return {"income": inc, "expense": exp}
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    return dict(BANK_FORMULA_PRESETS.get(account.bank_statement_mode or "direct", BANK_FORMULA_PRESETS["direct"]))


def normalize_bank_formula(raw: dict | None) -> dict | None:
    """清洗并校验前端提交的公式；非法返回 None。"""
    if not raw:
        return None
    inc = [c for c in raw.get("income", []) if c in VALID_INCOME_COMPONENTS]
    exp = [c for c in raw.get("expense", []) if c in VALID_EXPENSE_COMPONENTS]
    if not inc or not exp:
        return None
    return {"income": list(dict.fromkeys(inc)), "expense": list(dict.fromkeys(exp))}


def formula_text(formula: dict) -> str:
    income_part = " + ".join(COMPONENT_LABELS.get(c, c) for c in formula.get("income", []))
    expense_part = " + ".join(COMPONENT_LABELS.get(c, c) for c in formula.get("expense", []))
    return f"银行收入 = {income_part}；银行支出 = {expense_part}"


def map_bank_expected(formula: dict, income_total: float, expense_net: float,
                      expense_positive: float, refund_abs: float, transfer_in: float) -> dict:
    """按账户校验口径公式，把系统侧数字映射为银行期望收入/支出。"""
    parts = {
        "transfer_in": transfer_in,
        "refund": refund_abs,
        "income": income_total,
        "expense_positive": expense_positive,
        "expense_net": expense_net,
    }
    income = round(sum(parts[c] for c in formula["income"]), 2)
    expense = round(sum(parts[c] for c in formula["expense"]), 2)
    return {"income": income, "expense": expense}


def calc_expected_balance(initial_balance: float, total_income: float, total_expense: float,
                          transfer_in: float = 0.0, transfer_out: float = 0.0) -> float:
    """期望余额 = 期初 + 收入 − 支出 + 转入 − 转出（转账计入余额，口径无关）。"""
    return initial_balance + total_income - total_expense + transfer_in - transfer_out


def calc_unrecorded_months(last_recorded_date: Optional[str], now: Optional[datetime] = None) -> List[str]:
    """返回从 last_recorded_date 所在月的下一个月起、到当前月（含）之间未记的月份。

    若 last_recorded_date 已在当前月 -> 空列表（可核对）。
    无记录日期 -> 返回空（由调用方处理 can_check=false）。
    """
    if not last_recorded_date:
        return []
    now = now or datetime.now()
    try:
        last_dt = datetime.strptime(last_recorded_date, "%Y-%m-%d")
    except ValueError:
        return []
    last_month = last_dt.year * 12 + (last_dt.month - 1)  # 绝对月序号
    cur_month = now.year * 12 + (now.month - 1)
    if last_month >= cur_month:
        return []
    months = []
    for m in range(last_month + 1, cur_month + 1):
        months.append(f"{m // 12}-{m % 12 + 1:02d}")
    return months


# --------------------------------------------------------------------------- #
# 数据查询
# --------------------------------------------------------------------------- #

async def _get_owned_account(db: AsyncSession, user_id: str, account_id: str) -> Account:
    acc = (
        await db.execute(
            select(Account).where(Account.id == account_id, Account.user_id == user_id)
        )
    ).scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="账户不存在")
    return acc


async def _account_summary(db: AsyncSession, user_id: str, account: Account, year: int, month: int) -> dict:
    """计算某账户某月的拆分数字（收入/支出/退款/转入），并按校验口径公式映射银行期望值。"""
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"
    start = f"{year}-{month:02d}-01"

    # 收入合计
    income_total = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id,
                    Transaction.type == "income",
                    Transaction.account_id == account.id,
                    Transaction.date >= start,
                    Transaction.date < end,
                )
            )
        ).scalar()
        or 0
    )

    # 支出拆分：net / positive / refund
    exp_txns = (
        await db.execute(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.type == "expense",
                Transaction.account_id == account.id,
                Transaction.date >= start,
                Transaction.date < end,
            )
        )
    ).scalars().all()
    expense_net = 0.0
    expense_positive = 0.0
    refund = 0.0
    for txn in exp_txns:
        amt = txn.amount or 0
        expense_net += amt
        if amt >= 0:
            expense_positive += amt
        else:
            refund += amt

    # 转入转账（dest_account_id == 本账户）
    transfer_in = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id,
                    Transaction.type == "transfer",
                    Transaction.dest_account_id == account.id,
                    Transaction.date >= start,
                    Transaction.date < end,
                )
            )
        ).scalar()
        or 0
    )

    formula = resolve_bank_formula(account)
    bank_expected = map_bank_expected(
        formula, income_total,
        expense_net, expense_positive,
        abs(refund), transfer_in,
    )

    return {
        "account_id": account.id,
        "account_name": account.name,
        "account_type": account.account_type,
        "bank_statement_mode": account.bank_statement_mode or "direct",
        "bank_formula": formula,
        "formula_text": formula_text(formula),
        "year": year,
        "month": month,
        "income_breakdown": {"total": round(income_total, 2)},
        "expense_breakdown": {
            "net": round(expense_net, 2),
            "positive": round(expense_positive, 2),
            "refund": round(refund, 2),
            "refund_abs": round(abs(refund), 2),
        },
        "transfer_in": round(transfer_in, 2),
        "bank_expected": bank_expected,
    }


async def _expected_balance(db: AsyncSession, user_id: str, account: Account) -> dict:
    """今日余额核对：期望余额 + 未记月份。转账计入余额（口径无关）。"""
    total_income = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id,
                    Transaction.type == "income",
                    Transaction.account_id == account.id,
                )
            )
        ).scalar()
        or 0
    )
    total_expense = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id,
                    Transaction.type == "expense",
                    Transaction.account_id == account.id,
                )
            )
        ).scalar()
        or 0
    )
    transfer_in = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id,
                    Transaction.type == "transfer",
                    Transaction.dest_account_id == account.id,
                )
            )
        ).scalar()
        or 0
    )
    transfer_out = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id,
                    Transaction.type == "transfer",
                    Transaction.account_id == account.id,
                )
            )
        ).scalar()
        or 0
    )
    last_date = (
        await db.execute(
            select(func.max(Transaction.date)).where(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
            )
        )
    ).scalar()

    expected = calc_expected_balance(
        account.initial_balance or 0, total_income, total_expense,
        transfer_in, transfer_out,
    )
    unrecorded = calc_unrecorded_months(last_date)
    can_check = bool(last_date) and not unrecorded

    if not last_date:
        hint = "该账户暂无流水，请先补记"
    elif unrecorded:
        hint = f"还有 {'、'.join(unrecorded)} 未记完，请先补记或用月度汇总核对"
    else:
        hint = "该账户已记到当前月，可以核对今日余额（= 期初 + 收入 − 支出 + 转入 − 转出）"

    return {
        "account_id": account.id,
        "account_name": account.name,
        "expected_balance": round(expected, 2),
        "last_recorded_date": last_date,
        "unrecorded_months": unrecorded,
        "can_check": can_check,
        "hint": hint,
    }


# --------------------------------------------------------------------------- #
# 端点
# --------------------------------------------------------------------------- #

@router.get("/account-summary")
async def get_account_summary(
    account_id: str,
    year: int,
    month: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """第 1 层：月度汇总核对 —— 返回该账户该月系统侧映射后的数字。"""
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="month 必须在 1-12 之间")
    account = await _get_owned_account(db, user_id, account_id)
    return await _account_summary(db, user_id, account, year, month)


@router.get("/expected-balance")
async def get_expected_balance(
    account_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """第 3 层：今日余额核对 —— 系统期望余额 + 未记月份提示。"""
    account = await _get_owned_account(db, user_id, account_id)
    return await _expected_balance(db, user_id, account)


class RecordCreate(BaseModel):
    account_id: str
    year: int
    month: int  # 0 = 余额核对；1-12 = 月度汇总
    bank_income: Optional[float] = None
    bank_expense: Optional[float] = None
    balance_check_actual: Optional[float] = None
    notes: str = ""


@router.post("/records", status_code=201)
async def create_record(
    req: RecordCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """保存一条校验记录（自动保存：后端重算 sys 值与差异）。"""
    account = await _get_owned_account(db, user_id, req.account_id)

    if req.month == 0:
        # 余额核对变体
        if req.balance_check_actual is None:
            raise HTTPException(status_code=422, detail="余额核对需要 balance_check_actual")
        eb = await _expected_balance(db, user_id, account)
        expected = eb["expected_balance"]
        actual = round(float(req.balance_check_actual), 2)
        diff = round(actual - expected, 2)
        rec = ReconciliationRecord(
            user_id=user_id,
            account_id=account.id,
            year=req.year,
            month=0,
            balance_check_expected=expected,
            balance_check_actual=actual,
            balance_diff=diff,
            status="matched" if abs(diff) < 0.005 else "diff",
            notes=req.notes,
        )
    else:
        # 月度汇总变体
        if req.month < 1 or req.month > 12:
            raise HTTPException(status_code=422, detail="month 必须在 0-12 之间")
        if req.bank_income is None or req.bank_expense is None:
            raise HTTPException(status_code=422, detail="月度汇总核对需要 bank_income 和 bank_expense")
        summary = await _account_summary(db, user_id, account, req.year, req.month)
        sys_income = summary["bank_expected"]["income"]
        sys_expense = summary["bank_expected"]["expense"]
        bank_income = round(float(req.bank_income), 2)
        bank_expense = round(float(req.bank_expense), 2)
        income_diff = round(bank_income - sys_income, 2)
        expense_diff = round(bank_expense - sys_expense, 2)
        rec = ReconciliationRecord(
            user_id=user_id,
            account_id=account.id,
            year=req.year,
            month=req.month,
            bank_income=bank_income,
            bank_expense=bank_expense,
            sys_income=sys_income,
            sys_expense=sys_expense,
            income_diff=income_diff,
            expense_diff=expense_diff,
            status="matched" if abs(income_diff) < 0.005 and abs(expense_diff) < 0.005 else "diff",
            notes=req.notes,
        )

    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return _to_record_dict(rec)


@router.get("/records")
async def list_records(
    account_id: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    query = select(ReconciliationRecord).where(ReconciliationRecord.user_id == user_id)
    if account_id:
        query = query.where(ReconciliationRecord.account_id == account_id)
    if year:
        query = query.where(ReconciliationRecord.year == year)
    if month is not None:
        query = query.where(ReconciliationRecord.month == month)
    query = query.order_by(
        ReconciliationRecord.year.desc(),
        ReconciliationRecord.month.desc(),
        ReconciliationRecord.checked_at.desc(),
    )
    rows = (await db.execute(query)).scalars().all()
    return [_to_record_dict(r) for r in rows]


@router.delete("/records/{record_id}")
async def delete_record(
    record_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    rec = (
        await db.execute(
            select(ReconciliationRecord).where(
                ReconciliationRecord.id == record_id,
                ReconciliationRecord.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="校验记录不存在")
    await db.delete(rec)
    await db.commit()
    return {"ok": True}


def _to_record_dict(r: ReconciliationRecord) -> dict:
    return {
        "id": r.id,
        "account_id": r.account_id,
        "year": r.year,
        "month": r.month,
        "bank_income": r.bank_income,
        "bank_expense": r.bank_expense,
        "sys_income": r.sys_income,
        "sys_expense": r.sys_expense,
        "income_diff": r.income_diff,
        "expense_diff": r.expense_diff,
        "balance_check_expected": r.balance_check_expected,
        "balance_check_actual": r.balance_check_actual,
        "balance_diff": r.balance_diff,
        "status": r.status,
        "notes": r.notes,
        "checked_at": str(r.checked_at) if r.checked_at else "",
    }
