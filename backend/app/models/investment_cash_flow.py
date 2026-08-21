from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Index
from datetime import datetime
import uuid
from ..database import Base


class InvestmentCashFlow(Base):
    """Portfolio-level principal ledger — one row per deposit/withdrawal event.

    本金 (principal) = Σ deposits − Σ withdrawals. This mirrors the investment
    accounts' balance maintained in the bookkeeping tab (transfers in/out), so
    the two can be cross-checked (see /api/investments/consistency).
    """
    __tablename__ = "investment_cash_flows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    flow_type = Column(String, nullable=False)   # deposit | withdrawal
    amount = Column(Float, nullable=False)       # always positive
    flow_date = Column(String, nullable=False)   # yyyy-mm-dd
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_inv_cash_user_date", "user_id", "flow_date"),
    )
