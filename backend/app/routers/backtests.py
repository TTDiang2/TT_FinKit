from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas.backtest import BacktestCreate, BacktestResponse, BacktestResult
from ..services.backtest_service import (
    create_backtest, get_backtest, list_backtests, update_backtest_status, delete_backtest
)
from ..services.backtest_engine import run_backtest_in_subprocess, load_benchmark_series
import json

router = APIRouter(prefix="/api/backtests", tags=["backtests"])

# Keep strong references to in-flight background tasks so the event loop
# does not garbage-collect them mid-run.
_background_tasks: set = set()


def _backtest_to_response(bt, strategy_name: str | None = None, factor_keys: list[str] | None = None) -> BacktestResponse:
    resp = BacktestResponse(
        id=bt.id,
        strategy_id=bt.strategy_id,
        strategy_name=strategy_name,
        strategy_version=bt.strategy_version,
        params=json.loads(bt.params or "{}"),
        universe=json.loads(bt.universe or "[]"),
        start_date=bt.start_date,
        end_date=bt.end_date,
        rebalance_freq=bt.rebalance_freq,
        data_as_of=bt.data_as_of,
        status=bt.status,
        error=bt.error,
        results=json.loads(bt.results) if bt.results else None,
        factor_keys=factor_keys,
        created_at=str(bt.created_at),
        updated_at=str(bt.updated_at),
    )
    return resp

@router.get("", response_model=list[BacktestResponse])
async def list_backtests_endpoint(limit: int = Query(50), db: AsyncSession = Depends(get_db)):
    backtests = await list_backtests(db, limit)
    # Batch-load strategy names + factor_keys for all backtests
    strat_ids = list({bt.strategy_id for bt in backtests})
    strats = {}
    if strat_ids:
        from app.models.strategy import Strategy
        rows = (await db.execute(
            select(Strategy.id, Strategy.name, Strategy.factor_keys)
            .where(Strategy.id.in_(strat_ids))
        )).all()
        strats = {r[0]: (r[1], json.loads(r[2]) if r[2] else None) for r in rows}
    out = []
    for bt in backtests:
        name, fkeys = strats.get(bt.strategy_id, (None, None))
        out.append(_backtest_to_response(bt, strategy_name=name, factor_keys=fkeys))
    return out

@router.post("", response_model=BacktestResponse)
async def create_backtest_endpoint(req: BacktestCreate, db: AsyncSession = Depends(get_db)):
    from app.models.strategy import Strategy
    from app.models.research_asset import ResearchAsset
    result = await db.execute(select(Strategy).where(
        Strategy.id == req.strategy_id, Strategy.version == req.strategy_version
    ))
    strat = result.scalar_one_or_none()
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Validate universe: entries must be existing asset SYMBOLS
    universe = list(req.universe)
    if not universe and req.group_id:
        from app.models.research_group import ResearchGroupMember
        rows = await db.execute(
            select(ResearchAsset.symbol)
            .join(ResearchGroupMember, ResearchGroupMember.asset_id == ResearchAsset.id)
            .where(ResearchGroupMember.group_id == req.group_id,
                   ResearchAsset.status == "pooled")
        )
        universe = [r[0] for r in rows.all()]
    if not universe:
        raise HTTPException(status_code=400, detail="universe 不能为空：请至少选择一个标的")
    asset_res = await db.execute(
        select(ResearchAsset.symbol).where(ResearchAsset.symbol.in_(req.universe))
    )
    known = {r[0] for r in asset_res.all()}
    unknown = [s for s in req.universe if s not in known]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"标的代码不存在或未入池：{', '.join(unknown)}（universe 请使用标的代码如 000300，而非内部 id）",
        )

    bt = await create_backtest(
        db, strategy_id=req.strategy_id, strategy_version=req.strategy_version,
        params=req.params, universe=universe, start_date=req.start_date,
        end_date=req.end_date, rebalance_freq=req.rebalance_freq,
    )

    # Run in background task (non-blocking)
    import asyncio
    task = asyncio.create_task(_run_backtest_async(
        bt.id, strat.code, req.params, universe, req.start_date,
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

@router.get("/benchmark")
async def get_benchmark(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
):
    """CSI300 benchmark series for a date range.

    Lets OLD backtest results (created before benchmark was embedded) render
    the excess-return / rolling-alpha-beta charts without a re-run.
    """
    bench = load_benchmark_series("finkit.db", start, end)
    if not bench:
        raise HTTPException(status_code=404, detail="基准因子(equity)无该区间数据")
    return bench


@router.get("/{backtest_id}", response_model=BacktestResponse)
async def get_backtest_endpoint(backtest_id: str, db: AsyncSession = Depends(get_db)):
    bt = await get_backtest(db, backtest_id)
    if not bt:
        raise HTTPException(status_code=404, detail="Backtest not found")
    # Fetch strategy name + factor_keys for detail page
    from app.models.strategy import Strategy
    strat = (await db.execute(
        select(Strategy.name, Strategy.factor_keys).where(Strategy.id == bt.strategy_id)
    )).first()
    sname = strat[0] if strat else None
    fkeys = json.loads(strat[1]) if strat and strat[1] else None
    return _backtest_to_response(bt, strategy_name=sname, factor_keys=fkeys)

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
