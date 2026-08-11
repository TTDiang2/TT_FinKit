from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index, UniqueConstraint
from datetime import datetime
import uuid
from ..database import Base


class InvestmentNavSnapshot(Base):
    """Per-product NAV/valuation snapshot at a point in time.

    Used to compute time-weighted metrics and to anchor rolling-window returns
    (e.g. "last 1 year") without re-deriving historical state from raw events.
    """
    __tablename__ = "investment_nav_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    investment_id = Column(String, ForeignKey("investments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    snapshot_date = Column(String, nullable=False)  # yyyy-mm-dd
    unit_price = Column(Float, default=0.0)
    quantity_held = Column(Float, default=0.0)
    total_value = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("investment_id", "snapshot_date", name="uq_nav_investment_date"),
        Index("ix_nav_investment_date", "investment_id", "snapshot_date"),
    )
