"""AI-powered investment analysis endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.investment import Investment
from ..models.investment_ai_report import InvestmentAiReport
from ..schemas.ai_investment import AnalyzeRequest, InvestmentAnalysisResponse
from ..schemas.investment import InvestmentResponse
from ..middleware.auth import get_current_user_id
from ..services.ai_investment import analyze_investment

router = APIRouter(prefix="/api/investments", tags=["ai-investment"])


def _inv_to_response(inv: Investment) -> InvestmentResponse:
    total_value = (inv.quantity or 0) * (inv.current_price or 0)
    profit_loss = ((inv.current_price or 0) - (inv.purchase_price or 0)) * (inv.quantity or 0)
    return InvestmentResponse(
        id=inv.id,
        user_id=inv.user_id,
        name=inv.name,
        investment_type=inv.investment_type,
        underlying_asset_type=inv.underlying_asset_type or "",
        symbol=inv.symbol or "",
        exchange=inv.exchange or "",
        quantity=inv.quantity or 0,
        purchase_price=inv.purchase_price or 0,
        current_price=inv.current_price or 0,
        purchase_date=inv.purchase_date,
        sell_date=inv.sell_date,
        notes=inv.notes,
        last_price_update=str(inv.last_price_update) if inv.last_price_update else None,
        total_value=total_value,
        profit_loss=profit_loss,
        created_at=str(inv.created_at) if inv.created_at else "",
        updated_at=str(inv.updated_at) if inv.updated_at else "",
    )


@router.get("/ai/reports", response_model=List[dict])
async def list_ai_reports(
    investment_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List AI analysis reports for the user (optionally filtered by investment)."""
    q = select(InvestmentAiReport).where(InvestmentAiReport.user_id == user_id)
    if investment_id:
        q = q.where(InvestmentAiReport.investment_id == investment_id)
    q = q.order_by(InvestmentAiReport.generated_at.desc()).limit(50)
    res = await db.execute(q)
    return [
        {
            "id": r.id,
            "investment_id": r.investment_id,
            "investment_name": r.investment_name,
            "investment_symbol": r.investment_symbol,
            "query": r.query,
            "analysis": r.analysis,
            "raw_articles": r.raw_articles,
            "search_backend": r.search_backend,
            "llm_model": r.llm_model,
            "error": r.error,
            "generated_at": str(r.generated_at) if r.generated_at else None,
        }
        for r in res.scalars().all()
    ]


@router.get("/ai/reports/{report_id}")
async def get_ai_report(
    report_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(InvestmentAiReport).where(
            InvestmentAiReport.id == report_id,
            InvestmentAiReport.user_id == user_id,
        )
    )
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Report not found")
    return {
        "id": r.id,
        "investment_id": r.investment_id,
        "investment_name": r.investment_name,
        "investment_symbol": r.investment_symbol,
        "query": r.query,
        "analysis": r.analysis,
        "raw_articles": r.raw_articles,
        "search_backend": r.search_backend,
        "llm_model": r.llm_model,
        "error": r.error,
        "generated_at": str(r.generated_at) if r.generated_at else None,
    }


@router.post("/{investment_id}/ai-analysis")
async def analyze(
    investment_id: str,
    request: AnalyzeRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Run the search+LLM pipeline and persist a report row."""
    res = await db.execute(
        select(Investment).where(Investment.id == investment_id, Investment.user_id == user_id)
    )
    inv = res.scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Investment not found")

    try:
        report, analysis = await analyze_investment(db, inv, user_id, request)
    except Exception as e:
        # Service already persisted the report row with error; surface as 400/500
        raise HTTPException(400, detail=str(e))

    return {
        "report_id": report.id,
        "investment": _inv_to_response(inv),
        "analysis": analysis.model_dump(),
        "raw_articles": report.raw_articles,
        "search_backend": report.search_backend,
        "llm_model": report.llm_model,
        "generated_at": str(report.generated_at) if report.generated_at else None,
    }
