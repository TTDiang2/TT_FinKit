"""Signal generation service - runs active strategy to produce signal."""
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.signal import Signal
from app.models.strategy import Strategy

async def get_active_strategy(db: AsyncSession):
    """The strategy the user activated (latest activated_at wins).

    Falls back to None when nothing is activated — the caller returns a 404
    telling the user to activate a strategy first.
    """
    result = await db.execute(
        select(Strategy)
        .where(Strategy.activated_at.isnot(None))
        .order_by(Strategy.activated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()

async def get_latest_signal(db: AsyncSession, user_id: str) -> Signal | None:
    result = await db.execute(
        select(Signal).where(Signal.user_id == user_id)
        .order_by(Signal.created_at.desc()).limit(1))
    return result.scalar_one_or_none()

async def list_signals(db: AsyncSession, user_id: str, limit: int = 50) -> list[Signal]:
    result = await db.execute(
        select(Signal).where(Signal.user_id == user_id)
        .order_by(Signal.created_at.desc()).limit(limit))
    return list(result.scalars().all())

async def get_signal(db: AsyncSession, signal_id: str, user_id: str) -> Signal | None:
    result = await db.execute(
        select(Signal).where(Signal.id == signal_id, Signal.user_id == user_id))
    return result.scalar_one_or_none()

async def save_signal(db: AsyncSession, user_id: str, strategy_id: str, strategy_version: int,
                     run_date: str, as_of_date: str, next_rebalance_date: str | None,
                     target_weights: dict, risk_status: dict | None = None,
                     backtest_id: str | None = None) -> Signal:
    sig = Signal(
        user_id=user_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        run_date=run_date,
        as_of_date=as_of_date,
        next_rebalance_date=next_rebalance_date,
        target_weights=json.dumps(target_weights),
        risk_status=json.dumps(risk_status) if risk_status else None,
        backtest_id=backtest_id,
    )
    db.add(sig)
    await db.commit()
    await db.refresh(sig)
    return sig
