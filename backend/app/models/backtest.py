from sqlalchemy import Column, String, Text, Integer, Float, DateTime
from app.database import Base
import uuid, datetime

class Backtest(Base):
    """A single backtest run: strategy + params + universe snapshot + results.

    ``results`` holds the full engine output (nav_series, metrics,
    weight_history, rebalance_records, factor_view, risk_view) as JSON.
    ``data_as_of`` records the snapshot date for reproducibility.
    """
    __tablename__ = "backtests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String, nullable=False)
    strategy_version = Column(Integer, nullable=False)
    params = Column(Text, default="{}")  # JSON
    universe = Column(Text, default="[]")  # JSON: list of asset_ids
    start_date = Column(String, nullable=False)  # YYYY-MM-DD
    end_date = Column(String, nullable=False)
    rebalance_freq = Column(String, nullable=False)  # monthly / weekly
    data_as_of = Column(String, nullable=False)  # snapshot date for reproducibility
    status = Column(String, default="pending")  # pending/running/done/failed
    error = Column(Text, nullable=True)
    results = Column(Text, nullable=True)  # JSON: full results
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
