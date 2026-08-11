"""AI investment analysis orchestrator.

Pipeline:
  1. Build a focused news-search query from the investment's name + symbol.
  2. Run the configured search backend (DuckDuckGo / Tavily).
  3. Compose an OpenAI-compatible chat-completion request (system prompt
     baked in, articles inlined as user content) and POST to the user's
     default AI preset's api_url.
  4. Parse the structured JSON response into InvestmentAnalysisResponse.
  5. Persist a row to investment_ai_reports.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ai_preset import AiPreset
from ..models.investment import Investment
from ..models.investment_ai_report import InvestmentAiReport
from ..models.user_settings import UserSettings
from ..schemas.ai_investment import (
    AnalyzeRequest,
    InvestmentAnalysisResponse,
    RelevantIndicators,
    SearchResult,
)
from ..schemas.investment import InvestmentMetrics
from .search import get_backend

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are FinKit's investment-analysis assistant.

You will receive: (a) a product description, (b) the user's current position
metrics (cost basis, current value, P&L, days held), and (c) a set of recent
news articles about the product.

Produce a STRICT JSON object with EXACTLY these keys (no extra keys, no
commentary before/after):

{
  "summary": "2-3 sentence plain-language summary of the recent situation",
  "sentiment": "bullish" | "bearish" | "neutral" | "mixed",
  "sentiment_confidence": 0.0 to 1.0,
  "key_findings": ["..."],
  "key_risks": ["..."],
  "notable_developments": ["..."],
  "suggested_action": "buy" | "sell" | "hold" | "watch" | "insufficient_data",
  "action_confidence": 0.0 to 1.0,
  "relevant_indicators": {
    "short_term":  "positive" | "negative" | "neutral",
    "medium_term": "positive" | "negative" | "neutral",
    "long_term":   "positive" | "negative" | "neutral"
  },
  "data_quality": "high" | "medium" | "low"
}

Rules:
- All list items must be short (max ~30 words).
- Confidence values must reflect how strongly the evidence supports the
  sentiment/action — not a guess.
- If the news is sparse or off-topic, set data_quality="low" and
  suggested_action="insufficient_data".
- Output JSON ONLY. No prose, no markdown fences.
"""


def _build_query(inv: Investment, user_query: str) -> str:
    if user_query.strip():
        return user_query.strip()
    parts = [inv.name]
    if inv.symbol:
        parts.append(f"({inv.symbol})")
    parts.append("investment news analysis")
    return " ".join(parts)


def _format_user_prompt(
    inv: Investment,
    metrics: Optional[InvestmentMetrics],
    query: str,
    articles: list[SearchResult],
) -> str:
    lines = [
        f"Product: {inv.name}",
        f"Type: {inv.investment_type}",
    ]
    if inv.symbol:
        lines.append(f"Symbol: {inv.symbol} ({inv.exchange or 'unknown exchange'})")
    if metrics:
        lines.append("")
        lines.append("Current position:")
        lines.append(f"- Total invested: {metrics.total_invested:.2f}")
        lines.append(f"- Current value:  {metrics.current_value:.2f}")
        lines.append(f"- Total P&L:      {metrics.total_pnl:.2f} ({metrics.total_return_pct:.2f}%)")
        if metrics.xirr_annualized is not None:
            lines.append(f"- Annualized XIRR: {metrics.xirr_annualized*100:.2f}%")
        lines.append(f"- Days held:      {metrics.days_held}")
    lines.append("")
    lines.append(f"Search query used: {query}")
    lines.append("")
    lines.append(f"Recent news ({len(articles)} articles):")
    for i, a in enumerate(articles, 1):
        lines.append(f"\n[{i}] {a.title}")
        if a.source or a.date:
            lines.append(f"    Source: {a.source or 'unknown'} | Date: {a.date or 'unknown'}")
        if a.snippet:
            lines.append(f"    {a.snippet}")
    lines.append("")
    lines.append("Return the JSON object now.")
    return "\n".join(lines)


