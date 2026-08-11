"""Pydantic schemas for AI-powered investment analysis."""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class SearchResult(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
    date: Optional[str] = None
    source: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    provider: str
    results: List[SearchResult]
    error: Optional[str] = None


class RelevantIndicators(BaseModel):
    short_term: Literal["positive", "negative", "neutral"] = "neutral"
    medium_term: Literal["positive", "negative", "neutral"] = "neutral"
    long_term: Literal["positive", "negative", "neutral"] = "neutral"


class InvestmentAnalysisResponse(BaseModel):
    """Structured output of the AI investment analysis pipeline."""
    summary: str = Field(default="", description="2-3 sentence summary")
    sentiment: Literal["bullish", "bearish", "neutral", "mixed"] = "neutral"
    sentiment_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    key_findings: List[str] = Field(default_factory=list)
    key_risks: List[str] = Field(default_factory=list)
    notable_developments: List[str] = Field(default_factory=list)
    suggested_action: Literal["buy", "sell", "hold", "watch", "insufficient_data"] = "insufficient_data"
    action_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    relevant_indicators: RelevantIndicators = Field(default_factory=RelevantIndicators)
    data_quality: Literal["high", "medium", "low"] = "low"


class AnalyzeRequest(BaseModel):
    query: str = ""                  # free-form; default = use product name + symbol
    max_results: int = 8             # cap number of articles fetched
    days: int = 30                   # limit to recent window
