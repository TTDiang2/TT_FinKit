from typing import List, Optional

import asyncio
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, async_session_maker
from ..models.research_asset import ResearchAsset, ResearchAssetPrice
from ..schemas.research_asset import (
    ResearchAssetCreate,
    ResearchAssetPool,
    ResearchAssetUpdate,
    ResearchAssetResponse,
    ResearchAssetIndicators,
    ResearchAssetPriceStatus,
    ResearchPricePoint,
    SyncResult,
    RedeemRule,
)
from ..middleware.auth import get_current_user_id
from ..services import ifind_client
from ..services.asset_price_store import (
    sync_asset_prices,
    refresh_all_pooled,
    compute_asset_indicators,
    lag_days,
)
from ..services.price_provider import fetch_price, fetch_fund_meta, ProviderError

router = APIRouter(prefix="/api/research/assets", tags=["research-assets"])


# --------------------------------------------------------------------------- #
# Fee helpers
# --------------------------------------------------------------------------- #

def _rules_to_json(rules) -> str:
    """Serialize List[RedeemRule] (or plain dicts) to the DB Text column."""
    return json.dumps(
        [{"days": r.days, "fee_rate": r.fee_rate} for r in rules], ensure_ascii=False
    )


def _rules_to_note(rules) -> str:
    """Human-readable display text from redeem rules, e.g. "<7天 1.5%，其余 0"."""
    if not rules:
        return ""
    parts = []
    for r in rules:
        if r.days is None:
            parts.append(f"其余 {r.fee_rate:g}%")
        else:
            parts.append(f"<{r.days}天 {r.fee_rate:g}%")
    return "，".join(parts)


