from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, UniqueConstraint
from datetime import datetime
import uuid
from ..database import Base


class Factor(Base):
    """Factor library — one row per factor definition (preset or user/Agent built).

    ``config`` is the structured definition consumed by factor_store:
    {"type":"proxy","symbol":"000300","exchange":"SH"} or
    {"type":"spread","long":{...},"short":{...}}.  ``code`` (executable data
    pipeline source) is reserved for the Phase 7 Agent orchestration and stays
    NULL in Phase 2.  ``is_market`` marks the single equity-market factor used
    for money-market funds (ADR-10: mmf assets regress against market only).
    """
    __tablename__ = "factors"
    __table_args__ = (UniqueConstraint("name", name="uq_factor_name"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)                  # e.g. 权益(沪深300)
    category = Column(String, nullable=False)              # asset_class/style/macro/custom
    definition = Column(Text, nullable=False)              # natural-language definition
    code = Column(Text, nullable=True)                     # reserved for Agent pipeline code
    data_source = Column(String, default="")               # ifind/eastmoney/...
    frequency = Column(String, default="daily")
    proxy_symbol = Column(String, default="")              # primary proxy symbol for display
    config = Column(Text, nullable=True)                   # JSON: proxy/spread structured definition
    is_market = Column(Boolean, default=False)
    active = Column(Boolean, default=True)                 # deactivated factors keep history
    version = Column(Integer, default=1)                   # bumped on definition change
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FactorValue(Base):
    """Factor value series.  ``kind='return'`` rows hold daily returns (the
    regression input) and ``kind='level'`` rows hold raw closes (display only)
    — both written by the same sync pass, UNIQUE per (factor, date, kind)."""
    __tablename__ = "factor_values"
    __table_args__ = (UniqueConstraint("factor_id", "date", "kind", name="uq_factor_value_date_kind"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    factor_id = Column(String, ForeignKey("factors.id", ondelete="CASCADE"), nullable=False)
    date = Column(String, nullable=False)                  # YYYY-MM-DD
    value = Column(Float, nullable=False)
    kind = Column(String, nullable=False, default="return")  # return / level
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FactorExposure(Base):
    """Monthly factor exposure rows — one row per (asset, as_of month-end, factor).

    ``as_of_date`` is the regression window end (last common trading day of the
    month); all factor rows of one regression share the same ``r2``/``method``
    snapshot so per-asset quality badges are cheap to query.
    """
    __tablename__ = "factor_exposures"
    __table_args__ = (UniqueConstraint("asset_id", "as_of_date", "factor_id", name="uq_factor_exposure_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(String, ForeignKey("research_assets.id", ondelete="CASCADE"), nullable=False)
    as_of_date = Column(String, nullable=False)            # window end date YYYY-MM-DD
    factor_id = Column(String, ForeignKey("factors.id", ondelete="CASCADE"), nullable=False)
    beta = Column(Float, nullable=False)
    t_stat = Column(Float, nullable=True)
    r2 = Column(Float, nullable=False)                     # regression-wide R², redundant per row
    method = Column(String, nullable=False)                # ols / ridge
    window_days = Column(Integer, nullable=False)
    params = Column(Text, nullable=True)                   # JSON snapshot: window/alpha/factor_ids
    created_at = Column(DateTime, default=datetime.utcnow)
