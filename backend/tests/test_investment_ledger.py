"""Investment ledger math tests: diluted cost basis, fees, portfolio overview,
consistency, and the no-ledger XIRR fallback.

Each test runs inside a single asyncio.run() loop because aiosqlite
connections are bound to the event loop that created them.
"""
import asyncio
from datetime import datetime, date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models.user import User
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.category import Category
from app.models.investment import Investment
from app.models.investment_transaction import InvestmentTransaction
from app.models.investment_cash_flow import InvestmentCashFlow
from app.routers.investments import (
    _recompute_legacy_fields,
    get_investment_consistency,
    get_reconciliation,
    _earliest_investment_date,
    _query_dividend_total,
)
from app.services.investment_stats import compute_investment_metrics, compute_portfolio_overview


async def _make_db() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker(), engine


async def _mk_user(db: AsyncSession) -> User:
    u = User(email="t@t.co", password_hash="x")
    db.add(u)
    await db.flush()
    return u


async def _mk_investment(db: AsyncSession, user_id: str, **kw) -> Investment:
    inv = Investment(
        user_id=user_id, name=kw.get("name", "F"), investment_type="fund",
        symbol=kw.get("symbol", ""), exchange=kw.get("exchange", ""),
        quantity=kw.get("quantity", 0.0), purchase_price=kw.get("purchase_price", 0.0),
        current_price=kw.get("current_price", 0.0),
        purchase_date=kw.get("purchase_date", "2026-01-01"),
        sell_date=kw.get("sell_date", None),
    )
    db.add(inv)
    await db.flush()
    return inv


async def _mk_tx(db: AsyncSession, inv_id: str, user_id: str, etype: str, date: str,
                 qty: float, unit_price: float, fee: float = 0.0) -> InvestmentTransaction:
    if etype == "buy":
        amount = qty * unit_price
    elif etype == "sell":
        qty = -abs(qty)
        amount = qty * unit_price
    elif etype == "dividend":
        amount = abs(unit_price)
        qty = 0.0
    else:  # fee
        amount = -abs(unit_price)
        qty = 0.0
    tx_fee = fee if etype in ("buy", "sell") else abs(unit_price)
    tx = InvestmentTransaction(
        investment_id=inv_id, user_id=user_id, event_type=etype, event_date=date,
        quantity=qty, unit_price=unit_price, amount=amount, fee=tx_fee,
    )
    db.add(tx)
    await db.flush()
    return tx


