from typing import List, Optional

import asyncio
import json
import math
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_public_db, get_private_db, async_session_maker
from ..models.research_asset import ResearchAsset, ResearchAssetPrice
from ..models.research_group import ResearchGroup, ResearchGroupMember
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
    WatchlistImportRequest,
    WatchlistImportItem,
    BatchPoolRequest,
    BatchPoolResponse,
    BatchPoolRejected,
    AuditPooledResult,
    BatchRefreshProfilesRequest,
    ProfileRefreshResult,
    ResearchGroupCreate,
    ResearchGroupUpdate,
    ResearchGroupResponse,
)
from ..middleware.auth import get_current_user_id
from ..services import ifind_client, asset_holdings, fund_profile
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

def _rule_pair(r) -> tuple[Optional[int], float]:
    """(days, fee_rate) from a RedeemRule or a plain dict (model_dump output)."""
    if isinstance(r, dict):
        return r.get("days"), float(r.get("fee_rate") or 0.0)
    return r.days, r.fee_rate


def _rules_to_json(rules) -> str:
    """Serialize List[RedeemRule] (or plain dicts) to the DB Text column."""
    return json.dumps(
        [dict(zip(("days", "fee_rate"), _rule_pair(r))) for r in rules],
        ensure_ascii=False,
    )


def _rules_to_note(rules) -> str:
    """Human-readable display text from redeem rules, e.g. "<7天 1.5%，其余 0"."""
    if not rules:
        return ""
    parts = []
    for days, fee in map(_rule_pair, rules):
        if days is None:
            parts.append(f"其余 {fee:g}%")
        else:
            parts.append(f"<{days}天 {fee:g}%")
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


async def _get_public(asset_id: str, db: AsyncSession) -> ResearchAsset:
    """public 标的任何人可读（共享池），写操作才用 _get_owned。"""
    asset = await db.get(ResearchAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="标的不存在")
    return asset


async def _respond(db: AsyncSession, asset: ResearchAsset,
                   stats_row=None) -> ResearchAssetResponse:
    # indicators 优先读预计算表（O(1)）；stats_row 为 None 时才回退拉全历史现算
    if stats_row is not None and (stats_row.rows or 0) >= 30:
        prices = []
        indicators = {
            "points": stats_row.rows or 0,
            "first_date": None,
            "last_date": stats_row.last_date,
            "latest_close": None,
            "ret_1m": stats_row.ret_21d,
            "ret_1y": stats_row.ret_252d,
            "ann_return": stats_row.ann_all,
            "ann_volatility": stats_row.vol_all,
            "sharpe": stats_row.sharpe_all,
            "ann_return_1y": stats_row.ann_1y,
            "ann_volatility_1y": stats_row.vol_1y,
            "sharpe_1y": stats_row.sharpe_1y,
            "max_drawdown": stats_row.mdd_1y,
        }
    else:
        prices = (
            await db.execute(
                select(ResearchAssetPrice)
                .where(ResearchAssetPrice.asset_id == asset.id)
                .order_by(ResearchAssetPrice.date)
            )
        ).scalars().all()
        indicators = compute_asset_indicators(asset, list(prices))
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
        purchase_limit=asset.purchase_limit,
        purchase_status=asset.purchase_status or "",
        fund_kind=asset.fund_kind or "",
        asset_class=asset.asset_class or "",
        region=asset.region or "",
        auto_tags=fund_profile.read_auto_tags(asset.auto_tags),
        profile_synced_at=str(asset.profile_synced_at) if asset.profile_synced_at else None,
        indicators=indicators,
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


