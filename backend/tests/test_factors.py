"""Factor engine / store / router tests: synthetic regressions, seeded presets,
spread alignment, exposure matrix (mmf market-only), contribution identity,
and the Agent generate→preview→confirm flow (mocked LLM & market data).
"""
import asyncio
import json
import random

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models.user import User
from app.models.research_asset import ResearchAsset, ResearchAssetPrice
from app.models.factor import Factor, FactorValue, FactorExposure
from app.routers import factors as fr
from app.services import nav_history
from app.services.factor_engine import (
    compute_exposure,
    recompute_exposures,
    compute_contribution,
)
from app.services.factor_store import (
    seed_preset_factors,
    sync_factor_values,
    refresh_all_factors,
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


def _mk_factor(db: AsyncSession, name: str, config: dict, is_market: bool = False) -> Factor:
    f = Factor(name=name, category="asset_class", definition="d",
               config=json.dumps(config), is_market=is_market, proxy_symbol=config.get("symbol", ""))
    db.add(f)
    return f


def _days(n: int, start="2025-01-01") -> list[str]:
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


def _series(dates_prices) -> list[dict]:
    return [{"date": d, "close": p} for d, p in dates_prices]


def _no_ifind(monkeypatch):
    async def fake_creds(db, user_id):
        return None, None
    import app.services.ifind_client as ic
    monkeypatch.setattr(ic, "get_credentials", fake_creds)


class TestComputeExposure:
    def test_recovers_known_betas(self):
        rng = random.Random(42)
        dates = _days(600)
        f1 = [rng.gauss(0, 0.01) for _ in dates]
        f2 = [rng.gauss(0, 0.008) for _ in dates]
        asset = [0.8 * a + 0.2 * b + rng.gauss(0, 1e-6) for a, b in zip(f1, f2)]

        res = compute_exposure(
            list(zip(dates, asset)),
            {"f1": list(zip(dates, f1)), "f2": list(zip(dates, f2))},
        )
        assert res is not None
        assert abs(res["betas"]["f1"] - 0.8) < 0.05
        assert abs(res["betas"]["f2"] - 0.2) < 0.05
        assert res["r2"] > 0.9
        assert res["method"] == "ols"
        assert abs(res["t_stats"]["f1"]) > 10

    def test_perfect_collinearity_switches_to_ridge(self):
        rng = random.Random(7)
        dates = _days(600)
        f1 = [rng.gauss(0, 0.01) for _ in dates]
        f2 = [rng.gauss(0, 0.01) for _ in dates]
        f3 = [a + b for a, b in zip(f1, f2)]            # exact linear combination
        asset = [0.5 * a + 0.3 * b for a, b in zip(f1, f2)]

        res = compute_exposure(
            list(zip(dates, asset)),
            {"f1": list(zip(dates, f1)), "f2": list(zip(dates, f2)), "f3": list(zip(dates, f3))},
        )
        assert res is not None
        assert res["method"] == "ridge"
        assert res["vif_max"] > 5

    def test_insufficient_samples_returns_none(self):
        rng = random.Random(1)
        dates = _days(300)                               # < 500*0.8 = 400
        f1 = [rng.gauss(0, 0.01) for _ in dates]
        res = compute_exposure(list(zip(dates, f1)), {"f1": list(zip(dates, f1))})
        assert res is None

    def test_alpha_intercept(self):
        rng = random.Random(3)
        dates = _days(500)
        f1 = [rng.gauss(0, 0.01) for _ in dates]
        asset = [0.001 + a + rng.gauss(0, 1e-6) for a in f1]
        res = compute_exposure(list(zip(dates, asset)), {"f1": list(zip(dates, f1))})
        assert res is not None
        assert abs(res["alpha_daily"] - 0.001) < 1e-4


class TestFactorStore:
    def test_seed_is_idempotent(self):
        async def inner():
            db, engine = await _make_db()
            try:
                n1 = await seed_preset_factors(db)
                n2 = await seed_preset_factors(db)
                assert n1 == 7 and n2 == 0
                total = len((await db.execute(select(Factor))).scalars().all())
                assert total == 7
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_proxy_sync_writes_return_and_level(self, monkeypatch):
        async def inner():
            async def fake_fetch(symbol, exchange, begin, end, iu=None, ip=None, force_money_market=False):
                return _series([("2026-01-01", 1.0), ("2026-01-02", 1.1),
                                ("2026-01-03", 1.21), ("2026-01-04", 1.15)]), "ifind"

            monkeypatch.setattr(nav_history, "fetch_history_series", fake_fetch)
            db, engine = await _make_db()
            try:
                f = _mk_factor(db, "t1", {"type": "proxy", "symbol": "000300", "exchange": "SH"})
                await db.flush()
                r = await sync_factor_values(db, f, full=True)
                assert r.error is None and r.rows == 3
                levels = (await db.execute(
                    select(FactorValue).where(FactorValue.factor_id == f.id, FactorValue.kind == "level")
                )).scalars().all()
                returns = (await db.execute(
                    select(FactorValue).where(FactorValue.factor_id == f.id, FactorValue.kind == "return")
                )).scalars().all()
                assert len(levels) == 4 and len(returns) == 3
                by_date = {v.date: v.value for v in returns}
                assert abs(by_date["2026-01-02"] - 0.1) < 1e-9
                assert abs(by_date["2026-01-03"] - 0.1) < 1e-9      # 1.21/1.1
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_spread_sync_aligns_common_dates(self, monkeypatch):
        async def inner():
            async def fake_fetch(symbol, exchange, begin, end, iu=None, ip=None, force_money_market=False):
                if symbol == "000852":
                    return _series([("2026-01-01", 100.0), ("2026-01-02", 102.0), ("2026-01-03", 101.0)]), "ifind"
                return _series([("2026-01-02", 50.0), ("2026-01-03", 49.0), ("2026-01-04", 48.0)]), "ifind"

            monkeypatch.setattr(nav_history, "fetch_history_series", fake_fetch)
            db, engine = await _make_db()
            try:
                f = _mk_factor(db, "spread1", {
                    "type": "spread",
                    "long": {"type": "proxy", "symbol": "000852", "exchange": "SH"},
                    "short": {"type": "proxy", "symbol": "000300", "exchange": "SH"},
                })
                await db.flush()
                r = await sync_factor_values(db, f, full=True)
                assert r.error is None
                levels = (await db.execute(
                    select(FactorValue).where(FactorValue.factor_id == f.id, FactorValue.kind == "level")
                )).scalars().all()
                by_date = {v.date: v.value for v in levels}
                # common dates only: 01-02 (102-50=52) and 01-03 (101-49=52)
                assert sorted(by_date.keys()) == ["2026-01-02", "2026-01-03"]
                assert abs(by_date["2026-01-02"] - 52.0) < 1e-9
                returns = (await db.execute(
                    select(FactorValue).where(FactorValue.factor_id == f.id, FactorValue.kind == "return")
                )).scalars().all()
                assert len(returns) == 1 and returns[0].date == "2026-01-03"
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_refresh_all_failure_isolated(self, monkeypatch):
        async def inner():
            calls = []

            async def fake_fetch(symbol, exchange, begin, end, iu=None, ip=None, force_money_market=False):
                calls.append(symbol)
                if symbol == "000300":
                    raise nav_history.NavHistoryError("boom")
                return _series([("2026-01-01", 1.0), ("2026-01-02", 1.01)]), "ifind"

            monkeypatch.setattr(nav_history, "fetch_history_series", fake_fetch)
            db, engine = await _make_db()
            try:
                _mk_factor(db, "bad", {"type": "proxy", "symbol": "000300", "exchange": "SH"})
                _mk_factor(db, "good", {"type": "proxy", "symbol": "000905", "exchange": "SH"})
                await db.flush()
                results = await refresh_all_factors(db)
                assert len(results) == 2
                assert results[0].error is not None
                assert results[1].error is None and results[1].rows == 1
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


class TestRouter:
    def test_list_seeds_presets(self):
        async def inner():
            db, engine = await _make_db()
            try:
                listed = await fr.list_factors(category=None, db=db)
                assert len(listed) == 7
                names = [f.name for f in listed]
                assert "权益(沪深300)" in names and "规模(小盘−沪深300)" in names
                market = [f for f in listed if f.name == "权益(沪深300)"][0]
                assert market.is_market is True
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_create_and_duplicate(self):
        async def inner():
            db, engine = await _make_db()
            try:
                body = fr.FactorCreate(
                    name="自定义因子", category="custom", definition="测试",
                    config=fr.FactorConfig(type="proxy", symbol="000905", exchange="SH"),
                )
                created = await fr.create_factor(body, db=db)
                assert created.proxy_symbol == "000905"
                with pytest.raises(fr.HTTPException) as e:
                    await fr.create_factor(body, db=db)
                assert e.value.status_code == 409
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_update_bumps_version_and_deactivate(self):
        async def inner():
            db, engine = await _make_db()
            try:
                f = _mk_factor(db, "v1", {"type": "proxy", "symbol": "000300", "exchange": "SH"})
                await db.flush()
                out = await fr.update_factor(
                    f.id, fr.FactorUpdate(definition="new def"), db=db
                )
                assert out.version == 2
                out2 = await fr.deactivate_factor(f.id, db=db)
                assert out2.active is False
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def _seed_factor_series(self, db, factor: Factor, rets: list[tuple[str, float]]):
        prev = 1.0
        for d, r in rets:
            db.add(FactorValue(factor_id=factor.id, date=d, value=prev * (1 + r), kind="level"))
            db.add(FactorValue(factor_id=factor.id, date=d, value=r, kind="return"))
            prev = prev * (1 + r)

    def test_contribution_identity_and_mmf_market_only_matrix(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                dates = _days(80)
                rng = random.Random(11)
                market_rets = [rng.gauss(0, 0.01) for _ in dates]
                smallcap_rets = [rng.gauss(0, 0.012) for _ in dates]

                # factor library: market + smallcap
                fm = _mk_factor(db, "权益(沪深300)", {"type": "proxy", "symbol": "000300"}, is_market=True)
                fs = _mk_factor(db, "小盘(中证1000)", {"type": "proxy", "symbol": "000852"})
                await db.flush()
                self._seed_factor_series(db, fm, list(zip(dates, market_rets)))
                self._seed_factor_series(db, fs, list(zip(dates, smallcap_rets)))

                # pooled equity asset: close = 0.6*market + 0.3*smallcap + noise (small)
                a = ResearchAsset(user_id=u.id, symbol="161005", exchange="FUND_CN",
                                  name="混合A", status="pooled")
                db.add(a)
                # pooled mmf asset: random tiny returns (mmf only regresses vs market)
                m = ResearchAsset(user_id=u.id, symbol="163820", exchange="FUND_CN",
                                  name="货币B", status="pooled", is_money_market=True)
                db.add(m)
                await db.flush()

                prev_a, prev_m = 1.0, 1.0
                for i, d in enumerate(dates):
                    ar = 0.6 * market_rets[i] + 0.3 * smallcap_rets[i]
                    prev_a *= (1 + ar)
                    db.add(ResearchAssetPrice(asset_id=a.id, date=d, close=prev_a, source="test"))
                    mr = rng.gauss(0, 1e-4)
                    prev_m *= (1 + mr)
                    db.add(ResearchAssetPrice(asset_id=m.id, date=d, close=prev_m, source="test"))
                await db.flush()

                summary = await recompute_exposures(db, u.id, full=True, window_days=60)
                assert summary["rows_written"] > 0

                # mmf rows only cover the market factor
                mmf_rows = (await db.execute(
                    select(FactorExposure).where(FactorExposure.asset_id == m.id)
                )).scalars().all()
                assert mmf_rows and all(r.factor_id == fm.id for r in mmf_rows)

                equity_rows = (await db.execute(
                    select(FactorExposure).where(FactorExposure.asset_id == a.id)
                )).scalars().all()
                assert any(r.factor_id == fs.id for r in equity_rows)

                # matrix endpoint
                matrix = await fr.exposure_matrix(as_of=None, user_id=u.id, db=db)
                assert matrix.as_of is not None
                assert {r.asset_id for r in matrix.assets} == {a.id, m.id}
                mmf_matrix_row = [r for r in matrix.assets if r.asset_id == m.id][0]
                assert set(mmf_matrix_row.cells.keys()) == {fm.id}
                equity_matrix_row = [r for r in matrix.assets if r.asset_id == a.id][0]
                assert fs.id in equity_matrix_row.cells
                # beta direction sanity: market beta should dominate
                bm = equity_matrix_row.cells[fm.id].beta
                bs = equity_matrix_row.cells[fs.id].beta
                assert abs(bm - 0.6) < 0.35 and abs(bs - 0.3) < 0.35

                # contribution identity: sum(contrib) + alpha == total_return exactly
                start, end = dates[10], dates[-1]
                res = await compute_contribution(db, a.id, start, end, view="return")
                assert abs(res["identity_residual"]) < 1e-9
                assert res["n_days"] > 0
                # alpha should be near zero: asset returns are a pure linear combo
                assert abs(res["alpha"]) < 0.02

                risk = await compute_contribution(db, a.id, start, end, view="risk")
                assert len(risk["items"]) >= 1
                assert all(it["risk_contribution"] >= -1e-12 for it in risk["items"])
                assert abs(sum(it["risk_contribution"] for it in risk["items"]) - 1.0) < 1e-9
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_agent_generate_preview_confirm(self, monkeypatch):
        async def inner():
            _no_ifind(monkeypatch)

            class FakePreset:
                api_url = "http://x/v1"
                api_key = "k"
                model_name = "m"

            import app.services.ai_investment as ai

            async def fake_pick_preset(db, user_id):
                return FakePreset()

            async def fake_call_llm(preset, system_prompt, user_prompt):
                return json.dumps({
                    "name": "中盘(中证500)",
                    "category": "asset_class",
                    "definition": "中证500 日收益率",
                    "config": {"type": "proxy", "symbol": "000905", "exchange": "SH"},
                }, ensure_ascii=False)

            monkeypatch.setattr(ai, "_pick_preset", fake_pick_preset)
            monkeypatch.setattr(ai, "_call_llm", fake_call_llm)

            async def fake_fetch(symbol, exchange, begin, end, iu=None, ip=None, force_money_market=False):
                return _series([("2026-01-01", 5.5), ("2026-01-02", 5.56), ("2026-01-03", 5.6)]), "ifind"

            monkeypatch.setattr(nav_history, "fetch_history_series", fake_fetch)

            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                candidate = await fr.agent_generate(
                    fr.AgentGenerateRequest(prompt="加一个中盘因子"), user_id=u.id, db=db
                )
                assert candidate.config.symbol == "000905"

                preview = await fr.agent_preview(
                    fr.AgentPreviewRequest(candidate=candidate), user_id=u.id, db=db
                )
                assert preview.ok is True and preview.sample_days == 3
                assert preview.first_date == "2026-01-01"

                factor = await fr.agent_confirm(
                    fr.AgentPreviewRequest(candidate=candidate), user_id=u.id, db=db
                )
                assert factor.name == "中盘(中证500)"
                n_values = len((await db.execute(
                    select(FactorValue).where(FactorValue.factor_id == factor.id)
                )).scalars().all())
                assert n_values == 5          # 3 levels + 2 returns
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_contribution_no_exposure_400(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = await _mk_user(db)
                a = ResearchAsset(user_id=u.id, symbol="161005", exchange="FUND_CN",
                                  name="混合A", status="pooled")
                db.add(a)
                await db.flush()
                with pytest.raises(fr.HTTPException) as e:
                    await fr.contribution(asset_id=a.id, start="2026-01-01", end="2026-02-01",
                                          view="return", db=db)
                assert e.value.status_code == 400
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())
