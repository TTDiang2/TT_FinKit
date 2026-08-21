from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..database import get_db
from ..models.account import Account
from ..models.transaction import Transaction
from ..schemas.account import AccountCreate, AccountUpdate, AccountResponse, BankFormula
from ..middleware.auth import get_current_user_id
from .reconciliation import _formula_matches_preset
from typing import List
import json

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _serialize_formula(formula) -> str:
    if isinstance(formula, BankFormula):
        return json.dumps(formula.model_dump(), ensure_ascii=False)
    return json.dumps(formula, ensure_ascii=False)


def _apply_formula(account: Account, formula) -> None:
    account.bank_formula = _serialize_formula(formula)
    account.bank_statement_mode = _formula_matches_preset(formula if isinstance(formula, dict) else formula.model_dump())


def _formula_from_model(account: Account) -> BankFormula | None:
    if account.bank_formula:
        try:
            data = json.loads(account.bank_formula)
            return BankFormula(income=data.get("income", []), expense=data.get("expense", []))
        except (json.JSONDecodeError, AttributeError, TypeError):
            return None
    return None


async def _account_response(account: Account, db: AsyncSession) -> AccountResponse:
    balance = await get_account_balance(account, db)
    return AccountResponse(
        id=account.id, user_id=account.user_id, name=account.name, currency=account.currency,
        initial_balance=account.initial_balance, account_type=account.account_type or "cash",
        bank_statement_mode=account.bank_statement_mode or "direct",
        bank_formula=_formula_from_model(account),
        hidden=account.hidden, sort_order=account.sort_order,
        current_balance=balance, created_at=str(account.created_at), updated_at=str(account.updated_at)
    )


async def get_account_balance(account: Account, db: AsyncSession) -> float:
    inc_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id == account.id,
            Transaction.type == "income"
        )
    )
    exp_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id == account.id,
            Transaction.type == "expense"
        )
    )
    transfer_out = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id == account.id,
            Transaction.type == "transfer"
        )
    )
    transfer_in = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.dest_account_id == account.id,
            Transaction.type == "transfer"
        )
    )
    income = float(inc_result.scalar() or 0)
    expense = float(exp_result.scalar() or 0)
    transfer_out_amt = float(transfer_out.scalar() or 0)
    transfer_in_amt = float(transfer_in.scalar() or 0)
    return account.initial_balance + income - expense + transfer_in_amt - transfer_out_amt


@router.get("", response_model=List[AccountResponse])
async def get_accounts(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).where(Account.user_id == user_id).order_by(Account.sort_order))
    accounts = result.scalars().all()
    return [await _account_response(acc, db) for acc in accounts]


@router.post("", response_model=AccountResponse)
async def create_account(req: AccountCreate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    payload = req.model_dump()
    formula = payload.pop("bank_formula", None)
    account = Account(user_id=user_id, **payload)
    if formula:
        _apply_formula(account, formula)
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return await _account_response(account, db)


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(account_id: str, req: AccountUpdate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).where(Account.id == account_id, Account.user_id == user_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    for key, value in req.model_dump(exclude_unset=True).items():
        if key == "bank_formula":
            if value:
                _apply_formula(account, value)
            else:
                account.bank_formula = None
        else:
            setattr(account, key, value)
    await db.commit()
    await db.refresh(account)
    return await _account_response(account, db)


@router.delete("/{account_id}")
async def delete_account(account_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).where(Account.id == account_id, Account.user_id == user_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await db.delete(account)
    await db.commit()
    return {"message": "Account deleted"}


@router.get("/balances-as-of")
async def get_balances_as_of(year: int, month: int, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    """截至某年某月月末，每个账户系统记录的余额（含转账）。"""
    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="month 必须在 1-12 之间")
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"

    result = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.hidden.is_(False)).order_by(Account.sort_order)
    )
    accounts = result.scalars().all()

    async def _sum(account_id: str, tx_type: str, *, dest_is_self: bool = False) -> float:
        stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id,
            Transaction.type == tx_type,
            Transaction.date < end,
        )
        if dest_is_self:
            stmt = stmt.where(Transaction.dest_account_id == account_id)
        else:
            stmt = stmt.where(Transaction.account_id == account_id)
        return float((await db.execute(stmt)).scalar() or 0)

    rows = []
    for acc in accounts:
        income = await _sum(acc.id, "income")
        expense = await _sum(acc.id, "expense")
        transfer_in = await _sum(acc.id, "transfer", dest_is_self=True)
        transfer_out = await _sum(acc.id, "transfer")
        balance = round((acc.initial_balance or 0) + income - expense + transfer_in - transfer_out, 2)
        rows.append({
            "account_id": acc.id,
            "account_name": acc.name,
            "account_type": acc.account_type or "cash",
            "initial_balance": round(acc.initial_balance or 0, 2),
            "income": round(income, 2),
            "expense": round(expense, 2),
            "transfer_in": round(transfer_in, 2),
            "transfer_out": round(transfer_out, 2),
            "balance": balance,
        })
    return rows