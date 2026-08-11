from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..database import get_db
from ..models.account import Account
from ..models.transaction import Transaction
from ..schemas.account import AccountCreate, AccountUpdate, AccountResponse
from ..middleware.auth import get_current_user_id
from typing import List

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


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
    responses = []
    for acc in accounts:
        balance = await get_account_balance(acc, db)
        responses.append(AccountResponse(
            id=acc.id, user_id=acc.user_id, name=acc.name, currency=acc.currency,
            initial_balance=acc.initial_balance, account_type=acc.account_type or "cash", hidden=acc.hidden, sort_order=acc.sort_order,
            current_balance=balance, created_at=str(acc.created_at), updated_at=str(acc.updated_at)
        ))
    return responses


@router.post("", response_model=AccountResponse)
async def create_account(req: AccountCreate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    account = Account(user_id=user_id, **req.model_dump())
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return AccountResponse(
        id=account.id, user_id=account.user_id, name=account.name, currency=account.currency,
        initial_balance=account.initial_balance, account_type=account.account_type or "cash", hidden=account.hidden, sort_order=account.sort_order,
        current_balance=account.initial_balance, created_at=str(account.created_at), updated_at=str(account.updated_at)
    )


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(account_id: str, req: AccountUpdate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).where(Account.id == account_id, Account.user_id == user_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    await db.commit()
    await db.refresh(account)
    balance = await get_account_balance(account, db)
    return AccountResponse(
        id=account.id, user_id=account.user_id, name=account.name, currency=account.currency,
        initial_balance=account.initial_balance, account_type=account.account_type or "cash", hidden=account.hidden, sort_order=account.sort_order,
        current_balance=balance, created_at=str(account.created_at), updated_at=str(account.updated_at)
    )


@router.delete("/{account_id}")
async def delete_account(account_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).where(Account.id == account_id, Account.user_id == user_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await db.delete(account)
    await db.commit()
    return {"message": "Account deleted"}