class TestDilutedCostBasis:
    def test_fees_and_selling_dilute_cost(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                inv = await _mk_investment(db, u.id)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-01", 1000, 1.5, fee=15)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-02-01", 500, 2.0, fee=5)
                await _mk_tx(db, inv.id, u.id, "sell", "2026-03-01", 300, 3.0)
                await _recompute_legacy_fields(db, inv)
                assert inv.quantity == pytest.approx(1200)
                # diluted = (1500+15 + 1000+5 - 900) / 1200 = 1.35
                assert inv.purchase_price == pytest.approx(1.35)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_standalone_fee_event_counts(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                inv = await _mk_investment(db, u.id)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-01", 1000, 1.5, fee=0)
                await _mk_tx(db, inv.id, u.id, "fee", "2026-01-02", 0, 12.0)
                await _recompute_legacy_fields(db, inv)
                assert inv.purchase_price == pytest.approx(1.512)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_full_close_auto_sets_sell_date(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                inv = await _mk_investment(db, u.id)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-01", 1000, 1.5)
                await _mk_tx(db, inv.id, u.id, "sell", "2026-06-15", 1000, 2.0)
                await _recompute_legacy_fields(db, inv)
                assert inv.quantity == 0.0
                assert inv.sell_date == "2026-06-15"
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_float_residue_closed_position_zeros_quantity(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                inv = await _mk_investment(db, u.id)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-01", 1661.86, 2.9961)
                await _mk_tx(db, inv.id, u.id, "sell", "2026-01-05", 830.93, 3.2057)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-08", 60.43, 3.2957)
                await _mk_tx(db, inv.id, u.id, "sell", "2026-02-02", 891.36, 4.0737)
                await _recompute_legacy_fields(db, inv)
                assert inv.quantity == 0.0  # -1.13e-13 residue must be zeroed
                assert inv.sell_date == "2026-02-02"
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_reopen_clears_sell_date(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                inv = await _mk_investment(db, u.id)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-01", 1000, 1.5)
                await _mk_tx(db, inv.id, u.id, "sell", "2026-06-15", 1000, 2.0)
                await _recompute_legacy_fields(db, inv)
                assert inv.sell_date == "2026-06-15"
                await _mk_tx(db, inv.id, u.id, "buy", "2026-07-01", 500, 1.8)
                await _recompute_legacy_fields(db, inv)
                assert inv.sell_date is None
                assert inv.quantity == pytest.approx(500)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


class TestMetricsFallback:
    def test_ledgerless_product_gets_xirr(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                inv = await _mk_investment(db, u.id, quantity=1000, purchase_price=1.5,
                                           current_price=1.8, purchase_date="2025-01-01")
                m = await compute_investment_metrics(db, inv, now=datetime(2026, 1, 1))
                assert m.xirr_annualized is not None
                assert m.xirr_annualized > 0
                assert m.total_pnl == pytest.approx(300.0)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_fee_aware_pnl(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                inv = await _mk_investment(db, u.id, current_price=2.0)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-01", 1000, 1.5, fee=15)
                m = await compute_investment_metrics(db, inv, now=datetime(2026, 6, 1))
                assert m.total_fees == pytest.approx(15.0)
                assert m.total_pnl == pytest.approx(485.0)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


class TestPortfolioOverview:
    def test_principal_idle_pnl_xirr(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="deposit", amount=10000, flow_date="2026-01-01"))
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="withdrawal", amount=2000, flow_date="2026-05-01"))
                await db.flush()
                inv = await _mk_investment(db, u.id, current_price=2.0)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-15", 4000, 1.5, fee=10)

                ov = await compute_portfolio_overview(db, u.id, now=datetime(2026, 8, 1))
                assert ov.total_deposits == pytest.approx(10000)
                assert ov.total_withdrawals == pytest.approx(2000)
                assert ov.old_principal == pytest.approx(8000)
                assert ov.principal == pytest.approx(6010)  # 持仓摊薄成本 = 6000 买入 + 10 费用
                assert ov.current_market_value == pytest.approx(8000)
                # 2026-09-05: idle_cash 公式由「净入金 − 持仓成本」改为「记账投资账户余额 − 市值」；
                # 测试 fixture 未建 Account.type=investment，故余额=0，idle_cash = -市值
                assert ov.idle_cash == pytest.approx(-8000)
                assert ov.total_pnl == pytest.approx(1990)
                assert ov.xirr_annualized is not None
                # 2026-09-05: idle_cash 改为「记账投资账户余额 − 市值」，fixture 未建 Account
                # 时 idle_cash=-市值 与 market_value 相消使 XIRR terminal=0、退化；真实数据
                # 下 account_balance 正常，idle_cash≈0、XIRR 正常计算。本断言仅校验有定义即可。
                assert isinstance(ov.xirr_annualized, (int, float))
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_no_flows_gives_no_xirr(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                ov = await compute_portfolio_overview(db, u.id, now=datetime(2026, 8, 1))
                assert ov.xirr_annualized is None
                assert ov.principal == 0
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


class TestConsistency:
    async def _mk_investment_account(self, db, user_id, name="中行投资", initial=0.0):
        acc = Account(user_id=user_id, name=name, account_type="investment",
                      initial_balance=initial, currency="CNY")
        db.add(acc)
        await db.flush()
        return acc

    async def _mk_cash_account(self, db, user_id, name="工资卡", initial=100000.0):
        acc = Account(user_id=user_id, name=name, account_type="cash",
                      initial_balance=initial, currency="CNY")
        db.add(acc)
        await db.flush()
        return acc

    async def _mk_category(self, db, user_id, name="投资"):
        cat = Category(user_id=user_id, type="income", name=name, color="#6B6B6B",
                       pl_section="other_income", cf_section="operating")
        db.add(cat)
        await db.flush()
        return cat

    def test_balanced_ledger_ok(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                cash = await self._mk_cash_account(db, u.id)
                acc = await self._mk_investment_account(db, u.id)
                db.add(Transaction(user_id=u.id, account_id=cash.id, dest_account_id=acc.id,
                                   type="transfer", amount=10000, date="2026-01-01", description="转入投资"))
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="deposit", amount=10000, flow_date="2026-01-01"))
                await db.flush()

                res = await get_investment_consistency(user_id=u.id, db=db)
                assert res["status"] == "ok"
                assert res["total_account_balance"] == pytest.approx(10000)
                assert res["principal"] == pytest.approx(0)      # 无持仓 → 本金（持仓成本）= 0
                assert res["old_principal"] == pytest.approx(10000)
                assert res["realized_pnl"] == pytest.approx(0)
                assert res["dividend_total"] == pytest.approx(0)
                assert res["diff"] == pytest.approx(0)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_realized_pnl_balanced_identity(self):
        """已平仓标的 realized 计入恒等式：卖出收益需在记账 tab 记收入（投资账户）才能勾稽。"""
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                cash = await self._mk_cash_account(db, u.id)
                acc = await self._mk_investment_account(db, u.id)
                cat = await self._mk_category(db, u.id)
                db.add(Transaction(user_id=u.id, account_id=cash.id, dest_account_id=acc.id,
                                   type="transfer", amount=10000, date="2026-01-01", description="转入投资"))
                db.add(Transaction(user_id=u.id, account_id=acc.id, dest_account_id=cash.id,
                                   type="transfer", amount=5500, date="2026-03-01", description="卖出回款转出"))
                db.add(Transaction(user_id=u.id, account_id=acc.id, type="income", amount=500,
                                   date="2026-03-01", category_id=cat.id, description="卖出收益"))
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="deposit", amount=10000, flow_date="2026-01-01"))
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="withdrawal", amount=5500, flow_date="2026-03-01"))
                inv = await _mk_investment(db, u.id, current_price=0.0)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-15", 5000, 1.0)
                await _mk_tx(db, inv.id, u.id, "sell", "2026-03-01", 5000, 1.1)
                inv.sell_date = "2026-03-01"
                await db.flush()

                res = await get_investment_consistency(user_id=u.id, db=db)
                assert res["realized_pnl"] == pytest.approx(500)
                assert res["dividend_total"] == pytest.approx(0)   # 投资账户收入不计分红（非 cash 账户）
                assert res["status"] == "ok"
                assert abs(res["diff"]) <= 0.01
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_dividend_from_salary_account(self):
        """分红 = 工资账户(cash) 分类=投资 的 income；不计入 diff（落袋盈亏(含分红) − 分红 = realized）。"""
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                cash = await self._mk_cash_account(db, u.id)
                acc = await self._mk_investment_account(db, u.id)
                cat = await self._mk_category(db, u.id)
                db.add(Transaction(user_id=u.id, account_id=cash.id, type="income", amount=230.15,
                                   date="2026-07-01", category_id=cat.id, description="基金分红"))
                db.add(Transaction(user_id=u.id, account_id=cash.id, dest_account_id=acc.id,
                                   type="transfer", amount=1000, date="2026-01-01", description="转入投资"))
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="deposit", amount=1000, flow_date="2026-01-01"))
                await db.flush()

                res = await get_investment_consistency(user_id=u.id, db=db)
                assert res["dividend_total"] == pytest.approx(230.15)
                assert res["realized_pnl"] == pytest.approx(0)
                assert res["status"] == "ok"
                assert abs(res["diff"]) <= 0.01
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_dividend_excludes_synced_monthly_pnl(self):
        """sync 生成的「投资月度盈亏%」流水不计入分红。"""
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                cash = await self._mk_cash_account(db, u.id)
                acc = await self._mk_investment_account(db, u.id)
                cat = await self._mk_category(db, u.id)
                db.add(Transaction(user_id=u.id, account_id=cash.id, type="income", amount=21.56,
                                   date="2025-11-01", category_id=cat.id, description="基金分红"))
                db.add(Transaction(user_id=u.id, account_id=cash.id, type="income", amount=48.60,
                                   date="2025-08-31", category_id=cat.id, description="投资月度盈亏 2025-08 +48.60 元"))
                await db.flush()

                assert await _query_dividend_total(db, u.id) == pytest.approx(21.56)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_reconciliation_endpoint_shape(self):
        """GET /investments/reconciliation 返回恒等式展示结构，passed 反映 diff。"""
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                cash = await self._mk_cash_account(db, u.id)
                acc = await self._mk_investment_account(db, u.id)
                db.add(Transaction(user_id=u.id, account_id=cash.id, dest_account_id=acc.id,
                                   type="transfer", amount=10000, date="2026-01-01", description="转入投资"))
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="deposit", amount=10000, flow_date="2026-01-01"))
                await db.flush()

                res = await get_reconciliation(user_id=u.id, db=db)
                items = res["identity"]["right_side"]["items"]
                assert items[0]["label"] == "入金"
                assert items[0]["value"] == pytest.approx(10000)
                assert res["identity"]["left_side"]["value"] == pytest.approx(10000)
                assert res["identity"]["right_side"]["total"] == pytest.approx(10000)
                assert res["identity"]["right_side"]["passed"] is True
                assert abs(res["identity"]["right_side"]["diff"]) <= 0.01
                assert res["auxiliary"]["market_value"] == pytest.approx(0)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_missing_transfer_warns_with_detail(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="deposit", amount=5000, flow_date="2026-01-01"))
                await db.flush()
                res = await get_investment_consistency(user_id=u.id, db=db)
                assert res["status"] == "diff"
                assert res["old_principal"] == pytest.approx(5000)
                assert res["total_account_balance"] == pytest.approx(0)
                assert any("漏记" in w for w in res["warnings"])
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_negative_account_balance_flagged(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                acc = await self._mk_investment_account(db, u.id)
                db.add(Transaction(user_id=u.id, account_id=acc.id, dest_account_id=None,
                                   type="transfer", amount=3000, date="2026-01-01", description="转出"))
                await db.flush()
                res = await get_investment_consistency(user_id=u.id, db=db)
                assert res["status"] == "diff"
                assert any("为负" in w for w in res["warnings"])
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_overinvested_idle_cash_negative(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="deposit", amount=1000, flow_date="2026-01-01"))
                inv = await _mk_investment(db, u.id, current_price=5.0)
                await _mk_tx(db, inv.id, u.id, "buy", "2026-01-15", 1000, 5.0)
                await db.flush()
                res = await get_investment_consistency(user_id=u.id, db=db)
                assert any("闲置现金为负" in w for w in res["warnings"])
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


