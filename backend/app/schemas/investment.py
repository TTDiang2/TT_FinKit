from pydantic import BaseModel, Field
from typing import Optional, Literal


# --------------------------------------------------------------------------- #
# Investment (the product register row)
# --------------------------------------------------------------------------- #

class InvestmentCreate(BaseModel):
    name: str
    investment_type: Literal["stock", "fund", "bond", "crypto", "deposit", "other"] = "stock"
    underlying_asset_type: str = ""
    asset_class: str = ""               # 黄金/原油/美股/A股/油气/债券/货币/其他
    benchmark_symbol: str = ""
    benchmark_exchange: str = ""
    symbol: str = ""
    exchange: str = ""              # SH/SZ/HK/US/CRYPTO/FUND_CN
    quantity: float = 0.0
    purchase_price: float = 0.0
    current_price: float = 0.0
    purchase_date: str
    sell_date: Optional[str] = None
    notes: Optional[str] = None


class InvestmentUpdate(BaseModel):
    name: Optional[str] = None
    investment_type: Optional[str] = None
    underlying_asset_type: Optional[str] = None
    asset_class: Optional[str] = None
    benchmark_symbol: Optional[str] = None
    benchmark_exchange: Optional[str] = None
    symbol: Optional[str] = None
    exchange: Optional[str] = None
    quantity: Optional[float] = None
    purchase_price: Optional[float] = None
    current_price: Optional[float] = None
    purchase_date: Optional[str] = None
    sell_date: Optional[str] = None
    notes: Optional[str] = None


class InvestmentResponse(BaseModel):
    id: str
    user_id: str
    name: str
    investment_type: str
    underlying_asset_type: str = ""
    asset_class: str = ""
    benchmark_symbol: str = ""
    benchmark_exchange: str = ""
    symbol: str = ""
    exchange: str = ""
    quantity: float
    purchase_price: float
    current_price: float
    purchase_date: str
    sell_date: Optional[str]
    notes: Optional[str]
    last_price_update: Optional[str] = None
    total_value: float = 0.0
    profit_loss: float = 0.0
    created_at: str
    updated_at: str


# --------------------------------------------------------------------------- #
# Investment transactions (the ledger)
# --------------------------------------------------------------------------- #

class InvestmentTransactionCreate(BaseModel):
    event_type: Literal["buy", "sell", "dividend", "fee", "adjustment"]
    event_date: str
    quantity: float = Field(0.0, description="Signed: positive for buy, negative for sell")
    unit_price: float = 0.0
    notes: Optional[str] = None


class InvestmentTransactionUpdate(BaseModel):
    event_type: Optional[Literal["buy", "sell", "dividend", "fee", "adjustment"]] = None
    event_date: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    notes: Optional[str] = None


class InvestmentTransactionResponse(BaseModel):
    id: str
    investment_id: str
    user_id: str
    event_type: str
    event_date: str
    quantity: float
    unit_price: float
    amount: float
    notes: Optional[str]
    created_at: str
    updated_at: str


# --------------------------------------------------------------------------- #
# Stats / metrics
# --------------------------------------------------------------------------- #

class InvestmentMetrics(BaseModel):
    total_invested: float = 0.0       # cumulative net buy amount
    total_redeemed: float = 0.0       # cumulative sell proceeds
    total_dividends: float = 0.0
    total_fees: float = 0.0
    current_value: float = 0.0
    total_pnl: float = 0.0            # current_value + total_redeemed + dividends - total_invested - fees
    total_return_pct: float = 0.0     # total_pnl / total_invested * 100
    xirr_annualized: Optional[float] = None   # decimal, e.g. 0.155 = 15.5%
    last_1y_xirr: Optional[float] = None
    last_1m_xirr: Optional[float] = None
    days_held: int = 0
    last_event_date: Optional[str] = None


class PortfolioMetrics(BaseModel):
    total_invested: float
    total_redeemed: float
    total_dividends: float
    total_fees: float
    current_value: float
    total_pnl: float
    total_return_pct: float
    xirr_annualized: Optional[float]
    last_1y_xirr: Optional[float]
    last_1m_xirr: Optional[float]
    days_held: int
    per_product: dict[str, InvestmentMetrics] = {}


# --------------------------------------------------------------------------- #
# Migration (amount-only holdings → share-based ledger via iFinD NAV reverse-calc)
# --------------------------------------------------------------------------- #

class MigrationEntry(BaseModel):
    """One user-recorded historical purchase. Flows: input(date,amount) →
    preview(backend fills nav+shares) → commit(frontend echoes nav+shares back)."""
    date: str                             # YYYY-MM-DD 投资日
    amount: float                         # 投入金额（元）
    nav: Optional[float] = None           # 单位净值（preview 后端填 / commit 前端回传）
    shares: Optional[float] = None        # 反推份额（同上）
    status: str = "ok"                    # ok / no_nav / invalid


class MigrationRequest(BaseModel):
    entries: list[MigrationEntry]
    commit: bool = False                  # false=仅预览，true=落库生成 buy 流水
    symbol: str = ""                      # 可选，覆盖 investment.symbol（6位基金代码）


class MigrationResponse(BaseModel):
    results: list[MigrationEntry]
    preview: bool = True
    committed: int = 0                    # commit 模式下实际入库条数
