from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from ..database import Base


class ReportArchive(Base):
    __tablename__ = "report_archives"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(String, nullable=False)
    period_start = Column(String, nullable=False)
    period_end = Column(String, nullable=False)
    content = Column(Text, default="{}")
    generated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="report_archives")