from datetime import datetime, date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.investment import Investment
from ..models.investment_transaction import InvestmentTransaction
from ..models.investment_nav_snapshot import InvestmentNavSnapshot
from ..schemas.investment import (
    InvestmentCreate,
    InvestmentUpdate,
    InvestmentResponse,
    InvestmentTransactionCreate,
    InvestmentTransactionUpdate,
    InvestmentTransactionResponse,
    InvestmentMetrics,
    MigrationEntry,
    MigrationRequest,
    MigrationResponse,
)
from ..schemas.ai_investment import SearchResponse, SearchResult
from ..middleware.auth import get_current_user_id
from ..services.price_provider import fetch_price, ProviderError, get_provider, last_ifind_error
from ..services.investment_stats import compute_investment_metrics
from ..services import ifind_client
from ..services import migration_calc
from ..services import portfolio_health
from ..services import indicators

router = APIRouter(prefix="/api/investments", tags=["investments"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _to_response(inv: Investment) -> InvestmentResponse:
    total_value = (inv.quantity or 0) * (inv.current_price or 0)
    profit_loss = ((inv.current_price or 0) - (inv.purchase_price or 0)) * (inv.quantity or 0)
    return InvestmentResponse(
        id=inv.id,
        user_id=inv.user_id,
        name=inv.name,
        investment_type=inv.investment_type,
        underlying_asset_type=inv.underlying_asset_type or "",
        asset_class=inv.asset_class or "",
        benchmark_symbol=inv.benchmark_symbol or "",
        benchmark_exchange=inv.benchmark_exchange or "",
        symbol=inv.symbol or "",
        exchange=inv.exchange or "",
        quantity=inv.quantity or 0,
        purchase_price=inv.purchase_price or 0,
        current_price=inv.current_price or 0,
        purchase_date=inv.purchase_date,
        sell_date=inv.sell_date,
        notes=inv.notes,
        last_price_update=str(inv.last_price_update) if inv.last_price_update else None,
        total_value=total_value,
        profit_loss=profit_loss,
        created_at=str(inv.created_at) if inv.created_at else "",
        updated_at=str(inv.updated_at) if inv.updated_at else "",
    )


def _tx_to_response(tx: InvestmentTransaction) -> InvestmentTransactionResponse:
    return InvestmentTransactionResponse(
        id=tx.id,
        investment_id=tx.investment_id,
        user_id=tx.user_id,
        event_type=tx.event_type,
        event_date=tx.event_date,
        quantity=tx.quantity or 0,
        unit_price=tx.unit_price or 0,
        amount=tx.amount or 0,
        notes=tx.notes,
        created_at=str(tx.created_at) if tx.created_at else "",
        updated_at=str(tx.updated_at) if tx.updated_at else "",
    )


async def _recompute_legacy_fields(db: AsyncSession, investment: Investment) -> None:
    """Sync the legacy quantity / purchase_price fields from the ledger.

    The transaction ledger is the source of truth; we mirror the summary into
    the legacy columns so old code paths (and the list view) keep working
    without a separate query.
    """
    res = await db.execute(
        select(InvestmentTransaction)
        .where(InvestmentTransaction.investment_id == investment.id)
        .order_by(InvestmentTransaction.event_date.asc())
    )
    txs = list(res.scalars().all())
    if not txs:
        return

    qty = sum(t.quantity for t in txs if t.event_type not in ("dividend",))
    invested = sum(t.amount for t in txs if t.event_type == "buy")
    redeemed = sum(abs(t.amount) for t in txs if t.event_type == "sell")
    net_qty = qty

    # Average purchase price (cost basis): buys only
    buys = [t for t in txs if t.event_type == "buy" and t.quantity > 0]
    if buys:
        total_cost = sum(t.amount for t in buys)
        total_shares = sum(t.quantity for t in buys)
        avg_price = total_cost / total_shares if total_shares else 0
    else:
        avg_price = 0

    investment.quantity = net_qty
    investment.purchase_price = avg_price
    # purchase_date — earliest buy
    earliest_buy = min((t.event_date for t in txs if t.event_type == "buy"), default=None)
    if earliest_buy:
        investment.purchase_date = earliest_buy
    # current_price is NOT recomputed here — only by the price provider refresh


# --------------------------------------------------------------------------- #
# CRUD: investments
# --------------------------------------------------------------------------- #

@router.get("", response_model=List[InvestmentResponse])
async def get_investments(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Investment).where(Investment.user_id == user_id).order_by(Investment.created_at.desc())
    )
    return [_to_response(i) for i in res.scalars().all()]


@router.post("", response_model=InvestmentResponse)
async def create_investment(
    req: InvestmentCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    inv = Investment(user_id=user_id, **req.model_dump())
    db.add(inv)
    await db.flush()

    # Seed an initial buy transaction from legacy fields (if non-zero) so the
    # ledger is in sync with the snapshot from day one.
    if inv.quantity and inv.quantity > 0 and inv.purchase_price and inv.purchase_price > 0:
        seed = InvestmentTransaction(
            investment_id=inv.id,
            user_id=user_id,
            event_type="buy",
            event_date=inv.purchase_date,
            quantity=inv.quantity,
            unit_price=inv.purchase_price,
            amount=inv.quantity * inv.purchase_price,
            notes="Initial position (auto-seeded)",
        )
        db.add(seed)
    await db.commit()
    await db.refresh(inv)
    return _to_response(inv)


@router.get("/portfolio-health")
async def get_portfolio_health(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """组合体检：聚合用户全部持仓，计算集中度/资产配置/浮亏预警。

    返回 {concentration: {max_single_pct, top3_pct}, allocation: {asset_class: pct}, warnings: [...]}。
    compute_health 是纯计算（portfolio_health.py），不依赖 iFinD/迁移；现持仓数据即可算。
    """
    res = await db.execute(
        select(Investment).where(Investment.user_id == user_id)
    )
    invs = list(res.scalars().all())
    investments_data = [
        {
            "id": inv.id,
            "name": inv.name,
            "current_price": float(inv.current_price or 0),
            "quantity": float(inv.quantity or 0),
            "purchase_price": float(inv.purchase_price or 0),
            "asset_class": inv.asset_class or "",
        }
        for inv in invs
    ]
    return portfolio_health.compute_health(investments_data, [])


@router.get("/{investment_id}", response_model=InvestmentResponse)
async def get_investment(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    return _to_response(inv)


@router.put("/{investment_id}", response_model=InvestmentResponse)
async def update_investment(
    investment_id: str,
    req: InvestmentUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(inv, key, value)
    await db.commit()
    await db.refresh(inv)
    return _to_response(inv)


@router.delete("/{investment_id}")
async def delete_investment(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    await db.delete(inv)
    await db.commit()
    return {"message": "Investment deleted"}


# --------------------------------------------------------------------------- #
# Transactions (ledger)
# --------------------------------------------------------------------------- #

@router.get("/{investment_id}/transactions", response_model=List[InvestmentTransactionResponse])
async def list_transactions(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await _load_investment(db, investment_id, user_id)
    res = await db.execute(
        select(InvestmentTransaction)
        .where(InvestmentTransaction.investment_id == investment_id)
        .order_by(InvestmentTransaction.event_date.desc())
    )
    return [_tx_to_response(t) for t in res.scalars().all()]


@router.post("/{investment_id}/transactions", response_model=InvestmentTransactionResponse)
async def create_transaction(
    investment_id: str,
    req: InvestmentTransactionCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    # Sign convention: buys positive, sells negative
    qty = req.quantity if req.event_type != "sell" else -abs(req.quantity)
    amount = qty * req.unit_price
    if req.event_type == "dividend":
        # Dividend: quantity 0, amount = positive cash to investor (we record as positive)
        qty = 0
        amount = abs(req.unit_price)  # unit_price reused as the dividend amount
    if req.event_type == "fee":
        qty = 0
        amount = -abs(req.unit_price)  # fees are positive costs
    tx = InvestmentTransaction(
        investment_id=investment_id,
        user_id=user_id,
        event_type=req.event_type,
        event_date=req.event_date,
        quantity=qty,
        unit_price=req.unit_price,
        amount=amount,
        notes=req.notes,
    )
    db.add(tx)
    await db.flush()
    await _recompute_legacy_fields(db, inv)
    await db.commit()
    await db.refresh(tx)
    return _tx_to_response(tx)


@router.put("/{investment_id}/transactions/{tx_id}", response_model=InvestmentTransactionResponse)
async def update_transaction(
    investment_id: str,
    tx_id: str,
    req: InvestmentTransactionUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    res = await db.execute(
        select(InvestmentTransaction).where(
            InvestmentTransaction.id == tx_id,
            InvestmentTransaction.investment_id == investment_id,
        )
    )
    tx = res.scalar_one_or_none()
    if not tx:
        raise HTTPException(404, "Transaction not found")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(tx, k, v)
    # Re-derive amount from new quantity/unit_price
    if "quantity" in data or "unit_price" in data or "event_type" in data:
        qty = tx.quantity if tx.event_type != "sell" else -abs(tx.quantity)
        if tx.event_type == "dividend":
            qty = 0
            tx.amount = abs(tx.unit_price)
        elif tx.event_type == "fee":
            qty = 0
            tx.amount = -abs(tx.unit_price)
        else:
            tx.quantity = qty
            tx.amount = qty * tx.unit_price
    await _recompute_legacy_fields(db, inv)
    await db.commit()
    await db.refresh(tx)
    return _tx_to_response(tx)


@router.delete("/{investment_id}/transactions/{tx_id}")
async def delete_transaction(
    investment_id: str,
    tx_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    res = await db.execute(
        select(InvestmentTransaction).where(
            InvestmentTransaction.id == tx_id,
            InvestmentTransaction.investment_id == investment_id,
        )
    )
    tx = res.scalar_one_or_none()
    if not tx:
        raise HTTPException(404, "Transaction not found")
    await db.delete(tx)
    await _recompute_legacy_fields(db, inv)
    await db.commit()
    return {"message": "Transaction deleted"}


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

@router.get("/{investment_id}/metrics", response_model=InvestmentMetrics)
async def get_metrics(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    return await compute_investment_metrics(db, inv)


@router.get("/metrics/all", response_model=List[dict])
async def get_all_metrics(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return per-investment metrics for the user's portfolio."""
    res = await db.execute(
        select(Investment).where(Investment.user_id == user_id).order_by(Investment.created_at.desc())
    )
    out = []
    for inv in res.scalars().all():
        m = await compute_investment_metrics(db, inv)
        out.append({
            "investment_id": inv.id,
            "investment_name": inv.name,
            "metrics": m.model_dump(),
        })
    return out


# --------------------------------------------------------------------------- #
# Price refresh
# --------------------------------------------------------------------------- #

@router.post("/{investment_id}/refresh-price", response_model=InvestmentResponse)
async def refresh_price(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    if not inv.symbol or not inv.exchange:
        raise HTTPException(
            400,
            "Investment has no symbol/exchange set. Set them in the edit dialog first.",
        )
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    try:
        quote = await fetch_price(inv.symbol, inv.exchange, ifind_user, ifind_pass)
    except ProviderError as e:
        ie = last_ifind_error()
        raise HTTPException(502, str(e) + (f"（iFinD 亦失败：{ie}）" if ie else ""))
    inv.current_price = quote.price
    inv.last_price_update = quote.timestamp.replace(tzinfo=None)
    await db.commit()
    await db.refresh(inv)
    return _to_response(inv)


@router.post("/refresh-prices/all", response_model=List[dict])
async def refresh_all_prices(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Refresh prices for every investment that has symbol+exchange set."""
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    res = await db.execute(
        select(Investment).where(Investment.user_id == user_id)
    )
    invs = list(res.scalars().all())
    results = []
    for inv in invs:
        if not inv.symbol or not inv.exchange:
            continue
        try:
            quote = await fetch_price(inv.symbol, inv.exchange, ifind_user, ifind_pass)
            inv.current_price = quote.price
            inv.last_price_update = quote.timestamp.replace(tzinfo=None)
            results.append({"id": inv.id, "name": inv.name, "ok": True, "price": quote.price, "source": quote.source})
        except ProviderError as e:
            results.append({"id": inv.id, "name": inv.name, "ok": False, "error": str(e)})
    await db.commit()
    return results


# --------------------------------------------------------------------------- #
# NAV history (iFinD) — for the per-product curve + buy/sell markers
# --------------------------------------------------------------------------- #

@router.get("/{investment_id}/nav-history")
async def get_nav_history(
    investment_id: str,
    days: int = 365,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the daily close series + transaction events + cost basis for the
    per-product detail drawer (净值曲线 + 买卖点标注).

    Requires iFinD credentials to be configured (settings page).
    """
    inv = await _load_investment(db, investment_id, user_id)
    if not inv.symbol or not inv.exchange:
        raise HTTPException(400, "该产品未设置代码/市场，无法获取净值历史")
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    if not ifind_user or not ifind_pass:
        raise HTTPException(400, "未配置同花顺 iFinD 凭证，请在「设置」中填写")

    days = max(7, min(int(days), 3650))
    end = date.today().isoformat()
    begin = (date.today() - timedelta(days=days)).isoformat()
    try:
        series = await ifind_client.fetch_history_close(
            ifind_user, ifind_pass, inv.symbol, inv.exchange, begin, end
        )
    except ifind_client.IFindError as e:
        raise HTTPException(502, f"iFinD 取数失败：{e}")

    # Transaction events for buy/sell markers
    tx_res = await db.execute(
        select(InvestmentTransaction)
        .where(InvestmentTransaction.investment_id == investment_id)
        .order_by(InvestmentTransaction.event_date.asc())
    )
    events = [_tx_to_response(t).model_dump() for t in tx_res.scalars().all()]

    # Technical indicators (pure computation, indicators.py)
    closes = [p["close"] for p in series]
    max_drawdown = indicators.max_drawdown(closes)
    ma20 = indicators.sma(closes, 20)
    ma60 = indicators.sma(closes, 60)
    # 合并 MA 进 series 每个 point（前端 NavHistoryPoint.ma20/ma60 期望点级字段）
    for i, p in enumerate(series):
        p["ma20"] = ma20[i]
        p["ma60"] = ma60[i]

    return {
        "investment": {
            "id": inv.id,
            "name": inv.name,
            "symbol": inv.symbol,
            "exchange": inv.exchange,
            "investment_type": inv.investment_type,
        },
        "series": series,                        # [{date, close}]
        "events": events,                        # [{event_type, event_date, quantity, unit_price, amount, ...}]
        "cost_basis": inv.purchase_price or 0.0, # avg buy price — cost line
        "current_price": inv.current_price or 0.0,
        "max_drawdown": round(max_drawdown, 4),  # decimal, e.g. 0.235 = 23.5%
        "ma20": ma20,  # list[float|None], same length as series; null = window未填满
        "ma60": ma60,
        "source": "ifind",
        "begin": begin,
        "end": end,
    }


# --------------------------------------------------------------------------- #
# NAV snapshots (placeholder endpoint for future manual-entry support)
# --------------------------------------------------------------------------- #

@router.get("/{investment_id}/snapshots", response_model=List[dict])
async def list_snapshots(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await _load_investment(db, investment_id, user_id)
    res = await db.execute(
        select(InvestmentNavSnapshot)
        .where(InvestmentNavSnapshot.investment_id == investment_id)
        .order_by(InvestmentNavSnapshot.snapshot_date.desc())
        .limit(365)
    )
    return [
        {
            "snapshot_date": s.snapshot_date,
            "unit_price": s.unit_price,
            "quantity_held": s.quantity_held,
            "total_value": s.total_value,
        }
        for s in res.scalars().all()
    ]


# --------------------------------------------------------------------------- #
# Migration (amount-only holdings → share-based ledger via iFinD NAV reverse-calc)
# --------------------------------------------------------------------------- #

@router.post("/{investment_id}/migrate-entry", response_model=MigrationResponse)
async def migrate_entry(
    investment_id: str,
    req: MigrationRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """半自动迁移：用户输入历史投资记录（date+amount），后端用 iFinD 拉历史
    单位净值（ths_unit_nv_fund）反推份额。commit=false 仅预览；commit=true 生成 buy 流水。
    """
    inv = await _load_investment(db, investment_id, user_id)
    symbol = (req.symbol or inv.symbol or "").strip()
    if not symbol:
        raise HTTPException(400, "请填写基金代码（6位数字，如 000217）")
    # 用户持仓全是场外开放式基金；若 investment.exchange 未填，默认 FUND_CN
    exchange = (inv.exchange or "").strip() or "FUND_CN"

    # ---- commit 模式：落库生成 buy 流水 ----
    if req.commit:
        committed = 0
        results: list[MigrationEntry] = []
        for e in req.entries:
            if e.nav is None or e.shares is None or e.shares <= 0 or e.amount <= 0:
                results.append(MigrationEntry(
                    date=e.date, amount=e.amount, nav=e.nav, shares=e.shares, status="invalid",
                ))
                continue
            tx = InvestmentTransaction(
                investment_id=inv.id,
                user_id=user_id,
                event_type="buy",
                event_date=e.date[:10],
                quantity=float(e.shares),
                unit_price=float(e.nav),
                amount=float(e.amount),
                notes="迁移反推（iFinD 净值）",
            )
            db.add(tx)
            committed += 1
            results.append(MigrationEntry(
                date=e.date, amount=e.amount, nav=e.nav, shares=e.shares, status="ok",
            ))
        if committed > 0:
            await _recompute_legacy_fields(db, inv)
        await db.commit()
        return MigrationResponse(results=results, preview=False, committed=committed)

    # ---- preview 模式：拉净值 + 反推份额 ----
    creds = await ifind_client.get_credentials(db, user_id)
    if not creds[0]:
        raise HTTPException(400, "请先在「设置」页配置同花顺 iFinD 凭证")

    dates = [e.date[:10] for e in req.entries if e.date]
    if not dates:
        raise HTTPException(400, "没有有效的投资日期")
    begin, end = min(dates), max(dates)

    try:
        series = await ifind_client.fetch_history_close(
            creds[0], creds[1], symbol, exchange, begin, end,
        )
    except ifind_client.IFindError as e:
        raise HTTPException(502, f"iFinD 拉取净值失败：{e}")

    # migration_calc.build_migration_entries(inputs, nav_fetcher)
    # nav_fetcher 返回完整区间净值序列；内部 pick_nearest_nav 找每个投资日的最近净值
    inputs = [{"date": e.date[:10], "amount": float(e.amount)} for e in req.entries]
    nav_fetcher = lambda _dates: series  # noqa: E731
    raw = migration_calc.build_migration_entries(inputs, nav_fetcher)

    results = [
        MigrationEntry(
            date=r["date"],
            amount=r["amount"],
            nav=r.get("nav"),
            shares=r.get("shares"),
            status="no_nav" if r.get("error") else "ok",
        )
        for r in raw
    ]
    return MigrationResponse(results=results, preview=True, committed=0)


# --------------------------------------------------------------------------- #
# Internal
# --------------------------------------------------------------------------- #

async def _load_investment(db: AsyncSession, investment_id: str, user_id: str) -> Investment:
    res = await db.execute(
        select(Investment).where(Investment.id == investment_id, Investment.user_id == user_id)
    )
    inv = res.scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Investment not found")
    return inv
