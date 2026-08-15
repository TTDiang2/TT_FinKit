from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from datetime import datetime
import uuid
from ..database import Base


class ReconciliationRecord(Base):
    """校验记录：月度汇总核对（month=1-12）或今日余额核对（month=0）。"""

    __tablename__ = "reconciliation_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(String, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)  # 0 = 余额核对记录；1-12 = 月度汇总核对
    bank_income = Column(Float, nullable=True)
    bank_expense = Column(Float, nullable=True)
    sys_income = Column(Float, nullable=True)
    sys_expense = Column(Float, nullable=True)
    income_diff = Column(Float, nullable=True)
    expense_diff = Column(Float, nullable=True)
    balance_check_expected = Column(Float, nullable=True)
    balance_check_actual = Column(Float, nullable=True)
    balance_diff = Column(Float, nullable=True)
    status = Column(String, default="matched")  # matched / diff
    notes = Column(String, default="")
    checked_at = Column(DateTime, default=datetime.utcnow)
