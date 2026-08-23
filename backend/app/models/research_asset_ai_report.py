from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from datetime import datetime
import uuid
from ..database import Base


class ResearchAssetAiReport(Base):
    """AI analysis reports for research assets (per-asset news + LLM analysis).

    Mirrors investment_ai_reports but tied to research_assets. Persisted on
    every run — including failures (error column) — so history is queryable.
    """
    __tablename__ = "research_asset_ai_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String, ForeignKey("research_assets.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    asset_name = Column(String, nullable=False)
    asset_symbol = Column(String, nullable=False)
    query = Column(Text, nullable=False, default="")
    analysis = Column(Text, nullable=False)               # JSON: {summary, sentiment, key_findings, ...}
    raw_articles = Column(Text, nullable=False)           # JSON: [{title, url, snippet, date, source}]
    search_backend = Column(String, default="")
    llm_preset_id = Column(String, ForeignKey("ai_presets.id", ondelete="SET NULL"), nullable=True)
    llm_model = Column(String, default="")
    error = Column(Text, nullable=True)                   # failure also persisted
    generated_at = Column(DateTime, default=datetime.utcnow)
