from pydantic import BaseModel
from typing import Optional

class BacktestCreate(BaseModel):
    strategy_id: str
    strategy_version: int
    params: dict = {}
    universe: list[str] = []  # symbols; 空 + group_id 时由后端展开
    group_id: Optional[str] = None  # 单组合模式（保留兼容）
    group_ids: list[str] = []      # 多组合模式（新）
    all_pooled: bool = False       # True = 全部入池标的（无需前端传 18891 个代码）
    start_date: str  # YYYY-MM-DD
    end_date: str
    rebalance_freq: str = "monthly"


class BacktestGroupMeta(BaseModel):
    id: str
    name: str
    member_count: int


class BacktestResponse(BaseModel):
    id: str
    strategy_id: str
    strategy_name: Optional[str] = None
    strategy_version: int
    params: dict
    universe: list[str]
    universe_count: int = 0
    group_ids: list[str] = []
    group_names: list[BacktestGroupMeta] = []
    start_date: str
    end_date: str
    rebalance_freq: str
    data_as_of: str
    status: str
    progress: int = 0
    error: Optional[str] = None
    warning: Optional[str] = None
    results: Optional[dict] = None
    factor_keys: Optional[list[str]] = None
    created_at: str
    updated_at: str

class BacktestResult(BaseModel):
    nav_series: list[dict]  # [{"date": "...", "nav": 1.0, "portfolio_value": 100000}]
    metrics: dict  # {ann_return, ann_volatility, sharpe, max_drawdown, calmar, sortino, total_cost, turnover_annual}
    weight_history: list[dict]  # [{"date": "...", "weights": {"symbol": weight}}]
    rebalance_records: list[dict]  # [{"date": "...", "trades": [{"symbol": "", "side": "buy", "amount": 0, "fee": 0}]}]
    factor_view: dict  # {target_exposure, realized_exposure, contribution} — contribution keyed by symbol
    risk_view: dict  # {max_drawdown_series, var_95, cvar_95, risk_contrib}
