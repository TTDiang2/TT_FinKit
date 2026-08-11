from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    language = Column(String, default="zh")
    currency_symbol = Column(String, default="¥")
    date_format = Column(String, default="YYYY-MM-DD")
    timezone = Column(String, default="Asia/Shanghai")
    sidebar_expanded = Column(Boolean, default=True)

    # AI Investment Analysis settings
    ai_search_backend = Column(String, default="duckduckgo")    # duckduckgo | tavily
    ai_search_api_key = Column(String, default="")              # optional — only used by tavily
    ai_investment_preset_id = Column(String, nullable=True)     # which AI preset to use; null = default preset

    # iFinD (同花顺 quantapi) credentials — powers live quotes & NAV history
    ifind_username = Column(String, default="")
    ifind_password = Column(String, default="")

    user = relationship("User", back_populates="settings")
