from pydantic import BaseModel, field_validator
from typing import Optional, List, Literal


class RedeemRule(BaseModel):
    """Structured redemption fee tier: holding days < ``days`` → ``fee_rate`` %.

    ``days`` = null is the catch-all fallback tier (must be last).
    """
    days: Optional[int] = None
    fee_rate: float = 0.0


def validate_redeem_rules(rules: List[RedeemRule]) -> List[RedeemRule]:
    """Validate: fee_rate >= 0, days ascending, exactly one null-days fallback at the end."""
    if not rules:
        return []
    prev_days = -1
    seen_fallback = False
    for r in rules:
        if r.fee_rate < 0:
            raise ValueError("赎回费率不能为负数")
        if r.days is None:
            seen_fallback = True
        else:
            if seen_fallback:
                raise ValueError("兜底档（天数为空）必须是最后一档")
            if r.days <= prev_days:
                raise ValueError("赎回费档位天数必须递增")
            prev_days = r.days
    return rules


class ResearchAssetCreate(BaseModel):
    symbol: str
    exchange: str = ""
    name: str = ""                      # empty → auto-complete via price source
    asset_type: str = "fund"
    category: str = ""
    is_money_market: bool = False
    notes: Optional[str] = None
    # Full watchlist form (parity with pool form)
    purchase_limit: Optional[float] = None
    mgmt_fee: Optional[float] = None
    custody_fee: Optional[float] = None
    purchase_fee: Optional[float] = None
    sales_service_fee: Optional[float] = None
    redeem_rules: List[RedeemRule] = []
    redeem_fee_note: str = ""
    min_purchase: Optional[float] = None
    redeem_t_days: Optional[int] = None
    liquidity_note: str = ""

    @field_validator("redeem_rules")
    @classmethod
    def _check_rules_create(cls, v):
        return validate_redeem_rules(v)


class ResearchAssetPool(BaseModel):
    """Pooling form: fee terms + optional corrections."""
    name: Optional[str] = None
    category: Optional[str] = None
    purchase_limit: Optional[float] = None
    mgmt_fee: Optional[float] = None
    custody_fee: Optional[float] = None
    purchase_fee: Optional[float] = None
    sales_service_fee: Optional[float] = None     # %/year (C-class shares)
    redeem_rules: List[RedeemRule] = []
    redeem_fee_note: str = ""                     # display text; auto-generated if empty
    min_purchase: Optional[float] = None
    redeem_t_days: Optional[int] = None
    liquidity_note: str = ""
    data_quality: str = ""
    is_money_market: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("redeem_rules")
    @classmethod
    def _check_rules(cls, v):
        return validate_redeem_rules(v)


class ResearchAssetUpdate(BaseModel):
    name: Optional[str] = None
    asset_type: Optional[str] = None
    category: Optional[str] = None
    exchange: Optional[str] = None
    mgmt_fee: Optional[float] = None
    custody_fee: Optional[float] = None
    purchase_fee: Optional[float] = None
    sales_service_fee: Optional[float] = None
    redeem_rules: Optional[List[RedeemRule]] = None
    redeem_fee_note: Optional[str] = None
    min_purchase: Optional[float] = None
    redeem_t_days: Optional[int] = None
    liquidity_note: Optional[str] = None
    data_quality: Optional[str] = None
    purchase_limit: Optional[float] = None
    is_money_market: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("redeem_rules")
    @classmethod
    def _check_rules(cls, v):
        return validate_redeem_rules(v) if v is not None else v


class ResearchAssetIndicators(BaseModel):
    points: int = 0
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    latest_close: Optional[float] = None
    ret_1m: Optional[float] = None      # fractional, e.g. 0.0235
    ret_1y: Optional[float] = None
    # 全样本指标（含早期较差数据，可能与近 1Y 偏差较大）
    ann_return: Optional[float] = None
    ann_volatility: Optional[float] = None
    sharpe: Optional[float] = None
    # 近 1Y 滚动窗口指标，与 ret_1y 同口径
    ann_return_1y: Optional[float] = None
    ann_volatility_1y: Optional[float] = None
    sharpe_1y: Optional[float] = None
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
    sales_service_fee: Optional[float] = None
    redeem_rules: List[RedeemRule] = []
    redeem_fee_note: str = ""
    min_purchase: Optional[float] = None
    redeem_t_days: Optional[int] = None
    liquidity_note: str = ""
    data_quality: str = ""
    is_money_market: bool
    notes: Optional[str] = None
    purchase_limit: Optional[float] = None
    purchase_status: str = ""
    fund_kind: str = ""
    asset_class: str = ""
    region: str = ""
    auto_tags: List[str] = []
    profile_synced_at: Optional[str] = None
    indicators: ResearchAssetIndicators = ResearchAssetIndicators()


class ResearchPricePoint(BaseModel):
    date: str
    close: float
    nav: Optional[float] = None
    acc_nav: Optional[float] = None


class NavPoint(BaseModel):
    date: str
    close: float
    ma20: Optional[float] = None
    ma60: Optional[float] = None


class BenchmarkSeries(BaseModel):
    name: str
    symbol: str
    exchange: str
    series: List[dict] = []          # [{"date": "...", "close": 123.4}]


class NavHistoryDetail(BaseModel):
    series: List[NavPoint]
    benchmark: Optional[BenchmarkSeries] = None
    source: str = ""


class SyncResult(BaseModel):
    asset_id: str
    rows: int = 0
    source: str = ""
    begin: str = ""
    end: str = ""
    error: Optional[str] = None


class WatchlistImportRequest(BaseModel):
    """天天基金批量导入自选：纯代码列表，信息全部自动拉取。"""
    symbols: List[str]
    with_fees: bool = True        # false=跳过逐只费率页(全量导入用)
    sync_prices: bool = True      # false=不触发后台净值同步


class WatchlistImportItem(BaseModel):
    symbol: str
    name: str = ""
    status: Literal["added", "exists", "failed"]
    fund_type: str = ""
    daily_limit: Optional[float] = None
    error: Optional[str] = None


class BatchPoolRejected(BaseModel):
    asset_id: str
    symbol: str
    name: str
    reasons: List[str] = []


class BatchPoolResponse(BaseModel):
    pooled: List[ResearchAssetResponse] = []
    rejected: List[BatchPoolRejected] = []


class AuditPooledResult(BaseModel):
    asset_id: str
    symbol: str
    name: str
    status: Literal["kept", "demoted", "failed"]
    refreshed_fields: List[str] = []
    reasons: List[str] = []
    error: Optional[str] = None


class BatchPoolRequest(BaseModel):
    ids: List[str]
    apply_defaults: bool = True       # true=入池时沿用导入/自选阶段存的费率限额


class BatchRefreshProfilesRequest(BaseModel):
    ids: Optional[List[str]] = None   # None → 全部基金型标的


class ProfileRefreshResult(BaseModel):
    asset_id: str
    symbol: str
    name: str
    status: Literal["updated", "partial", "failed", "skipped"] = "updated"
    changed_fields: List[str] = []
    tags_rebuilt: bool = False
    error: Optional[str] = None

class ResearchGroupCreate(BaseModel):
    name: str
    note: str = ""
    asset_ids: List[str] = []


class ResearchGroupUpdate(BaseModel):
    name: Optional[str] = None
    note: Optional[str] = None
    asset_ids: Optional[List[str]] = None   # None=不动，[]/列表=整体替换


class ResearchGroupResponse(BaseModel):
    id: str
    name: str
    note: str
    asset_ids: List[str] = []
