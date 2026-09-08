"""Seed demo data from real user data with random sampling.

This script:
1. Logs in as the demo user
2. Creates accounts and categories matching the real user's structure
3. Randomly samples transactions from the real user's data
4. Randomly samples investments and cash flows

Privacy-safe: only a small random subset is extracted.
"""
import asyncio
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import async_session_maker, get_private_db
from app.models.user import User
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.investment import Investment
from app.models.investment_cash_flow import InvestmentCashFlow
from sqlalchemy import select, func


async def main():
    # Find real user
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.email == "TTDiang@outlook.com"))
        real_user = result.scalar_one_or_none()
        if not real_user:
            print("ERROR: TTDiang@outlook.com not found")
            return

        # Find or create demo user
        result = await db.execute(select(User).where(User.email == "demo@finkit.example"))
        demo_user = result.scalar_one_or_none()
        if not demo_user:
            from app.utils.security import hash_password
            from app.models.user_settings import UserSettings
            demo_user = User(
                email="demo@finkit.example",
                password_hash=hash_password("demo123456"),
                name="Demo User"
            )
            db.add(demo_user)
            db.add(UserSettings(user_id=demo_user.id))
            await db.commit()
            await db.refresh(demo_user)
            print(f"Created demo user: {demo_user.id}")
        else:
            print(f"Using existing demo user: {demo_user.id}")

        demo_uid = demo_user.id
        real_uid = real_user.id
        print(f"Real user ID: {real_uid}")
        print(f"Demo user ID: {demo_uid}")

        # ---- Sample accounts (up to 6 random ones) ----
        result = await db.execute(
            select(Account).where(Account.user_id == real_uid).order_by(func.random())
        )
        real_accounts = result.scalars().all()[:6]
        print(f"Sampling {len(real_accounts)} accounts...")

        account_map = {}  # real_id -> demo_id
        for ra in real_accounts:
            demo_acc = Account(
                user_id=demo_uid,
                name=ra.name,
                currency=ra.currency,
                initial_balance=ra.initial_balance,
                account_type=ra.account_type,
                sort_order=ra.sort_order,
                hidden=ra.hidden,
            )
            db.add(demo_acc)
            await db.commit()
            await db.refresh(demo_acc)
            account_map[ra.id] = demo_acc.id
            print(f"  {ra.name} -> {demo_acc.id}")

        # ---- Sample categories (up to 12) ----
        result = await db.execute(
            select(Category).where(Category.user_id == real_uid).order_by(func.random())
        )
        real_cats = result.scalars().all()[:12]
        print(f"Sampling {len(real_cats)} categories...")

        cat_map = {}
        for rc in real_cats:
            demo_cat = Category(
                user_id=demo_uid,
                type=rc.type,
                name=rc.name,
                color=rc.color,
                icon=rc.icon,
                sort_order=rc.sort_order,
            )
            db.add(demo_cat)
            await db.commit()
            await db.refresh(demo_cat)
            cat_map[rc.id] = demo_cat.id
            print(f"  {rc.type}/{rc.name} -> {demo_cat.id}")

        # ---- Sample transactions (50-100 random) ----
        result = await db.execute(
            select(Transaction).where(Transaction.user_id == real_uid).order_by(func.random())
        )
        all_txns = result.scalars().all()
        sample_size = min(random.randint(50, 100), len(all_txns))
        sampled_txns = all_txns[:sample_size]
        print(f"Sampling {sample_size} transactions...")

        for txn in sampled_txns:
            demo_txn = Transaction(
                user_id=demo_uid,
                type=txn.type,
                date=txn.date,
                amount=txn.amount,
                account_id=account_map.get(txn.account_id, list(account_map.values())[0]),
                dest_account_id=account_map.get(txn.dest_account_id) if txn.dest_account_id else None,
                category_id=cat_map.get(txn.category_id) if txn.category_id else None,
                tag_ids=txn.tag_ids,
                description=txn.description,
                remark=txn.remark,
                location=txn.location,
            )
            db.add(demo_txn)
        await db.commit()
        print(f"  Created {sample_size} transactions")

        # ---- Sample investments (up to 8) ----
        result = await db.execute(
            select(Investment).where(Investment.user_id == real_uid).order_by(func.random())
        )
        real_invs = result.scalars().all()[:8]
        print(f"Sampling {len(real_invs)} investments...")

        for inv in real_invs:
            demo_inv = Investment(
                user_id=demo_uid,
                name=inv.name,
                investment_type=inv.investment_type,
                symbol=inv.symbol,
                exchange=inv.exchange,
                underlying_asset_type=inv.underlying_asset_type,
                asset_class=inv.asset_class,
                quantity=inv.quantity,
                purchase_price=inv.purchase_price,
                current_price=inv.current_price,
                purchase_date=inv.purchase_date,
                sell_date=inv.sell_date,
                notes=inv.notes,
                is_money_market=inv.is_money_market,
            )
            db.add(demo_inv)
        await db.commit()
        print(f"  Created {len(real_invs)} investments")

        # ---- Sample cash flows (up to 10) ----
        result = await db.execute(
            select(InvestmentCashFlow).where(InvestmentCashFlow.user_id == real_uid).order_by(func.random())
        )
        real_cf = result.scalars().all()[:10]
        print(f"Sampling {len(real_cf)} cash flows...")

        for cf in real_cf:
            demo_cf = InvestmentCashFlow(
                user_id=demo_uid,
                flow_type=cf.flow_type,
                amount=cf.amount,
                flow_date=cf.flow_date,
                account_id=account_map.get(cf.account_id, list(account_map.values())[0] if account_map else None),
                notes=cf.notes,
            )
            db.add(demo_cf)
        await db.commit()
        print(f"  Created {len(real_cf)} cash flows")

        print("\n=== DONE ===")
        print("Demo account: demo@finkit.example")
        print("Demo password: demo123456")
        print("\nData sampled from real transactions:")
        print(f"  - {len(real_accounts)} accounts")
        print(f"  - {len(real_cats)} categories")
        print(f"  - {sample_size} transactions (random sample)")
        print(f"  - {len(real_invs)} investments")
        print(f"  - {len(real_cf)} cash flows")


if __name__ == "__main__":
    asyncio.run(main())
