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
    purchase_fee: float = 0.0              # 初始买入费用（计入摊薄成本）
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
    is_money_market: bool = False
    seven_day_yield: Optional[float] = None
    mmf_shares: Optional[float] = None
    total_value: float = 0.0
    profit_loss: float = 0.0
    ann_volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    ann_return: Optional[float] = None
    created_at: str
    updated_at: str
    locked: bool = False
    merged_into: Optional[str] = None
    merged_message: Optional[str] = None


# --------------------------------------------------------------------------- #
# Investment transactions (the ledger)
# --------------------------------------------------------------------------- #

class InvestmentTransactionCreate(BaseModel):
    event_type: Literal["buy", "sell", "dividend", "fee", "adjustment"]
    event_date: str
    quantity: float = Field(0.0, description="Signed: positive for buy, negative for sell")
    unit_price: float = 0.0
    fee: float = Field(0.0, description="Transaction fee (buy/sell); for standalone fee events this is the fee amount")
    notes: Optional[str] = None


class InvestmentTransactionUpdate(BaseModel):
    event_type: Optional[Literal["buy", "sell", "dividend", "fee", "adjustment"]] = None
    event_date: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    fee: Optional[float] = None
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
    fee: float = 0.0
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


# --------------------------------------------------------------------------- #
# Portfolio principal ledger (deposits / withdrawals)
# --------------------------------------------------------------------------- #

class CashFlowCreate(BaseModel):
    flow_type: Literal["deposit", "withdrawal"]
    amount: float = Field(..., gt=0)
    flow_date: str
    notes: Optional[str] = None


class CashFlowUpdate(BaseModel):
    flow_type: Optional[Literal["deposit", "withdrawal"]] = None
    amount: Optional[float] = Field(None, gt=0)
    flow_date: Optional[str] = None
    notes: Optional[str] = None


class CashFlowResponse(BaseModel):
    id: str
    user_id: str
    flow_type: str
    amount: float
    flow_date: str
    notes: Optional[str]
    created_at: str
    updated_at: str


# --------------------------------------------------------------------------- #
# Portfolio overview (summary cards) & symbol lookup
# --------------------------------------------------------------------------- #

class PortfolioOverview(BaseModel):
    total_deposits: float = 0.0           # 累计入金
    total_withdrawals: float = 0.0        # 累计出金
    old_principal: float = 0.0            # 入金 − 出金（旧口径，仅参考）
    principal: float = 0.0                # 本金 = 当前持仓摊薄成本（Σ买入+费用−卖出−分红，未平仓）
    current_market_value: float = 0.0     # 当前持仓市值（未平仓）
    idle_cash: float = 0.0                # 入出金净额 − 持仓成本（未投资现金推算）
    total_pnl: float = 0.0                # 整体盈亏（已落袋 + 当前浮盈浮亏）
    realized_pnl: float = 0.0             # 已落袋盈亏：已平仓产品的回款+分红 − 成本（不含记账 tab 分红）
    dividend_total: float = 0.0           # 分红：记账 tab 现金账户「投资」分类收入（不含投资月度盈亏流水）
    floating_pnl: float = 0.0             # 当前浮盈浮亏：未平仓产品的市值 − 持仓成本
    total_return_pct: float = 0.0         # 整体收益率
    xirr_annualized: Optional[float] = None   # 组合年化 XIRR（入金/出金 + 期末市值+闲置）
    days_held: int = 0                    # 自首笔入金以来的天数


class LookupCandidate(BaseModel):
    exchange: str                         # SH / SZ / FUND_CN / HK
    name: str
    price: float
    currency: str = "CNY"
    source: str


# --------------------------------------------------------------------------- #
# Closed positions (fully sold products: realized P&L + annualized return)
# --------------------------------------------------------------------------- #

class ClosedPosition(BaseModel):
    id: str
    name: str
    symbol: str = ""
    exchange: str = ""
    investment_type: str = ""
    purchase_date: str
    sell_date: str
    buy_amount: float                     # Σ buy.amount (cost basis before fees)
    proceeds: float                       # |Σ sell.amount + Σ dividend.amount|
    total_fee: float                      # Σ all fees (buy/sell/standalone)
    cost: float                           # buy_amount + total_fee
    realized_pnl: float                   # proceeds - cost
    return_rate: Optional[float] = None   # realized_pnl / cost
    days_held: int
    ann_return: Optional[float] = None     # (1 + return_rate)^(365/days_held) - 1
    ann_volatility: Optional[float] = None  # 持有期年化波动率（净值序列）
    sharpe_ratio: Optional[float] = None   # 持有期夏普（净值序列）


class ClosedPositionsResponse(BaseModel):
    positions: list[ClosedPosition]
    total_realized: float
    total_cost: float
    total_return_rate: Optional[float] = None
    count: int
