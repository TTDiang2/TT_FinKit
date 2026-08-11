from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from ..database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    color = Column(String, default="#6B6B6B")
    icon = Column(String, default="")
    sort_order = Column(Integer, default=0)
    is_necessary = Column(Boolean, default=False)
    pl_section = Column(String, default="")  # main_income/other_income/exclude_income/main_cost/other_cost/exclude_expense
    cf_section = Column(String, default="")  # operating/investing/financing
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="categories")