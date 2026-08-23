"""P1.2 factor sync tests — pure transforms + incremental upsert only.

Network wrappers in ``app/services/factor_sources.py`` are deliberately NOT
tested here: every one of them hits a live akshare endpoint (East Money,
Sina, JY, ...), and pytest must never make network calls.  Wrapper behaviour
is verified separately via the one-off live probe script (smoke_sync.py) and
by the runtime-verification notes in the factor_sources module docstring.
"""
import asyncio
import os
import sys
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models.factor import Factor, FactorValue
from app.services.factor_sources import NoDataError
from app.services.factor_registry import FactorDef
from app.services.factor_sync import (
    transform_proxy_diff,
    transform_level_diff,
    transform_level_spread_diff,
    transform_level_pct,
    transform_monthly_ffill,
    transform_monthly_ffill_diff,
    transform_flow_zscore,
    _incremental_upsert,
    _transform_for_factor,
)


async def _make_db() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker(), engine


def _days(n: int, start="2026-01-01") -> list[str]:
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


class TestProxyDiff:
    def test_common_dates_alignment(self):
        long = [("2026-01-01", 0.01), ("2026-01-02", 0.02), ("2026-01-03", -0.005)]
        short = [("2026-01-01", 0.005), ("2026-01-03", 0.01), ("2026-01-04", 0.001)]
        out = transform_proxy_diff(long, short)
        # only common dates 01-01 and 01-03 survive
        assert [(d, round(v, 6)) for d, v in out] == [
            ("2026-01-01", 0.005),
            ("2026-01-03", -0.015),
        ]

    def test_empty_intersection(self):
        out = transform_proxy_diff([("2026-01-01", 0.1)], [("2026-01-02", 0.2)])
        assert out == []


class TestLevelDiff:
    def test_scaling_bp_to_decimal(self):
        levels = [("2026-01-01", 1.50), ("2026-01-02", 1.60), ("2026-01-03", 1.40)]
        out = transform_level_diff(levels)
        # +10bp -> 0.001, -20bp -> -0.002
        assert [(d, round(v, 6)) for d, v in out] == [
            ("2026-01-02", 0.001),
            ("2026-01-03", -0.002),
        ]

    def test_spread_diff(self):
        a = [("2026-01-01", 3.0), ("2026-01-02", 3.1), ("2026-01-03", 3.05)]
        b = [("2026-01-01", 2.5), ("2026-01-02", 2.6), ("2026-01-03", 2.6)]
        out = transform_level_spread_diff(a, b)
        # spreads: 0.5, 0.5, 0.45 -> diffs (0)/100, (-0.05)/100
        assert [(d, round(v, 6)) for d, v in out] == [
            ("2026-01-02", 0.0),
            ("2026-01-03", -0.0005),
        ]

    def test_level_pct(self):
        levels = [("2026-01-01", 7.0), ("2026-01-02", 7.07), ("2026-01-03", 7.0)]
        out = transform_level_pct(levels)
        assert abs(out[0][1] - 0.01) < 1e-9      # 7.07/7.0 - 1
        assert abs(out[1][1] - (7.0 / 7.07 - 1.0)) < 1e-9


class TestFlowZscore:
    def test_scaled_unit_variance(self):
        rng = random.Random(1)
        series = [(d, rng.uniform(-10.0, 10.0)) for d in _days(120)]
        out = transform_flow_zscore(series, window=20)
        vals = np.array([v for _, v in out])
        assert len(out) == 100                      # first change lands at index 20
        assert abs(vals.mean()) < 1e-9              # zscore is centered
        assert abs(vals.std(ddof=0) - 0.1) < 1e-9   # /10 scale
        dates = [d for d, _ in out]
        assert dates == sorted(dates)

    def test_insufficient_history(self):
        series = [(d, 1.0) for d in _days(30)]
        with pytest.raises(NoDataError):
            transform_flow_zscore(series, window=20)

    def test_constant_series_guard(self):
        series = [(d, 5.0) for d in _days(80)]
        out = transform_flow_zscore(series, window=20)
        assert all(v == 0.0 for _, v in out)



    def test_flow_zscore_uses_fetched_series_not_sidecar(self):
        """Regression: northbound/margin (source != moneyflow) must feed the
        transform with their fetched daily flow series, NOT the moneyflow
        JSON sidecar (only moneyflow accumulates history in the sidecar)."""
        defn = FactorDef(
            key="northbound", name="北向", category="alpha",
            source="stock_hsgt_fund_flow_summary_em",
            transform="flow_zscore", source_config={"ma": 20},
        )
        series = [(d, float(i % 5)) for i, d in enumerate(_days(60))]
        ret, lvl = _transform_for_factor(defn, {"type": "series", "series": series})
        assert len(ret) > 0
        assert lvl == series


class TestMonthlyFfill:
    def test_mom_diff_emission(self):
        monthly = [("2025-01-01", 2.0), ("2025-02-01", 2.3), ("2025-03-01", 2.1)]
        out = transform_monthly_ffill(monthly)
        # MoM change of the level, /100, one row per monthly observation
        assert [(d, round(v, 6)) for d, v in out] == [
            ("2025-02-01", 0.003),
            ("2025-03-01", -0.002),
        ]

    def test_ffill_diff_same_math(self):
        monthly = [("2025-01-01", 54.7), ("2025-02-01", 54.5), ("2025-03-01", 57.9)]
        assert transform_monthly_ffill_diff(monthly) == transform_monthly_ffill(monthly)
        assert round(transform_monthly_ffill_diff(monthly)[0][1], 6) == -0.002


class TestIncrementalUpsert:
    def test_idempotent_and_level_rows(self):
        async def inner():
            db, engine = await _make_db()
            try:
                f = Factor(name="测试因子", key="test_key", category="macro", definition="d")
                db.add(f)
                await db.flush()
                rows = [("2026-01-01", 0.01), ("2026-01-02", 0.02), ("2026-01-03", -0.01)]
                levels = [("2026-01-01", 1.5), ("2026-01-02", 1.6)]
                n1 = await _incremental_upsert(db, f, rows, level_rows=levels)
                assert n1 == 3                       # return-kind rows written
                stored = (await db.execute(
                    select(FactorValue).where(FactorValue.factor_id == f.id)
                )).scalars().all()
                assert len(stored) == 5              # 3 return + 2 level
                # re-run identical payload -> nothing new (UNIQUE conflict skip)
                n2 = await _incremental_upsert(db, f, rows, level_rows=levels)
                assert n2 == 0
                # newer row appended, stale row not
                n3 = await _incremental_upsert(db, f, [("2026-01-04", 0.005)])
                assert n3 == 1
                total = len((await db.execute(
                    select(FactorValue).where(FactorValue.factor_id == f.id)
                )).scalars().all())
                assert total == 6
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())
