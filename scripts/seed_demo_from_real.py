"""Clean and regenerate demo data from real user data (2026-06 to 2026-08)."""
import sys
sys.path.insert(0, 'backend')

from app.database import async_session_maker
import asyncio
from sqlalchemy import select, func, delete
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.investment import Investment
from app.models.investment_cash_flow import InvestmentCashFlow


DEMO_UID = "38ffb6af-e864-45ca-9267-3005d554c0db"
REAL_UID = "4481a5f7-6e5a-483e-972f-edcfa0f288df"


async def main():
    async with async_session_maker() as db:
        # Step 1: Clean ALL existing demo data
        print("=== Cleaning all existing demo data ===")
        await db.execute(delete(InvestmentCashFlow).where(InvestmentCashFlow.user_id == DEMO_UID))
        await db.execute(delete(Investment).where(Investment.user_id == DEMO_UID))
        await db.execute(delete(Transaction).where(Transaction.user_id == DEMO_UID))
        await db.execute(delete(Category).where(Category.user_id == DEMO_UID))
        await db.execute(delete(Account).where(Account.user_id == DEMO_UID))
        await db.commit()
        
        # Verify clean
        for model, name in [(Account, "Accounts"), (Category, "Categories"), 
                            (Transaction, "Transactions"), (Investment, "Investments"),
                            (InvestmentCashFlow, "CashFlows")]:
            r = await db.execute(select(func.count()).where(model.user_id == DEMO_UID))
            count = r.scalar()
            print(f"  {name}: {count} {'OK' if count == 0 else 'WARNING!'}")

        # Step 2: Sample accounts
        print("\n=== Sampling accounts ===")
        result = await db.execute(
            select(Account).where(Account.user_id == REAL_UID).order_by(func.random())
        )
        real_accounts = result.scalars().all()[:6]
        account_map = {}
        for ra in real_accounts:
            demo_acc = Account(
                user_id=DEMO_UID, name=ra.name, currency=ra.currency,
                initial_balance=ra.initial_balance, account_type=ra.account_type,
                sort_order=ra.sort_order, hidden=ra.hidden,
            )
            db.add(demo_acc)
            await db.commit()
            await db.refresh(demo_acc)
            account_map[ra.id] = demo_acc.id
            print(f"  {ra.name}")

        # Step 3: Sample categories
        print("\n=== Sampling categories ===")
        result = await db.execute(
            select(Category).where(Category.user_id == REAL_UID).order_by(func.random())
        )
        real_cats = result.scalars().all()[:12]
        cat_map = {}
        for rc in real_cats:
            demo_cat = Category(
                user_id=DEMO_UID, type=rc.type, name=rc.name, color=rc.color,
                icon=rc.icon, sort_order=rc.sort_order,
            )
            db.add(demo_cat)
            await db.commit()
            await db.refresh(demo_cat)
            cat_map[rc.id] = demo_cat.id
            print(f"  {rc.type}/{rc.name}")

        # Step 4: Sample transactions from Jun-Aug 2026
        print("\n=== Sampling transactions (2026-06 to 2026-08) ===")
        result = await db.execute(
            select(Transaction)
            .where(Transaction.user_id == REAL_UID,
                   Transaction.date >= "2026-06-01", Transaction.date <= "2026-08-31")
            .order_by(func.random())
        )
        all_txns = result.scalars().all()
        sample_size = min(80, len(all_txns))
        sampled_txns = all_txns[:sample_size]
        june = len([t for t in sampled_txns if t.date.startswith("2026-06")])
        july = len([t for t in sampled_txns if t.date.startswith("2026-07")])
        aug = len([t for t in sampled_txns if t.date.startswith("2026-08")])
        print(f"  Found {len(all_txns)} in range, sampling {sample_size}")
        print(f"  Distribution: June={june}, July={july}, August={aug}")

        for txn in sampled_txns:
            demo_txn = Transaction(
                user_id=DEMO_UID, type=txn.type, date=txn.date, amount=txn.amount,
                account_id=account_map.get(txn.account_id, list(account_map.values())[0]),
                dest_account_id=account_map.get(txn.dest_account_id) if txn.dest_account_id else None,
                category_id=cat_map.get(txn.category_id) if txn.category_id else None,
                tag_ids=txn.tag_ids, description=txn.description, remark=txn.remark,
                location=txn.location,
            )
            db.add(demo_txn)
        await db.commit()
        print(f"  Created {sample_size} transactions")

        # Step 5: Sample investments
        print("\n=== Sampling investments ===")
        result = await db.execute(
            select(Investment).where(Investment.user_id == REAL_UID).order_by(func.random())
        )
        real_invs = result.scalars().all()[:8]
        for inv in real_invs:
            demo_inv = Investment(
                user_id=DEMO_UID, name=inv.name, investment_type=inv.investment_type,
                symbol=inv.symbol, exchange=inv.exchange,
                underlying_asset_type=inv.underlying_asset_type, asset_class=inv.asset_class,
                quantity=inv.quantity, purchase_price=inv.purchase_price,
                current_price=inv.current_price, purchase_date=inv.purchase_date,
                sell_date=inv.sell_date, notes=inv.notes, is_money_market=inv.is_money_market,
            )
            db.add(demo_inv)
        await db.commit()
        print(f"  Created {len(real_invs)} investments")

        # Step 6: Sample cash flows
        print("\n=== Sampling cash flows ===")
        result = await db.execute(
            select(InvestmentCashFlow).where(InvestmentCashFlow.user_id == REAL_UID).order_by(func.random())
        )
        real_cf = result.scalars().all()[:8]
        for cf in real_cf:
            demo_cf = InvestmentCashFlow(
                user_id=DEMO_UID, flow_type=cf.flow_type, amount=cf.amount,
                flow_date=cf.flow_date, notes=cf.notes,
            )
            db.add(demo_cf)
        await db.commit()
        print(f"  Created {len(real_cf)} cash flows")

        # Final verification
        print("\n=== Final verification ===")
        for model, name in [(Account, "Accounts"), (Category, "Categories"),
                            (Transaction, "Transactions"), (Investment, "Investments"),
                            (InvestmentCashFlow, "CashFlows")]:
            r = await db.execute(select(func.count()).where(model.user_id == DEMO_UID))
            print(f"  {name}: {r.scalar()}")

        print("\n=== DONE ===")
        print("Demo account: demo@finkit.example")
        print("Demo password: demo123456")


if __name__ == "__main__":
    asyncio.run(main())
