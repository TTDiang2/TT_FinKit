from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas.strategy import (
    StrategyCreate, StrategyResponse,
    StrategyImportResult, ActiveStrategySet, ActiveStrategyResponse,
)
from ..services.strategy_service import (
    list_strategies, get_strategy, import_strategy,
    delete_strategy_version, validate_strategy_code,
)
import json

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

def _strategy_to_response(s) -> StrategyResponse:
    return StrategyResponse(
        id=s.id, name=s.name, description=s.description,
        version=s.version,
        params_schema=json.loads(s.params_schema or "{}"),
        rebalance_freq=s.rebalance_freq,
        is_builtin=s.is_builtin,
        created_at=str(s.created_at), updated_at=str(s.updated_at),
    )

@router.get("", response_model=list[StrategyResponse])
async def list_strategies_endpoint(db: AsyncSession = Depends(get_db)):
    """List all strategies. Returns latest version per strategy name."""
    strategies = await list_strategies(db)
    # deduplicate by name, keep latest version
    seen = {}
    for s in strategies:
        if s.name not in seen:
            seen[s.name] = s
    return [_strategy_to_response(s) for s in seen.values()]

@router.post("/import", response_model=StrategyImportResult)
async def import_strategy_endpoint(req: StrategyCreate, db: AsyncSession = Depends(get_db)):
    valid, msg = validate_strategy_code(req.code)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid strategy code: {msg}")

    strat, status = await import_strategy(
        db, name=req.name, code=req.code, description=req.description,
        params_schema=req.params_schema, rebalance_freq=req.rebalance_freq,
    )
    return StrategyImportResult(strategy_id=strat.id, version=strat.version, status=status)

# In-memory active strategy (per-user in production would go to user_settings table)
_active_strategies: dict[str, ActiveStrategySet] = {}

@router.post("/active")
async def set_active_strategy(req: ActiveStrategySet, db: AsyncSession = Depends(get_db)):
    """Set the active strategy for the current user."""
    strat = await get_strategy(db, req.strategy_id, req.version)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")
    _active_strategies["default"] = req
    return {"status": "ok"}

@router.get("/active", response_model=ActiveStrategyResponse | None)
async def get_active_strategy(db: AsyncSession = Depends(get_db)):
    active = _active_strategies.get("default")
    if not active:
        return None
    strat = await get_strategy(db, active.strategy_id, active.version)
    if not strat:
        return None
    return ActiveStrategyResponse(
        strategy_id=strat.id, version=strat.version, params=active.params,
        name=strat.name, description=strat.description,
        rebalance_freq=strat.rebalance_freq,
    )

@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy_endpoint(
    strategy_id: str,
    version: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    strat = await get_strategy(db, strategy_id, version)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return _strategy_to_response(strat)

@router.delete("/{strategy_id}/{version}")
async def delete_strategy_version_endpoint(
    strategy_id: str, version: int,
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_strategy_version(db, strategy_id, version)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot delete this version")
    return {"status": "ok"}
