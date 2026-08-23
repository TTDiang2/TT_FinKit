"""Holdings transparency for pooled funds — quarterly top-10 holdings + asset
class mix via akshare, cached in ``research_asset_holdings``.

Data-source fallback chain (all via akshare):
1. ``fund_portfolio_hold_em``  — 天天基金季度股票重仓（股票/混合型基金）
2. ``fund_individual_detail_hold_xq`` — 雪球资产配置（现金/债券/股票/其他；商品/ETF 类也有）
3. ``fund_individual_basic_info_xq`` — 雪球基金档案（基金类型等附加信息）

Only meaningful for ``FUND_CN`` funds (``exchange == 'FUND_CN'`` and
``asset_type == 'fund'``). Other types return ``unsupported``.
"""
import asyncio
import json
from datetime import datetime, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.research_asset import ResearchAsset
from ..models.research_asset_holding import ResearchAssetHolding

CACHE_MAX_AGE_DAYS = 7


def is_eligible(asset: ResearchAsset) -> bool:
    return asset.exchange == "FUND_CN" and asset.asset_type == "fund"


async def get_holdings(db: AsyncSession, asset: ResearchAsset) -> dict:
    """Return cached holdings (if fresh) or empty payload."""
    res = await db.execute(
        select(ResearchAssetHolding)
        .where(ResearchAssetHolding.asset_id == asset.id)
        .order_by(ResearchAssetHolding.report_date.desc())
    )
    rows = list(res.scalars().all())
    if not rows:
        return {"report_date": None, "asset_classes": [], "top_holdings": [], "fund_type": None}
    report_date = rows[0].report_date
    asset_classes = [
        {"name": r.name, "ratio": r.ratio}
        for r in rows if r.kind == "asset_class"
    ]
    top_holdings = [
        {"name": r.name, "ratio": r.ratio}
        for r in rows if r.kind == "top_holding"
    ]
    fund_type = next((r.name for r in rows if r.kind == "fund_type"), None)
    return {"report_date": report_date, "asset_classes": asset_classes,
            "top_holdings": top_holdings, "fund_type": fund_type}


async def refresh_holdings(db: AsyncSession, asset: ResearchAsset) -> dict:
    """Fetch fresh holdings via the fallback chain and persist.

    Raises RuntimeError when no source returns anything usable.
    """
    if not is_eligible(asset):
        raise RuntimeError("unsupported")

    def _fetch_top() -> list[dict]:
        """天天基金季度股票重仓；商品/ETF/货币类基金通常返回空表。"""
        import akshare as ak
        top = ak.fund_portfolio_hold_em(symbol=asset.symbol)
        return top.to_dict("records") if top is not None else []

    def _fetch_mix() -> list[dict]:
        """雪球资产配置：资产类型 / 仓位占比（%）。"""
        import akshare as ak
        df = ak.fund_individual_detail_hold_xq(symbol=asset.symbol)
        return df.to_dict("records") if df is not None else []

    def _fetch_basic() -> dict:
        """雪球基金档案：基金类型等。"""
        import akshare as ak
        df = ak.fund_individual_basic_info_xq(symbol=asset.symbol)
        out: dict[str, str] = {}
        if df is not None:
            for r in df.to_dict("records"):
                k = str(r.get("item") or "").strip()
                v = r.get("value")
                if k and v is not None:
                    out[k] = str(v)
        return out

    async def _safe(fn, retries: int = 1):
        """Run fetch in a thread, swallow errors, retry once (xq is rate-limited)."""
        for attempt in range(retries + 1):
            try:
                return await asyncio.to_thread(fn)
            except Exception:
                if attempt < retries:
                    await asyncio.sleep(1.0)
                    continue
                return None

    top_rows = await _safe(_fetch_top) or []
    mix_rows = (await _safe(_fetch_mix) or []) if not top_rows else []
    basic = (await _safe(_fetch_basic) or {}) if not top_rows else {}

    if not top_rows and not mix_rows:
        raise RuntimeError(
            "未获取到该基金的持仓数据（天天基金与雪球均无返回，"
            "可能为场内 ETF 或数据源暂不可用）"
        )

    # Clear old rows and write fresh ones
    await db.execute(
        delete(ResearchAssetHolding).where(ResearchAssetHolding.asset_id == asset.id)
    )
    added = 0
    report_date = datetime.utcnow().strftime("%Y-%m-%d")

    if top_rows:
        # akshare returns ALL historical quarters — keep only the latest quarter
        def _quarter_key(r: dict) -> str:
            for key in ("季度", "截止日期", "报告期", "日期"):
                if r.get(key):
                    return str(r[key])
            return ""

        q_keys = [_quarter_key(r) for r in top_rows]
        latest_q = max(q_keys) if q_keys else ""
        latest_rows = [r for r in top_rows if _quarter_key(r) == latest_q]
        # report_date → quarter-end date (2024年2季度 → 2024-06-30)
        import re
        m = re.search(r"(\d{4})年(\d)季度", latest_q)
        if m:
            year, q = int(m.group(1)), int(m.group(2))
            report_date = f"{year}-{['03', '06', '09', '12'][q - 1]}-{['31', '30', '30', '31'][q - 1]}"
        for r in latest_rows[:10]:
            name = r.get("股票名称") or r.get("名称") or r.get("基金代码")
            ratio = r.get("占净值比例") or r.get("持仓占比")
            if not name:
                continue
            db.add(ResearchAssetHolding(
                asset_id=asset.id,
                report_date=report_date,
                kind="top_holding",
                name=str(name),
                ratio=float(ratio) if ratio is not None else None,
                raw=json.dumps(r, ensure_ascii=False, default=str),
            ))
            added += 1
    elif mix_rows:
        # 商品/ETF/货币类基金：只有资产配置，没有股票重仓
        for r in mix_rows:
            label = str(r.get("资产类型") or r.get("asset_type") or "").strip()
            value = r.get("仓位占比") or r.get("ratio")
            if not label or value is None:
                continue
            db.add(ResearchAssetHolding(
                asset_id=asset.id, report_date=report_date,
                kind="asset_class", name=label, ratio=float(value),
                raw=json.dumps(r, ensure_ascii=False, default=str),
            ))
            added += 1
        if basic.get("基金类型"):
            db.add(ResearchAssetHolding(
                asset_id=asset.id, report_date=report_date,
                kind="fund_type", name=basic["基金类型"], ratio=None,
                raw=json.dumps({"fund_type": basic["基金类型"]}, ensure_ascii=False),
            ))

    await db.flush()
    if added == 0:
        raise RuntimeError("解析持仓数据失败")
    return await get_holdings(db, asset)


async def is_fresh(db: AsyncSession, asset: ResearchAsset) -> bool:
    res = await db.execute(
        select(ResearchAssetHolding.updated_at)
        .where(ResearchAssetHolding.asset_id == asset.id)
        .limit(1)
    )
    updated = res.scalar_one_or_none()
    if updated is None:
        return False
    return datetime.utcnow() - updated.replace(tzinfo=None) < timedelta(days=CACHE_MAX_AGE_DAYS)
