from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas.signal import SignalResponse, SignalRunResult
from ..services.signal_service import (
    get_active_strategy, get_latest_signal, list_signals, get_signal, save_signal
)
from ..services.signal_engine import generate_signal
import json
from datetime import date

router = APIRouter(prefix="/api/signals", tags=["signals"])

def _signal_to_response(s) -> SignalResponse:
    return SignalResponse(
        id=s.id,
        strategy_id=s.strategy_id,
        strategy_version=s.strategy_version,
        run_date=s.run_date,
        as_of_date=s.as_of_date,
        next_rebalance_date=s.next_rebalance_date,
        target_weights=json.loads(s.target_weights or "{}"),
        risk_status=json.loads(s.risk_status) if s.risk_status else None,
        backtest_id=s.backtest_id,
        created_at=str(s.created_at),
    )

@router.post("/run", response_model=SignalRunResult)
async def run_signal_endpoint(db: AsyncSession = Depends(get_db)):
    """Run the active strategy to generate a new signal."""
    # Get active strategy (latest imported or the one set as active)
    # For now: use the most recently created strategy
    strat = await get_active_strategy(db)
    if not strat:
        raise HTTPException(status_code=404, detail="No active strategy found. Please import or activate a strategy first.")

    # Load strategy params from active (or use defaults)
    active_params = {}

    # Get universe from pooled research assets (by SYMBOL, matching strategy API)
    from app.models.research_asset import ResearchAsset
    result = await db.execute(select(ResearchAsset).where(ResearchAsset.status == "pooled"))
    assets = list(result.scalars().all())
    universe = [a.symbol for a in assets]

    try:
        signal_result = generate_signal(
            strategy_code=strat.code,
            params=active_params,
            universe=universe,
            rebalance_freq=strat.rebalance_freq or "monthly",
        )
    except Exception as e:
        return SignalRunResult(signal_id="", status="error", error=str(e))

    if signal_result["status"] != "ok":
        return SignalRunResult(signal_id="", status="error", error=signal_result.get("error"))

    # Save signal
    sig = await save_signal(
        db,
        strategy_id=strat.id,
        strategy_version=strat.version,
        run_date=date.today().isoformat(),
        as_of_date=signal_result["as_of_date"],
        next_rebalance_date=signal_result["next_rebalance_date"],
        target_weights=signal_result["target_weights"],
        risk_status=signal_result["risk_status"],
    )

    return SignalRunResult(signal_id=sig.id, status="ok")

@router.get("/current", response_model=SignalResponse | None)
async def get_current_signal_endpoint(db: AsyncSession = Depends(get_db)):
    sig = await get_latest_signal(db)
    if not sig:
        return None
    return _signal_to_response(sig)

@router.get("", response_model=list[SignalResponse])
async def list_signals_endpoint(limit: int = Query(50), db: AsyncSession = Depends(get_db)):
    signals = await list_signals(db, limit)
    return [_signal_to_response(s) for s in signals]

@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal_endpoint(signal_id: str, db: AsyncSession = Depends(get_db)):
    sig = await get_signal(db, signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _signal_to_response(sig)
