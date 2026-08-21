from pydantic import BaseModel
from typing import Optional, List, Literal


class ResearchAssetCreate(BaseModel):
    symbol: str
    exchange: str = ""
    name: str = ""                      # empty → auto-complete via price source
    asset_type: str = "fund"
    category: str = ""
    is_money_market: bool = False
    notes: Optional[str] = None


class ResearchAssetPool(BaseModel):
    """Pooling form: fee terms + optional corrections."""
    name: Optional[str] = None
    category: Optional[str] = None
    mgmt_fee: Optional[float] = None
    custody_fee: Optional[float] = None
    purchase_fee: Optional[float] = None
    redeem_fee_note: str = ""
    min_purchase: Optional[float] = None
    redeem_t_days: Optional[int] = None
    liquidity_note: str = ""
    data_quality: str = ""
    is_money_market: Optional[bool] = None
    notes: Optional[str] = None


class ResearchAssetUpdate(BaseModel):
    name: Optional[str] = None
    asset_type: Optional[str] = None
    category: Optional[str] = None
    exchange: Optional[str] = None
    mgmt_fee: Optional[float] = None
    custody_fee: Optional[float] = None
    purchase_fee: Optional[float] = None
    redeem_fee_note: Optional[str] = None
    min_purchase: Optional[float] = None
    redeem_t_days: Optional[int] = None
    liquidity_note: Optional[str] = None
    data_quality: Optional[str] = None
    is_money_market: Optional[bool] = None
    notes: Optional[str] = None


class ResearchAssetIndicators(BaseModel):
    points: int = 0
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    latest_close: Optional[float] = None
    ret_1m: Optional[float] = None      # fractional, e.g. 0.0235
    ret_1y: Optional[float] = None
    ann_return: Optional[float] = None
    ann_volatility: Optional[float] = None
    sharpe: Optional[float] = None
    max_drawdown: Optional[float] = None  # fractional, e.g. -0.2130


class ResearchAssetPriceStatus(BaseModel):
    asset_id: str
    symbol: str
    name: str
    status: str
    rows: int = 0
    last_date: Optional[str] = None
    last_sync: Optional[str] = None      # ISO datetime of latest price row update
    source: Optional[str] = None
    lag_days: Optional[int] = None       # calendar days behind today


class ResearchAssetResponse(BaseModel):
    id: str
    symbol: str
    exchange: str
    name: str
    asset_type: str
    category: str
    status: Literal["watchlist", "pooled"]
    mgmt_fee: Optional[float] = None
    custody_fee: Optional[float] = None
    purchase_fee: Optional[float] = None
    redeem_fee_note: str = ""
    min_purchase: Optional[float] = None
    redeem_t_days: Optional[int] = None
    liquidity_note: str = ""
    data_quality: str = ""
    is_money_market: bool
    notes: Optional[str] = None
    indicators: ResearchAssetIndicators = ResearchAssetIndicators()


class ResearchPricePoint(BaseModel):
    date: str
    close: float
    nav: Optional[float] = None
    acc_nav: Optional[float] = None


class SyncResult(BaseModel):
    asset_id: str
    rows: int = 0
    source: str = ""
    begin: str = ""
    end: str = ""
    error: Optional[str] = None