def _parse_rules_json(raw: Optional[str]) -> List[RedeemRule]:
    """Parse DB Text column back into RedeemRule objects (tolerant)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [RedeemRule(**d) for d in data if isinstance(d, dict)]
    except (json.JSONDecodeError, ValueError):
        return []


def _pick_benchmark(asset: ResearchAsset):
    """Map an asset to its comparison benchmark (symbol, exchange) per confirmed
    decision D2. Returns None for money-market funds (no benchmark)."""
    if asset.is_money_market:
        return None
    text = f"{asset.name or ''} {asset.category or ''}"
    if "黄金" in text or "金" in text and "现金" not in text:
        return ("518880", "SH")
    if "债" in text:
        return ("bench-cnbd", "IDX")  # 中债综合财富指数；nav_history 拉取失败降级 511010
    if any(k in text for k in ("海外", "纳指", "标普", "QDII", "美股", "港")):
        return ("513100", "SH")
    return ("000300", "SH")


async def _get_owned(asset_id: str, user_id: str, db: AsyncSession) -> ResearchAsset:
    asset = await db.get(ResearchAsset, asset_id)
    if not asset or asset.user_id != user_id:
        raise HTTPException(status_code=404, detail="标的不存在")
    return asset


async def _respond(db: AsyncSession, asset: ResearchAsset) -> ResearchAssetResponse:
    prices = (
        await db.execute(
            select(ResearchAssetPrice)
            .where(ResearchAssetPrice.asset_id == asset.id)
            .order_by(ResearchAssetPrice.date)
        )
    ).scalars().all()
    return ResearchAssetResponse(
        id=asset.id,
        symbol=asset.symbol,
        exchange=asset.exchange,
        name=asset.name,
        asset_type=asset.asset_type,
        category=asset.category,
        status=asset.status,  # type: ignore[arg-type]
        mgmt_fee=asset.mgmt_fee,
        custody_fee=asset.custody_fee,
        purchase_fee=asset.purchase_fee,
        sales_service_fee=asset.sales_service_fee,
        redeem_rules=_parse_rules_json(asset.redeem_rules),
        redeem_fee_note=asset.redeem_fee_note or _rules_to_note(_parse_rules_json(asset.redeem_rules)),
        min_purchase=asset.min_purchase,
        redeem_t_days=asset.redeem_t_days,
        liquidity_note=asset.liquidity_note or "",
        data_quality=asset.data_quality or "",
        is_money_market=bool(asset.is_money_market),
        notes=asset.notes,
        indicators=compute_asset_indicators(asset, list(prices)),
    )


async def _pool_sync_task(asset_id: str, user_id: str) -> None:
    """Background full history pull after pooling — own session (request one is closed)."""
    async with async_session_maker() as db:
        asset = await db.get(ResearchAsset, asset_id)
        if not asset:
            return
        ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
        try:
            result = await sync_asset_prices(db, asset, ifind_user, ifind_pass, full=True)
            if result.error:
                print(f"[research_assets] _pool_sync_task {asset_id}: {result.error}", flush=True)
            else:
                print(f"[research_assets] _pool_sync_task {asset_id}: {result.rows} rows, source={result.source}", flush=True)
        except Exception as e:
            print(f"[research_assets] _pool_sync_task {asset_id} FAILED: {type(e).__name__}: {e}", flush=True)


async def _sync_asset_prices_task(asset_id: str, user_id: str) -> None:
    """Lightweight sync for watchlist assets (default full=False, recent ~2Y).

    Lets the user see the NAV curve in the detail panel before pooling.
    """
    async with async_session_maker() as db:
        asset = await db.get(ResearchAsset, asset_id)
        if not asset:
            return
        ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
        try:
            result = await sync_asset_prices(db, asset, ifind_user, ifind_pass, full=False)
            if result.error:
                print(f"[research_assets] _sync_asset_prices_task {asset_id}: {result.error}", flush=True)
            else:
                print(f"[research_assets] _sync_asset_prices_task {asset_id}: {result.rows} rows, source={result.source}", flush=True)
        except Exception as e:
            print(f"[research_assets] _sync_asset_prices_task {asset_id} FAILED: {type(e).__name__}: {e}", flush=True)


@router.get("", response_model=List[ResearchAssetResponse])
async def list_assets(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(ResearchAsset).where(ResearchAsset.user_id == user_id)
    if status:
        q = q.where(ResearchAsset.status == status)
    if category:
        q = q.where(ResearchAsset.category == category)
    if search:
        like = f"%{search}%"
        q = q.where((ResearchAsset.name.like(like)) | (ResearchAsset.symbol.like(like)))
    assets = (await db.execute(q.order_by(ResearchAsset.created_at))).scalars().all()
    return [await _respond(db, a) for a in assets]


@router.post("", response_model=ResearchAssetResponse)
async def create_asset(
    req: ResearchAssetCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    symbol = req.symbol.strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="代码不能为空")

    dup = (
        await db.execute(
            select(ResearchAsset).where(
                ResearchAsset.user_id == user_id, ResearchAsset.symbol == symbol
            )
        )
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="该代码已在标的池中")

    name = req.name.strip()
    is_money_market = req.is_money_market
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    if not name or not is_money_market:
        try:
            quote = await fetch_price(symbol, req.exchange or "FUND_CN", ifind_user, ifind_pass)
            if not name:
                name = quote.name or name
            if quote.source == "eastmoney-money-market":
                is_money_market = True
        except ProviderError:
            pass
    if (not name or not is_money_market) and (req.exchange or "FUND_CN") == "FUND_CN":
        # iFinD quotes carry no name — eastmoney pingzhongdata fills name + ishb
        meta = await fetch_fund_meta(symbol)
        if meta:
            if not name:
                name = meta[0] or name
            is_money_market = is_money_market or meta[1]

    if not name:
        name = symbol

    asset = ResearchAsset(
        user_id=user_id,
        symbol=symbol,
        exchange=req.exchange or "FUND_CN",
        name=name,
        asset_type=req.asset_type,
        category=req.category,
        is_money_market=bool(is_money_market),
        notes=req.notes,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    # Trigger background price sync so the watchlist asset has history for the
    # detail-panel NAV chart. Pooled assets do this in pool_asset (full=True).
    asyncio.create_task(_sync_asset_prices_task(asset.id, user_id))

    return await _respond(db, asset)


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    await db.execute(delete(ResearchAssetPrice).where(ResearchAssetPrice.asset_id == asset.id))
    await db.delete(asset)
    await db.commit()
    return {"message": "deleted"}


# Static paths must be registered BEFORE /{asset_id} routes — FastAPI matches
# in declaration order and would otherwise treat "price-status" as an asset id.
@router.post("/refresh-prices", response_model=List[SyncResult])
async def refresh_prices(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    return await refresh_all_pooled(db, user_id, ifind_user, ifind_pass)


@router.get("/price-status", response_model=List[ResearchAssetPriceStatus])
async def price_status(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    assets = (
        await db.execute(
            select(ResearchAsset).where(ResearchAsset.user_id == user_id)
            .order_by(ResearchAsset.created_at)
        )
    ).scalars().all()
    if not assets:
        return []

    rows = (
        await db.execute(
            select(
                ResearchAssetPrice.asset_id,
                func.count(ResearchAssetPrice.id),
                func.max(ResearchAssetPrice.date),
                func.max(ResearchAssetPrice.updated_at),
                func.max(ResearchAssetPrice.source),
            ).where(ResearchAssetPrice.asset_id.in_([a.id for a in assets]))
            .group_by(ResearchAssetPrice.asset_id)
        )
    ).all()
    stats = {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}

    out: List[ResearchAssetPriceStatus] = []
    for a in assets:
        rows_n, last_date, last_sync, source = stats.get(a.id, (0, None, None, None))
        out.append(
            ResearchAssetPriceStatus(
                asset_id=a.id,
                symbol=a.symbol,
                name=a.name,
                status=a.status,  # type: ignore[arg-type]
                rows=rows_n,
                last_date=last_date,
                last_sync=str(last_sync) if last_sync else None,
                source=source,
                lag_days=lag_days(last_date),
            )
        )
    return out


@router.get("/{asset_id}", response_model=ResearchAssetResponse)
async def get_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    return await _respond(db, asset)


@router.get("/{asset_id}/nav-history")
async def get_nav_history(
    asset_id: str,
    days: Optional[int] = Query(None),
    with_benchmark: bool = Query(False),
    with_ma: bool = Query(False),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Asset NAV history.

    Plain call (no extra params) → legacy List[ResearchPricePoint] (all rows).
    With ``days``/``with_benchmark``/``with_ma`` → NavHistoryDetail with
    optional MA20/MA60 and a comparison benchmark (per D2 mapping).
    """
    asset = await _get_owned(asset_id, user_id, db)
    q = select(ResearchAssetPrice).where(ResearchAssetPrice.asset_id == asset.id)
    if days and days > 0:
        begin = (date.today() - timedelta(days=days)).isoformat()
        q = q.where(ResearchAssetPrice.date >= begin)
    q = q.order_by(ResearchAssetPrice.date)
    prices = (await db.execute(q)).scalars().all()

    if not (days or with_benchmark or with_ma):
        return [
            ResearchPricePoint(date=p.date, close=p.close, nav=p.nav, acc_nav=p.acc_nav)
            for p in prices
        ]

    # Build enhanced response
    from ..schemas.research_asset import NavHistoryDetail, NavPoint, BenchmarkSeries
    from ..services import nav_history as nav_svc

    series = [
        NavPoint(date=p.date, close=p.close)
        for p in prices
    ]
    # MA20/MA60 via indicators.sma (same as backtest engine)
    if with_ma and len(series) >= 2:
        from ..services.indicators import sma
        closes = [p.close for p in series]
        ma20 = sma(closes, 20)
        ma60 = sma(closes, 60)
        for i, pt in enumerate(series):
            pt.ma20 = round(ma20[i], 6) if ma20[i] is not None else None
            pt.ma60 = round(ma60[i], 6) if ma60[i] is not None else None

    benchmark = None
    bench_source = ""
    if with_benchmark:
        picked = _pick_benchmark(asset)
        if picked:
            bench_symbol, bench_exchange = picked
            begin_d = (date.today() - timedelta(days=days or 365)).isoformat()
            end_d = date.today().isoformat()
            b_series, b_err = await nav_svc.fetch_asset_benchmark(
                bench_symbol, bench_exchange, begin_d, end_d,
            )
            if b_series:
                bench_name = {
                    "000300": "沪深300", "518880": "黄金ETF", "513100": "纳指ETF",
                    "bench-cnbd": "中债综合财富",
                }.get(bench_symbol, bench_symbol)
                benchmark = BenchmarkSeries(
                    name=bench_name,
                    symbol=bench_symbol,
                    exchange=bench_exchange,
                    series=b_series,
                )
                bench_source = b_err or "tencent"
            else:
                bench_source = b_err or "基准获取失败"

    return NavHistoryDetail(series=series, benchmark=benchmark, source=bench_source)


