"""持仓穿透原型（用户拍板 2026-08-29：报告 + 独特性因子）。

层级：
  L1 大类资产占比（股票/债券/现金/其他）：全池可拉，相似度 = 1 - TV距离。
  L2 十大重仓（股票型/混合型）：akshare 按需拉，重叠度 = 重仓名集合 Jaccard。

报告 = 给定一组标的 → 两两相似度矩阵 + 每只标的的"最相似同伴" +
独特性得分（1 - 最大重叠度），并写回 research_asset_stats（独特性因子）。
"""
from __future__ import annotations

import asyncio
import math
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.research_asset import ResearchAsset
from ..models.research_asset_holding import ResearchAssetHolding as ResearchAssetHoldings
from ..services import asset_holdings


async def _ensure_holdings(db: AsyncSession, asset: ResearchAsset,
                           force: bool = False) -> bool:
    """确保持仓数据存在（默认 30 天新鲜度）。返回是否有 L2 十大重仓。"""
    fresh = await asset_holdings.get_holdings(db, asset)
    if force or not fresh.get("report_date"):
        try:
            await asset_holdings.refresh_holdings(db, asset)
        except Exception:  # noqa: BLE001 — 单只失败不阻断
            return False
    rows = (await db.execute(
        select(ResearchAssetHoldings).where(
            ResearchAssetHoldings.asset_id == asset.id,
            ResearchAssetHoldings.kind == "top_holding")
    )).scalars().all()
    return bool(rows)


def _mix_vector(db_rows: list) -> dict[str, float]:
    return {r.name: (r.ratio or 0.0) for r in db_rows if r.kind == "asset_class"}


def _mix_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """1 - 半总变化距离（0=完全不同 1=完全相同）。"""
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    tv = sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys) / 2.0
    return max(0.0, 1.0 - tv)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


async def lookthrough_report(db: AsyncSession, user_id: str,
                             symbols: list[str], force: bool = False,
                             max_fetch: int = 20) -> dict:
    ph = ",".join("?" for _ in symbols)
    assets = (await db.execute(
        select(ResearchAsset).where(
            ResearchAsset.user_id == user_id,
            ResearchAsset.symbol.in_(symbols))
    )).scalars().all()
    fetched = 0
    mix: dict[str, dict[str, float]] = {}
    tops: dict[str, set[str]] = {}
    report_date: dict[str, str | None] = {}

    for a in assets:
        has_l2 = await _ensure_holdings(db, a, force=force)
        fetched += 1
        rows = (await db.execute(
            select(ResearchAssetHoldings).where(
                ResearchAssetHoldings.asset_id == a.id)
        )).scalars().all()
        mix[a.symbol] = _mix_vector(rows)
        report_date[a.symbol] = max(
            (r.report_date for r in rows), default=None)
        if has_l2:
            tops[a.symbol] = {
                (r.name or "").strip() for r in rows
                if r.kind == "top_holding" and r.name
            }
        if fetched >= max_fetch:
            await db.commit()
            break
    await db.commit()

    # 两两相似度
    syms = [a.symbol for a in assets][:max_fetch]
    pairs: list[dict] = []
    names = {a.symbol: a.name for a in assets}
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            s1, s2 = syms[i], syms[j]
            sim_mix = _mix_similarity(mix.get(s1, {}), mix.get(s2, {}))
            if s1 in tops and s2 in tops:
                overlap = _jaccard(tops[s1], tops[s2])
                level = "L2-重仓"
            elif mix.get(s1) and mix.get(s2):
                overlap = sim_mix
                level = "L1-大类"
            else:
                overlap = None
                level = "no_data"
            pairs.append({"a": s1, "b": s2,
                          "similarity": round(overlap, 4), "level": level})
    pairs.sort(key=lambda x: -(x["similarity"] if x["similarity"] is not None else -1))

    uniqueness: dict[str, float] = {}
    for s1 in syms:
        sims = [p["similarity"] for p in pairs
                if (p["a"] == s1 or p["b"] == s1) and p["level"] != "no_data"]
        if not mix.get(s1) and s1 not in tops:
            uniqueness[s1] = None  # 无持仓数据，无法计算独特性
            continue
        uniqueness[s1] = round(1.0 - max(sims), 4) if sims else 1.0

    # 独特性得分写入预计算表（因子化）
    conn = await db.connection()
    for s1, score in uniqueness.items():
        await conn.exec_driver_sql(
            "UPDATE research_asset_stats SET uniqueness=? WHERE asset_id IN "
            "(SELECT id FROM research_assets WHERE symbol=? AND user_id=?)",
            (score, s1, user_id))
    await db.commit()

    return {
        "as_of": datetime.utcnow().isoformat(),
        "symbols": syms,
        "names": names,
        "report_dates": report_date,
        "pairs": pairs[:50],
        "uniqueness": uniqueness,
        "note": "L2-重仓=十大重仓 Jaccard；L1-大类=资产占比总变化距离（无重仓名细时降级）",
    }
