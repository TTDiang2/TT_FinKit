"""Backtest management service."""
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.backtest import Backtest
from app.models.strategy import Strategy

async def create_backtest(db: AsyncSession, strategy_id: str, strategy_version: int,
                          params: dict, universe: list[str], start_date: str,
                          end_date: str, rebalance_freq: str) -> Backtest:
    # Get latest data_as_of (today)
    from datetime import date
    data_as_of = date.today().isoformat()

    bt = Backtest(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        params=json.dumps(params),
        universe=json.dumps(universe),
        start_date=start_date,
        end_date=end_date,
        rebalance_freq=rebalance_freq,
        data_as_of=data_as_of,
        status="pending",
    )
    db.add(bt)
    await db.commit()
    await db.refresh(bt)
    return bt

async def get_backtest(db: AsyncSession, backtest_id: str) -> Backtest | None:
    result = await db.execute(select(Backtest).where(Backtest.id == backtest_id))
    return result.scalar_one_or_none()

async def list_backtests(db: AsyncSession, limit: int = 50) -> list[Backtest]:
    result = await db.execute(select(Backtest).order_by(Backtest.created_at.desc()).limit(limit))
    return list(result.scalars().all())

async def update_backtest_status(db: AsyncSession, backtest_id: str, status: str,
                                 error: str | None = None, results: dict | None = None):
    bt = await get_backtest(db, backtest_id)
    if not bt:
        return
    bt.status = status
    if error is not None:
        bt.error = error
    if results is not None:
        bt.results = json.dumps(results)
    await db.commit()

async def delete_backtest(db: AsyncSession, backtest_id: str) -> bool:
    bt = await get_backtest(db, backtest_id)
    if not bt:
        return False
    await db.delete(bt)
    await db.commit()
    return True
