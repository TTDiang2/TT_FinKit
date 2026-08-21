from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas.backtest import BacktestCreate, BacktestResponse, BacktestResult
from ..services.backtest_service import (
    create_backtest, get_backtest, list_backtests, update_backtest_status, delete_backtest
)
from ..services.backtest_engine import run_backtest_in_subprocess
import json

router = APIRouter(prefix="/api/backtests", tags=["backtests"])

# Keep strong references to in-flight background tasks so the event loop
# does not garbage-collect them mid-run.
_background_tasks: set = set()


def _backtest_to_response(bt) -> BacktestResponse:
    return BacktestResponse(
        id=bt.id,
        strategy_id=bt.strategy_id,
        strategy_version=bt.strategy_version,
        params=json.loads(bt.params or "{}"),
        universe=json.loads(bt.universe or "[]"),
        start_date=bt.start_date,
        end_date=bt.end_date,
        rebalance_freq=bt.rebalance_freq,
        data_as_of=bt.data_as_of,
        status=bt.status,
        error=bt.error,
        created_at=str(bt.created_at),
        updated_at=str(bt.updated_at),
    )

@router.get("", response_model=list[BacktestResponse])
async def list_backtests_endpoint(limit: int = Query(50), db: AsyncSession = Depends(get_db)):
    backtests = await list_backtests(db, limit)
    return [_backtest_to_response(bt) for bt in backtests]

@router.post("", response_model=BacktestResponse)
async def create_backtest_endpoint(req: BacktestCreate, db: AsyncSession = Depends(get_db)):
    from app.models.strategy import Strategy
    result = await db.execute(select(Strategy).where(
        Strategy.id == req.strategy_id, Strategy.version == req.strategy_version
    ))
    strat = result.scalar_one_or_none()
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")

    bt = await create_backtest(
        db, strategy_id=req.strategy_id, strategy_version=req.strategy_version,
        params=req.params, universe=req.universe, start_date=req.start_date,
        end_date=req.end_date, rebalance_freq=req.rebalance_freq,
    )

    # Run in background task (non-blocking)
    import asyncio
    task = asyncio.create_task(_run_backtest_async(
        bt.id, strat.code, req.params, req.universe, req.start_date,
        req.end_date, req.rebalance_freq,
    ))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return _backtest_to_response(bt)

async def _run_backtest_async(backtest_id: str, strategy_code: str, params: dict, universe: list[str], start_date: str, end_date: str, rebalance_freq: str):
    from app.database import async_session_maker
    async with async_session_maker() as db:
        try:
            result = await run_backtest_in_subprocess(
                strategy_code=strategy_code,
                params=params,
                universe=universe,
                start_date=start_date,
                end_date=end_date,
                rebalance_freq=rebalance_freq,
                db_path="finkit.db",  # SQLite path relative to backend/
            )
            if result.get("status") == "ok":
                await update_backtest_status(db, backtest_id, "done", results=result)
            else:
                await update_backtest_status(
                    db, backtest_id, "failed", error=result.get("error", "backtest failed")
                )
        except Exception as e:
            await update_backtest_status(db, backtest_id, "failed", error=str(e))

@router.get("/{backtest_id}", response_model=BacktestResponse)
async def get_backtest_endpoint(backtest_id: str, db: AsyncSession = Depends(get_db)):
    bt = await get_backtest(db, backtest_id)
    if not bt:
        raise HTTPException(status_code=404, detail="Backtest not found")
    resp = _backtest_to_response(bt)
    if bt.results:
        resp.results = json.loads(bt.results)
    return resp

@router.get("/{backtest_id}/status")
async def get_backtest_status_endpoint(backtest_id: str, db: AsyncSession = Depends(get_db)):
    bt = await get_backtest(db, backtest_id)
    if not bt:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return {"status": bt.status, "error": bt.error}

@router.delete("/{backtest_id}")
async def delete_backtest_endpoint(backtest_id: str, db: AsyncSession = Depends(get_db)):
    ok = await delete_backtest(db, backtest_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return {"status": "ok"}
