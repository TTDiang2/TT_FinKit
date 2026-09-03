from datetime import datetime, date, timedelta
from typing import List
import asyncio
import time as _time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_private_db
from ..models.investment import Investment, open_position_cond
from ..models.investment_transaction import InvestmentTransaction
from ..models.investment_cash_flow import InvestmentCashFlow
from ..models.investment_nav_snapshot import InvestmentNavSnapshot
from ..schemas.investment import (
    InvestmentCreate,
    InvestmentUpdate,
    InvestmentResponse,
    InvestmentTransactionCreate,
    InvestmentTransactionUpdate,
    InvestmentTransactionResponse,
    InvestmentMetrics,
    CashFlowCreate,
    CashFlowUpdate,
    CashFlowResponse,
    PortfolioOverview,
    ClosedPosition,
    ClosedPositionsResponse,
    LookupCandidate,
    MigrationEntry,
    MigrationRequest,
    MigrationResponse,
)
from ..schemas.ai_investment import SearchResponse, SearchResult
from ..middleware.auth import get_current_user_id
from ..services.price_provider import fetch_price, ProviderError, get_provider, last_ifind_error
from ..services.investment_stats import compute_investment_metrics, compute_portfolio_overview, compute_position_indicators, get_or_create_investment_category
from ..services import ifind_client
from ..services import migration_calc
from ..services import nav_history
from ..services import portfolio_health
from ..services import indicators
from ..services.portfolio_nav import build_portfolio_nav, snap_date, compute_pnl_by_period

# Computation cache for /portfolio-nav: NAV reconstruction is heavy (network
# fetches + per-day share walk); 5-minute TTL, invalidated on price refresh.
_PORTFOLIO_NAV_CACHE: dict[tuple[str, int], tuple[float, dict]] = {}
_PORTFOLIO_NAV_TTL = 300.0
_PNL_HISTORY_CACHE: dict[tuple[str, str, int], tuple[float, dict]] = {}
_PNL_HISTORY_TTL = 300.0

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
        is_money_market=bool(inv.is_money_market),
        seven_day_yield=inv.seven_day_yield,
        total_value=total_value,
        profit_loss=profit_loss,
        ann_volatility=None,
        sharpe_ratio=None,
        ann_return=None,
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
        fee=tx.fee or 0,
        notes=tx.notes,
        created_at=str(tx.created_at) if tx.created_at else "",
        updated_at=str(tx.updated_at) if tx.updated_at else "",
    )


def _flow_to_response(f: InvestmentCashFlow) -> CashFlowResponse:
    return CashFlowResponse(
        id=f.id,
        user_id=f.user_id,
        flow_type=f.flow_type,
        amount=f.amount,
        flow_date=f.flow_date,
        notes=f.notes,
        created_at=str(f.created_at) if f.created_at else "",
        updated_at=str(f.updated_at) if f.updated_at else "",
    )


async def _recompute_legacy_fields(db: AsyncSession, investment: Investment) -> None:
    """Sync the legacy quantity / purchase_price fields from the ledger.

    The transaction ledger is the source of truth; we mirror the summary into
    the legacy columns so old code paths (and the list view) keep working
    without a separate query.

    摊薄单价（diluted cost basis）= (累计买入金额 + 累计费用 − 累计卖出回款) ÷ 当前份额。
    卖出回款全额冲减成本 —— 与基金 APP 的「摊薄成本法」一致；部分止盈后成本下降。
    """
    res = await db.execute(
        select(InvestmentTransaction)
        .where(InvestmentTransaction.investment_id == investment.id)
        .order_by(InvestmentTransaction.event_date.asc())
    )
    txs = list(res.scalars().all())
    if not txs:
        return

    net_qty = sum(
        t.quantity for t in txs
        if t.event_type not in ("dividend", "fee")
    )

    buys = sum(t.amount for t in txs if t.event_type == "buy")
    sells = sum(abs(t.amount) for t in txs if t.event_type == "sell")
    fees = sum(
        abs(t.fee or 0) if (t.fee or 0) != 0
        else (abs(t.amount) if t.event_type == "fee" else 0.0)
        for t in txs
    )

    diluted_cost = buys + fees - sells

    # 份额残差容差：买入/卖出份额都是浮点，全部卖出后累加常留下 ~1e-13 的碎股
    # （如 308.07 + 358.35 - 666.42 = 1.14e-13）。若不设容差，该标的会被判定
    # 为"仍持仓"，既进不了已平仓列表，成本价还会被除成天文数字（2026-09-02）。
    QTY_EPS = 1e-6
    has_position = net_qty > QTY_EPS
    avg_price = diluted_cost / net_qty if has_position else 0.0

    investment.quantity = net_qty if has_position else 0.0
    investment.purchase_price = avg_price
    earliest_buy = min((t.event_date for t in txs if t.event_type == "buy"), default=None)
    if earliest_buy:
        investment.purchase_date = earliest_buy

    last_sell = max((t.event_date for t in txs if t.event_type == "sell"), default=None)
    if not has_position and last_sell:
        investment.sell_date = last_sell
    elif has_position and investment.sell_date:
        investment.sell_date = None
    # current_price is NOT recomputed here — only by the price provider refresh


