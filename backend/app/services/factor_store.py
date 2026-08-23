"""Factor value warehouse: preset seeding + proxy/spread series sync (Phase 2).

Factor returns are derived from the same verified pipeline as research prices
(nav_history.fetch_history_series).  Each sync writes two kinds of rows per
date: ``level`` (raw close / spread level, display) and ``return`` (daily
pct-change / return spread, the regression input).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.factor import Factor, FactorValue
from ..schemas.factor import FactorConfig, FactorSyncResult
from . import nav_history

_FULL_BEGIN = "1990-01-01"
# incremental sync re-pulls a one-week tail: pct-change needs the previous
# close, and long holidays (CNY) can make the last trading day > 3 days old
_TAIL_BUFFER_DAYS = 7
_BATCH = 500

PRESET_FACTORS: list[dict] = [
    {
        "name": "权益(沪深300)",
        "category": "asset_class",
        "definition": "A 股大盘权益市场因子，沪深300 指数日收益率",
        "config": {"type": "proxy", "symbol": "000300", "exchange": "SH"},
        "proxy_symbol": "000300",
        "is_market": True,
    },
    {
        "name": "小盘(中证1000)",
        "category": "asset_class",
        "definition": "A 股小盘权益因子，中证1000 指数日收益率",
        "config": {"type": "proxy", "symbol": "000852", "exchange": "SH"},
        "proxy_symbol": "000852",
        "is_market": False,
    },
    {
        "name": "债券(国债ETF)",
        "category": "asset_class",
        "definition": "利率债因子，国债ETF(511010)日收益率",
        "config": {"type": "proxy", "symbol": "511010", "exchange": "SH"},
        "proxy_symbol": "511010",
        "is_market": False,
    },
    {
        "name": "信用债(城投债ETF)",
        "category": "asset_class",
        "definition": "信用债因子，城投债ETF(511220)日收益率（中证信用债指数 H30269 数据源不可用，以 ETF 代理）",
        "config": {"type": "proxy", "symbol": "511220", "exchange": "SH"},
        "proxy_symbol": "511220",
        "is_market": False,
    },
    {
        "name": "黄金(黄金ETF)",
        "category": "asset_class",
        "definition": "商品/黄金因子，黄金ETF(518880)日收益率",
        "config": {"type": "proxy", "symbol": "518880", "exchange": "SH"},
        "proxy_symbol": "518880",
        "is_market": False,
    },
    {
        "name": "海外权益(纳指ETF)",
        "category": "asset_class",
        "definition": "海外权益因子，纳指ETF(513100)日收益率（QDII，净值披露滞后由共同交易日对齐处理）",
        "config": {"type": "proxy", "symbol": "513100", "exchange": "SH"},
        "proxy_symbol": "513100",
        "is_market": False,
    },
    {
        "name": "规模(小盘−沪深300)",
        "category": "style",
        "definition": "规模风格价差因子：中证1000 日收益率 − 沪深300 日收益率。与大类权益因子精确共线，回归时由 VIF 检测自动切岭回归",
        "config": {
            "type": "spread",
            "long": {"type": "proxy", "symbol": "000852", "exchange": "SH"},
            "short": {"type": "proxy", "symbol": "000300", "exchange": "SH"},
        },
        "proxy_symbol": "000852-000300",
        "is_market": False,
    },
]


async def seed_preset_factors(db: AsyncSession) -> int:
    """Insert preset factors that do not exist yet (idempotent by name).

    Seeds BOTH the legacy asset-class factors (PRESET_FACTORS) AND the V2
    registry (60 factors across style/industry/country/macro/statistical/alpha)
    via ``factor_registry.ensure_factors``.
    """
    from .factor_registry import ensure_factors

    added = 0
    for spec in PRESET_FACTORS:
        exists = (await db.execute(select(Factor).where(Factor.name == spec["name"]))).scalar_one_or_none()
        if exists:
            continue
        db.add(Factor(
            name=spec["name"],
            category=spec["category"],
            definition=spec["definition"],
            data_source="ifind/eastmoney",
            proxy_symbol=spec["proxy_symbol"],
            config=json.dumps(spec["config"], ensure_ascii=False),
            is_market=spec["is_market"],
        ))
        added += 1

    # V2 registry: 60 factors across 6 categories (idempotent by key)
    await ensure_factors(db)

    await db.commit()
    return added


def _config_of(factor: Factor) -> Optional[FactorConfig]:
    if not factor.config:
        return None
    try:
        return FactorConfig.model_validate_json(factor.config)
    except Exception:
        return None


async def _pull(
    symbol: str,
    exchange: str,
    begin: str,
    end: str,
    ifind_user: Optional[str],
    ifind_pass: Optional[str],
) -> tuple[list[tuple[str, float]], str]:
    series, source = await nav_history.fetch_history_series(
        symbol, exchange, begin, end, ifind_user, ifind_pass
    )
    return [(p["date"], float(p["close"])) for p in series], source


def _returns_from_levels(levels: list[tuple[str, float]]) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for i in range(1, len(levels)):
        prev_c = levels[i - 1][1]
        if prev_c > 0:
            out.append((levels[i][0], levels[i][1] / prev_c - 1.0))
    return out


def _chunks(rows: list[dict]) -> list[list[dict]]:
    return [rows[i : i + _BATCH] for i in range(0, len(rows), _BATCH)]


async def _upsert_values(db: AsyncSession, factor_id: str, rows: list[dict]) -> int:
    for chunk in _chunks(rows):
        await db.execute(
            sqlite_insert(FactorValue)
            .values(chunk)
            .on_conflict_do_update(
                index_elements=["factor_id", "date", "kind"],
                set_={"value": sqlite_insert(FactorValue).excluded.value},
            )
        )
    return len(rows)


async def sync_factor_values(
    db: AsyncSession,
    factor: Factor,
    ifind_user: Optional[str] = None,
    ifind_pass: Optional[str] = None,
    full: bool = False,
) -> FactorSyncResult:
    """Pull and persist factor value series (idempotent upsert on factor/date/kind).

    full=True wipes and rebuilds; otherwise a 7-day tail is re-pulled so the
    pct-change of the newest day is recomputed with a valid previous close.
    """
    cfg = _config_of(factor)
    if cfg is None or cfg.type not in ("proxy", "spread"):
        return FactorSyncResult(factor_id=factor.id, name=factor.name, error="factor has no valid config")

    latest_level = (
        await db.execute(
            select(FactorValue.date)
            .where(FactorValue.factor_id == factor.id, FactorValue.kind == "level")
            .order_by(FactorValue.date.desc())
            .limit(1)
        )
    ).scalar()

    if full or latest_level is None:
        begin = _FULL_BEGIN
        await db.execute(delete(FactorValue).where(FactorValue.factor_id == factor.id))
    else:
        begin = (date.fromisoformat(latest_level) - timedelta(days=_TAIL_BUFFER_DAYS)).isoformat()
    end = date.today().strftime("%Y-%m-%d")

    try:
        if cfg.type == "proxy":
            levels, source = await _pull(cfg.symbol, cfg.exchange, begin, end, ifind_user, ifind_pass)
            returns = _returns_from_levels(levels)
        else:
            if cfg.long is None or cfg.short is None:
                return FactorSyncResult(factor_id=factor.id, name=factor.name, error="spread config missing long/short")
            long_levels, s1 = await _pull(cfg.long.symbol, cfg.long.exchange, begin, end, ifind_user, ifind_pass)
            short_levels, s2 = await _pull(cfg.short.symbol, cfg.short.exchange, begin, end, ifind_user, ifind_pass)
            source = s1 if s1 == s2 else f"{s1}/{s2}"
            long_map, short_map = dict(long_levels), dict(short_levels)
            common = sorted(set(long_map) & set(short_map))
            # spread level/return are computed on consecutive *common* dates so
            # both legs cover identical spans even around holidays
            levels = [(d, long_map[d] - short_map[d]) for d in common]
            returns = _returns_from_levels(levels)
    except nav_history.NavHistoryError as e:
        return FactorSyncResult(factor_id=factor.id, name=factor.name, error=str(e))

    if not levels:
        return FactorSyncResult(factor_id=factor.id, name=factor.name, rows=0, source=source,
                                begin=begin, end=end, error="empty series")

    rows = (
        [{"factor_id": factor.id, "date": d, "value": v, "kind": "level"} for d, v in levels]
        + [{"factor_id": factor.id, "date": d, "value": v, "kind": "return"} for d, v in returns]
    )
    await _upsert_values(db, factor.id, rows)
    await db.commit()

    return FactorSyncResult(
        factor_id=factor.id,
        name=factor.name,
        rows=len(returns),
        source=source,
        begin=levels[0][0],
        end=levels[-1][0],
    )


async def refresh_all_factors(
    db: AsyncSession,
    ifind_user: Optional[str] = None,
    ifind_pass: Optional[str] = None,
) -> list[FactorSyncResult]:
    """Incremental refresh for every active factor, serial and failure-isolated."""
    factors = (
        await db.execute(select(Factor).where(Factor.active.is_(True)).order_by(Factor.created_at))
    ).scalars().all()
    results: list[FactorSyncResult] = []
    for factor in factors:
        try:
            results.append(await sync_factor_values(db, factor, ifind_user, ifind_pass))
        except Exception as e:  # noqa: BLE001 — one bad source must not kill the batch
            results.append(FactorSyncResult(factor_id=factor.id, name=factor.name, error=str(e)))
    return results


async def factor_stats(db: AsyncSession, factor: Factor) -> tuple[Optional[float], Optional[float], Optional[str], int]:
    """(latest_return, latest_level, latest_date, return_rows) for list display."""
    row = (await db.execute(
        select(FactorValue.value, FactorValue.date)
        .where(FactorValue.factor_id == factor.id, FactorValue.kind == "return")
        .order_by(FactorValue.date.desc())
        .limit(1)
    )).first()
    level = (await db.execute(
        select(FactorValue.value)
        .where(FactorValue.factor_id == factor.id, FactorValue.kind == "level")
        .order_by(FactorValue.date.desc())
        .limit(1)
    )).scalar()
    count = (await db.execute(
        select(func.count())
        .select_from(FactorValue)
        .where(FactorValue.factor_id == factor.id, FactorValue.kind == "return")
    )).scalar()
    return (row.value if row else None), level, (row.date if row else None), int(count or 0)
