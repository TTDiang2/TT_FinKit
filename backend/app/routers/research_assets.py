from typing import List, Optional

import asyncio
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
        redeem_fee_note=asset.redeem_fee_note or "",
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
        await sync_asset_prices(db, asset, ifind_user, ifind_pass, full=True)


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


@router.get("/{asset_id}/nav-history", response_model=List[ResearchPricePoint])
async def get_nav_history(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    prices = (
        await db.execute(
            select(ResearchAssetPrice)
            .where(ResearchAssetPrice.asset_id == asset.id)
            .order_by(ResearchAssetPrice.date)
        )
    ).scalars().all()
    return [
        ResearchPricePoint(date=p.date, close=p.close, nav=p.nav, acc_nav=p.acc_nav)
        for p in prices
    ]


@router.post("/{asset_id}/pool", response_model=ResearchAssetResponse)
async def pool_asset(
    asset_id: str,
    req: ResearchAssetPool,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    for key, value in req.model_dump(exclude_unset=True).items():
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
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(asset, key, value)
    await db.commit()
    await db.refresh(asset)
    return await _respond(db, asset)


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
