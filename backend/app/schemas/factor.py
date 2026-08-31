from pydantic import BaseModel
from typing import Optional, List, Literal


class FactorConfig(BaseModel):
    """Structured factor definition consumed by factor_store.

    proxy: one instrument's daily return is the factor return.
    spread: long daily return minus short daily return (style factors).
    """
    type: Literal["proxy", "spread"]
    symbol: Optional[str] = None
    exchange: str = "SH"
    long: Optional["FactorConfig"] = None
    short: Optional["FactorConfig"] = None


FactorConfig.model_rebuild()


class FactorCreate(BaseModel):
    name: str
    category: Literal["asset_class", "style", "macro", "custom"] = "custom"
    definition: str
    config: FactorConfig
    data_source: str = ""
    is_market: bool = False


class FactorUpdate(BaseModel):
    definition: Optional[str] = None
    config: Optional[FactorConfig] = None     # config change bumps version
    active: Optional[bool] = None
    is_market: Optional[bool] = None


class FactorStat(BaseModel):
    latest_value: Optional[float] = None      # latest kind=return value
    latest_level: Optional[float] = None
    latest_date: Optional[str] = None
    rows: int = 0


class FactorResponse(BaseModel):
    id: str
    name: str
    key: str = ""
    category: str
    definition: str
    code: Optional[str] = None
    data_source: str = ""
    frequency: str = "daily"
    proxy_symbol: str = ""
    config: Optional[FactorConfig] = None
    is_market: bool = False
    active: bool = True
    version: int = 1
    data_status: str = "ok"
    stats: FactorStat = FactorStat()


class FactorValuePoint(BaseModel):
    date: str
    value: float


class FactorDetail(FactorResponse):
    level_series: List[FactorValuePoint] = []


class FactorSyncResult(BaseModel):
    factor_id: str
    name: str = ""
    rows: int = 0                              # return-kind rows written
    source: str = ""
    begin: str = ""
    end: str = ""
    error: Optional[str] = None


class ExposureCell(BaseModel):
    beta: float
    t_stat: Optional[float] = None
    significant: bool = False                  # |t| > 1.5 (methodology §8)


class AssetExposureRow(BaseModel):
    asset_id: str
    asset_name: str
    symbol: str
    is_money_market: bool = False
    r2: Optional[float] = None
    method: Optional[str] = None
    n_samples: Optional[int] = None
    cells: dict[str, ExposureCell] = {}        # factor_id -> cell


class ExposureMatrix(BaseModel):
    as_of: Optional[str] = None
    factors: List[FactorResponse] = []
    assets: List[AssetExposureRow] = []
    total_assets: Optional[int] = None  # 筛选口径下的总资产数（分页用）


class ExposureHistoryPoint(BaseModel):
    as_of_date: str
    factor_id: str
    factor_name: str
    beta: float
    t_stat: Optional[float] = None
    r2: float = 0.0
    method: str = ""


class ContributionItem(BaseModel):
    factor_id: str
    factor_name: str
    beta: float
    contribution: Optional[float] = None       # return view
    risk_contribution: Optional[float] = None  # risk view
    sigma_ann: Optional[float] = None          # risk view


class ContributionResult(BaseModel):
    view: Literal["return", "risk"]
    asset_id: str
    asset_name: str
    start: str
    end: str
    as_of: Optional[str] = None
    n_days: Optional[int] = None
    total_return: Optional[float] = None
    alpha: Optional[float] = None
    sum_contributions: Optional[float] = None
    identity_residual: Optional[float] = None
    explained_vol: Optional[float] = None
    items: List[ContributionItem] = []


class AgentFactorCandidate(BaseModel):
    """LLM-generated factor candidate — confirm flow stores it verbatim."""
    name: str
    category: Literal["asset_class", "style", "macro", "custom"] = "custom"
    definition: str
    config: FactorConfig


class AgentGenerateRequest(BaseModel):
    prompt: str


class AgentPreviewRequest(BaseModel):
    candidate: AgentFactorCandidate


class AgentPreviewResult(BaseModel):
    ok: bool
    sample_days: int = 0
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    latest_level: Optional[float] = None
    latest_return: Optional[float] = None
    source: str = ""
    error: Optional[str] = None