async def _resolve_sell_unit_price(
    inv: Investment, event_date: str, db: AsyncSession, user_id: str
) -> tuple[float, str] | None:
    """平仓未填净值时自动补净值：优先卖出日（或此前最近交易日）收盘价，回退最新净值。

    返回 (price, 来源说明)，取不到返回 None（此时调用方保持 0 并让前端提示）。
    历史净值为已知数据，要求用户手填既不必要、漏填又会把回款算成 0（全额成本变亏损）。
    """
    if not inv.symbol or not inv.exchange:
        return None
    try:
        end_d = datetime.strptime((event_date or "")[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        end_d = datetime.now()
    begin_d = end_d - timedelta(days=30)  # 覆盖节假日/停牌：取此前最近交易日
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    series: list[dict] = []
    try:
        series, _source = await asyncio.wait_for(
            nav_history.fetch_history_series(
                inv.symbol, inv.exchange,
                begin_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d"),
                ifind_user, ifind_pass,
                force_money_market=bool(inv.is_money_market),
            ),
            timeout=20,
        )
    except Exception:
        series = []
    end_s = end_d.strftime("%Y-%m-%d")
    picks = [
        p for p in (series or [])
        if str(p.get("date", "")) <= end_s and (p.get("close") or 0) > 0
    ]
    if picks:
        last = picks[-1]
        return float(last["close"]), f"{last['date']} 收盘净值"
    if (inv.current_price or 0) > 0:
        return float(inv.current_price), "最新净值（当日净值缺失）"
    return None


# --------------------------------------------------------------------------- #
# CRUD: investments
# --------------------------------------------------------------------------- #

@router.get("", response_model=List[InvestmentResponse])
async def get_investments(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    res = await db.execute(
        select(Investment).where(Investment.user_id == user_id).order_by(Investment.created_at.desc())
    )
    invs = list(res.scalars().all())
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    out = []
    for i in invs:
        resp = _to_response(i)
        if i.is_money_market and resp.quantity > 0:
            from ..services import money_market_fund
            tx_res = await db.execute(
                select(InvestmentTransaction).where(InvestmentTransaction.investment_id == i.id)
            )
            its = list(tx_res.scalars().all())
            mmf_evs = [t for t in its if t.event_type in ("buy", "sell")]
            shares = await money_market_fund.mmf_current_shares(i.symbol, mmf_evs)
            resp.mmf_shares = shares
            resp.total_value = round(shares * (i.current_price or 0), 2)
            resp.profit_loss = round(resp.total_value - (i.purchase_price or 0) * resp.quantity, 2)
        out.append(resp)

    indicator_tasks = [
        compute_position_indicators(
            i.symbol or "", i.exchange or "",
            i.purchase_date[:10] if i.purchase_date else today,
            today, ifind_user, ifind_pass,
            is_money_market=bool(i.is_money_market),
        )
        for i in invs
    ]
    indicators_list = await asyncio.gather(*indicator_tasks, return_exceptions=True)
    for resp, ind in zip(out, indicators_list):
        if isinstance(ind, dict):
            resp.ann_volatility = ind.get("ann_volatility")
            resp.sharpe_ratio = ind.get("sharpe")
            resp.ann_return = ind.get("ann_return")
    return out


@router.post("", response_model=InvestmentResponse)
async def create_investment(
    req: InvestmentCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    payload = req.model_dump()
    purchase_fee = float(payload.pop("purchase_fee", 0.0) or 0.0)
    if payload.get("investment_type") == "fund" and not payload.get("exchange"):
        payload["exchange"] = "FUND_CN"

    symbol = (payload.get("symbol") or "").strip()
    exchange = (payload.get("exchange") or "").strip()
    if symbol and exchange:
        existing = await db.execute(
            select(Investment).where(
                Investment.user_id == user_id,
                Investment.symbol == symbol,
                Investment.exchange == exchange,
                open_position_cond(),
            )
        )
        match = existing.scalars().first()
        if match and float(payload.get("quantity") or 0) > 0 and float(payload.get("purchase_price") or 0) > 0:
            qty = float(payload["quantity"])
            price = float(payload["purchase_price"])
            date = payload.get("purchase_date")
            db.add(InvestmentTransaction(
                investment_id=match.id,
                user_id=user_id,
                event_type="buy",
                event_date=date,
                quantity=qty,
                unit_price=price,
                amount=qty * price,
                fee=purchase_fee,
                notes="Merged purchase (auto)",
            ))
            match.quantity = float(match.quantity or 0) + qty
            if not match.current_price:
                match.current_price = payload.get("current_price")
            await db.commit()
            await db.refresh(match)
            _invalidate_portfolio_nav_cache(user_id)
            resp = _to_response(match)
            resp.merged_into = match.id
            resp.merged_message = (
                f"已合并到现有持仓「{match.name}」：新增申购 {qty:g} 份 @ {price:g}，"
                f"费用 {purchase_fee:g}"
            )
            return resp

    inv = Investment(user_id=user_id, **payload)
    if exchange == "FUND_CN" and symbol:
        from ..services import money_market_fund

        inv.is_money_market, inv.seven_day_yield = await money_market_fund.probe(symbol)
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
            fee=purchase_fee,
            notes="Initial position (auto-seeded)",
        )
        db.add(seed)
    await db.commit()
    _invalidate_portfolio_nav_cache(user_id)
    await db.refresh(inv)
    return _to_response(inv)


@router.get("/portfolio-health")
async def get_portfolio_health(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """组合体检：未平仓持仓的整体浮盈亏 + 逐基金浮亏预警（带名称）。

    compute_health 是纯计算（portfolio_health.py），不依赖 iFinD/网络。
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
            "sell_date": inv.sell_date,
        }
        for inv in invs
    ]
    return portfolio_health.compute_health(investments_data, [])


@router.get("/closed-positions", response_model=ClosedPositionsResponse)
async def get_closed_positions(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """已平仓产品：实现盈亏与年化收益。

    判定 sell_date 非空（自动平仓时设置）；盈亏 = 回款(卖出+分红) − 成本(买入+费用)；
    年化 = (1+收益率)^(365/持有天数)−1，持有天数 = sell_date − purchase_date。
    """
    res = await db.execute(
        select(Investment)
        .where(Investment.user_id == user_id, func.coalesce(Investment.sell_date, "") != "")
        .order_by(Investment.sell_date.desc())
    )
    invs = list(res.scalars().all())
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    positions: list[ClosedPosition] = []
    total_realized = 0.0
    total_cost = 0.0
    for inv in invs:
        tx_res = await db.execute(
            select(InvestmentTransaction)
            .where(InvestmentTransaction.investment_id == inv.id)
        )
        txs = list(tx_res.scalars().all())
        buy_amount = sum(float(t.amount or 0) for t in txs if t.event_type == "buy")
        proceeds = -sum(float(t.amount or 0) for t in txs if t.event_type in ("sell", "dividend"))
        total_fee = sum(float(t.fee or 0) for t in txs)
        cost = buy_amount + total_fee
        realized = round(proceeds - cost, 2)
        return_rate = realized / cost if cost > 0 else None
        try:
            d0 = datetime.strptime((inv.purchase_date or "")[:10], "%Y-%m-%d")
            d1 = datetime.strptime((inv.sell_date or "")[:10], "%Y-%m-%d")
            days = (d1 - d0).days
        except (ValueError, TypeError):
            days = 0
        ann = None
        # (1+return_rate) 必须为正才能开分数次幂：return_rate <= -100% 时
        # Python 会返回复数，round(complex) 抛 TypeError 让整个接口 500
        # （2026-09-02：平仓净值缺失导致 realized = -cost，正好越过 -100%）。
        if days > 0 and return_rate is not None and return_rate > -1.0:
            ann = (1.0 + return_rate) ** (365.0 / days) - 1.0
        positions.append(ClosedPosition(
            id=inv.id,
            name=inv.name,
            symbol=inv.symbol or "",
            exchange=inv.exchange or "",
            investment_type=inv.investment_type,
            purchase_date=inv.purchase_date,
            sell_date=inv.sell_date,
            buy_amount=round(buy_amount, 2),
            proceeds=round(proceeds, 2),
            total_fee=round(total_fee, 2),
            cost=round(cost, 2),
            realized_pnl=realized,
            return_rate=round(return_rate, 4) if return_rate is not None else None,
            days_held=days,
            ann_return=round(ann, 4) if ann is not None else None,
            ann_volatility=None,
            sharpe_ratio=None,
        ))
        total_realized += realized
        total_cost += cost

    indicator_tasks = [
        compute_position_indicators(
            inv.symbol or "", inv.exchange or "",
            inv.purchase_date[:10] if inv.purchase_date else "",
            (inv.sell_date or "")[:10],
            ifind_user, ifind_pass,
            is_money_market=bool(inv.is_money_market),
        )
        for inv in invs
    ]
    indicator_results = await asyncio.gather(*indicator_tasks, return_exceptions=True)
    for pos, ind in zip(positions, indicator_results):
        if isinstance(ind, dict):
            pos.ann_volatility = ind.get("ann_volatility")
            pos.sharpe_ratio = ind.get("sharpe")

    total_return_rate = total_realized / total_cost if total_cost > 0 else None
    return ClosedPositionsResponse(
        positions=positions,
        total_realized=round(total_realized, 2),
        total_cost=round(total_cost, 2),
        total_return_rate=round(total_return_rate, 4) if total_return_rate is not None else None,
        count=len(positions),
    )


@router.post("/maintenance/backfill-sell-nav")
async def backfill_sell_nav(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """回填历史卖出记录里缺失的净值，并重算全部持仓的汇总字段。

    场景：平仓时未填净值 → unit_price/amount 为 0 → 回款算 0，全部成本被计为亏损。
    同时修复份额浮点残差导致的"已卖光但仍挂在持仓"（_recompute_legacy_fields 容差）。
    """
    inv_res = await db.execute(
        select(Investment).where(Investment.user_id == user_id).order_by(Investment.name.asc())
    )
    invs = list(inv_res.scalars().all())
    updated: list[dict] = []
    skipped: list[dict] = []
    for inv in invs:
        tx_res = await db.execute(
            select(InvestmentTransaction)
            .where(
                InvestmentTransaction.investment_id == inv.id,
                InvestmentTransaction.event_type == "sell",
                or_(
                    InvestmentTransaction.unit_price.is_(None),
                    InvestmentTransaction.unit_price <= 0,
                ),
            )
            .order_by(InvestmentTransaction.event_date.asc())
        )
        for tx in list(tx_res.scalars().all()):
            resolved = await _resolve_sell_unit_price(inv, tx.event_date, db, user_id)
            if not resolved:
                skipped.append({
                    "symbol": inv.symbol, "name": inv.name,
                    "event_date": tx.event_date, "reason": "未取到净值（无代码/无行情源）",
                })
                continue
            price, src = resolved
            base_notes = (tx.notes or "").split("（净值自动补全")[0].strip()
            tx.unit_price = price
            tx.amount = float(tx.quantity or 0) * price
            tx.notes = f"{base_notes}（净值自动补全：{src}）".strip()
            updated.append({
                "symbol": inv.symbol, "name": inv.name,
                "event_date": tx.event_date,
                "quantity": tx.quantity, "unit_price": round(price, 4),
                "amount": round(tx.amount, 2), "source": src,
            })
        # 无论有无回填都重算：修复份额残差 / 成本价被极小份额放大等历史脏数据
        await _recompute_legacy_fields(db, inv)
    await db.commit()
    _invalidate_portfolio_nav_cache(user_id)
    return {"updated": updated, "skipped": skipped,
            "updated_count": len(updated), "skipped_count": len(skipped)}


async def _consistency_core(db: AsyncSession, user_id: str) -> dict:
    """投资 tab ↔ 记账 tab 一致性校验核心（恒等式，容差 ≤ 0.01）。

    记账余额 = 入金 − 出金 + 落袋盈亏(含分红) − 分红 + 浮动盈亏 − 当月盈亏
    化简（落袋盈亏(含分红) − 分红 = realized）：记账余额 = 入金 − 出金 + realized + 浮动盈亏 − 当月盈亏。
    辅助校验：闲置现金 = 记账余额 + 当月盈亏 − 市值 ≈ 0（所有钱都在持仓里时）。
    被 /consistency 与 /reconciliation 复用。
    """
    from ..models.account import Account
    from ..models.transaction import Transaction
    from .accounts import get_account_balance

    acc_res = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.account_type == "investment")
    )
    accounts = list(acc_res.scalars().all())
    account_list = []
    total_account_balance = 0.0
    negative_accounts: list[dict] = []
    for acc in accounts:
        balance = await get_account_balance(acc, db)
        account_list.append({"id": acc.id, "name": acc.name, "balance": round(balance, 2)})
        total_account_balance += balance
        if balance < -0.01:
            negative_accounts.append({"name": acc.name, "balance": round(balance, 2)})

    flow_res = await db.execute(
        select(InvestmentCashFlow).where(InvestmentCashFlow.user_id == user_id)
    )
    flows = list(flow_res.scalars().all())
    total_deposits = sum(f.amount for f in flows if f.flow_type == "deposit")
    total_withdrawals = sum(f.amount for f in flows if f.flow_type == "withdrawal")
    old_principal = total_deposits - total_withdrawals

    inv_res = await db.execute(select(Investment).where(Investment.user_id == user_id))
    invs = list(inv_res.scalars().all())
    inv_ids = [i.id for i in invs]
    txs: list[InvestmentTransaction] = []
    if inv_ids:
        tx_res = await db.execute(
            select(InvestmentTransaction).where(InvestmentTransaction.investment_id.in_(inv_ids))
        )
        txs = list(tx_res.scalars().all())
    txs_by_inv: dict[str, list[InvestmentTransaction]] = {}
    for t in txs:
        txs_by_inv.setdefault(t.investment_id, []).append(t)

    holdings_cost = 0.0   # 当前持仓摊薄成本（未平仓产品：买入+费用−卖出−分红）
    total_current = 0.0   # 当前持仓市值
    for inv in invs:
        its = txs_by_inv.get(inv.id, [])
        if its:
            b = sum(t.amount for t in its if t.event_type == "buy")
            s = sum(abs(t.amount) for t in its if t.event_type == "sell")
            d = sum(abs(t.amount) for t in its if t.event_type == "dividend")
            f = sum(
                abs(t.fee or 0) if (t.fee or 0) != 0
                else (abs(t.amount) if t.event_type == "fee" else 0.0)
                for t in its
            )
            qty = sum(t.quantity for t in its if t.event_type not in ("dividend", "fee"))
        else:
            qty = inv.quantity or 0
        # 份额容差：浮点累加会留下 ~1e-13 碎股，不能当作"仍持仓"
        is_open = not inv.sell_date and qty > 1e-6
        if is_open:
            if its:
                holdings_cost += b + f - s - d
            else:
                holdings_cost += qty * (inv.purchase_price or 0)
            if inv.is_money_market:
                from ..services import money_market_fund
                mmf_evs = [t for t in its if t.event_type in ("buy", "sell")]
                qty = await money_market_fund.mmf_current_shares(inv.symbol, mmf_evs)
            total_current += qty * (inv.current_price or 0)

    floating_pnl = total_current - holdings_cost

    current_month_pnl = 0.0
    try:
        today = date.today()
        month_start = today.replace(day=1)
        if month_start <= today:
            ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
            month_ctx = await _build_portfolio_series(db, user_id, (today - month_start).days + 1, ifind_user, ifind_pass)
            if month_ctx["invs"]:
                month_nav = build_portfolio_nav(
                    month_ctx["dates"], month_ctx["fund_navs"], month_ctx["fund_qty"],
                    month_ctx["cash_by_date"], month_ctx["deposit_by_date"], month_ctx["withdrawal_by_date"],
                )
                series = month_nav["series"]
                if series:
                    month_start_iso = month_start.isoformat()
                    baseline_value = next(
                        (p["total_value"] for p in series if p["date"] >= month_start_iso),
                        series[0]["total_value"],
                    )
                    current_value = series[-1]["total_value"]
                    month_deposit = sum(amount for d, amount in month_ctx["deposit_by_date"].items() if d >= month_start.isoformat())
                    month_withdrawal = sum(amount for d, amount in month_ctx["withdrawal_by_date"].items() if d >= month_start.isoformat())
                    current_month_pnl = current_value - baseline_value - (month_deposit - month_withdrawal)
    except Exception as _e:
        current_month_pnl = 0.0

    realized_pnl = 0.0   # 落袋盈亏 = 已平仓标的 realized（回款 − 成本），不含分红
    closed_res = await db.execute(
        select(Investment).where(
            Investment.user_id == user_id,
            func.coalesce(Investment.sell_date, "") != "",
        )
    )
    for inv in closed_res.scalars().all():
        its = txs_by_inv.get(inv.id, [])
        if not its:
            continue
        buy_amount = sum(float(t.amount or 0) for t in its if t.event_type == "buy")
        proceeds = -sum(float(t.amount or 0) for t in its if t.event_type in ("sell", "dividend"))
        total_fee = sum(float(t.fee or 0) for t in its)
        realized_pnl += round(proceeds - (buy_amount + total_fee), 2)

    dividend_total = await _query_dividend_total(db, user_id)

    idle_cash = total_account_balance + current_month_pnl - total_current
    diff = total_account_balance - (old_principal + realized_pnl + floating_pnl - current_month_pnl)
    warnings: list[str] = []
    status = "ok"

    acc_detail = "、".join(f"{a['name']} {a['balance']:,.2f}" for a in account_list) or "（无投资账户）"
    if abs(diff) > 0.01:
        status = "diff"
        if diff > 0:
            warnings.append(
                f"记账 tab 投资账户余额合计（{total_account_balance:,.2f}）比投资 tab 推算余额"
                f"（入金 {total_deposits:,.2f} − 出金 {total_withdrawals:,.2f} + 落袋盈亏 {realized_pnl:,.2f}"
                f" + 浮动盈亏 {floating_pnl:,.2f} − 当月盈亏 {current_month_pnl:,.2f} = {old_principal + realized_pnl + floating_pnl - current_month_pnl:,.2f}）"
                f"多 {diff:,.2f} 元。"
                f"常见原因：① 同步盈亏到记账未执行或漏了历史已平仓标的；② 分红统计口径不一致；"
                f"③ 记账 tab 记了转入投资账户的转账，但投资 tab 漏记了对应的入金。"
                f"请核对【{acc_detail}】各账户余额与投资 tab 入金/出金流水。"
            )
        else:
            warnings.append(
                f"投资 tab 推算余额（入金 {total_deposits:,.2f} − 出金 {total_withdrawals:,.2f}"
                f" + 落袋盈亏 {realized_pnl:,.2f} + 浮动盈亏 {floating_pnl:,.2f} − 当月盈亏 {current_month_pnl:,.2f}"
                f" = {old_principal + realized_pnl + floating_pnl - current_month_pnl:,.2f}）"
                f"比记账 tab 投资账户余额合计（{total_account_balance:,.2f}）多 {abs(diff):,.2f} 元。"
                f"常见原因：① 投资 tab 记了入金，但记账 tab 漏记了转账给投资账户；"
                f"② 记账 tab 记了投资账户转出，但投资 tab 漏记了对应的出金；"
                f"③ 同步盈亏到记账重复入账。"
                f"请核对【{acc_detail}】各账户余额与投资 tab 入金/出金流水。"
            )
    for na in negative_accounts:
        status = "diff" if status == "ok" else status
        warnings.append(
            f"记账 tab 投资账户「{na['name']}」余额为负（{na['balance']:,.2f}）。"
            f"请检查：期初余额是否填错、转账方向是否记反、是否有支出/退款漏记。"
        )
    if old_principal < -0.01:
        status = "diff"
        warnings.append(
            f"投资 tab 本金（出入金净额）为负（{old_principal:,.2f}）：累计出金超过了累计入金。"
            f"请检查入金/出金流水是否有金额或方向录错。"
        )
    if idle_cash < -0.5:
        status = "diff"
        warnings.append(
            f"闲置现金为负（{idle_cash:,.2f}）：记账 tab 投资账户余额不足以覆盖持仓市值。"
            f"常见原因：① 卖出回款后转出了资金但未记出金；② 浮动盈亏未同步到记账账户；"
            f"③ 漏记了入金/转入。"
        )

    return {
        "accounts": account_list,
        "total_account_balance": round(total_account_balance, 2),
        "total_deposits": round(total_deposits, 2),
        "total_withdrawals": round(total_withdrawals, 2),
        "old_principal": round(old_principal, 2),
        "principal": round(holdings_cost, 2),
        "total_current": round(total_current, 2),
        "floating_pnl": round(floating_pnl, 2),
        "realized_pnl": round(realized_pnl, 2),
        "dividend_total": dividend_total,
        "current_month_pnl": round(current_month_pnl, 2),
        "idle_cash": round(idle_cash, 2),
        "diff": round(diff, 2),
        "status": status,
        "warnings": warnings,
    }


@router.get("/consistency")
async def get_investment_consistency(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """投资 tab ↔ 记账 tab 一致性校验（前端 OverviewTab 调用）。"""
    return await _consistency_core(db, user_id)


@router.get("/reconciliation")
async def get_reconciliation(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """勾稽 Tab 数据：恒等式展示结构（纯只读，复用 _consistency_core）。

    展示「记账余额 = 入金 − 出金 + 落袋盈亏(含分红) − 分红 + 浮动盈亏 − 当月盈亏」，
    通过标准：ABS(记账余额 − 右侧合计) ≤ 0.01。作为所有投资勾稽关系的统一归档数据源。
    """
    core = await _consistency_core(db, user_id)
    dividend_total = core["dividend_total"]
    realized = core["realized_pnl"]
    realized_with_div = round(realized + dividend_total, 2)
    items = [
        {"label": "入金", "value": core["total_deposits"], "operator": "+"},
        {"label": "出金", "value": core["total_withdrawals"], "operator": "-"},
        {"label": "落袋盈亏(含分红)", "value": realized_with_div, "operator": "+"},
        {"label": "  ├ 已平仓 realized", "value": realized, "operator": ""},
        {"label": "  └ 分红(工资账户)", "value": dividend_total, "operator": ""},
        {"label": "分红", "value": dividend_total, "operator": "-"},
        {"label": "浮动盈亏", "value": core["floating_pnl"], "operator": "+"},
        {"label": "当月盈亏", "value": core["current_month_pnl"], "operator": "-"},
    ]
    right = round(
        core["total_deposits"] - core["total_withdrawals"]
        + realized_with_div - dividend_total
        + core["floating_pnl"] - core["current_month_pnl"],
        2,
    )
    diff = round(core["total_account_balance"] - right, 2)
    idle_check = round(core["total_account_balance"] + core["current_month_pnl"] - core["total_current"], 2)

    # ---- 账户级勾稽：每个记账账户 期望余额 vs 实际余额 ----
    from ..models.account import Account
    from ..models.transaction import Transaction
    from .accounts import get_account_balance
    from .reconciliation import calc_expected_balance

    acc_res = await db.execute(
        select(Account).where(Account.user_id == user_id).order_by(Account.account_type, Account.name)
    )
    account_checks = []
    for acc in acc_res.scalars().all():
        t_res = await db.execute(
            select(
                func.coalesce(func.sum(Transaction.amount).filter(Transaction.type == "income"), 0),
                func.coalesce(func.sum(Transaction.amount).filter(Transaction.type == "expense"), 0),
                func.coalesce(
                    func.sum(Transaction.amount).filter(
                        Transaction.type == "transfer", Transaction.account_id == acc.id
                    ),
                    0,
                ),
            ).where(Transaction.user_id == user_id, Transaction.account_id == acc.id)
        )
        income, expense, t_out = t_res.one()
        t_in_res = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id,
                Transaction.type == "transfer",
                Transaction.dest_account_id == acc.id,
            )
        )
        t_in = t_in_res.scalar() or 0
        expected = calc_expected_balance(
            acc.initial_balance or 0, float(income or 0), float(expense or 0),
            float(t_in or 0), float(t_out or 0),
        )
        actual = await get_account_balance(acc, db)
        account_checks.append({
            "account_id": acc.id,
            "account_name": acc.name,
            "account_type": acc.account_type,
            "initial_balance": round(acc.initial_balance or 0, 2),
            "income": round(float(income or 0), 2),
            "expense": round(float(expense or 0), 2),
            "transfer_in": round(float(t_in or 0), 2),
            "transfer_out": round(float(t_out or 0), 2),
            "expected_balance": round(expected, 2),
            "actual_balance": round(actual, 2),
            "diff": round(actual - expected, 2),
            "passed": abs(actual - expected) <= 0.01,
        })

    # ---- 出入金对应勾稽：投资 tab 入金/出金 ↔ 记账 tab 投资账户转账 ----
    inv_acc_ids = [
        a["id"] for a in core["accounts"] if a["id"]
    ]
    flow_res = await db.execute(
        select(InvestmentCashFlow).where(InvestmentCashFlow.user_id == user_id)
    )
    flows = list(flow_res.scalars().all())
    deposits_total = sum(f.amount for f in flows if f.flow_type == "deposit")
    withdrawals_total = sum(f.amount for f in flows if f.flow_type == "withdrawal")
    initial_deposit = sum(
        f.amount for f in flows
        if f.flow_type == "deposit" and f.notes and "初始余额" in (f.notes or "")
    )
    trans_res = await db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.type == "transfer",
        )
    )
    transfers = list(trans_res.scalars().all())
    bk_transfer_in = sum(
        float(t.amount or 0) for t in transfers if t.dest_account_id in inv_acc_ids
    )
    bk_transfer_out = sum(
        float(t.amount or 0) for t in transfers if t.account_id in inv_acc_ids
    )
    flow_checks = {
        "deposits": {
            "investment_tab_total": round(deposits_total, 2),
            "bookkeeping_transfer_in": round(bk_transfer_in, 2),
            "initial_balance_deposit": round(initial_deposit, 2),
            "implied_transfer_in": round(deposits_total - initial_deposit, 2),
            "diff": round((deposits_total - initial_deposit) - bk_transfer_in, 2),
        },
        "withdrawals": {
            "investment_tab_total": round(withdrawals_total, 2),
            "bookkeeping_transfer_out": round(bk_transfer_out, 2),
            "diff": round(withdrawals_total - bk_transfer_out, 2),
        },
    }

    # ---- 同步状态勾稽：记账 tab 已入账的月度盈亏流水 ----
    sync_res = await db.execute(
        select(
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.amount), 0),
            func.min(Transaction.date),
            func.max(Transaction.date),
        ).where(
            Transaction.user_id == user_id,
            Transaction.type == "income",
            Transaction.description.like("投资月度盈亏%"),
        )
    )
    sync_count, sync_total, sync_min, sync_max = sync_res.one()
    sync_checks = {
        "booked_monthly_count": int(sync_count or 0),
        "booked_monthly_total": round(float(sync_total or 0), 2),
        "first_booked_month": sync_min[:7] if sync_min else None,
        "last_booked_month": sync_max[:7] if sync_max else None,
        "current_month_skipped": (sync_max or "")[:7] != date.today().strftime("%Y-%m"),
    }

    return {
        "identity": {
            "left_side": {"label": "记账 tab 投资账户余额", "value": core["total_account_balance"]},
            "right_side": {"items": items, "total": right, "diff": diff, "passed": abs(diff) <= 0.01},
        },
        "auxiliary": {
            "market_value": core["total_current"],
            "idle_cash": core["idle_cash"],
            "idle_cash_check": {"label": "记账余额 + 当月盈亏 − 市值", "value": idle_check},
            "status": core["status"],
            "warnings": core["warnings"],
        },
        "account_checks": account_checks,
        "flow_checks": flow_checks,
        "sync_checks": sync_checks,
    }


@router.get("/lookup", response_model=List[LookupCandidate])
async def lookup_symbol(
    symbol: str = Query(..., min_length=1, max_length=16),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """按代码跨市场查找产品（名称 + 现价），用于「输代码自动补全」。

    同一代码可能命中多个市场（如 000001 = 平安银行 SZ / 华夏成长基金 FUND_CN），
    全部返回给前端让用户选择。
    """
    sym = symbol.strip()
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    candidates: list[LookupCandidate] = []
    errors: list[str] = []

    digits = sym.isdigit()
    markets: list[str] = []
    if digits:
        if len(sym) == 6:
            markets = ["FUND_CN", "SH", "SZ"]
        elif len(sym) == 5:
            markets = ["HK"]
        if not markets:
            markets = ["FUND_CN", "SH", "SZ"]
    else:
        markets = ["US"] if sym.isascii() and sym.isalpha() else []

    for ex in markets:
        if get_provider(ex) is None:
            continue
        try:
            quote = await fetch_price(sym, ex, ifind_user, ifind_pass)
            candidates.append(LookupCandidate(
                exchange=ex,
                name=quote.name or quote.raw_symbol,
                price=quote.price,
                currency=quote.currency,
                source=quote.source,
            ))
        except ProviderError as e:
            errors.append(f"{ex}: {e}")

    if not candidates and errors:
        raise HTTPException(502, "代码查询失败：" + "；".join(errors))
    return candidates


@router.get("/portfolio-metrics", response_model=PortfolioOverview)
async def get_portfolio_metrics(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    return await compute_portfolio_overview(db, user_id)


async def _build_portfolio_series(
    db: AsyncSession,
    user_id: str,
    days: int,
    ifind_user: str,
    ifind_pass: str,
) -> dict:
    """Fetch every fund's NAV history and assemble the portfolio share/cash books.

    Shared by /portfolio-nav and /pnl-history: NAV reconstruction is identical
    for both, only the downstream aggregation differs.
    """
    inv_res = await db.execute(select(Investment).where(Investment.user_id == user_id))
    invs = [i for i in inv_res.scalars().all() if i.symbol and i.exchange]
    days = max(30, min(int(days), 3650))
    end = date.today().isoformat()
    begin = (date.today() - timedelta(days=days)).isoformat()
    if not invs:
        return {"invs": [], "fund_navs": {}, "dates": [], "funds_meta": [], "txs": [],
                "fund_qty": {}, "cash_by_date": {}, "deposit_by_date": {}, "withdrawal_by_date": {},
                "begin": begin, "end": end}

    tx_res = await db.execute(
        select(InvestmentTransaction).where(InvestmentTransaction.user_id == user_id)
    )
    txs = list(tx_res.scalars().all())

    mmf_ids = {inv.id for inv in invs if inv.is_money_market}
    fund_navs: dict[str, dict[str, float]] = {}
    funds_meta = []

    async def _fetch_one(inv):
        try:
            series, source = await nav_history.fetch_history_series(
                inv.symbol, inv.exchange, begin, end, ifind_user, ifind_pass,
                force_money_market=(inv.id in mmf_ids),
            )
            return inv, {p["date"]: p["close"] for p in series}, source, None
        except nav_history.NavHistoryError as e:
            return inv, None, None, str(e)

    results = await asyncio.gather(*[_fetch_one(inv) for inv in invs])
    for inv, series_map, source, err in results:
        if err or series_map is None:
            continue
        fund_navs[inv.id] = series_map
        funds_meta.append({"id": inv.id, "name": inv.name, "symbol": inv.symbol, "source": source})

    dates = sorted(set().union(*[set(navs) for navs in fund_navs.values()])) if fund_navs else []

    inv_ids = {i.id for i in invs}
    txs = [t for t in txs if t.investment_id in inv_ids]

    def snap(d: str) -> str:
        return snap_date(d, dates)

    fund_qty: dict[str, dict[str, float]] = {}
    for inv in invs:
      evs = sorted(
        [t for t in txs if t.investment_id == inv.id and t.event_type in ("buy", "sell")],
        key=lambda t: t.event_date,
      )
      if inv.id in mmf_ids:
        from ..services import money_market_fund

        fund_qty[inv.id] = await money_market_fund.mmf_shares_by_date(inv.symbol, dates, evs)
        continue
      qty_by_date: dict[str, float] = {}
      shares = 0.0
      ei = 0
      for d in dates:
        while ei < len(evs) and evs[ei].event_date[:10] <= d:
          shares += evs[ei].quantity or 0
          ei += 1
        if shares > 0:
          qty_by_date[d] = shares
      # Fallback: when no buy/sell transaction exists for this investment but the legacy
      # snapshot fields (quantity > 0) indicate a holding, seed fund_qty from those fields.
      # This keeps portfolio-nav consistent with overview's total_assets (which uses
      # Investment.quantity × Investment.current_price). The cash leg is NOT deducted here
      # because compute_portfolio_overview treats these phantom holdings as already-funded
      # by the implicit principal (via idle_cash = principal - holdings_cost).
      if (not qty_by_date and dates and inv.quantity and inv.quantity > 0
              and inv.current_price and inv.current_price > 0):
        first_d = dates[0]
        qty_by_date[first_d] = inv.quantity
      fund_qty[inv.id] = qty_by_date

    flow_res = await db.execute(
        select(InvestmentCashFlow).where(InvestmentCashFlow.user_id == user_id)
    )
    flows = list(flow_res.scalars().all())
    deposit_by_date: dict[str, float] = {}
    withdrawal_by_date: dict[str, float] = {}
    for f in flows:
        d = snap(f.flow_date[:10])
        if f.flow_type == "deposit":
            deposit_by_date[d] = deposit_by_date.get(d, 0.0) + f.amount
        else:
            withdrawal_by_date[d] = withdrawal_by_date.get(d, 0.0) + f.amount

    trade_cash_by_date: dict[str, float] = {}
    for t in txs:
        d = snap(t.event_date[:10])
        et = t.event_type
        if et == "buy":
            delta = -abs(t.amount or 0) - abs(t.fee or 0)
        elif et == "sell":
            delta = abs(t.amount or 0) - abs(t.fee or 0)
        elif et == "dividend":
            delta = abs(t.amount or 0)
        elif et == "fee":
            delta = -abs(t.amount or 0)
        else:
            delta = 0.0
        if delta:
            trade_cash_by_date[d] = trade_cash_by_date.get(d, 0.0) + delta
    cash_by_date: dict[str, float] = {}
    cum_flow = 0.0
    cum_trade = 0.0
    for d in dates:
        cum_flow += deposit_by_date.get(d, 0.0) - withdrawal_by_date.get(d, 0.0)
        cum_trade += trade_cash_by_date.get(d, 0.0)
        cash_by_date[d] = cum_flow + cum_trade

    # Ledger with no external cash flows (deposits/withdrawals never recorded):
    # treating buys as cash outflows drives cash deeply negative and the NAV
    # walk degenerates (nav = holdings - principal ≈ noisy near-zero series).
    # In that mode buys/sells are pure internal rebalancing: cash stays 0 and
    # the flows go to build_portfolio_nav as internal unit subscriptions at
    # prev_nav, producing a proper time-weighted index. Accounts WITH external
    # flows keep the existing cash-ledger behavior.
    internal_flow_by_date: dict[str, float] | None = None
    if not deposit_by_date and not withdrawal_by_date:
        internal_flow_by_date = {d: -delta for d, delta in trade_cash_by_date.items()}
        cash_by_date = {d: 0.0 for d in dates}

    return {"invs": invs, "txs": txs, "fund_navs": fund_navs, "funds_meta": funds_meta,
            "dates": dates, "fund_qty": fund_qty, "cash_by_date": cash_by_date,
            "deposit_by_date": deposit_by_date, "withdrawal_by_date": withdrawal_by_date,
            "internal_flow_by_date": internal_flow_by_date,
            "begin": begin, "end": end}


@router.get("/portfolio-nav")
async def get_portfolio_nav(
    days: int = 365,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """组合净值指数曲线（现金流免疫）+ 年化收益/波动率/夏普/最大回撤。

    单位法：入金按前一日净值申购份额、出金赎回份额，份额 × 基金净值 + 闲置现金
    = 组合总值；净值序列的日收益不受出入金影响，可用于波动率/夏普。
    数据源链与单产品净值曲线相同（iFinD → 东财 → akshare）。
    """
    cache_key = (user_id, days)
    cached = _PORTFOLIO_NAV_CACHE.get(cache_key)
    if cached and _time.monotonic() - cached[0] < _PORTFOLIO_NAV_TTL:
        return cached[1]

    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    ctx = await _build_portfolio_series(db, user_id, days, ifind_user, ifind_pass)
    invs, txs, fund_navs, funds_meta = ctx["invs"], ctx["txs"], ctx["fund_navs"], ctx["funds_meta"]
    dates, fund_qty, cash_by_date = ctx["dates"], ctx["fund_qty"], ctx["cash_by_date"]
    deposit_by_date, withdrawal_by_date = ctx["deposit_by_date"], ctx["withdrawal_by_date"]
    begin, end = ctx["begin"], ctx["end"]
    if not invs:
        return {"series": [], "metrics": {}, "funds": []}

    if not fund_navs:
        raise HTTPException(502, "组合净值获取失败：所有持仓产品都拉不到净值历史（iFinD/东财/akshare 均未成功）")

    result = build_portfolio_nav(dates, fund_navs, fund_qty, cash_by_date,
                                 deposit_by_date, withdrawal_by_date,
                                 internal_flow_by_date=ctx.get("internal_flow_by_date"))

    nav_closes = [p["nav"] for p in result["series"]]
    metrics = dict(result["metrics"])
    metrics["sortino"] = indicators.sortino_ratio(nav_closes)
    metrics["calmar"] = indicators.calmar_ratio(nav_closes)
    metrics["downside_deviation"] = indicators.downside_deviation(nav_closes)
    metrics["max_drawdown_duration"] = indicators.max_drawdown_duration(nav_closes)
    metrics["recovery_days"] = indicators.recovery_days(nav_closes)

    benchmark = None
    try:
        b_series, b_source = await nav_history.fetch_benchmark_series(begin, end)
        b_map = {p["date"]: p["close"] for p in b_series}
        pairs = [(p["date"], p["nav"], b_map[p["date"]]) for p in result["series"] if p["date"] in b_map]
        if len(pairs) >= 2:
            fund_rets = [pairs[i][1] / pairs[i - 1][1] - 1 for i in range(1, len(pairs))]
            bench_rets = [pairs[i][2] / pairs[i - 1][2] - 1 for i in range(1, len(pairs))]
            beta, alpha = indicators.beta_alpha(fund_rets, bench_rets)
            b_ann = indicators.annualized_return([p[2] for p in pairs])
            ann_ret = metrics.get("ann_return")
            excess = (ann_ret - b_ann) if (ann_ret is not None and b_ann is not None) else None
            benchmark = {
                "name": "沪深300",
                "symbol": "000300",
                "exchange": "SH",
                "source": b_source,
                "series": [{"date": d, "close": c} for d, _, c in pairs],
                "ann_return": b_ann,
                "beta": beta,
                "alpha": alpha,
                "excess_return": excess,
            }
    except nav_history.NavHistoryError:
        benchmark = None

    inv_by_id = {i.id: i for i in invs}
    events = []
    for t in txs:
        if t.event_type in ("buy", "sell") and begin <= t.event_date[:10] <= end:
            inv = inv_by_id.get(t.investment_id)
            events.append({
                "date": snap_date(t.event_date[:10], dates),
                "type": t.event_type,
                "name": inv.name if inv else "",
                "quantity": abs(t.quantity or 0),
                "amount": abs(t.amount or 0),
            })
    events.sort(key=lambda e: e["date"])

    payload = {
        "series": result["series"],
        "metrics": metrics,
        "funds": funds_meta,
        "benchmark": benchmark,
        "events": events,
    }
    _PORTFOLIO_NAV_CACHE[cache_key] = (_time.monotonic(), payload)
    return payload


@router.get("/pnl-history")
async def get_pnl_history(
    granularity: str = Query("day", pattern="^(day|month|year)$"),
    days: int = 365,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """盈亏柱状图数据：日盈亏 = Δtotal_value − 当日净入金。

    买卖只是现金与持仓互换，不产生盈亏；入金/出金是外部资金进出，扣除后
    Δtotal_value 即为当日市场盈亏（已实现 + 浮动均含）。
    """
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    pnl_cache_key = (user_id, granularity, days)
    cached = _PNL_HISTORY_CACHE.get(pnl_cache_key)
    if cached and _time.monotonic() - cached[0] < _PNL_HISTORY_TTL:
        return cached[1]
    # Daily aggregation is shared across day/month/year; cache the daily
    # series under a synthetic key so a granularity switch only re-buckets.
    daily_cache_key = (user_id, "__daily__", days)
    daily_cached = _PNL_HISTORY_CACHE.get(daily_cache_key)
    if daily_cached and _time.monotonic() - daily_cached[0] < _PNL_HISTORY_TTL:
        daily = daily_cached[1]
    else:
        ctx = await _build_portfolio_series(db, user_id, days, ifind_user, ifind_pass)
        if not ctx["invs"]:
            return {"series": [], "granularity": granularity}
        result = build_portfolio_nav(
            ctx["dates"], ctx["fund_navs"], ctx["fund_qty"],
            ctx["cash_by_date"], ctx["deposit_by_date"], ctx["withdrawal_by_date"],
        )
        daily = []
        prev_value = None
        for p in result["series"]:
            d = p["date"]
            flow = ctx["deposit_by_date"].get(d, 0.0) - ctx["withdrawal_by_date"].get(d, 0.0)
            pnl = 0.0 if prev_value is None else p["total_value"] - prev_value - flow
            daily.append({"date": d, "pnl": round(pnl, 2)})
            prev_value = p["total_value"]
        _PNL_HISTORY_CACHE[daily_cache_key] = (_time.monotonic(), daily)

    if granularity == "day":
        out = daily
    else:
        buckets: dict[str, float] = {}
        for it in daily:
            key = it["date"][:7] if granularity == "month" else it["date"][:4]
            buckets[key] = buckets.get(key, 0.0) + it["pnl"]
        out = [{"date": k, "pnl": round(v, 2)} for k, v in sorted(buckets.items())]
    payload = {"series": out, "granularity": granularity}
    _PNL_HISTORY_CACHE[pnl_cache_key] = (_time.monotonic(), payload)
    return payload


# --------------------------------------------------------------------------- #
# Portfolio principal ledger (deposits / withdrawals)
# --------------------------------------------------------------------------- #

@router.post("/cash-flows/sync-from-bookkeeping")
async def sync_cash_flows_from_bookkeeping(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """把记账 tab 投资账户的转入/转出转账同步为投资 tab 的入金/出金流水。

    规则：transfer 且转入方是投资账户 → deposit；transfer 且转出方是投资账户
    → withdrawal。已存在同日同额同类型的流水则跳过（幂等）。
    """
    from ..models.account import Account
    from ..models.transaction import Transaction

    acc_res = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.account_type == "investment")
    )
    inv_accounts = list(acc_res.scalars().all())
    inv_account_ids = {a.id for a in inv_accounts}
    if not inv_account_ids:
        return {"created": 0, "skipped": 0, "items": [], "message": "记账 tab 没有投资类型账户，无从同步"}

    txn_res = await db.execute(
        select(Transaction).where(Transaction.user_id == user_id, Transaction.type == "transfer")
    )
    transfers = list(txn_res.scalars().all())

    flow_res = await db.execute(
        select(InvestmentCashFlow).where(InvestmentCashFlow.user_id == user_id)
    )
    existing = {
        (f.flow_date[:10], round(float(f.amount), 2), f.flow_type)
        for f in flow_res.scalars().all()
    }

    created = []
    skipped = 0
    for t in transfers:
        if t.dest_account_id in inv_account_ids and t.account_id not in inv_account_ids:
            flow_type, src_desc = "deposit", "转入投资账户"
        elif t.account_id in inv_account_ids and t.dest_account_id not in inv_account_ids:
            flow_type, src_desc = "withdrawal", "从投资账户转出"
        else:
            continue
        amt = round(float(t.amount or 0), 2)
        if amt <= 0:
            continue
        d = t.date[:10]
        if (d, amt, flow_type) in existing:
            skipped += 1
            continue
        flow = InvestmentCashFlow(
            user_id=user_id,
            flow_type=flow_type,
            amount=amt,
            flow_date=d,
            notes=f"同步自记账tab转账（{src_desc}）",
        )
        db.add(flow)
        existing.add((d, amt, flow_type))
        created.append({"flow_type": flow_type, "amount": amt, "flow_date": d})

    flow_all = await db.execute(
        select(InvestmentCashFlow).where(
            InvestmentCashFlow.user_id == user_id, InvestmentCashFlow.flow_type == "deposit"
        )
    )
    deposit_amounts = {round(float(f.amount), 2) for f in flow_all.scalars().all()}
    for a in inv_accounts:
        bal = round(float(a.initial_balance or 0), 2)
        if bal <= 0 or bal in deposit_amounts:
            continue
        flow = InvestmentCashFlow(
            user_id=user_id,
            flow_type="deposit",
            amount=bal,
            flow_date=(a.created_at or datetime.min).strftime("%Y-%m-%d"),
            notes="同步自记账tab投资账户初始余额",
        )
        db.add(flow)
        deposit_amounts.add(bal)
        created.append({"flow_type": "deposit", "amount": bal, "flow_date": flow.flow_date})

    await db.commit()
    return {
        "created": len(created),
        "skipped": skipped,
        "items": created,
        "message": f"已同步 {len(created)} 笔，跳过已存在 {skipped} 笔",
    }


@router.post("/sync-pnl-to-bookkeeping")
async def sync_pnl_to_bookkeeping(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """按月拆分入账（投资分类、全 income）。

    - **历史回溯**：窗口从最早投资活动日期所在月开始（不再默认近 365 天），
      确保覆盖所有历史已平仓标的的 realized P&L（旧版只回看 365 天，
      2025-07 之前平仓的标的在 NAV 序列中无份额，realized 全部漏算）。
    - **跳过当前未结束月份**：今天所在月不写入（月度盈亏只针对已完整结束的
      月份）；若旧版已遗留当前月流水（bug 产物）则删除。
    - **分红纳入统计**：返回 dividend_total（记账 tab 工资账户「投资」分类
      收入，排除 sync 生成的「投资月度盈亏%」流水）。
    - 幂等：同月 description「投资月度盈亏 YYYY-MM」已存在则跳过。
    """
    from ..models.account import Account
    from ..models.transaction import Transaction

    acc_res = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.account_type == "investment")
    )
    accounts = list(acc_res.scalars().all())
    if not accounts:
        return {"ok": False, "adjusted": False, "message": "记账 tab 没有投资类型账户，无从同步"}
    if len(accounts) > 1:
        return {"ok": False, "adjusted": False, "message": "存在多个投资账户，暂不支持自动同步；请先合并或手动核对"}

    acc = accounts[0]
    category_id = await get_or_create_investment_category(db, user_id)

    # --- 历史回溯窗口：最早投资活动日期所在月 1 号 → 今天 ---
    earliest = await _earliest_investment_date(db, user_id)
    begin = earliest.replace(day=1)
    today = date.today()
    days = max((today - begin).days + 1, 30)

    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    ctx = await _build_portfolio_series(db, user_id, days, ifind_user, ifind_pass)
    if not ctx["invs"]:
        return {"ok": True, "adjusted": False, "created": 0, "skipped": 0, "message": "组合为空，无可同步盈亏"}
    nav = build_portfolio_nav(
        ctx["dates"], ctx["fund_navs"], ctx["fund_qty"],
        ctx["cash_by_date"], ctx["deposit_by_date"], ctx["withdrawal_by_date"],
    )
    monthly = compute_pnl_by_period(
        nav["series"], ctx["deposit_by_date"], ctx["withdrawal_by_date"], "month"
    )

    stale = await db.execute(
        select(Transaction).where(
            Transaction.account_id == acc.id,
            Transaction.description.like("投资市值调整%"),
        )
    )
    for old in stale.scalars().all():
        await db.delete(old)

    legacy_exp = await db.execute(
        select(Transaction).where(
            Transaction.account_id == acc.id,
            Transaction.type == "expense",
            Transaction.description.like("投资月度盈亏%"),
        )
    )
    migrated = 0
    for old in legacy_exp.scalars().all():
        old.type = "income"
        old.category_id = category_id
        if old.amount > 0:
            old.amount = -old.amount
        migrated += 1
    await db.flush()

    # --- 删除旧版误入账的当前月流水（未结束月份不应有月度盈亏） ---
    current_month = today.strftime("%Y-%m")
    stale_cur = await db.execute(
        select(Transaction).where(
            Transaction.account_id == acc.id,
            Transaction.description.like(f"投资月度盈亏 {current_month}%"),
        )
    )
    deleted_current = 0
    for t in stale_cur.scalars().all():
        await db.delete(t)
        deleted_current += 1

    months_to_check = [m for m in monthly if m["date"] != current_month and abs(m["pnl"]) >= 0.005]
    created, skipped, updated = 0, 0, 0
    items: list[dict] = []
    for m in months_to_check:
        month_key = m["date"]
        desc_prefix = f"投资月度盈亏 {month_key}"
        dup_res = await db.execute(
            select(Transaction).where(
                Transaction.account_id == acc.id,
                Transaction.description.like(f"{desc_prefix}%"),
            )
        )
        existing = dup_res.scalars().first()
        new_amount = round(m["pnl"], 2)
        if existing:
            # 幂等：不重复创建；但旧算法入账金额与当前算法不一致时修正数字
            amount_differs = abs(round(existing.amount or 0, 2) - new_amount) >= 0.005
            if amount_differs:
                existing.amount = new_amount
                sign = '+' if new_amount > 0 else '-'
                existing.description = f"{desc_prefix} {sign}{abs(new_amount):,.2f} 元"
                updated += 1
            else:
                skipped += 1
            items.append({"month": month_key, "pnl": m["pnl"], "status": "updated" if amount_differs else "skipped"})
            continue
        last_day = _month_last_day(month_key)
        sign = '+' if new_amount > 0 else '-'
        txn = Transaction(
            user_id=user_id,
            account_id=acc.id,
            type="income",
            date=last_day,
            amount=new_amount,
            category_id=category_id,
            tag_ids=[],
            description=f"{desc_prefix} {sign}{abs(new_amount):,.2f} 元",
            remark=f"由投资 tab「同步盈亏到记账」按月拆分生成（{desc_prefix}）；负数为月度亏损（仍入收入作负收入）；幂等：同月重复点击仅入账一次",
        )
        db.add(txn)
        created += 1
        items.append({"month": month_key, "pnl": m["pnl"], "status": "created"})

    dividend_total = await _query_dividend_total(db, user_id)
    await db.commit()
    return {
        "ok": True,
        "adjusted": created > 0 or deleted_current > 0 or updated > 0,
        "created": created,
        "skipped": skipped,
        "updated": updated,
        "migrated": migrated,
        "deleted_current_month": deleted_current,
        "dividend_total": dividend_total,
        "dividend_note": "分红 = 记账 tab 工资账户「投资」分类收入（不含投资月度盈亏流水）",
        "category_id": category_id,
        "items": items,
        "message": (
            f"已按月拆分同步：新增 {created} 笔，修正 {updated} 笔，跳过已存在 {skipped} 笔，"
            f"迁移旧 expense {migrated} 笔，删除当前月误入账 {deleted_current} 笔"
            f"（共查验 {len(months_to_check)} 个月，当前月 {current_month} 不入账）"
        ),
    }


async def _earliest_investment_date(db: AsyncSession, user_id: str) -> date:
    """最早投资活动日期：InvestmentTransaction.event_date / Investment.purchase_date /
    InvestmentCashFlow.flow_date 三者最小值。无任何记录时返回今天。"""
    candidates: list[date] = []
    for model, col in [
        (InvestmentTransaction, InvestmentTransaction.event_date),
        (Investment, Investment.purchase_date),
        (InvestmentCashFlow, InvestmentCashFlow.flow_date),
    ]:
        v = (
            await db.execute(select(func.min(col)).where(model.user_id == user_id))
        ).scalar()
        if v:
            try:
                candidates.append(date.fromisoformat(str(v)[:10]))
            except ValueError:
                pass
    if not candidates:
        return date.today()
    return min(candidates)


async def _query_dividend_total(db: AsyncSession, user_id: str) -> float:
    """分红总额，实现见 services.investment_stats.query_dividend_total（保持本名便于测试引用）。"""
    from ..services.investment_stats import query_dividend_total

    return await query_dividend_total(db, user_id)


def _month_last_day(month_key: str) -> str:
    """YYYY-MM → 该月最后一天 yyyy-mm-dd."""
    import calendar
    y, m = month_key.split("-")
    last = calendar.monthrange(int(y), int(m))[1]
    return f"{y}-{m}-{last:02d}"


@router.get("/cash-flows", response_model=List[CashFlowResponse])
async def list_cash_flows(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    res = await db.execute(
        select(InvestmentCashFlow)
        .where(InvestmentCashFlow.user_id == user_id)
        .order_by(InvestmentCashFlow.flow_date.desc())
    )
    return [_flow_to_response(f) for f in res.scalars().all()]


@router.post("/cash-flows", response_model=CashFlowResponse)
async def create_cash_flow(
    req: CashFlowCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    flow = InvestmentCashFlow(user_id=user_id, **req.model_dump())
    db.add(flow)
    await db.commit()
    _invalidate_portfolio_nav_cache(user_id)
    await db.refresh(flow)
    return _flow_to_response(flow)


@router.put("/cash-flows/{flow_id}", response_model=CashFlowResponse)
async def update_cash_flow(
    flow_id: str,
    req: CashFlowUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    res = await db.execute(
        select(InvestmentCashFlow).where(
            InvestmentCashFlow.id == flow_id, InvestmentCashFlow.user_id == user_id
        )
    )
    flow = res.scalar_one_or_none()
    if not flow:
        raise HTTPException(404, "Cash flow not found")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(flow, k, v)
    await db.commit()
    await db.refresh(flow)
    _invalidate_portfolio_nav_cache(user_id)
    return _flow_to_response(flow)


@router.delete("/cash-flows/{flow_id}")
async def delete_cash_flow(
    flow_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    res = await db.execute(
        select(InvestmentCashFlow).where(
            InvestmentCashFlow.id == flow_id, InvestmentCashFlow.user_id == user_id
        )
    )
    flow = res.scalar_one_or_none()
    if not flow:
        raise HTTPException(404, "Cash flow not found")
    await db.delete(flow)
    await db.commit()
    _invalidate_portfolio_nav_cache(user_id)
    return {"message": "Cash flow deleted"}


@router.get("/{investment_id}", response_model=InvestmentResponse)
async def get_investment(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    return _to_response(inv)


@router.put("/{investment_id}", response_model=InvestmentResponse)
async def update_investment(
    investment_id: str,
    req: InvestmentUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    update_payload = req.model_dump(exclude_unset=True)
    old_quantity = inv.quantity or 0.0
    for key, value in update_payload.items():
        setattr(inv, key, value)
    if inv.investment_type == "fund" and not inv.exchange:
        inv.exchange = "FUND_CN"

    # If quantity changed via the legacy snapshot field but the change isn't reflected
    # in the ledger, synthesize a buy transaction so portfolio-nav stays consistent.
    # This prevents NAV jumps caused by editing quantity directly.
    new_quantity = inv.quantity or 0.0
    if "quantity" in update_payload and abs(new_quantity - old_quantity) > 1e-9:
        res = await db.execute(
            select(InvestmentTransaction)
            .where(InvestmentTransaction.investment_id == inv.id)
            .order_by(InvestmentTransaction.event_date.asc())
        )
        existing_txs = list(res.scalars().all())
        tx_qty_sum = sum(
            t.quantity for t in existing_txs
            if t.event_type not in ("dividend", "fee")
        )
        diff = new_quantity - tx_qty_sum
        if abs(diff) > 1e-9:
            unit_price = inv.purchase_price or inv.current_price or 0.0
            tx_type = "buy" if diff > 0 else "sell"
            db.add(InvestmentTransaction(
                investment_id=inv.id,
                user_id=user_id,
                event_type=tx_type,
                event_date=inv.purchase_date or datetime.utcnow().strftime("%Y-%m-%d"),
                quantity=diff,
                unit_price=unit_price,
                amount=diff * unit_price,
                fee=0.0,
                notes=f"Legacy field adjust: {old_quantity} → {new_quantity}",
            ))
            await db.flush()
            await _recompute_legacy_fields(db, inv)

    await db.commit()
    await db.refresh(inv)
    _invalidate_portfolio_nav_cache(user_id)
    return _to_response(inv)


@router.delete("/{investment_id}")
async def delete_investment(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    await db.execute(delete(InvestmentTransaction).where(
        InvestmentTransaction.investment_id == investment_id))
    await db.delete(inv)
    await db.commit()
    _invalidate_portfolio_nav_cache(user_id)
    return {"message": "Investment deleted"}


# --------------------------------------------------------------------------- #
# Transactions (ledger)
# --------------------------------------------------------------------------- #

@router.get("/{investment_id}/transactions", response_model=List[InvestmentTransactionResponse])
async def list_transactions(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
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
    db: AsyncSession = Depends(get_private_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    # Sign convention: buys positive, sells negative; amount excludes fee (fee is a separate column)
    qty = req.quantity if req.event_type != "sell" else -abs(req.quantity)
    unit_price = float(req.unit_price or 0)
    notes = req.notes
    if req.event_type == "sell" and unit_price <= 0:
        # 净值为已知数据，允许留空：自动取卖出日（或此前最近交易日）净值，
        # 否则 amount=0 会让回款算成 0，把全部成本计为亏损。
        resolved = await _resolve_sell_unit_price(inv, req.event_date, db, user_id)
        if resolved:
            unit_price, src = resolved
            notes = f"{notes or ''}（净值自动补全：{src}）".strip()
    amount = qty * unit_price
    fee = abs(req.fee or 0)
    if req.event_type == "dividend":
        # Dividend: quantity 0, amount = positive cash to investor
        qty = 0
        amount = abs(req.unit_price)  # unit_price reused as the dividend amount
        fee = 0.0
    if req.event_type == "fee":
        qty = 0
        amount = -abs(req.unit_price)  # standalone fee event: amount mirrors the fee
        fee = abs(req.unit_price)
    tx = InvestmentTransaction(
        investment_id=investment_id,
        user_id=user_id,
        event_type=req.event_type,
        event_date=req.event_date,
        quantity=qty,
        unit_price=unit_price,
        amount=amount,
        fee=fee,
        notes=notes,
    )
    db.add(tx)
    await db.flush()
    await _recompute_legacy_fields(db, inv)
    await db.commit()
    await db.refresh(tx)
    _invalidate_portfolio_nav_cache(user_id)
    return _tx_to_response(tx)


@router.put("/{investment_id}/transactions/{tx_id}", response_model=InvestmentTransactionResponse)
async def update_transaction(
    investment_id: str,
    tx_id: str,
    req: InvestmentTransactionUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
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
    # Re-derive amount/fee from the (possibly new) quantity/unit_price/fee/event_type
    if {"quantity", "unit_price", "fee", "event_type"} & data.keys():
        fee = abs(tx.fee or 0)
        if tx.event_type == "dividend":
            tx.quantity = 0
            tx.amount = abs(tx.unit_price)
            fee = 0.0
        elif tx.event_type == "fee":
            tx.quantity = 0
            tx.amount = -abs(tx.unit_price)
            fee = abs(tx.unit_price)
        else:
            if tx.event_type == "sell":
                tx.quantity = -abs(tx.quantity)
                if float(tx.unit_price or 0) <= 0:
                    resolved = await _resolve_sell_unit_price(inv, tx.event_date, db, user_id)
                    if resolved:
                        tx.unit_price, src = resolved
                        tx.notes = f"{tx.notes or ''}（净值自动补全：{src}）".strip()
            tx.amount = tx.quantity * tx.unit_price
        tx.fee = fee
    await _recompute_legacy_fields(db, inv)
    await db.commit()
    await db.refresh(tx)
    _invalidate_portfolio_nav_cache(user_id)
    return _tx_to_response(tx)


@router.delete("/{investment_id}/transactions/{tx_id}")
async def delete_transaction(
    investment_id: str,
    tx_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
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
    _invalidate_portfolio_nav_cache(user_id)
    return {"message": "Transaction deleted"}


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

@router.get("/{investment_id}/metrics", response_model=InvestmentMetrics)
async def get_metrics(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    inv = await _load_investment(db, investment_id, user_id)
    return await compute_investment_metrics(db, inv)


@router.get("/metrics/all", response_model=List[dict])
async def get_all_metrics(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
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

def _invalidate_portfolio_nav_cache(user_id: str) -> None:
    for k in [k for k in _PORTFOLIO_NAV_CACHE if k[0] == user_id]:
        del _PORTFOLIO_NAV_CACHE[k]
    for k in [k for k in _PNL_HISTORY_CACHE if k[0] == user_id]:
        del _PNL_HISTORY_CACHE[k]


@router.post("/{investment_id}/refresh-price", response_model=InvestmentResponse)
async def refresh_price(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
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
    if not inv.is_money_market and quote.source == "eastmoney-money-market":
        inv.is_money_market = True
    if inv.is_money_market:
        from ..services import money_market_fund

        inv.seven_day_yield = await money_market_fund.latest_seven_day(inv.symbol) or inv.seven_day_yield
    await db.commit()
    _invalidate_portfolio_nav_cache(user_id)
    await db.refresh(inv)
    resp = _to_response(inv)
    today = date.today().isoformat()
    if inv.symbol and inv.exchange:
        ind = await compute_position_indicators(
            inv.symbol, inv.exchange, inv.purchase_date[:10], today, ifind_user, ifind_pass,
            is_money_market=bool(inv.is_money_market),
        )
        if isinstance(ind, dict):
            resp.ann_volatility = ind.get("ann_volatility")
            resp.sharpe_ratio = ind.get("sharpe")
            resp.ann_return = ind.get("ann_return")
    return resp


@router.post("/refresh-prices/all", response_model=List[dict])
async def refresh_all_prices(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """Refresh prices for every investment. Items without symbol/exchange are
    reported as skipped (ok=false) instead of silently vanishing from the result."""
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    res = await db.execute(
        select(Investment).where(Investment.user_id == user_id)
    )
    invs = list(res.scalars().all())
    results = []
    for inv in invs:
        if inv.sell_date:
            continue
        if not inv.symbol or not inv.exchange:
            results.append({
                "id": inv.id, "name": inv.name, "ok": False,
                "error": "未设置代码/市场，无法自动刷新；请编辑该产品补上代码",
            })
            continue
        try:
            quote = await fetch_price(inv.symbol, inv.exchange, ifind_user, ifind_pass)
            inv.current_price = quote.price
            inv.last_price_update = quote.timestamp.replace(tzinfo=None)
            if not inv.is_money_market and quote.source == "eastmoney-money-market":
                inv.is_money_market = True
            if inv.is_money_market:
                from ..services import money_market_fund

                inv.seven_day_yield = await money_market_fund.latest_seven_day(inv.symbol) or inv.seven_day_yield
            results.append({"id": inv.id, "name": inv.name, "ok": True, "price": quote.price, "source": quote.source})
        except ProviderError as e:
            results.append({"id": inv.id, "name": inv.name, "ok": False, "error": str(e)})
    await db.commit()
    _invalidate_portfolio_nav_cache(user_id)
    return results


# --------------------------------------------------------------------------- #
# NAV history (iFinD) — for the per-product curve + buy/sell markers
# --------------------------------------------------------------------------- #

@router.get("/{investment_id}/nav-history")
async def get_nav_history(
    investment_id: str,
    days: int = 365,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    """Return the daily close series + transaction events + cost basis for the
    per-product detail drawer (净值曲线 + 买卖点).

    Source chain: iFinD (if configured) → Eastmoney → akshare — works without
    iFinD credentials.
    """
    inv = await _load_investment(db, investment_id, user_id)
    if not inv.symbol or not inv.exchange:
        raise HTTPException(400, "该产品未设置代码/市场，无法获取净值历史")
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)

    days = max(7, min(int(days), 3650))
    end = date.today().isoformat()
    begin = (date.today() - timedelta(days=days)).isoformat()
    try:
        series, source = await nav_history.fetch_history_series(
            inv.symbol, inv.exchange, begin, end, ifind_user, ifind_pass,
            force_money_market=bool(inv.is_money_market),
        )
    except nav_history.NavHistoryError as e:
        raise HTTPException(502, f"净值历史获取失败（iFinD/东财/akshare 均未成功）：{e}")

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
    ann_vol = indicators.annualized_volatility(closes)
    ann_ret = indicators.annualized_return(closes)
    sortino = indicators.sortino_ratio(closes)
    calmar = indicators.calmar_ratio(closes)
    downside = indicators.downside_deviation(closes)
    mdd_duration = indicators.max_drawdown_duration(closes)
    recovery = indicators.recovery_days(closes)
    # 合并 MA 进 series 每个 point（前端 NavHistoryPoint.ma20/ma60 期望点级字段）
    for i, p in enumerate(series):
        p["ma20"] = ma20[i]
        p["ma60"] = ma60[i]

    benchmark = None
    try:
        b_series, b_source = await nav_history.fetch_benchmark_series(begin, end)
        b_map = {p["date"]: p["close"] for p in b_series}
        pairs = [(p["date"], p["close"], b_map[p["date"]]) for p in series if p["date"] in b_map]
        if len(pairs) >= 2:
            fund_rets = [pairs[i][1] / pairs[i - 1][1] - 1 for i in range(1, len(pairs))]
            bench_rets = [pairs[i][2] / pairs[i - 1][2] - 1 for i in range(1, len(pairs))]
            beta, alpha = indicators.beta_alpha(fund_rets, bench_rets)
            b_ann = indicators.annualized_return([p[2] for p in pairs])
            excess = (ann_ret - b_ann) if (ann_ret is not None and b_ann is not None) else None
            benchmark = {
                "name": "沪深300",
                "symbol": "000300",
                "exchange": "SH",
                "source": b_source,
                "series": [{"date": d, "close": c} for d, _, c in pairs],
                "ann_return": b_ann,
                "beta": beta,
                "alpha": alpha,
                "excess_return": excess,
            }
    except nav_history.NavHistoryError:
        benchmark = None

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
        "ann_volatility": ann_vol,               # decimal, e.g. 0.18 = 18%/年
        "ann_return": ann_ret,
        "sortino": sortino,
        "calmar": calmar,
        "downside_deviation": downside,
        "max_drawdown_duration": mdd_duration,   # trading days
        "recovery_days": recovery,               # trading days; null = 尚未收复失地
        "benchmark": benchmark,                  # {series, ann_return, beta, alpha, excess_return} | null
        "ma20": ma20,  # list[float|None], same length as series; null = window未填满
        "ma60": ma60,
        "source": source,
        "begin": begin,
        "end": end,
    }


# --------------------------------------------------------------------------- #
# NAV snapshots (placeholder endpoint for future manual-entry support)
# --------------------------------------------------------------------------- #
async def list_snapshots(
    investment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
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
    db: AsyncSession = Depends(get_private_db),
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
        _invalidate_portfolio_nav_cache(user_id)
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
