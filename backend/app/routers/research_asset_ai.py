"""AI analysis endpoints for research assets (per-asset news + LLM synthesis)."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_private_db, get_public_db
from ..models.research_asset import ResearchAsset
from ..models.research_asset_ai_report import ResearchAssetAiReport
from ..schemas.ai_investment import AnalyzeRequest
from ..middleware.auth import get_current_user_id
from ..services import research_ai

router = APIRouter(prefix="/api/research/assets", tags=["research-asset-ai"])


def _report_dict(r: ResearchAssetAiReport) -> dict:
    return {
        "report_id": r.id,
        "asset_id": r.asset_id,
        "asset_name": r.asset_name,
        "asset_symbol": r.asset_symbol,
        "query": r.query,
        "analysis": json.loads(r.analysis) if r.analysis else None,
        "raw_articles": json.loads(r.raw_articles) if r.raw_articles else [],
        "search_backend": r.search_backend,
        "llm_model": r.llm_model,
        "error": r.error,
        "generated_at": str(r.generated_at),
    }


async def _get_public(asset_id: str, db: AsyncSession) -> ResearchAsset:
    """共享池标的任何人可读；报告本身按 user_id 隔离在 private 库。"""
    asset = await db.get(ResearchAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="标的不存在")
    return asset


@router.post("/{asset_id}/ai-analysis")
async def run_ai_analysis(
    asset_id: str,
    req: AnalyzeRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
    pub: AsyncSession = Depends(get_public_db),
):
    asset = await _get_public(asset_id, pub)
    try:
        report, analysis = await research_ai.analyze_research_asset(db, asset, user_id, req)
        await db.commit()
    except RuntimeError as e:
        await db.commit()  # persist the error row
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "report_id": report.id,
        "asset": {
            "id": asset.id, "symbol": asset.symbol, "name": asset.name,
            "asset_type": asset.asset_type, "category": asset.category,
        },
        "analysis": analysis.model_dump(),
        "raw_articles": json.loads(report.raw_articles or "[]"),
        "search_backend": report.search_backend,
        "llm_model": report.llm_model,
        "generated_at": str(report.generated_at),
    }


@router.get("/{asset_id}/ai-reports")
async def list_ai_reports(
    asset_id: str,
    limit: int = Query(50),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
    pub: AsyncSession = Depends(get_public_db),
):
    await _get_public(asset_id, pub)
    res = await db.execute(
        select(ResearchAssetAiReport)
        .where(ResearchAssetAiReport.asset_id == asset_id,
               ResearchAssetAiReport.user_id == user_id)
        .order_by(ResearchAssetAiReport.generated_at.desc())
        .limit(limit)
    )
    return [_report_dict(r) for r in res.scalars().all()]


@router.get("/ai-reports/{report_id}")
async def get_ai_report(
    report_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    res = await db.execute(
        select(ResearchAssetAiReport).where(
            ResearchAssetAiReport.id == report_id,
            ResearchAssetAiReport.user_id == user_id,
        )
    )
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="报告不存在")
    return _report_dict(r)


@router.delete("/ai-reports/{report_id}")
async def delete_ai_report(
    report_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    res = await db.execute(
        select(ResearchAssetAiReport).where(
            ResearchAssetAiReport.id == report_id,
            ResearchAssetAiReport.user_id == user_id,
        )
    )
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="报告不存在")
    await db.delete(r)
    await db.commit()
    return {"ok": True, "report_id": report_id}
