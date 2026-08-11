from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from datetime import datetime
import uuid
from ..database import Base


class AiPreset(Base):
    __tablename__ = "ai_presets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    api_url = Column(String, default="https://api.openai.com/v1")
    api_key = Column(String, default="")
    model_name = Column(String, default="gpt-4o")
    system_prompt = Column(Text, default="")
    is_default = Column(String, default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
