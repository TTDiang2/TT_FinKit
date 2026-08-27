from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, UniqueConstraint
from datetime import datetime
import uuid
from ..database import Base


class ResearchAsset(Base):
    """Research asset pool — one row per tracked research instrument (watchlist or pooled).

    Separate from the ``investments`` ledger (actual holdings): the pool is the
    data foundation for factor exposure / backtest / signal modules, mapped to
    holdings by (symbol, exchange).
    """
    __tablename__ = "research_assets"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_research_asset_user_symbol"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String, nullable=False)              # e.g. "161005", "000300"
    exchange = Column(String, default="")                # FUND_CN / SH / SZ / US
    name = Column(String, nullable=False)
    asset_type = Column(String, default="fund")          # fund/stock/index/gold/other
    category = Column(String, default="")                # user-defined tag e.g. 核心-宽基
    status = Column(String, default="watchlist")         # watchlist / pooled

    # Pooling fee terms (filled on pool action)
    mgmt_fee = Column(Float, nullable=True)              # percent per year
    custody_fee = Column(Float, nullable=True)           # percent per year
    purchase_fee = Column(Float, nullable=True)          # percent per purchase
    sales_service_fee = Column(Float, nullable=True)     # percent per year (C-class shares)
    redeem_fee_note = Column(String, default="")           # e.g. <7 days 1.5%, >30 days 0
    redeem_rules = Column(Text, default="[]")              # structured JSON: [{"days":7,"fee_rate":1.5},{"days":null,"fee_rate":0}]
    min_purchase = Column(Float, nullable=True)           # yuan
    redeem_t_days = Column(Integer, nullable=True)        # redemption arrival trading days
    liquidity_note = Column(String, default="")

    data_quality = Column(String, default="")             # good/fair/poor (manual annotation)
    is_money_market = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

    # Purchase quota + multi-dimension auto classification (from eastmoney profile)
    purchase_limit = Column(Float, nullable=True)         # 日申购限额(元); None=未设置/不限
    fund_kind = Column(String, default="")                # ETF/ETF联接/LOF/FOF/指数跟踪/指数增强/主动管理/货币
    asset_class = Column(String, default="")              # 偏股/偏债/混合/商品-黄金/另类/货币
    region = Column(String, default="")                   # 境内/QDII-美国/QDII-香港/QDII-新兴市场/QDII-全球/QDII-其他
    auto_tags = Column(Text, default="[]")                # JSON list — 持仓推断主题标签 e.g. ["重仓黄金","科技"]
    profile_synced_at = Column(DateTime, nullable=True)   # 最近一次天天基金 profile 拉取时间

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResearchAssetPrice(Base):
    """Local price warehouse for research assets.

    ``close`` is the unified series fed to indicator/factor computations:
    adjusted NAV for funds (source-dependent), or market close for indexes.
    Money-market funds store the income-converted equivalent series and the
    asset is flagged ``is_money_market`` so vol/sharpe are skipped downstream.
    """
    __tablename__ = "research_prices"
    __table_args__ = (UniqueConstraint("asset_id", "date", name="uq_research_price_asset_date"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String, ForeignKey("research_assets.id", ondelete="CASCADE"), nullable=False)
    date = Column(String, nullable=False)                # YYYY-MM-DD
    nav = Column(Float, nullable=True)                   # unit NAV; None for money market
    acc_nav = Column(Float, nullable=True)               # cumulative NAV (eastmoney)
    close = Column(Float, nullable=False)                # unified series input
    source = Column(String, default="")                   # ifind/eastmoney/tencent/akshare
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