@router.get("/selector")
async def assets_selector(
    status: Optional[str] = Query(None),
    group_id: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """轻量标的选择器列表（统计页）：读预计算表 research_asset_stats，
    不再拉价格现算（旧实现拉 320 万行现算夏普 = 12 秒，2026-08-29）。"""
    from ..models.research_asset_stats import ResearchAssetStats

    aq = select(ResearchAsset, ResearchAssetStats).join(
        ResearchAssetStats, ResearchAssetStats.asset_id == ResearchAsset.id, isouter=True
    ).where()
    if status:
        aq = aq.where(ResearchAsset.status == status)
    if group_id:
        from ..models.research_group import ResearchGroupMember
        member_ids = select(ResearchGroupMember.asset_id).where(
            ResearchGroupMember.group_id == group_id)
        aq = aq.where(ResearchAsset.id.in_(member_ids))
    aq = aq.order_by(ResearchAsset.created_at)
    pairs = (await db.execute(aq)).all()

    items = []
    for a, st in pairs:
        has_data = st is not None and (st.rows or 0) >= 60
        items.append({
            "id": a.id, "symbol": a.symbol, "name": a.name, "status": a.status,
            "category": a.category or "", "fund_kind": a.fund_kind or "",
            "asset_class": a.asset_class or "", "region": a.region or "",
            "exchange": a.exchange or "", "is_money_market": bool(a.is_money_market),
            "has_data": has_data,
            "sharpe_1y": st.sharpe_1y if (st is not None and has_data) else None,
        })
    return {"items": items}



# --------------------------------------------------------------------------- #
# Research groups (标的组合)
# --------------------------------------------------------------------------- #

@router.get("/groups", response_model=List[ResearchGroupResponse])
async def list_groups(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    id_rows = (await db.execute(
        select(ResearchAsset.id, ResearchAsset.symbol, ResearchAsset.name)
        .where()
    )).all()
    asset_map = {r[0]: r for r in id_rows}
    rows = (await db.execute(
        select(ResearchGroup).where()
        .order_by(ResearchGroup.created_at)
    )).scalars().all()
    out = []
    for g in rows:
        members = []
        for m in g.members:
            a = asset_map.get(m.asset_id)
            members.append({"id": m.asset_id, "symbol": a.symbol if a else "?", "name": a.name if a else "?"})
        out.append(ResearchGroupResponse(
            id=g.id, name=g.name, note=g.note or "",
            asset_ids=[m.asset_id for m in g.members],
            members=members,
        ))
    return out


@router.post("/groups", response_model=ResearchGroupResponse)
async def create_group(
    req: ResearchGroupCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="组合名称不能为空")
    dup = (await db.execute(
        select(ResearchGroup).where(ResearchGroup.name == name)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"组合「{name}」已存在")

    g = ResearchGroup(user_id=user_id, name=name, note=req.note or "")
    db.add(g)
    await db.flush()
    owned = set((await db.execute(
        select(ResearchAsset.id).where(ResearchAsset.id.in_(req.asset_ids))
    )).scalars().all())
    for aid in req.asset_ids:
        if aid in owned:
            db.add(ResearchGroupMember(group_id=g.id, asset_id=aid))
    await db.commit()
    await db.refresh(g)
    return ResearchGroupResponse(id=g.id, name=g.name, note=g.note or "",
                                 asset_ids=[m.asset_id for m in g.members])


@router.put("/groups/{group_id}", response_model=ResearchGroupResponse)
async def update_group(
    group_id: str,
    req: ResearchGroupUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    g = (await db.execute(
        select(ResearchGroup).where(ResearchGroup.id == group_id)
    )).scalar_one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="组合不存在")

    if req.name is not None and req.name.strip() and req.name.strip() != g.name:
        dup = (await db.execute(
            select(ResearchGroup).where(ResearchGroup.name == req.name.strip())
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail=f"组合「{req.name.strip()}」已存在")
        g.name = req.name.strip()
    if req.note is not None:
        g.note = req.note
    if req.asset_ids is not None:
        owned = set((await db.execute(
            select(ResearchAsset.id).where(ResearchAsset.id.in_(req.asset_ids))
        )).scalars().all())
        await db.execute(delete(ResearchGroupMember).where(ResearchGroupMember.group_id == g.id))
        for aid in req.asset_ids:
            if aid in owned:
                db.add(ResearchGroupMember(group_id=g.id, asset_id=aid))
    await db.commit()
    await db.refresh(g)
    return ResearchGroupResponse(id=g.id, name=g.name, note=g.note or "",
                                 asset_ids=[m.asset_id for m in g.members])


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    g = (await db.execute(
        select(ResearchGroup).where(ResearchGroup.id == group_id)
    )).scalar_one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="组合不存在")
    await db.delete(g)
    await db.commit()
    return {"ok": True}


@router.get("/pooled-count")
async def pooled_count(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """入池标的数量（纯 COUNT，毫秒级）——回测面板「全部入池标的」显示用。
    旧实现拉全量 18891 只逐只算指标（N+1 全历史价格），分钟级超时。"""
    n = (await db.execute(
        select(func.count()).select_from(ResearchAsset)
        .where(ResearchAsset.status == "pooled")
    )).scalar_one()
    return {"count": n}


@router.get("/ids")
async def list_asset_ids(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    fund_kind: Optional[str] = Query(None),
    asset_class: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    limit_filter: Optional[str] = Query(None),
    group_id: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """轻量 id 全集（同 list_assets 筛选口径）——供前端「全选筛选结果」。"""
    q = select(ResearchAsset.id, ResearchAsset.symbol, ResearchAsset.name, ResearchAsset.status)\
        .where()
    if status:
        q = q.where(ResearchAsset.status == status)
    if category:
        q = q.where(ResearchAsset.category == category)
    if fund_kind:
        q = q.where(ResearchAsset.fund_kind == fund_kind)
    if asset_class:
        q = q.where(ResearchAsset.asset_class == asset_class)
    if region:
        q = q.where(ResearchAsset.region == region)
    if limit_filter == "limited":
        q = q.where(ResearchAsset.purchase_limit.isnot(None), ResearchAsset.purchase_limit < 100000)
    elif limit_filter == "unlimited":
        q = q.where((ResearchAsset.purchase_limit.is_(None)) | (ResearchAsset.purchase_limit >= 100000))
    if group_id:
        member_ids = select(ResearchGroupMember.asset_id).where(ResearchGroupMember.group_id == group_id)
        q = q.where(ResearchAsset.id.in_(member_ids))
    if search:
        like = f"%{search}%"
        q = q.where((ResearchAsset.name.like(like)) | (ResearchAsset.symbol.like(like)))
    rows = (await db.execute(q.order_by(ResearchAsset.created_at))).all()
    return {"items": [{"id": r[0], "symbol": r[1], "name": r[2], "status": r[3]} for r in rows],
            "total": len(rows)}


@router.post("/lookthrough")
async def lookthrough_endpoint(req: dict,
                               user_id: str = Depends(get_current_user_id),
                               db: AsyncSession = Depends(get_public_db)):
    """持仓穿透报告：给一组标的代码，返回两两重叠度 + 独特性得分。"""
    from ..services.lookthrough import lookthrough_report
    symbols = [x.strip() for x in str(req.get("symbols", "")).split(",") if x.strip()][:20]
    if len(symbols) < 2:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="请至少输入 2 个标的代码")
    force = bool(req.get("force"))
    return await lookthrough_report(db, user_id, symbols, force=force)


@router.get("/hot")
async def hot_overview_endpoint(user_id: str = Depends(get_current_user_id),
                                db: AsyncSession = Depends(get_private_db),
                                pub: AsyncSession = Depends(get_public_db)):
    """热点页：持仓Recently变动 + 全池不动量（自动数据刷新统计）。"""
    from ..services.hot_movers import hot_overview
    return await hot_overview(pub, user_id, priv=db)


@router.get("", response_model=None)
async def list_assets(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    fund_kind: Optional[str] = Query(None),
    asset_class: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    limit_filter: Optional[str] = Query(None),   # limited / unlimited
    group_id: Optional[str] = Query(None),       # 标的组合过滤
    page: int = Query(0, ge=0),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: Optional[str] = Query(None, description="全库排序: sharpe_1y/ret_252d/ret_63d/mdd_1y/vol_252d/rows"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    with_stats: int = Query(1, description="分页模式下附带 research_asset_stats 指标"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """标的列表。page>=1 时返回分页信封 {items,total,page,pages}（大库必需）；
    不传则维持旧的全量数组行为。指标只对本页标的计算——曾经的超时根因是
    全库 N+1 全历史价格查询。

    sort_by 走预计算表 research_asset_stats（全库级排序，服务端完成）；
    with_stats=1 时每行附带 stats 指标供展示。"""
    q = select(ResearchAsset).where()
    if status:
        q = q.where(ResearchAsset.status == status)
    if category:
        q = q.where(ResearchAsset.category == category)
    if fund_kind:
        q = q.where(ResearchAsset.fund_kind == fund_kind)
    if asset_class:
        q = q.where(ResearchAsset.asset_class == asset_class)
    if region:
        q = q.where(ResearchAsset.region == region)
    if limit_filter == "limited":
        q = q.where(ResearchAsset.purchase_limit.isnot(None), ResearchAsset.purchase_limit < 100000)
    elif limit_filter == "unlimited":
        q = q.where((ResearchAsset.purchase_limit.is_(None)) | (ResearchAsset.purchase_limit >= 100000))
    if group_id:
        g = (await db.execute(
            select(ResearchGroup).where(ResearchGroup.id == group_id)
        )).scalar_one_or_none()
        if not g:
            raise HTTPException(status_code=404, detail="组合不存在")
        member_ids = select(ResearchGroupMember.asset_id).where(ResearchGroupMember.group_id == group_id)
        q = q.where(ResearchAsset.id.in_(member_ids))
    if search:
        like = f"%{search}%"
        q = q.where((ResearchAsset.name.like(like)) | (ResearchAsset.symbol.like(like)))

    _STATS_SORTABLE = {
        "sharpe_1y", "ret_252d", "ret_63d", "ret_21d",
        "mdd_1y", "vol_1y", "sharpe_all", "rows", "last_date",
    }
    stats_join_active = False
    if page >= 1 and sort_by in _STATS_SORTABLE:
        from ..models.research_asset_stats import ResearchAssetStats
        q = q.join(ResearchAssetStats,
                   ResearchAssetStats.asset_id == ResearchAsset.id, isouter=True)
        col = getattr(ResearchAssetStats, sort_by)
        q = q.order_by(col.desc() if order == "desc" else col.asc())
        stats_join_active = True

    if page >= 1:
        total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        order_col = ResearchAsset.created_at if not stats_join_active else None
        stmt = q
        if order_col is not None:
            stmt = stmt.order_by(order_col)
        rows = (await db.execute(
            stmt.offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        # 批量取本页的预计算指标（R4：消灭逐条拉全历史）
        from ..models.research_asset_stats import ResearchAssetStats as _RAS
        page_ids = [a.id for a in rows]
        smap: dict = {}
        if page_ids:
            srows = (await db.execute(
                select(_RAS).where(_RAS.asset_id.in_(page_ids))
            )).scalars().all()
            smap = {r.asset_id: r for r in srows}
        items = [await _respond(db, a, stats_row=smap.get(a.id)) for a in rows]
        out = {"items": items, "total": total, "page": page,
               "pages": max(1, math.ceil(total / page_size))}
        if with_stats:
            from ..models.research_asset_stats import ResearchAssetStats
            ids = [a.id for a in rows]
            if ids:
                srows = (await db.execute(select(ResearchAssetStats).where(
                    ResearchAssetStats.asset_id.in_(ids)))).scalars().all()
                smap = {r.asset_id: r for r in srows}
                out["stats"] = {
                    a.id: ({
                        "sharpe_1y": sm.sharpe_1y, "ret_252d": sm.ret_252d,
                        "ret_63d": sm.ret_63d, "mdd_1y": sm.mdd_1y,
                        "vol_1y": sm.vol_1y, "last_date": sm.last_date,
                        "computed_at": sm.computed_at,
                    } if (sm := smap.get(a.id)) else None)
                    for a in rows
                }
        return out

    assets = (await db.execute(q.order_by(ResearchAsset.created_at))).scalars().all()
    return [await _respond(db, a) for a in assets]


@router.post("", response_model=ResearchAssetResponse)
async def create_asset(
    req: ResearchAssetCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    symbol = req.symbol.strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="代码不能为空")

    dup = (
        await db.execute(
            select(ResearchAsset).where(
                ResearchAsset.symbol == symbol
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
        purchase_limit=req.purchase_limit,
        mgmt_fee=req.mgmt_fee,
        custody_fee=req.custody_fee,
        purchase_fee=req.purchase_fee,
        sales_service_fee=req.sales_service_fee,
        redeem_rules=_rules_to_json(req.redeem_rules),
        redeem_fee_note=req.redeem_fee_note or _rules_to_note(req.redeem_rules),
        min_purchase=req.min_purchase,
        redeem_t_days=req.redeem_t_days,
        liquidity_note=req.liquidity_note,
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
    db: AsyncSession = Depends(get_public_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    await db.execute(delete(ResearchAssetPrice).where(ResearchAssetPrice.asset_id == asset.id))
    await db.delete(asset)
    await db.commit()
    return {"message": "deleted"}


# Static paths must be registered BEFORE /{asset_id} routes — FastAPI matches
# in declaration order and would otherwise treat "price-status" as an asset id.


@router.post("/import-from-em", response_model=List[WatchlistImportItem])
async def import_watchlist_from_eastmoney(
    req: WatchlistImportRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """天天基金批量导入自选：代码列表 → 自动拉名称/类型/限额/费率并打标。"""
    symbols = [s.strip() for s in req.symbols if s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols 不能为空")
    if len(symbols) > 100:
        raise HTTPException(status_code=400, detail="单次最多导入 100 个标的")

    existing = {
        r[0] for r in (
            await db.execute(
                select(ResearchAsset.symbol).where(
                    ResearchAsset.symbol.in_(symbols),
                )
            )
        ).all()
    }

    table = await asyncio.to_thread(fund_profile.get_purchase_table)
    out: list[WatchlistImportItem] = []
    for sym in symbols:
        row = table.get(sym)
        if not row:
            out.append(WatchlistImportItem(symbol=sym, status="failed", error="天天基金无此基金代码"))
            continue
        if sym in existing:
            out.append(WatchlistImportItem(
                symbol=sym, name=row["name"], status="exists",
                fund_type=row["fund_type"], daily_limit=fund_profile.normalize_daily_limit(row["daily_limit"]),
            ))
            continue
        try:
            if req.with_fees:
                fees = await asyncio.to_thread(fund_profile.fetch_fee_profile, sym)
            else:
                fees = {}
            tags = fund_profile.derive_tags(row["name"], row["fund_type"])
            tiers = (fees or {}).get("redeem_rules") or []
            asset = ResearchAsset(
                user_id=user_id,
                symbol=sym,
                exchange="FUND_CN",
                name=row["name"] or sym,
                asset_type="fund",
                purchase_limit=fund_profile.normalize_daily_limit(row["daily_limit"]),
                purchase_status=(row.get("purchase_status") or "").strip(),
                min_purchase=row["min_buy"],
                mgmt_fee=fees.get("mgmt_fee"),
                custody_fee=fees.get("custody_fee"),
                sales_service_fee=fees.get("sales_service_fee"),
                purchase_fee=fees.get("purchase_fee"),
                redeem_rules=json.dumps(tiers, ensure_ascii=False) if tiers else "[]",
                redeem_fee_note=fund_profile.note_from_tiers(tiers) if tiers else "",
                fund_kind=tags["fund_kind"],
                asset_class=tags["asset_class"],
                region=tags["region"],
                auto_tags=json.dumps(tags["auto_tags"], ensure_ascii=False),
                profile_synced_at=datetime.utcnow(),
            )
            db.add(asset)
            await db.commit()
            await db.refresh(asset)
            existing.add(sym)
            if req.sync_prices:
                asyncio.create_task(_sync_asset_prices_task(asset.id, user_id))
            out.append(WatchlistImportItem(
                symbol=sym, name=asset.name, status="added",
                fund_type=row["fund_type"], daily_limit=asset.purchase_limit,
            ))
        except Exception as e:  # noqa: BLE001 — 单只失败不阻断批次
            await db.rollback()
            out.append(WatchlistImportItem(symbol=sym, status="failed", error=f"{type(e).__name__}: {e}"))
    return out


async def _refresh_profile(db: AsyncSession, a: ResearchAsset, skip_holdings: bool = False) -> list[str]:
    """从天天基金刷新单只档案（一览表 + 费率页）。返回变更字段。"""
    table = await asyncio.to_thread(fund_profile.get_purchase_table)
    row = table.get(a.symbol)
    fees = await asyncio.to_thread(fund_profile.fetch_fee_profile, a.symbol)
    holdings_payload: dict | None = None
    if not skip_holdings:
        try:
            holdings_payload = await asset_holdings.refresh_holdings(db, a)
        except Exception:  # noqa: BLE001 — 持仓失败只降级打标精度
            pass
    return fund_profile.apply_profile(a, row or {}, fees, holdings_payload)


@router.post("/batch-pool", response_model=BatchPoolResponse)
async def batch_pool_assets(
    req: BatchPoolRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """自选批量入池。入池前自动审查：硬违规(暂停申购/限额<1000)直接拒绝；
    档案缺失/过期先尝试刷新，仍不完整才拒绝。"""
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    assets = (await db.execute(
        select(ResearchAsset).where(ResearchAsset.id.in_(req.ids))
    )).scalars().all()
    pooled: list[ResearchAsset] = []
    rejected: list[BatchPoolRejected] = []
    for a in assets:
        if a.status == "pooled":
            pooled.append(a)
            continue
        hard, soft = fund_profile.audit_violations(a)
        if soft:
            try:
                await _refresh_profile(db, a, skip_holdings=req.skip_holdings)
                await db.commit()
                _, soft_after = fund_profile.audit_violations(a)
                if soft_after:
                    # 重新跑硬检查——刷新可能带出暂停申购等状态
                    hard2, _ = fund_profile.audit_violations(a)
                    rejected.append(BatchPoolRejected(
                        asset_id=a.id, symbol=a.symbol, name=a.name,
                        reasons=hard2 + [f"档案不完整：{'、'.join(soft_after)}"],
                    ))
                    continue
            except Exception as e:  # noqa: BLE001
                await db.rollback()
                rejected.append(BatchPoolRejected(
                    asset_id=a.id, symbol=a.symbol, name=a.name,
                    reasons=[f"档案更新失败：{type(e).__name__}"] + hard,
                ))
                continue
        if hard:
            rejected.append(BatchPoolRejected(asset_id=a.id, symbol=a.symbol, name=a.name, reasons=hard))
            continue
        a.status = "pooled"
        pooled.append(a)
    await db.commit()
    for a in pooled:
        if a.status == "pooled":
            await db.refresh(a)
            if a.status == "pooled":
                asyncio.create_task(_pool_sync_task(a.id, user_id))
    return BatchPoolResponse(pooled=[await _respond(db, a) for a in pooled], rejected=rejected)


@router.post("/batch-audit-pooled", response_model=List[AuditPooledResult])
async def batch_audit_pooled(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """已入池标的自动审查：刷新档案 → 硬违规或仍缺档案的踢回自选。"""
    assets = (await db.execute(
        select(ResearchAsset).where(
            ResearchAsset.status == "pooled",
            ResearchAsset.exchange == "FUND_CN",
        ).order_by(ResearchAsset.created_at)
    )).scalars().all()
    if len(assets) > 200:  # 每日自动体检也走这里；200 已远超实际池规模
        assets = assets[:200]
    out: list[AuditPooledResult] = []
    demoted_any = False
    for a in assets:
        refreshed: list[str] = []
        try:
            refreshed = await _refresh_profile(db, a)
            await db.commit()
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            out.append(AuditPooledResult(
                asset_id=a.id, symbol=a.symbol, name=a.name,
                status="failed", error=f"{type(e).__name__}: {e}",
            ))
            continue
        hard, soft = fund_profile.audit_violations(a)
        reasons = hard + (soft and ["档案不完整：" + "、".join(soft)])
        if reasons:
            a.status = "watchlist"
            await db.commit()
            demoted_any = True
            out.append(AuditPooledResult(
                asset_id=a.id, symbol=a.symbol, name=a.name,
                status="demoted", refreshed_fields=sorted(set(refreshed)), reasons=reasons,
            ))
        else:
            out.append(AuditPooledResult(
                asset_id=a.id, symbol=a.symbol, name=a.name,
                status="kept", refreshed_fields=sorted(set(refreshed)),
            ))
    return out


@router.post("/batch-refresh-profiles", response_model=List[ProfileRefreshResult])
async def batch_refresh_profiles(
    req: BatchRefreshProfilesRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """批量更新档案（费率/限购额/申购状态）并重算标签 — 数据源天天基金。"""
    q = select(ResearchAsset).where()
    if req.ids:
        q = q.where(ResearchAsset.id.in_(req.ids))
    else:
        q = q.where(ResearchAsset.exchange == "FUND_CN", ResearchAsset.asset_type == "fund")
    assets = (await db.execute(q.order_by(ResearchAsset.created_at))).scalars().all()
    if len(assets) > 60:
        assets = assets[:60]

    table = await asyncio.to_thread(fund_profile.get_purchase_table)
    results: list[ProfileRefreshResult] = []
    for a in assets:
        row = table.get(a.symbol)
        if not row:
            results.append(ProfileRefreshResult(
                asset_id=a.id, symbol=a.symbol, name=a.name,
                status="skipped", error="天天基金无此代码",
            ))
            continue
        try:
            holdings_payload: dict = {}
            tags_rebuilt = False
            if not req.skip_holdings:
                try:
                    holdings_payload = await asset_holdings.refresh_holdings(db, a)
                    tags_rebuilt = True
                except Exception:  # noqa: BLE001 — 持仓失败只降级打标精度
                    pass
            fees = await asyncio.to_thread(fund_profile.fetch_fee_profile, a.symbol)
            changed = fund_profile.apply_profile(a, row, fees, holdings_payload or None)
            await db.commit()
            results.append(ProfileRefreshResult(
                asset_id=a.id, symbol=a.symbol, name=a.name,
                status="updated" if changed else "partial",
                changed_fields=sorted(set(changed)), tags_rebuilt=tags_rebuilt,
            ))
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            results.append(ProfileRefreshResult(
                asset_id=a.id, symbol=a.symbol, name=a.name,
                status="failed", error=f"{type(e).__name__}: {e}",
            ))
    return results


@router.post("/refresh-prices", response_model=List[SyncResult])
async def refresh_prices(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    return await refresh_all_pooled(db, user_id, ifind_user, ifind_pass)


_PRICE_STATUS_TTL_S = 600          # 数据新鲜度看板缓存时长（秒）
_price_status_cache: dict = {"ts": 0.0, "rows": [], "refreshing": False}


async def _rebuild_price_status(db: AsyncSession, user_id: str) -> list:
    """全库价格新鲜度聚合（647 万行 GROUP BY，冷启动 ~50s）。"""
    assets = (
        await db.execute(
            select(ResearchAsset).where()
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
        out.append(ResearchAssetPriceStatus(
            asset_id=a.id, symbol=a.symbol, name=a.name, status=a.status,
            rows=rows_n, last_date=last_date,
            last_sync=str(last_sync) if last_sync else None, source=source,
            lag_days=lag_days(last_date)))
    return out


@router.get("/price-status", response_model=List[ResearchAssetPriceStatus])
async def price_status(
    status: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """serve-stale-while-revalidate：先回缓存旧值，过期后后台重算。
    冷启动 50s 的聚合查询绝不能挡在用户请求路径上（2026-08-29 事故）。"""
    import time as _time
    import asyncio as _asyncio

    stale = _time.time() - _price_status_cache["ts"] > _PRICE_STATUS_TTL_S
    if stale and not _price_status_cache["refreshing"]:
        _price_status_cache["refreshing"] = True

        async def _revalidate() -> None:
            try:
                rows = await _rebuild_price_status(db, user_id)
                if rows:
                    _price_status_cache["rows"] = rows
                    _price_status_cache["ts"] = _time.time()
            except Exception:  # noqa: BLE001 — 刷新失败沿用旧值
                pass
            finally:
                _price_status_cache["refreshing"] = False

        _asyncio.create_task(_revalidate())

    data = _price_status_cache["rows"]
    if status:
        data = [r for r in data if r.status == status]
    return data


@router.get("/{asset_id}", response_model=ResearchAssetResponse)
async def get_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    asset = await _get_public(asset_id, db)
    return await _respond(db, asset)


@router.get("/{asset_id}/nav-history")
async def get_nav_history(
    asset_id: str,
    days: Optional[int] = Query(None),
    with_benchmark: bool = Query(False),
    with_ma: bool = Query(False),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """Asset NAV history.

    Plain call (no extra params) → legacy List[ResearchPricePoint] (all rows).
    With ``days``/``with_benchmark``/``with_ma`` → NavHistoryDetail with
    optional MA20/MA60 and a comparison benchmark (per D2 mapping).
    """
    asset = await _get_public(asset_id, db)
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


@router.post("/{asset_id}/unpool", response_model=ResearchAssetResponse)
async def unpool_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """踢出入池：状态回退自选，价格/档案数据全部保留。"""
    asset = await _get_owned(asset_id, user_id, db)
    if asset.status != "pooled":
        raise HTTPException(status_code=400, detail="该标的不在池内")
    asset.status = "watchlist"
    await db.commit()
    await db.refresh(asset)
    return await _respond(db, asset)


@router.post("/{asset_id}/pool", response_model=ResearchAssetResponse)
async def pool_asset(
    asset_id: str,
    req: ResearchAssetPool,
    force: bool = Query(False, description="跳过入池审查强制入池"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    if not force:
        hard, soft = fund_profile.audit_violations(asset)
        try:
            if soft:
                await _refresh_profile(db, asset)
                await db.commit()
                await db.refresh(asset)
                hard, soft = fund_profile.audit_violations(asset)
        except Exception:  # noqa: BLE001 — 刷新失败不阻断单只入池，仅按已有数据审
            await db.rollback()
            hard, soft = fund_profile.audit_violations(asset)
        problems = hard + [f"档案不完整：{'、'.join(soft)}"] if soft else hard
        if problems:
            raise HTTPException(
                status_code=422,
                detail="自动审查未通过：" + "；".join(problems) + "。仍要入池请在批量管理中重试或先更新档案。",
            )
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
    db: AsyncSession = Depends(get_public_db),
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
    db: AsyncSession = Depends(get_public_db),
):
    """Cached holdings transparency (quarterly top-10 + asset class mix)."""
    asset = await _get_public(asset_id, db)
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
    db: AsyncSession = Depends(get_public_db),
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
    db: AsyncSession = Depends(get_public_db),
):
    asset = await _get_owned(asset_id, user_id, db)
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    result = await sync_asset_prices(db, asset, ifind_user, ifind_pass, full=full)
    if result.error:
        raise HTTPException(status_code=502, detail=f"行情同步失败：{result.error}")
    return result