async def _pick_preset(db: AsyncSession, user_id: str) -> Optional[AiPreset]:
    """Find the user's default AI preset, or any preset if no default."""
    res = await db.execute(
        select(AiPreset)
        .where(AiPreset.user_id == user_id, AiPreset.is_default == "true")
        .limit(1)
    )
    preset = res.scalars().first()
    if preset:
        return preset
    # Fallback: any preset for this user
    res = await db.execute(
        select(AiPreset).where(AiPreset.user_id == user_id).limit(1)
    )
    return res.scalars().first()


async def _pick_settings(db: AsyncSession, user_id: str) -> UserSettings:
    res = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    s = res.scalars().first()
    if s is None:
        # Create on the fly with defaults
        s = UserSettings(user_id=user_id)
        db.add(s)
        await db.flush()
    return s


async def _call_llm(preset: AiPreset, system_prompt: str, user_prompt: str) -> str:
    """Call an OpenAI-compatible chat-completion endpoint. Returns raw text."""
    url = preset.api_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        if url.endswith("/v1"):
            url = url + "/chat/completions"
        else:
            url = url.rstrip("/") + "/v1/chat/completions"

    payload = {
        "model": preset.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {preset.api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:500]}")
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"LLM response missing content: {data}") from e


def _parse_analysis(raw: str) -> InvestmentAnalysisResponse:
    """Parse LLM JSON output into InvestmentAnalysisResponse, tolerating fences."""
    text = raw.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` fences
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM returned invalid JSON: {e}; payload: {text[:500]}") from e
    # Pydantic validation will coerce / reject
    return InvestmentAnalysisResponse.model_validate(obj)


async def analyze_investment(
    db: AsyncSession,
    investment: Investment,
    user_id: str,
    request: Optional[AnalyzeRequest] = None,
) -> tuple[InvestmentAiReport, InvestmentAnalysisResponse]:
    """Run the full pipeline. Always persists a report row (success or failure)."""
    request = request or AnalyzeRequest()

    settings = await _pick_settings(db, user_id)
    preset = await _pick_preset(db, user_id)

    # Build the report row early so we always have something to persist
    report = InvestmentAiReport(
        investment_id=investment.id,
        user_id=user_id,
        investment_name=investment.name,
        investment_symbol=investment.symbol or "",
        query=request.query,
        search_backend=settings.ai_search_backend or "duckduckgo",
        llm_preset_id=preset.id if preset else None,
        llm_model=preset.model_name if preset else "",
    )

    if preset is None:
        report.error = (
            "No AI preset configured. Open Admin → AI Settings and add an OpenAI-compatible preset."
        )
        db.add(report)
        await db.flush()
        raise RuntimeError(report.error)

    # 1) Run the search
    query = _build_query(investment, request.query)
    backend = get_backend(settings.ai_search_backend, api_key=settings.ai_search_api_key)
    search_resp = await backend.search(
        query=query, max_results=request.max_results, days=request.days
    )
    report.raw_articles = [r.model_dump() for r in search_resp.results]
    if search_resp.error:
        report.error = search_resp.error
        db.add(report)
        await db.flush()
        raise RuntimeError(search_resp.error)
    if not search_resp.results:
        report.error = "Search returned no results. Try a different query or backend."
        db.add(report)
        await db.flush()
        raise RuntimeError(report.error)

    # 2) Compute current metrics (lazy import to avoid circular)
    from .investment_stats import compute_investment_metrics
    metrics = await compute_investment_metrics(db, investment)

    # 3) Call the LLM
    user_prompt = _format_user_prompt(investment, metrics, query, search_resp.results)
    try:
        raw = await _call_llm(preset, SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        report.error = f"LLM call failed: {e}"
        db.add(report)
        await db.flush()
        raise RuntimeError(report.error) from e

    # 4) Parse
    try:
        analysis = _parse_analysis(raw)
    except Exception as e:
        report.error = f"LLM output parse failed: {e}"
        db.add(report)
        await db.flush()
        raise RuntimeError(report.error) from e

    report.analysis = analysis.model_dump()
    db.add(report)
    await db.flush()
    return report, analysis
