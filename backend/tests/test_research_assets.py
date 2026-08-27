"""Research asset pool tests: price sync (mocked sources), indicators,
router CRUD/pool/status — all against in-memory SQLite.
"""
import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models.user import User
from app.models.research_asset import ResearchAsset, ResearchAssetPrice
from app.routers import research_assets as ra
from app.services import nav_history
from app.services.asset_price_store import (
    sync_asset_prices,
    compute_asset_indicators,
    refresh_all_pooled,
    lag_days,
)


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


async def _mk_asset(db: AsyncSession, user_id: str, **kw) -> ResearchAsset:
    a = ResearchAsset(
        user_id=user_id,
        symbol=kw.get("symbol", "161005"),
        exchange=kw.get("exchange", "FUND_CN"),
        name=kw.get("name", "Test Fund"),
        asset_type=kw.get("asset_type", "fund"),
        status=kw.get("status", "watchlist"),
        is_money_market=kw.get("is_money_market", False),
    )
    db.add(a)
    await db.flush()
    return a


def _series(dates_prices: list[tuple[str, float]]) -> list[dict]:
    return [{"date": d, "close": p} for d, p in dates_prices]


class TestSyncAssetPrices:
    def test_full_sync_inserts_and_reruns_idempotent(self, monkeypatch):
        async def inner():
            calls = []

            async def fake_fetch(symbol, exchange, begin, end, iu=None, ip=None, force_money_market=False):
                calls.append((begin, end))
                return _series([("2026-01-01", 1.0), ("2026-01-02", 1.1), ("2026-01-03", 1.2)]), "eastmoney"

            monkeypatch.setattr(nav_history, "fetch_history_series", fake_fetch)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                a = await _mk_asset(db, u.id)
                r1 = await sync_asset_prices(db, a, full=True)
                assert r1.rows == 3 and r1.source == "eastmoney" and r1.error is None
                rows = (await db.execute(
                    __import__("sqlalchemy").select(ResearchAssetPrice)
                    .where(ResearchAssetPrice.asset_id == a.id)
                )).scalars().all()
                assert len(rows) == 3

                r2 = await sync_asset_prices(db, a, full=True)
                assert r2.rows == 3
                rows = (await db.execute(
                    __import__("sqlalchemy").select(ResearchAssetPrice)
                    .where(ResearchAssetPrice.asset_id == a.id)
                )).scalars().all()
                assert len(rows) == 3  # full sync wipes then re-inserts
                assert calls[0][0] == "1990-01-01"
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_incremental_upserts_from_latest(self, monkeypatch):
        async def inner():
            async def fake_fetch(symbol, exchange, begin, end, iu=None, ip=None, force_money_market=False):
                return _series([("2026-01-02", 1.1), ("2026-01-03", 1.2), ("2026-01-04", 1.3)]), "ifind"

            monkeypatch.setattr(nav_history, "fetch_history_series", fake_fetch)
            db, engine = await _make_db()
            from sqlalchemy import select
            try:
                u = await _mk_user(db)
                a = await _mk_asset(db, u.id)
                for d, p in [("2026-01-01", 1.0), ("2026-01-02", 1.05)]:
                    db.add(ResearchAssetPrice(asset_id=a.id, date=d, close=p, source="old"))
                await db.flush()

                r = await sync_asset_prices(db, a)
                assert r.rows == 3
                rows = (await db.execute(
                    select(ResearchAssetPrice)
                    .where(ResearchAssetPrice.asset_id == a.id)
                    .order_by(ResearchAssetPrice.date)
                )).scalars().all()
                assert [x.date for x in rows] == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
                by_date = {x.date: x for x in rows}
                assert by_date["2026-01-02"].close == 1.1   # corrected by re-pull
                assert by_date["2026-01-02"].source == "ifind"
                assert by_date["2026-01-01"].source == "old"  # untouched
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_source_error_returns_error_result(self, monkeypatch):
        async def inner():
            async def fake_fetch(symbol, exchange, begin, end, iu=None, ip=None, force_money_market=False):
                raise nav_history.NavHistoryError("all sources failed")

            monkeypatch.setattr(nav_history, "fetch_history_series", fake_fetch)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                a = await _mk_asset(db, u.id)
                r = await sync_asset_prices(db, a, full=True)
                assert r.error is not None and r.rows == 0
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


