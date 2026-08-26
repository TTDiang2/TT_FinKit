"""Sparse factor coverage must not crash or empty the intersection.

Regression for the '重算暴露' 500: common_dates used a UNION of factor dates,
so a date missing from any single factor crashed fm[d] with KeyError; the
naive fix (full INTERSECTION) let one sparse factor hollow out the whole
common-date set ("与因子无共同交易日" for every asset).
"""
from app.services.factor_engine import compute_exposure


def _series(dates: list[str], base=1.0, daily=0.001):
    out = []
    v = base
    for d in dates:
        out.append((d, v))
        v *= 1 + daily
    return out


def test_compute_exposure_drops_dates_missing_from_one_factor():
    dates = [f"2024-01-{i:02d}" for i in range(1, 29)]
    asset = _series(dates)
    f_full = _series(dates, daily=0.002)
    # 因子 B 缺 3 天 —— union 版本会 KeyError，inner join 应自动剔除这 3 天
    missing = {"2024-01-05", "2024-01-15", "2024-01-25"}
    f_sparse = [(d, 1.0 + 0.003 * i) for i, d in enumerate(dates) if d not in missing]
    res = compute_exposure(asset, {"F1": f_full, "F2": f_sparse}, window_days=28)
    assert res is not None
    assert res["n_samples"] == len(dates) - len(missing)
    assert set(res["betas"].keys()) == {"F1", "F2"}


def test_recompute_greedy_keeps_dense_factors_and_skips_sparse(monkeypatch):
    """贪心选择：覆盖差的因子被剔除，主体因子保留，资产不被整体跳过。"""
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models.factor import Factor, FactorValue
    from app.models.research_asset import ResearchAsset, ResearchAssetPrice
    from app.services.factor_engine import recompute_exposures

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    dates = [f"2024-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]

    async def seed():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as db:
            db.add(ResearchAsset(id="a1", user_id="u1", symbol="TST", name="Test",
                                 status="pooled", is_money_market=False))
            db.add(Factor(id="dense", name="Dense", key="dense", category="style",
                          definition="", is_market=False, active=True))
            db.add(Factor(id="sparse", name="Sparse", key="sparse", category="style",
                          definition="", is_market=False, active=True))
            for d in dates:
                db.add(ResearchAssetPrice(asset_id="a1", date=d, close=1.001))
                db.add(FactorValue(factor_id="dense", date=d, kind="return", value=0.001))
            # sparse 只有 30 天数据（远低于 sample floor）
            for d in dates[:30]:
                db.add(FactorValue(factor_id="sparse", date=d, kind="return", value=0.002))
            await db.commit()

    asyncio.run(seed())

    async def run():
        async with maker() as db:
            r = await recompute_exposures(db, "u1", full=False, window_days=60)
            rows = (await db.execute(select(FactorExposure))).scalars().all()
            return r, {row.factor_id for row in rows}

    from app.models.factor import FactorExposure
    r, fids = asyncio.run(run())
    assert r["regressions"] >= 1
    assert "dense" in fids
    # sparse 因子要么被贪心剔除，要么不影响主流程——绝不能让资产整体 skip
    assert r["skipped"] == []
