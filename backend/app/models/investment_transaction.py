from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Index
from datetime import datetime
import uuid
from ..database import Base


class InvestmentTransaction(Base):
    """Investment ledger — one row per cash-flow event (buy/sell/dividend/fee/adjustment)."""
    __tablename__ = "investment_transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    investment_id = Column(String, ForeignKey("investments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    event_type = Column(String, nullable=False)   # buy | sell | dividend | fee | adjustment
    event_date = Column(String, nullable=False)    # yyyy-mm-dd
    quantity = Column(Float, default=0.0)          # signed: positive for buy, negative for sell
    unit_price = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)            # signed: positive cost (buy), negative proceeds (sell/dividend)
    fee = Column(Float, default=0.0)               # transaction fee (always a positive cost); standalone fee events carry it here too
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_inv_tx_investment_date", "investment_id", "event_date"),
        Index("ix_inv_tx_user", "user_id"),
    )
