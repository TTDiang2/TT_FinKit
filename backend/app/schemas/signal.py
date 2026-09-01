from pydantic import BaseModel
from typing import Optional

class SignalResponse(BaseModel):
    id: str
    strategy_id: str
    strategy_version: int
    strategy_name: Optional[str] = None  # 便于前端展示信号来自哪个策略
    strategy_version_note: Optional[str] = None  # 策略作者声明的语义版本（如 v3.0-balanced-50-45）
    run_date: str
    as_of_date: str
    next_rebalance_date: Optional[str] = None
    target_weights: dict  # {symbol: weight}
    weights_detail: Optional[list] = None  # [{symbol, name, weight}] 按权重降序
    risk_status: Optional[dict] = None
    backtest_id: Optional[str] = None
    created_at: str

class SignalRunResult(BaseModel):
    signal_id: str
    status: str  # ok / error
    error: Optional[str] = None
