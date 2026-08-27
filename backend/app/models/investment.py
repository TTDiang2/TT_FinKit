from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean
from datetime import datetime
import uuid
from ..database import Base


class Investment(Base):
    """Investment product register — one row per tracked product (e.g. one stock/ETF/fund)."""
    __tablename__ = "investments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    investment_type = Column(String, nullable=False)  # stock/fund/bond/crypto/deposit/other
    underlying_asset_type = Column(String, default="")

    # Decision-support fields (P0): standardized asset class + benchmark proxy
    asset_class = Column(String, default="")           # 黄金/原油/美股/A股/油气/债券/货币/其他
    benchmark_symbol = Column(String, default="")       # 底层代理代码 e.g. 000300.SH
    benchmark_exchange = Column(String, default="")     # 代理市场 e.g. SH/US

    # Market identifiers (new) — used by price providers
    symbol = Column(String, default="", nullable=False)   # e.g. "600519", "AAPL", "BTC"
    exchange = Column(String, default="", nullable=False)  # SH/SZ/HK/US/CRYPTO/FUND_CN

    # Legacy snapshot fields (kept for backward compat; the authoritative truth is now
    # the investment_transactions ledger, but these still drive existing UIs/APIs)
    quantity = Column(Float, default=0.0)
    purchase_price = Column(Float, default=0.0)
    current_price = Column(Float, default=0.0)
    purchase_date = Column(String, nullable=False)
    sell_date = Column(String, nullable=True)

    notes = Column(Text, nullable=True)

    # Price provider bookkeeping
    last_price_update = Column(DateTime, nullable=True)

    # Money-market fund support: flagged on create/refresh; seven-day annualized
    # yield shown in the UI instead of unit price
    is_money_market = Column(Boolean, default=False)
    seven_day_yield = Column(Float, nullable=True)  # percent, e.g. 1.45

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def open_position_cond():
    """sell_date is stored as '' (empty string) by some legacy paths, so an
    IS NULL check alone misclassifies live holdings as closed."""
    return Investment.sell_date.is_(None) | (Investment.sell_date == "")
