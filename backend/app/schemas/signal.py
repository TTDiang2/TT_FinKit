from pydantic import BaseModel
from typing import Optional

class SignalResponse(BaseModel):
    id: str
    strategy_id: str
    strategy_version: int
    run_date: str
    as_of_date: str
    next_rebalance_date: Optional[str] = None
    target_weights: dict  # {asset_id: weight}
    risk_status: Optional[dict] = None
    backtest_id: Optional[str] = None
    created_at: str

class SignalRunResult(BaseModel):
    signal_id: str
    status: str  # ok / error
    error: Optional[str] = None