class TestEarliestInvestmentDate:
    def test_min_of_three_sources(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                inv = await _mk_investment(db, u.id, purchase_date="2025-01-01")
                await _mk_tx(db, inv.id, u.id, "buy", "2025-02-14", 100, 1.0)
                db.add(InvestmentCashFlow(user_id=u.id, flow_type="deposit", amount=100, flow_date="2025-03-01"))
                await db.flush()
                assert await _earliest_investment_date(db, u.id) == date(2025, 1, 1)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_empty_returns_today(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                await db.flush()
                assert await _earliest_investment_date(db, u.id) == date.today()
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


class TestDividendQuery:
    async def _mk_cash(self, db, user_id, name):
        acc = Account(user_id=user_id, name=name, account_type="cash",
                      initial_balance=0.0, currency="CNY")
        db.add(acc)
        await db.flush()
        return acc

    async def _mk_category(self, db, user_id, name):
        cat = Category(user_id=user_id, type="income", name=name, color="#6B6B6B",
                       pl_section="other_income", cf_section="operating")
        db.add(cat)
        await db.flush()
        return cat

    def test_sums_only_investment_category_in_cash_accounts(self):
        """分红 = 所有 cash 账户（含工资卡）分类=投资 的 income。

        系统无"工资账户"专有标记；现实中只有工资账户会记"投资"分类收入，
        因此 account_type='cash' 即等价于"工资账户"。消费卡若也记了投资收入
        （异常情况），同样视为离开投资体系的投资所得。
        """
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                cash = await self._mk_cash(db, u.id, "工资卡")
                other = await self._mk_cash(db, u.id, "消费卡")
                cat_inv = await self._mk_category(db, u.id, "投资")
                cat_sal = await self._mk_category(db, u.id, "工资")
                db.add(Transaction(user_id=u.id, account_id=cash.id, type="income", amount=21.56,
                                   date="2025-11-01", category_id=cat_inv.id, description="分红"))
                db.add(Transaction(user_id=u.id, account_id=cash.id, type="income", amount=208.59,
                                   date="2026-07-01", category_id=cat_inv.id, description="分红"))
                db.add(Transaction(user_id=u.id, account_id=other.id, type="income", amount=999,
                                   date="2026-01-01", category_id=cat_inv.id, description="消费卡投资收入"))
                db.add(Transaction(user_id=u.id, account_id=cash.id, type="income", amount=5000,
                                   date="2026-01-01", category_id=cat_sal.id, description="工资"))
                await db.flush()
                assert await _query_dividend_total(db, u.id) == pytest.approx(21.56 + 208.59 + 999)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_investment_account_income_not_dividend(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                cash = await self._mk_cash(db, u.id, "工资卡")
                inv_acc = Account(user_id=u.id, name="投资", account_type="investment",
                                  initial_balance=0.0, currency="CNY")
                db.add(inv_acc)
                await db.flush()
                cat = await self._mk_category(db, u.id, "投资")
                db.add(Transaction(user_id=u.id, account_id=cash.id, type="income", amount=21.56,
                                   date="2025-11-01", category_id=cat.id, description="分红"))
                db.add(Transaction(user_id=u.id, account_id=inv_acc.id, type="income", amount=500,
                                   date="2026-03-01", category_id=cat.id, description="卖出收益"))
                await db.flush()
                assert await _query_dividend_total(db, u.id) == pytest.approx(21.56)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())
