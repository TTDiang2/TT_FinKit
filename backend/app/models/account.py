from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from ..database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    currency = Column(String, default="CNY")
    initial_balance = Column(Float, default=0.0)
    account_type = Column(String, default="cash")
    bank_statement_mode = Column(String, default="direct")  # 兼容旧字段；direct=工资账户式；composite=消费账户式；custom=自定义
    bank_formula = Column(String, nullable=True)  # 校验口径公式 JSON：{"income":["transfer_in","refund","income"],"expense":["expense_positive"]}
    hidden = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="accounts")