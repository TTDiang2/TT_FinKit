"""Monitor service tests: zone1 target weights must map signal target_weights
(symbol-keyed) onto held symbols, not treat keys as research-asset ids.

Regression: an earlier build read `sig.target_weights` keys as `asset_id`
(`asset_id_to_asset.get(key)`), but the signal engine writes symbol keys — so
every target collapsed to 0.0 and zone1 showed phantom 100pp deviations.
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
from app.services import monitor_service


def _mk_signal(target: dict, user_id: str | None = None) -> Signal:
    return Signal(
        user_id=user_id, strategy_id="s1", strategy_version=1,
        run_date=date.today().isoformat(), as_of_date=date.today().isoformat(),
        target_weights=json.dumps(target),
    )


async def _make_db() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker(), engine


async def _add_asset(db: AsyncSession, user_id: str, sym: str, close: float) -> ResearchAsset:
    a = ResearchAsset(user_id=user_id, symbol=sym, exchange="FUND_CN", name=f"基金{sym}",
                      asset_type="fund", status="pooled")
    db.add(a)
    await db.flush()
    db.add(ResearchAssetPrice(asset_id=a.id, date=(date.today() - timedelta(days=1)).isoformat(),
                              close=close))
    return a


def _add_holding(db: AsyncSession, user_id: str, sym: str, qty: float, px: float) -> None:
    db.add(Investment(user_id=user_id, name=f"持仓{sym}", investment_type="fund",
                     symbol=sym, exchange="FUND_CN", quantity=qty,
                     purchase_price=px, current_price=px,
                     purchase_date=(date.today() - timedelta(days=40)).isoformat()))


class TestMonitorZone1:
    def test_symbol_keyed_targets_map_to_held_symbols(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = User(email="t@t.co", password_hash="x")
                db.add(u)
                await db.flush()
                # A not held, B held at full value; targets keyed by symbol.
                await _add_asset(db, u.id, "A", 1.0)
                await _add_asset(db, u.id, "B", 2.0)
                _add_holding(db, u.id, "B", 10000, 2.0)
                db.add(_mk_signal({"A": 0.5, "B": 0.5}, user_id=u.id))
                await db.commit()

                data = await monitor_service.get_monitor_overview(db, db, u.id)
                z1 = data["zone1_portfolio"]
                by_sym = {it["symbol"]: it for it in z1["items"]}
                # Both target symbols must appear with their real target weight
                assert by_sym["B"]["target_weight"] == 0.5
                assert by_sym["A"]["target_weight"] == 0.5
                # B actual = 1.0 (only holding), deviation 0.5 → alert
                assert by_sym["B"]["actual_weight"] == 1.0
                assert by_sym["B"]["has_alert"] is True
                # A has no holding → actual 0.0, deviation 0.5 → alert
                assert by_sym["A"]["actual_weight"] == 0.0
                assert by_sym["A"]["has_alert"] is True
                assert len(z1["alerts"]) == 2
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_asset_id_keyed_targets_still_supported(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = User(email="t@t.co", password_hash="x")
                db.add(u)
                await db.flush()
                a = await _add_asset(db, u.id, "A", 1.0)
                b = await _add_asset(db, u.id, "B", 2.0)
                _add_holding(db, u.id, "B", 10000, 2.0)
                db.add(_mk_signal({a.id: 0.5, b.id: 0.5}, user_id=u.id))  # legacy asset-id keys
                await db.commit()

                data = await monitor_service.get_monitor_overview(db, db, u.id)
                z1 = data["zone1_portfolio"]
                by_sym = {it["symbol"]: it for it in z1["items"]}
                # Legacy asset-id keys must still resolve to the right symbols
                assert by_sym["A"]["target_weight"] == 0.5
                assert by_sym["B"]["target_weight"] == 0.5
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_unknown_keys_are_dropped_not_zeroed(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = User(email="t@t.co", password_hash="x")
                db.add(u)
                await db.flush()
                await _add_asset(db, u.id, "A", 1.0)
                _add_holding(db, u.id, "A", 100, 1.0)
                db.add(_mk_signal({"ZZZ": 1.0, "A": 0.2}, user_id=u.id))  # ZZZ not a real symbol
                await db.commit()

                data = await monitor_service.get_monitor_overview(db, db, u.id)
                z1 = data["zone1_portfolio"]
                by_sym = {it["symbol"]: it for it in z1["items"]}
                # Unknown symbol must not appear as a row
                assert "ZZZ" not in by_sym
                assert by_sym["A"]["target_weight"] == 0.2
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())
