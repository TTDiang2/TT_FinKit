from sqlalchemy import Column, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from ..database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)
    date = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    account_id = Column(String, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    dest_account_id = Column(String, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True)
    category_id = Column(String, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    tag_ids = Column(JSON, default=list)
    description = Column(String, default="")
    remark = Column(String, default="")
    location = Column(String, default="")  # 交易地点/附言（银行流水原始字段，辅助分类与审计）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="transactions")
    account = relationship("Account", foreign_keys=[account_id])
    dest_account = relationship("Account", foreign_keys=[dest_account_id])
    category = relationship("Category")