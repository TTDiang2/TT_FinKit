from sqlalchemy import Column, String, Text, Integer, DateTime
from app.database import Base
import uuid, datetime

class Signal(Base):
    __tablename__ = "signals"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True)  # owner; NULL = legacy global row
    strategy_id = Column(String, nullable=False)
    strategy_version = Column(Integer, nullable=False)
    run_date = Column(String, nullable=False)  # YYYY-MM-DD: when signal was generated
    as_of_date = Column(String, nullable=False)  # data cutoff date
    next_rebalance_date = Column(String, nullable=True)  # next scheduled rebalance
    target_weights = Column(Text, nullable=False)  # JSON: {asset_id: weight}
    risk_status = Column(Text, nullable=True)  # JSON: risk status summary
    backtest_id = Column(String, nullable=True)  # linked most recent backtest
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
