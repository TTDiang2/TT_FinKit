"""AI analysis for research assets (news search + LLM synthesis).

Reuses the pipeline components from ``ai_investment`` (settings/preset/LLM/
parse) and the shared search backends. Persists every run to
``research_asset_ai_reports`` — including failures (error column).
"""
import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.research_asset import ResearchAsset
from ..models.research_asset_ai_report import ResearchAssetAiReport
from ..schemas.ai_investment import AnalyzeRequest, InvestmentAnalysisResponse
from . import ai_investment as ai_svc
from .search.registry import get_backend


def build_query(asset: ResearchAsset, user_query: str) -> str:
    if user_query.strip():
        return user_query.strip()
    return f"{asset.name} ({asset.symbol}) 基金 最新动态 业绩 分析"


def _format_user_prompt(
    asset: ResearchAsset,
    query: str,
    articles,
) -> str:
    lines = [
        f"Product: {asset.name}",
        f"Symbol: {asset.symbol} ({asset.exchange or 'unknown exchange'})",
        f"Asset type: {asset.asset_type or 'unknown'}",
        "",
        f"Search query used: {query}",
        "",
        f"Recent news ({len(articles)} articles):",
    ]
    for i, a in enumerate(articles, 1):
        lines.append(f"\n[{i}] {a.title}")
        if a.source or a.date:
            lines.append(f"    Source: {a.source or 'unknown'} | Date: {a.date or 'unknown'}")
        if a.snippet:
            lines.append(f"    {a.snippet}")
    lines.append("")
    lines.append("Return the JSON object now.")
    return "\n".join(lines)


async def analyze_research_asset(
    db: AsyncSession,
    asset: ResearchAsset,
    user_id: str,
    request: Optional[AnalyzeRequest] = None,
) -> tuple[ResearchAssetAiReport, InvestmentAnalysisResponse]:
    """Run the full pipeline for a research asset. Always persists a report row."""
    request = request or AnalyzeRequest()

    settings = await ai_svc._pick_settings(db, user_id)
    preset = await ai_svc._pick_preset(db, user_id)

    report = ResearchAssetAiReport(
        asset_id=asset.id,
        user_id=user_id,
        asset_name=asset.name,
        asset_symbol=asset.symbol,
        query=request.query,
        search_backend=settings.ai_search_backend or "duckduckgo",
        llm_preset_id=preset.id if preset else None,
        llm_model=preset.model_name if preset else "",
    )

    if preset is None:
        report.error = (
            "No AI preset configured. Open Settings → AI 设置 and add an OpenAI-compatible preset."
        )
        db.add(report)
        await db.flush()
        raise RuntimeError(report.error)

    # 1) Search
    query = build_query(asset, request.query)
    backend = get_backend(settings.ai_search_backend, api_key=settings.ai_search_api_key)
    search_resp = await backend.search(
        query=query, max_results=request.max_results, days=request.days
    )
    report.raw_articles = json.dumps([r.model_dump() for r in search_resp.results], ensure_ascii=False)
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

    # 2) LLM
    user_prompt = _format_user_prompt(asset, query, search_resp.results)
    try:
        raw = await ai_svc._call_llm(preset, ai_svc.SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        report.error = f"LLM call failed: {e}"
        db.add(report)
        await db.flush()
        raise RuntimeError(report.error) from e

    # 3) Parse
    try:
        analysis = ai_svc._parse_analysis(raw)
    except Exception as e:
        report.error = f"LLM output parse failed: {e}"
        db.add(report)
        await db.flush()
        raise RuntimeError(report.error) from e

    report.analysis = json.dumps(analysis.model_dump(), ensure_ascii=False)
    report.raw_articles = json.dumps([r.model_dump() for r in search_resp.results], ensure_ascii=False)
    db.add(report)
    await db.flush()
    return report, analysis
