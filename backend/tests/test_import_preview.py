"""Import preview/commit tests: duplicate candidates in parse-import, and
income-with-negative-amount normalization on commit.

Each test runs inside a single asyncio.run() loop because aiosqlite
connections are bound to the event loop that created them.
"""
import asyncio
import io

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models.user import User
from app.models.account import Account
from app.models.transaction import Transaction
from app.routers.transactions import parse_import, commit_import
from app.schemas.transaction import ImportCommitRequest, ImportCommitRow


async def _make_db() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker(), engine


async def _mk_user(db: AsyncSession) -> User:
    u = User(email="imp@t.co", password_hash="x")
    db.add(u)
    await db.flush()
    return u


async def _mk_account(db: AsyncSession, user_id: str, name: str) -> Account:
    a = Account(user_id=user_id, name=name, initial_balance=0)
    db.add(a)
    await db.flush()
    return a


def _csv(rows) -> bytes:
    header = "交易日期,方向,金额,本方账户,对方账户,分类,描述\n"
    body = "\n".join(",".join(str(c) for c in r) for r in rows)
    return (header + body).encode("utf-8-sig")


async def _parse(db: AsyncSession, user_id: str, content: bytes):
    return await parse_import(
        file=UploadFile(filename="t.csv", file=io.BytesIO(content)),
        user_id=user_id, db=db,
    )


def test_parse_import_duplicate_candidates():
    async def run():
        db, engine = await _make_db()
        try:
            u = await _mk_user(db)
            acc = await _mk_account(db, u.id, "消费账户")
            await db.commit()
            db.add(Transaction(user_id=u.id, type="expense", date="2026-08-01",
                               amount=-60.0, account_id=acc.id,
                               description="退款-测试", location="美团"))
            await db.commit()

            content = _csv([("2026-08-01", "expense", "-60", "消费账户", "", "", "退款-测试")])
            preview = await _parse(db, u.id, content)

            assert preview.rows, "应解析出 1 行"
            row = preview.rows[0]
            assert row.is_duplicate is True
            assert len(row.duplicate_with) == 1
            d = row.duplicate_with[0]
            assert d.account == "消费账户"
            assert d.amount == -60.0
            assert d.date == "2026-08-01"
            assert d.type == "expense"
            assert d.description == "退款-测试"
            assert d.location == "美团"
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_parse_import_no_duplicate():
    async def run():
        db, engine = await _make_db()
        try:
            u = await _mk_user(db)
            await _mk_account(db, u.id, "消费账户")
            await db.commit()

            content = _csv([("2026-08-01", "expense", "-60", "消费账户", "", "", "退款-测试")])
            preview = await _parse(db, u.id, content)

            assert preview.rows[0].is_duplicate is False
            assert preview.rows[0].duplicate_with == []
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_parse_import_income_negative_accepted():
    """负数金额 + 收入方向：允许（人工改判退款为收入），不报错。"""
    async def run():
        db, engine = await _make_db()
        try:
            u = await _mk_user(db)
            await _mk_account(db, u.id, "消费账户")
            await db.commit()

            content = _csv([("2026-08-01", "income", "-60", "消费账户", "", "", "退款改判收入")])
            preview = await _parse(db, u.id, content)

            row = preview.rows[0]
            assert row.error == ""
            assert row.is_duplicate is False
        finally:
            await engine.dispose()
    asyncio.run(run())


def _commit_rows(*rows):
    return ImportCommitRequest(rows=[ImportCommitRow(**r) for r in rows])


def test_commit_income_negative_stores_positive():
    """收入行负数金额入库时取绝对值（退款改判收入 → 确认是收入）。"""
    async def run():
        db, engine = await _make_db()
        try:
            u = await _mk_user(db)
            await _mk_account(db, u.id, "消费账户")
            await db.commit()

            req = _commit_rows(dict(date="2026-08-01", direction="income", amount=-60.0,
                                    account="消费账户", dest_account="", category="",
                                    tags="", description="退款改判收入", remark="", location=""))
            result = await commit_import(req, user_id=u.id, db=db)

            assert result.inserted == 1
            assert result.errors == []
            stored = (await db.execute(
                select(Transaction).where(Transaction.user_id == u.id)
            )).scalars().all()
            assert len(stored) == 1
            assert stored[0].amount == 60.0
            assert stored[0].type == "income"
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_commit_expense_refund_keeps_negative():
    """支出退款（负数）入库保持负数：冲销语义不变。"""
    async def run():
        db, engine = await _make_db()
        try:
            u = await _mk_user(db)
            await _mk_account(db, u.id, "消费账户")
            await db.commit()

            req = _commit_rows(dict(date="2026-08-01", direction="expense", amount=-60.0,
                                    account="消费账户", dest_account="", category="",
                                    tags="", description="退款", remark="", location=""))
            result = await commit_import(req, user_id=u.id, db=db)

            assert result.inserted == 1
            stored = (await db.execute(
                select(Transaction).where(Transaction.user_id == u.id)
            )).scalars().all()
            assert stored[0].amount == -60.0
        finally:
            await engine.dispose()
    asyncio.run(run())
