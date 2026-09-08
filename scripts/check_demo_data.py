import sys
sys.path.insert(0, 'backend')

from app.database import async_session_maker
import asyncio
from sqlalchemy import select, func
from app.models.transaction import Transaction
from app.models.investment import Investment
from app.models.account import Account
from app.models.category import Category

DEMO_UID = "38ffb6af-e864-45ca-9267-3005d554c0db"

async def check():
    async with async_session_maker() as db:
        r = await db.execute(select(func.count()).where(Transaction.user_id == DEMO_UID))
        print(f"Transactions: {r.scalar()}")
        
        r2 = await db.execute(select(func.count()).where(Investment.user_id == DEMO_UID))
        print(f"Investments: {r2.scalar()}")
        
        r3 = await db.execute(select(func.count()).where(Account.user_id == DEMO_UID))
        print(f"Accounts: {r3.scalar()}")
        
        r4 = await db.execute(select(func.count()).where(Category.user_id == DEMO_UID))
        print(f"Categories: {r4.scalar()}")
        
        # Sample some transactions
        r5 = await db.execute(
            select(Transaction.date, Transaction.type, Transaction.amount, Transaction.description)
            .where(Transaction.user_id == DEMO_UID)
            .order_by(Transaction.date.desc())
            .limit(10)
        )
        print("\nRecent transactions:")
        for row in r5.all():
            print(f"  {row[0]} | {row[1]} | {row[2]} | {row[3]}")

asyncio.run(check())
