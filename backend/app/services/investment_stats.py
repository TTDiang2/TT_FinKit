"""Investment return metrics.

We use money-weighted returns via XIRR — the de-facto standard for personal
portfolio trackers. See SPEC.md / proposal for the rationale.

Key formulas:
  total_return   = (current_value + total_redeemed + total_dividends - total_invested - fees) / total_invested
  XIRR           = pyxirr.xirr(dates, cashflows)   # cashflows signed: neg=outflow, pos=inflow
  annualization  = (1 + r)^(365.25 / days) - 1     # only when not already annualized

For rolling windows (last 1y / last 1m) we anchor the cashflow series at the
window's start using the most recent NAV snapshot ≤ window start (if any),
falling back to a linear interpolation between adjacent snapshots, falling
back to None if we have no anchor at all.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from pyxirr import xirr
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.investment import Investment
from ..models.investment_transaction import InvestmentTransaction
from ..models.investment_nav_snapshot import InvestmentNavSnapshot
from ..schemas.investment import InvestmentMetrics, PortfolioOverview


def _parse_date(s: str) -> datetime:
    """Lenient YYYY-MM-DD parser (also accepts full datetime strings)."""
    return datetime.fromisoformat(s[:10])


def _days_between(start: datetime, end: datetime) -> int:
    return max((end - start).days, 1)


def _annualize(rate: float, days: int) -> Optional[float]:
    """Compound-annualize a rate over a period length."""
    if days <= 0 or rate is None:
        return None
    return (1.0 + rate) ** (365.25 / days) - 1.0


def _build_cashflows(
    txs: list[InvestmentTransaction],
    end_value: float,
    end_date: datetime,
) -> tuple[list[datetime], list[float]]:
    """Build XIRR cashflow series: outflows negative, inflows positive, terminal value negative-of-current.

    Wait — terminal convention: from the investor's perspective:
      - buy / fee    = OUT cash  → negative
      - sell         = IN cash   → positive
      - dividend     = IN cash   → positive
      - end-of-window mark-to-market = the position's current value as if it were redeemed today → positive

    pyxirr expects (dates, amounts) where the IRR is the rate that makes NPV = 0.
    """
    dates: list[datetime] = []
    amounts: list[float] = []
    for tx in txs:
        try:
            d = _parse_date(tx.event_date)
        except Exception:
            continue
        fee = abs(tx.fee or 0)
        if tx.event_type in ("buy", "fee"):
            amt = -abs(tx.amount or 0) - fee
        elif tx.event_type in ("sell", "dividend"):
            amt = abs(tx.amount or 0) - fee
        elif tx.event_type == "adjustment":
            amt = 0.0  # neutral — split/consolidation; no cash impact
        else:
            amt = -abs(tx.amount or 0) - fee
        # Skip zero entries to keep the series clean
        if amt != 0.0:
            dates.append(d)
            amounts.append(amt)
    # Terminal value (always at end_date) — current holdings valued at market
    if end_value > 0:
        dates.append(end_date)
        amounts.append(end_value)
    return dates, amounts


async def compute_investment_metrics(
    db: AsyncSession,
    investment: Investment,
    now: Optional[datetime] = None,
) -> InvestmentMetrics:
    """Compute full metrics for a single investment using its transaction ledger."""
    now = now or datetime.utcnow()

    tx_res = await db.execute(
        select(InvestmentTransaction)
        .where(InvestmentTransaction.investment_id == investment.id)
        .order_by(InvestmentTransaction.event_date.asc())
    )
    txs = list(tx_res.scalars().all())

    if not txs:
        # Fallback to the legacy snapshot fields when no ledger exists yet
        invested = (investment.quantity or 0) * (investment.purchase_price or 0)
        current_value = (investment.quantity or 0) * (investment.current_price or 0)
        pnl = current_value - invested
        start = now
        try:
            if investment.purchase_date:
                start = _parse_date(investment.purchase_date)
        except Exception:
            start = now
        days = _days_between(start, now) if start < now else 0
        fallback_xirr: Optional[float] = None
        if invested > 0 and current_value > 0 and start < now:
            try:
                fallback_xirr = xirr([start, now], [-invested, current_value])
            except Exception:
                fallback_xirr = None
        return InvestmentMetrics(
            total_invested=round(invested, 4),
            total_redeemed=0.0,
            total_dividends=0.0,
            total_fees=0.0,
            current_value=round(current_value, 4),
            total_pnl=round(pnl, 4),
            total_return_pct=round(pnl / invested * 100, 4) if invested > 0 else 0.0,
            xirr_annualized=fallback_xirr,
            last_1y_xirr=None,
            last_1m_xirr=None,
            days_held=days,
            last_event_date=investment.purchase_date,
        )

    # Aggregate the ledger
    total_invested = sum(t.amount for t in txs if t.event_type == "buy")
    total_redeemed = sum(abs(t.amount) for t in txs if t.event_type == "sell")
    total_dividends = sum(abs(t.amount) for t in txs if t.event_type == "dividend")
    total_fees = sum(
        abs(t.fee or 0) if (t.fee or 0) != 0
        else (abs(t.amount) if t.event_type == "fee" else 0.0)
        for t in txs
    )

    current_qty = sum(t.quantity for t in txs if t.event_type != "dividend" and t.event_type != "fee")
    current_value = current_qty * (investment.current_price or 0)

    pnl = current_value + total_redeemed + total_dividends - total_invested - total_fees

    last_event_date = txs[-1].event_date

    # XIRR since inception
    try:
        start_dt = _parse_date(txs[0].event_date)
        end_dt = now
        days_held = _days_between(start_dt, end_dt)
        dates, amounts = _build_cashflows(txs, current_value, end_dt)
        xirr_inception = xirr(dates, amounts) if len(dates) >= 2 else None
    except Exception:
        xirr_inception = None
        days_held = 0

    # Rolling windows — anchored by historical snapshot of total_value
    last_1y_xirr = await _rolling_xirr(db, investment, txs, current_value, now, timedelta(days=365))
    last_1m_xirr = await _rolling_xirr(db, investment, txs, current_value, now, timedelta(days=30))

    return InvestmentMetrics(
        total_invested=round(total_invested, 4),
        total_redeemed=round(total_redeemed, 4),
        total_dividends=round(total_dividends, 4),
        total_fees=round(total_fees, 4),
        current_value=round(current_value, 4),
        total_pnl=round(pnl, 4),
        total_return_pct=round(pnl / total_invested * 100, 4) if total_invested > 0 else 0.0,
        xirr_annualized=xirr_inception,
        last_1y_xirr=last_1y_xirr,
        last_1m_xirr=last_1m_xirr,
        days_held=days_held,
        last_event_date=last_event_date,
    )


async def _rolling_xirr(
    db: AsyncSession,
    investment: Investment,
    txs: list[InvestmentTransaction],
    current_value: float,
    now: datetime,
    window: timedelta,
) -> Optional[float]:
    """XIRR over the last `window` window.

    Strategy: get the most recent NAV snapshot ≤ (now - window). Use its
    total_value as a positive "virtual outflow" at the window-start date,
    then include only transactions within the window.
    """
    window_start = now - window
    window_start_str = window_start.strftime("%Y-%m-%d")

    snap_res = await db.execute(
        select(InvestmentNavSnapshot)
        .where(
            InvestmentNavSnapshot.investment_id == investment.id,
            InvestmentNavSnapshot.snapshot_date <= window_start_str,
        )
        .order_by(InvestmentNavSnapshot.snapshot_date.desc())
        .limit(1)
    )
    anchor = snap_res.scalars().first()
    if anchor is None or anchor.total_value <= 0:
        return None

    # Anchor cashflow: at anchor.snapshot_date we treat the existing holding as
    # an "in" of zero (mark-to-market is captured at the end). To anchor IRR
    # properly we model it as an outflow (capital already deployed) and the
    # terminal value as inflow.
    anchor_dt = _parse_date(anchor.snapshot_date)

    # Transactions within (anchor, now]
    in_window = [t for t in txs if _parse_date(t.event_date) > anchor_dt]
    dates: list[datetime] = [anchor_dt]
    amounts: list[float] = [-anchor.total_value]
    for t in in_window:
        try:
            d = _parse_date(t.event_date)
        except Exception:
            continue
        fee = abs(t.fee or 0)
        if t.event_type in ("buy", "fee"):
            amt = -abs(t.amount) - fee
        elif t.event_type in ("sell", "dividend"):
            amt = abs(t.amount) - fee
        else:
            amt = 0.0
        if amt != 0.0:
            dates.append(d)
            amounts.append(amt)
    dates.append(now)
    amounts.append(current_value)
    try:
        return xirr(dates, amounts)
    except Exception:
        return None


def _tx_fee(t: InvestmentTransaction) -> float:
    if (t.fee or 0) != 0:
        return abs(t.fee)
    return abs(t.amount) if t.event_type == "fee" else 0.0


async def query_dividend_total(db: AsyncSession, user_id: str) -> float:
    """分红总额 = 记账 tab 中「现金账户(cash) + 分类=投资 + income」的收入合计，
    排除 sync 自动生成的「投资月度盈亏%」流水。

    用户实际场景：基金分红默认到账工资卡（现金账户），记 income + category=投资；
    投资 tab 的 investment_transactions 从不记 dividend 事件（恒为 0），
    因此分红的唯一数据源是记账 tab 流水。
    """
    from ..models.account import Account
    from ..models.category import Category
    from ..models.transaction import Transaction

    val = (
        await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .join(Account, Transaction.account_id == Account.id)
            .join(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.user_id == user_id,
                Transaction.type == "income",
                Account.account_type == "cash",
                Category.name == "投资",
                Transaction.description.not_like("投资月度盈亏%"),
            )
        )
    ).scalar()
    return round(float(val or 0), 2)


async def compute_portfolio_overview(
    db: AsyncSession,
    user_id: str,
    now: Optional[datetime] = None,
) -> "PortfolioOverview":
    """Portfolio summary: principal ledger + product ledgers + market value.

    整体盈亏/收益率口径与单产品一致（含已平仓）：
      pnl = Σ(市值 + 卖出回款 + 分红 − 买入 − 费用)
    组合 XIRR 只看穿越组合边界的现金流：入金(−)、出金(+)、期末(市值+闲置现金)。
    """
    from ..models.investment_cash_flow import InvestmentCashFlow
    now = now or datetime.utcnow()

    flow_res = await db.execute(
        select(InvestmentCashFlow)
        .where(InvestmentCashFlow.user_id == user_id)
        .order_by(InvestmentCashFlow.flow_date.asc())
    )
    flows = list(flow_res.scalars().all())
    deposits = sum(f.amount for f in flows if f.flow_type == "deposit")
    withdrawals = sum(f.amount for f in flows if f.flow_type == "withdrawal")
    principal = deposits - withdrawals

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

    total_pnl = 0.0
    realized_pnl = 0.0
    floating_pnl = 0.0
    market_value = 0.0
    invested_cost = 0.0        # Σ(买入 + 费用)，收益率分母
    holdings_cost = 0.0        # 当前持仓摊薄成本（未平仓产品的 买入+费用−卖出−分红）
    for inv in invs:
        its = txs_by_inv.get(inv.id, [])
        if its:
            b = sum(t.amount for t in its if t.event_type == "buy")
            s = sum(abs(t.amount) for t in its if t.event_type == "sell")
            d = sum(abs(t.amount) for t in its if t.event_type == "dividend")
            f = sum(_tx_fee(t) for t in its)
            qty = sum(t.quantity for t in its if t.event_type not in ("dividend", "fee"))
        else:
            b, s, d, f = (inv.quantity or 0) * (inv.purchase_price or 0), 0.0, 0.0, 0.0
            qty = inv.quantity or 0
        is_open = not inv.sell_date and qty > 0
        if inv.is_money_market and qty > 0:
            from ..services import money_market_fund
            mmf_evs = [t for t in its if t.event_type in ("buy", "sell")]
            qty = await money_market_fund.mmf_current_shares(inv.symbol, mmf_evs)
        mv_i = 0.0 if not is_open else qty * (inv.current_price or 0)
        market_value += mv_i
        invested_cost += b + f
        if is_open:
            holdings_cost += b + f - s - d
            floating_pnl += mv_i - (b + f - s - d)
        else:
            realized_pnl += s + d - b - f
        total_pnl += mv_i + s + d - b - f

    # 未投资现金（推算）= 记账 tab 投资账户余额 − 当前持仓市值。
    # 投资账户余额经「投资月度盈亏」流水已滚动计入基金市值，所以
    # 现金 = 账户余额 − 市值；旧公式「净入金 − 持仓成本」混淆了
    # 成本与市值，在落袋再投入场景下出现 −2,032 的伪负值（2026-09-05 修正）。
    from ..models.account import Account
    from ..models.transaction import Transaction
    from ..models.investment_cash_flow import InvestmentCashFlow
    account_balance = 0.0
    acc_rows = (await db.execute(
        select(Account).where(Account.user_id == user_id, Account.account_type == "investment")
    )).scalars().all()
    for acc in acc_rows:
        inc = (await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acc.id, Transaction.type == "income")
        )).scalar() or 0
        exp = (await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acc.id, Transaction.type == "expense")
        )).scalar() or 0
        tin = (await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.dest_account_id == acc.id, Transaction.type == "transfer")
        )).scalar() or 0
        tout = (await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acc.id, Transaction.type == "transfer")
        )).scalar() or 0
        account_balance += (acc.initial_balance or 0) + float(inc) - float(exp) + float(tin) - float(tout)
    idle_cash = account_balance - market_value

    portfolio_xirr: Optional[float] = None
    days_held = 0
    dates: list[datetime] = []
    amounts: list[float] = []
    first_date: Optional[datetime] = None
    for fl in flows:
        try:
            d = _parse_date(fl.flow_date)
        except Exception:
            continue
        if first_date is None:
            first_date = d
        amt = fl.amount if fl.flow_type == "deposit" else -fl.amount
        if amt != 0:
            dates.append(d)
            amounts.append(-amt)   # deposit=outflow(neg), withdrawal=inflow(pos)
    if dates:
        terminal = market_value + idle_cash
        if terminal != 0:
            dates.append(now)
            amounts.append(terminal)
        try:
            portfolio_xirr = xirr(dates, amounts)
        except Exception:
            portfolio_xirr = None
        if first_date and first_date < now:
            days_held = _days_between(first_date, now)

    dividend_total = await query_dividend_total(db, user_id)

    return PortfolioOverview(
        total_deposits=round(deposits, 2),
        total_withdrawals=round(withdrawals, 2),
        old_principal=round(principal, 2),
        principal=round(holdings_cost, 2),
        current_market_value=round(market_value, 2),
        idle_cash=round(idle_cash, 2),
        total_pnl=round(total_pnl, 2),
        realized_pnl=round(realized_pnl, 2),
        dividend_total=dividend_total,
        floating_pnl=round(floating_pnl, 2),
        total_return_pct=round(total_pnl / invested_cost * 100, 4) if invested_cost > 0 else 0.0,
        xirr_annualized=portfolio_xirr,
        days_held=days_held,
    )


async def compute_position_indicators(
    symbol: str,
    exchange: str,
    begin: str,
    end: str,
    ifind_user: str | None,
    ifind_pass: str | None,
    is_money_market: bool = False,
) -> dict:
    """持仓期内的年化波动率/夏普/年化收益（对 close 序列）。

    Returns ``{ann_volatility, sharpe, ann_return, points}``；任一步失败返回
    全 None + points=0，调用方按 None 跳过展示。``end`` 截到今天（已平仓用 sell_date）。

    货币基金（is_money_market=True）：净值/收益序列近乎恒定（或为万份收益制），
    年化波动率趋近 0 → 夏普 = (年化收益 − 无风险)/波动率 会爆炸成数千的荒谬值。
    货币基金无"净值波动"概念，直接不产出 vol/sharpe（ann_return 一并置 None 避免误导）。
    """
    from . import nav_history
    from .indicators import annualized_return, annualized_volatility, sharpe_ratio

    if not symbol or not exchange:
        return {"ann_volatility": None, "sharpe": None, "ann_return": None, "points": 0}
    if is_money_market:
        return {"ann_volatility": None, "sharpe": None, "ann_return": None, "points": 0}
    try:
        series, _src = await nav_history.fetch_history_series(
            symbol, exchange, begin, end, ifind_user, ifind_pass
        )
    except nav_history.NavHistoryError:
        return {"ann_volatility": None, "sharpe": None, "ann_return": None, "points": 0}
    closes = [p["close"] for p in series if p.get("close")]
    if len(closes) < 2:
        return {"ann_volatility": None, "sharpe": None, "ann_return": None, "points": len(closes)}
    return {
        "ann_volatility": annualized_volatility(closes),
        "sharpe": sharpe_ratio(closes),
        "ann_return": annualized_return(closes),
        "points": len(closes),
    }


async def get_or_create_investment_category(db, user_id: str) -> str:
    """找/创投资 tab 同步用的记账「投资」分类 id。

    匹配策略：name == "投资" 的 category（任意 pl_section、其他属性不限制）取第一个；
    没有则新建一个 type='income' pl_section='other_income' color='#6B6B6B' 的；返回 id。
    落地后调用方 commit 即可。
    """
    from ..models.category import Category

    res = await db.execute(
        select(Category).where(Category.user_id == user_id, Category.name == "投资")
    )
    found = res.scalars().first()
    if found:
        return found.id
    cat = Category(
        user_id=user_id,
        name="投资",
        type="income",
        color="#6B6B6B",
        icon="",
        sort_order=0,
        is_necessary=False,
        pl_section="other_income",
        cf_section="operating",
    )
    db.add(cat)
    await db.flush()
    return cat.id
