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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.investment import Investment
from ..models.investment_transaction import InvestmentTransaction
from ..models.investment_nav_snapshot import InvestmentNavSnapshot
from ..schemas.investment import InvestmentMetrics


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
        if tx.event_type in ("buy", "fee"):
            amt = -abs(tx.amount) if tx.amount else 0.0
        elif tx.event_type in ("sell", "dividend"):
            amt = abs(tx.amount) if tx.amount else 0.0
        elif tx.event_type == "adjustment":
            amt = 0.0  # neutral — split/consolidation; no cash impact
        else:
            amt = -abs(tx.amount) if tx.amount else 0.0
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
        try:
            start = _parse_date(investment.purchase_date) if investment.purchase_date else now
            days = _days_between(start, now)
        except Exception:
            days = 0
        return InvestmentMetrics(
            total_invested=round(invested, 4),
            total_redeemed=0.0,
            total_dividends=0.0,
            total_fees=0.0,
            current_value=round(current_value, 4),
            total_pnl=round(pnl, 4),
            total_return_pct=round(pnl / invested * 100, 4) if invested > 0 else 0.0,
            xirr_annualized=None,
            last_1y_xirr=None,
            last_1m_xirr=None,
            days_held=days,
            last_event_date=investment.purchase_date,
        )

    # Aggregate the ledger
    total_invested = sum(t.amount for t in txs if t.event_type == "buy")
    total_redeemed = sum(abs(t.amount) for t in txs if t.event_type == "sell")
    total_dividends = sum(abs(t.amount) for t in txs if t.event_type == "dividend")
    total_fees = sum(abs(t.amount) for t in txs if t.event_type == "fee")

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
        if t.event_type in ("buy", "fee"):
            amt = -abs(t.amount)
        elif t.event_type in ("sell", "dividend"):
            amt = abs(t.amount)
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