class TestComputeIndicators:
    def _prices(self, dates_prices):
        return [ResearchAssetPrice(date=d, close=p) for d, p in dates_prices]

    def test_empty_series(self):
        a = ResearchAsset(symbol="x", name="x", user_id="u")
        ind = compute_asset_indicators(a, [])
        assert ind.points == 0 and ind.latest_close is None and ind.ret_1m is None

    def test_normal_series(self):
        a = ResearchAsset(symbol="x", name="x", user_id="u", is_money_market=False)
        dates = []
        p = 1.0
        from datetime import date, timedelta
        start = date.today() - timedelta(days=299)  # 300 daily points ending yesterday
        for i in range(300):
            dates.append(((start + timedelta(days=i)).isoformat(), round(p, 6)))
            p *= 1.001
        ind = compute_asset_indicators(a, self._prices(dates))
        assert ind.points == 300
        assert ind.ret_1y is not None and ind.ret_1y > 0
        assert ind.ret_1m is not None and 0 < ind.ret_1m < ind.ret_1y
        assert ind.ann_volatility is not None and ind.ann_volatility > 0
        assert ind.sharpe is not None
        assert ind.max_drawdown is not None and ind.max_drawdown <= 0

    def test_stale_series_window_returns_none(self):
        a = ResearchAsset(symbol="x", name="x", user_id="u")
        from datetime import date, timedelta
        start = date.today() - timedelta(days=500)
        pts = [((start + timedelta(days=i)).isoformat(), 1.0 + i * 0.001) for i in range(200)]
        ind = compute_asset_indicators(a, self._prices(pts))
        # 1m window has no fresh points at the tail → None; 1y window starts
        # inside the series → return measured to the (stale) last point
        assert ind.ret_1m is None
        assert ind.ret_1y is not None
        assert ind.ann_return is not None

    def test_money_market_returns_none_ratios(self):
        a = ResearchAsset(symbol="x", name="x", user_id="u", is_money_market=True)
        ind = compute_asset_indicators(a, self._prices([("2026-01-01", 1.0), ("2026-01-02", 1.0001)]))
        assert ind.ann_volatility is None and ind.sharpe is None and ind.ann_return is None
        assert ind.ret_1m is None and ind.ret_1y is None and ind.max_drawdown is None
        assert ind.points == 2 and ind.latest_close == 1.0001

    def test_bulk_insert_chunking_survives_long_history(self, monkeypatch):
        async def inner():
            async def fake_fetch(symbol, exchange, begin, end, iu=None, ip=None, force_money_market=False):
                pts = []
                p = 1.0
                from datetime import date, timedelta
                start = date(2010, 1, 1)
                for i in range(5300):  # 5300 rows × 8 params > SQLite 32766 cap
                    pts.append({"date": (start + timedelta(days=i)).isoformat(), "close": round(p, 6)})
                    p *= 1.0001
                return pts, "ifind"

            monkeypatch.setattr(nav_history, "fetch_history_series", fake_fetch)
            db, engine = await _make_db()
            from sqlalchemy import select, func
            try:
                u = await _mk_user(db)
                a = await _mk_asset(db, u.id)
                r = await sync_asset_prices(db, a, full=True)
                assert r.rows == 5300 and r.error is None
                n = (await db.execute(
                    select(func.count(ResearchAssetPrice.id))
                    .where(ResearchAssetPrice.asset_id == a.id)
                )).scalar()
                assert n == 5300
                ind = compute_asset_indicators(
                    a, (await db.execute(
                        select(ResearchAssetPrice).where(ResearchAssetPrice.asset_id == a.id)
                    )).scalars().all()
                )
                assert ind.points == 5300 and ind.ann_return is not None
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_short_history_no_1y(self):
        a = ResearchAsset(symbol="x", name="x", user_id="u")
        # 25-day span: >= 2/3 of the 30d window (fallback applies) but far
        # below the 365d window
        ind = compute_asset_indicators(a, self._prices([("2026-07-26", 1.0), ("2026-08-20", 1.02)]))
        assert ind.ret_1y is None
        assert ind.ret_1m is not None and ind.ret_1m == pytest.approx(0.02)

    def test_very_short_history_all_none(self):
        a = ResearchAsset(symbol="x", name="x", user_id="u")
        ind = compute_asset_indicators(a, self._prices([("2026-08-01", 1.0), ("2026-08-20", 1.02)]))
        assert ind.ret_1m is None and ind.ret_1y is None  # 19d span < 20d threshold

    def test_lag_days(self):
        from datetime import date
        today = date.today().isoformat()
        assert lag_days(today) == 0
        assert lag_days(None) is None
        assert lag_days("2020-01-01") > 1000

    def test_dual_sharpe_windows(self):
        """Full-sample vs trailing-1Y windows diverge when early history
        drags the long-run mean (the user-visible scenario)."""
        import random
        from datetime import date, timedelta

        random.seed(42)
        rows = []
        # 3 years: year 1 choppy negative drift, years 2-3 strong uptrend
        d = date(2023, 8, 1)
        end = date(2026, 8, 1)
        price = 1.0
        while d <= end:
            year = d.year
            if year == 2023:
                price *= (1 + random.uniform(-0.012, 0.004))
            else:
                price *= (1 + random.uniform(0.000, 0.010))
            rows.append((d.isoformat(), round(price, 4)))
            d += timedelta(days=1)
        a = ResearchAsset(symbol="x", name="x", user_id="u")
        ind = compute_asset_indicators(a, self._prices(rows))

        assert ind.sharpe is not None and ind.sharpe_1y is not None
        # Trailing 1Y is anchored to the strong recent window, so it should
        # dominate the full-sample (which still includes 2023's drag).
        assert ind.sharpe_1y > ind.sharpe, (
            f"trailing-1Y {ind.sharpe_1y:.2f} should beat full-sample "
            f"{ind.sharpe:.2f} when recent history is much stronger"
        )
        # Both windows still need valid vol and a positive number of points.
        assert ind.ann_volatility > 0 and ind.ann_volatility_1y > 0
        assert ind.points == len(rows)