@router.post("/{asset_id}/pool", response_model=ResearchAssetResponse)
async def pool_asset(
    asset_id: str,
    req: ResearchAssetPool,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    data = req.model_dump(exclude_unset=True)
    rules = data.pop("redeem_rules", None)
    if rules:
        asset.redeem_rules = _rules_to_json(rules)
        if not data.get("redeem_fee_note"):
            asset.redeem_fee_note = _rules_to_note(rules)
    for key, value in data.items():
        setattr(asset, key, value)
    asset.status = "pooled"
    await db.commit()
    await db.refresh(asset)
    asyncio.create_task(_pool_sync_task(asset.id, user_id))
    return await _respond(db, asset)


@router.put("/{asset_id}", response_model=ResearchAssetResponse)
async def update_asset(
    asset_id: str,
    req: ResearchAssetUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    data = req.model_dump(exclude_unset=True)
    rules = data.pop("redeem_rules", None)
    if rules is not None:
        asset.redeem_rules = _rules_to_json(rules)
        if not data.get("redeem_fee_note"):
            asset.redeem_fee_note = _rules_to_note(rules)
    for key, value in data.items():
        setattr(asset, key, value)
    await db.commit()
    await db.refresh(asset)
    return await _respond(db, asset)


@router.get("/{asset_id}/holdings")
async def get_asset_holdings(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Cached holdings transparency (quarterly top-10 + asset class mix)."""
    asset = await _get_owned(asset_id, user_id, db)
    from ..services import asset_holdings
    if not asset_holdings.is_eligible(asset):
        return {"status": "unsupported", "report_date": None, "asset_classes": [], "top_holdings": []}
    data = await asset_holdings.get_holdings(db, asset)
    data["status"] = "ok"
    return data


@router.post("/{asset_id}/holdings/refresh")
async def refresh_asset_holdings(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a fresh akshare pull of quarterly holdings (async-safe, cached 7d)."""
    asset = await _get_owned(asset_id, user_id, db)
    from ..services import asset_holdings
    if not asset_holdings.is_eligible(asset):
        return {"status": "unsupported", "report_date": None, "asset_classes": [], "top_holdings": []}
    try:
        data = await asset_holdings.refresh_holdings(db, asset)
        await db.commit()
        data["status"] = "ok"
        return data
    except RuntimeError as e:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"持仓数据获取失败：{e}")


@router.post("/{asset_id}/sync", response_model=SyncResult)
async def sync_asset(
    asset_id: str,
    full: bool = Query(False),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    result = await sync_asset_prices(db, asset, ifind_user, ifind_pass, full=full)
    if result.error:
        raise HTTPException(status_code=502, detail=f"行情同步失败：{result.error}")
    return result
