from pydantic import BaseModel
from typing import Optional

class StrategyCreate(BaseModel):
    name: str
    description: str = ""
    code: str
    params_schema: dict = {}
    rebalance_freq: str = "monthly"
    folder: str = ""
    source_file: Optional[str] = None
    factor_keys: Optional[list[str]] = None

class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None
    params_schema: Optional[dict] = None
    rebalance_freq: Optional[str] = None

class StrategyResponse(BaseModel):
    id: str
    name: str
    description: str
    version: int
    params_schema: dict
    rebalance_freq: str
    is_builtin: bool
    folder: str = ""
    factor_keys: list[str] = []
    source_file: Optional[str] = None
    activated_at: Optional[str] = None
    latest_backtest: Optional[dict] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

class StrategyImportResult(BaseModel):
    strategy_id: str
    version: int
    status: str  # imported / updated
    error: Optional[str] = None

class StrategyParseRequest(BaseModel):
    code: str

class StrategyMoveRequest(BaseModel):
    folder: str

class ActiveStrategySet(BaseModel):
    strategy_id: str
    version: int
    params: dict = {}

class ActiveStrategyResponse(BaseModel):
    strategy_id: str
    version: int
    params: dict
    name: str
    description: str
    rebalance_freq: str

    class Config:
        from_attributes = True