class TestRouter:
    def _no_ifind(self, monkeypatch):
        async def fake_creds(db, user_id):
            return None, None

        async def fake_bg_sync(asset_id, user_id):
            pass

        import app.services.ifind_client as ic
        monkeypatch.setattr(ic, "get_credentials", fake_creds)
        # create_asset schedules a real-network price sync in the background;
        # asyncio.run teardown waits for its non-cancellable to_thread call,
        # which hangs the test whenever eastmoney is slow/unreachable
        monkeypatch.setattr(ra, "_sync_asset_prices_task", fake_bg_sync)

    def test_create_autocompletes_name_and_detects_money_market(self, monkeypatch):
        async def inner():
            self._no_ifind(monkeypatch)

            class FakeQuote:
                name = "中银货币B"
                source = "eastmoney-money-market"

            async def fake_fetch_price(symbol, exchange, iu=None, ip=None):
                return FakeQuote()

            monkeypatch.setattr(ra, "fetch_price", fake_fetch_price)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                created = await ra.create_asset(
                    ra.ResearchAssetCreate(symbol="163820"), user_id=u.id, db=db
                )
                assert created.name == "中银货币B"
                assert created.is_money_market is True
                assert created.status == "watchlist"
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_create_ifind_no_name_falls_back_to_pingzhongdata(self, monkeypatch):
        async def inner():
            self._no_ifind(monkeypatch)

            class FakeQuote:
                name = ""            # iFinD branch returns no name
                source = "ifind"

            async def fake_fetch_price(symbol, exchange, iu=None, ip=None):
                return FakeQuote()

            async def fake_meta(symbol):
                return "富国天惠成长混合", False

            monkeypatch.setattr(ra, "fetch_price", fake_fetch_price)
            monkeypatch.setattr(ra, "fetch_fund_meta", fake_meta)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                created = await ra.create_asset(
                    ra.ResearchAssetCreate(symbol="161005"), user_id=u.id, db=db
                )
                assert created.name == "富国天惠成长混合"
                assert created.is_money_market is False

                async def fake_meta_mmf(symbol):
                    return "中银货币B", True

                monkeypatch.setattr(ra, "fetch_fund_meta", fake_meta_mmf)
                created2 = await ra.create_asset(
                    ra.ResearchAssetCreate(symbol="163820"), user_id=u.id, db=db
                )
                assert created2.name == "中银货币B"
                assert created2.is_money_market is True
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_create_duplicate_409(self, monkeypatch):
        async def inner():
            self._no_ifind(monkeypatch)

            async def fake_fetch_price(symbol, exchange, iu=None, ip=None):
                raise ra.ProviderError("no quote")

            monkeypatch.setattr(ra, "fetch_price", fake_fetch_price)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                await ra.create_asset(ra.ResearchAssetCreate(symbol="161005"), user_id=u.id, db=db)
                with pytest.raises(ra.HTTPException) as e:
                    await ra.create_asset(ra.ResearchAssetCreate(symbol="161005"), user_id=u.id, db=db)
                assert e.value.status_code == 409
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_pool_triggers_background_sync(self, monkeypatch):
        async def inner():
            self._no_ifind(monkeypatch)
            synced = []

            async def fake_pool_sync(asset_id, user_id):
                synced.append(asset_id)

            monkeypatch.setattr(ra, "_pool_sync_task", fake_pool_sync)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                a = await _mk_asset(db, u.id)
                out = await ra.pool_asset(
                    a.id, ra.ResearchAssetPool(mgmt_fee=0.5, purchase_fee=0.15),
                    user_id=u.id, db=db,
                )
                assert out.status == "pooled"
                assert out.mgmt_fee == 0.5 and out.purchase_fee == 0.15
                await asyncio.sleep(0.05)  # let create_task run
                assert synced == [a.id]
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_pool_with_redeem_rules_dict_input(self, monkeypatch):
        """Regression: model_dump turns redeem_rules into list[dict] — the
        fee helpers must accept both RedeemRule objects and plain dicts
        (the frontend pool/edit forms always send rules, which used to 500)."""
        async def inner():
            self._no_ifind(monkeypatch)

            async def fake_pool_sync(asset_id, user_id):
                pass

            monkeypatch.setattr(ra, "_pool_sync_task", fake_pool_sync)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                a = await _mk_asset(db, u.id)
                out = await ra.pool_asset(
                    a.id,
                    ra.ResearchAssetPool(
                        redeem_rules=[
                            ra.RedeemRule(days=7, fee_rate=1.5),
                            ra.RedeemRule(days=30, fee_rate=0.5),
                            ra.RedeemRule(days=None, fee_rate=0.0),
                        ],
                    ),
                    user_id=u.id, db=db,
                )
                assert out.status == "pooled"
                assert [r.model_dump() for r in out.redeem_rules] == [
                    {"days": 7, "fee_rate": 1.5},
                    {"days": 30, "fee_rate": 0.5},
                    {"days": None, "fee_rate": 0.0},
                ]
                assert out.redeem_fee_note == "<7天 1.5%，<30天 0.5%，其余 0%"

                upd = await ra.update_asset(
                    a.id,
                    ra.ResearchAssetUpdate(
                        redeem_rules=[ra.RedeemRule(days=7, fee_rate=1.0),
                                      ra.RedeemRule(days=None, fee_rate=0.0)],
                    ),
                    user_id=u.id, db=db,
                )
                assert [r.model_dump() for r in upd.redeem_rules] == [
                    {"days": 7, "fee_rate": 1.0}, {"days": None, "fee_rate": 0.0}
                ]
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_list_filter_and_search(self, monkeypatch):
        async def inner():
            self._no_ifind(monkeypatch)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                a1 = await _mk_asset(db, u.id, symbol="161005", name="富国天惠")
                await _mk_asset(db, u.id, symbol="000300", name="沪深300", status="pooled")
                listed = await ra.list_assets(status="watchlist", category=None, search=None,
                                              fund_kind=None, asset_class=None, region=None, limit_filter=None,
                                              page=0, page_size=50,
                                              user_id=u.id, db=db)
                assert [x.symbol for x in listed] == ["161005"]
                found = await ra.list_assets(status=None, category=None, search="沪深",
                                             fund_kind=None, asset_class=None, region=None, limit_filter=None,
                                             page=0, page_size=50,
                                             user_id=u.id, db=db)
                assert [x.symbol for x in found] == ["000300"]
                got = await ra.get_asset(a1.id, user_id=u.id, db=db)
                assert got.indicators.points == 0
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_update_and_delete(self, monkeypatch):
        async def inner():
            self._no_ifind(monkeypatch)
            db, engine = await _make_db()
            from sqlalchemy import select
            try:
                u = await _mk_user(db)
                a = await _mk_asset(db, u.id)
                db.add(ResearchAssetPrice(asset_id=a.id, date="2026-01-01", close=1.0, source="t"))
                await db.flush()
                upd = await ra.update_asset(
                    a.id, ra.ResearchAssetUpdate(category="核心-宽基", notes="test"),
                    user_id=u.id, db=db,
                )
                assert upd.category == "核心-宽基"
                await ra.delete_asset(a.id, user_id=u.id, db=db)
                left = (await db.execute(select(ResearchAssetPrice))).scalars().all()
                assert left == []  # prices cascade-deleted with the asset
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_price_status(self, monkeypatch):
        async def inner():
            self._no_ifind(monkeypatch)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                a = await _mk_asset(db, u.id, status="pooled")
                db.add(ResearchAssetPrice(asset_id=a.id, date="2026-01-05", close=1.0, source="ifind"))
                await db.flush()
                st = await ra.price_status(user_id=u.id, db=db)
                assert len(st) == 1
                assert st[0].rows == 1 and st[0].last_date == "2026-01-05"
                assert st[0].source == "ifind" and st[0].lag_days >= 0
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_refresh_all_pooled_isolated_failures(self, monkeypatch):
        async def inner():
            state = {"n": 0}

            async def fake_fetch(symbol, exchange, begin, end, iu=None, ip=None, force_money_market=False):
                state["n"] += 1
                if state["n"] == 1:
                    raise nav_history.NavHistoryError("boom")
                return _series([("2026-01-01", 1.0)]), "eastmoney"

            monkeypatch.setattr(nav_history, "fetch_history_series", fake_fetch)
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                await _mk_asset(db, u.id, symbol="111111", status="pooled")
                await _mk_asset(db, u.id, symbol="222222", status="pooled")
                await _mk_asset(db, u.id, symbol="333333", status="watchlist")  # skipped
                results = await refresh_all_pooled(db, u.id)
                assert len(results) == 2
                assert results[0].error is not None
                assert results[1].rows == 1 and results[1].error is None
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())
