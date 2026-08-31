"""Trade plan tests: signal target vs holdings → buy/sell rows with fee tiers,
T+N arrival and buffer-band suppression — in-memory SQLite, direct router calls.
"""
import asyncio
import json
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models.user import User
from app.models.research_asset import ResearchAsset, ResearchAssetPrice
from app.models.investment import Investment
from app.models.signal import Signal
from app.routers import signals as sg


async def _make_db() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker(), engine


def _mk_signal(target: dict) -> Signal:
    return Signal(
        strategy_id="s1", strategy_version=1,
        run_date=date.today().isoformat(), as_of_date=date.today().isoformat(),
        target_weights=json.dumps(target),
    )


class TestTradePlan:
    def test_buy_sell_with_limit_cap_and_fee_tiers(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = User(email="t@t.co", password_hash="x")
                db.add(u)
                await db.flush()

                # Target: A/B each 50%; user holds only B at full weight
                gold = ResearchAsset(user_id=u.id, symbol="A", exchange="FUND_CN",
                                     name="基金A", asset_type="fund", status="pooled",
                                     purchase_fee=0.15, purchase_limit=1000.0,
                                     redeem_rules=json.dumps(
                                         [{"days": 7, "fee_rate": 1.5}, {"days": None, "fee_rate": 0}]))
                bond = ResearchAsset(user_id=u.id, symbol="B", exchange="FUND_CN",
                                     name="基金B", asset_type="fund", status="pooled",
                                     redeem_rules=json.dumps(
                                         [{"days": 30, "fee_rate": 0.5}, {"days": None, "fee_rate": 0.1}]),
                                     redeem_t_days=2)
                db.add_all([gold, bond])
                await db.flush()
                db.add_all([
                    ResearchAssetPrice(asset_id=gold.id, date="2026-08-20", close=1.0),
                    ResearchAssetPrice(asset_id=bond.id, date="2026-08-20", close=2.0),
                    Investment(user_id=u.id, name="持仓B", investment_type="fund",
                               symbol="B", exchange="FUND_CN", quantity=10000,
                               current_price=2.0,
                               purchase_date=(date.today() - timedelta(days=40)).isoformat()),
                    _mk_signal({"A": 0.5, "B": 0.5}),
                ])
                await db.commit()

                plan = await sg.compute_trade_plan(db, db, u.id)
                assert plan["total_value"] == 20000.0
                rows = {r["symbol"]: r for r in plan["rows"]}

                buy = rows["A"]
                assert buy["action"] == "buy"
                assert buy["amount"] == 1000.0            # capped by daily limit
                assert any("限额" in w for w in buy["warnings"])
                assert buy["est_fee_pct"] == 0.15

                sell = rows["B"]
                assert sell["action"] == "sell"
                assert sell["amount"] == 10000.0
                assert sell["est_fee_pct"] == 0.1         # held 40d → fallback tier
                assert sell["t_plus"] == "T+2"
                assert sell["arrive_date"] is not None
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_buffer_band_suppresses_small_delta(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = User(email="t@t.co", password_hash="x")
                db.add(u)
                await db.flush()
                a = ResearchAsset(user_id=u.id, symbol="A", exchange="FUND_CN",
                                  name="基金A", asset_type="fund", status="pooled")
                db.add(a)
                await db.flush()
                db.add_all([
                    ResearchAssetPrice(asset_id=a.id, date="2026-08-20", close=1.0),
                    Investment(user_id=u.id, name="h", investment_type="fund",
                               symbol="A", exchange="FUND_CN", quantity=1000,
                               current_price=1.0, purchase_date="2026-01-01"),
                    _mk_signal({"A": 0.996}),   # Δ ≈ -4元 → hold via buffer band
                ])
                await db.commit()
                plan = await sg.compute_trade_plan(db, db, u.id)
                assert plan["rows"][0]["action"] == "hold"
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_no_signal_tiny_holdings_stay_hold(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = User(email="t@t.co", password_hash="x")
                db.add(u)
                await db.flush()
                db.add(Investment(user_id=u.id, name="h", investment_type="fund",
                                  symbol="X", exchange="FUND_CN", quantity=10,
                                  current_price=5.0, purchase_date="2026-01-01"))
                await db.commit()
                plan = await sg.compute_trade_plan(db, db, u.id)
                assert plan["signal_id"] is None
                row = plan["rows"][0]
                assert row["symbol"] == "X" and row["target_weight"] == 0
                assert row["action"] == "hold"      # |Δ|=50元 < 100元缓冲线
                assert plan["total_value"] == 50.0
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())
