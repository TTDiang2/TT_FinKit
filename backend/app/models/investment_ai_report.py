from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from datetime import datetime
import uuid
from ..database import Base


class InvestmentAiReport(Base):
    """Persisted AI investment analysis reports — so user can browse history."""
    __tablename__ = "investment_ai_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    investment_id = Column(String, ForeignKey("investments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # The query/context
    investment_name = Column(String, nullable=False)
    investment_symbol = Column(String, default="")
    query = Column(Text, default="")  # free-form query the user typed (optional)

    # The full structured response (matches InvestmentAnalysisResponse schema)
    analysis = Column(JSON, nullable=True)
    raw_articles = Column(JSON, nullable=True)   # raw search results, for debugging/transparency

    # Bookkeeping
    search_backend = Column(String, default="")  # e.g. "duckduckgo" / "tavily"
    llm_preset_id = Column(String, ForeignKey("ai_presets.id", ondelete="SET NULL"), nullable=True)
    llm_model = Column(String, default="")
    error = Column(Text, nullable=True)          # populated if the analysis failed

    generated_at = Column(DateTime, default=datetime.utcnow)
