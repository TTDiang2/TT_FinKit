"""AI 财富咨询路由 — 严厉审计师人设的问答 + 画像编辑 + 数据快照。"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_private_db
from ..middleware.auth import get_current_user_id
from ..config import private_db_path
from ..services.ai_advisor import (
    ask_advisor,
    ensure_tables,
    get_profile,
    save_profile,
)
from ..services.finance_snapshot import finance_snapshot

BACKEND = Path(__file__).resolve().parents[1]
# advisor_chats 由 private session 读写——建表必须落在 private 库，
# 曾经指向 finkit.db 导致双库后 no such table（2026-08-31）
DB = private_db_path()

router = APIRouter(prefix="/api/ai-advisor", tags=["ai-advisor"])


class ProfileUpdate(BaseModel):
    profile_md: str


class AskRequest(BaseModel):
    question: str


@router.get("/profile")
async def get_profile_endpoint(user_id: str = Depends(get_current_user_id),
                               db: AsyncSession = Depends(get_private_db)):
    ensure_tables(DB)
    return {"profile_md": await get_profile(db, user_id)}


@router.put("/profile")
async def put_profile_endpoint(req: ProfileUpdate,
                               user_id: str = Depends(get_current_user_id),
                               db: AsyncSession = Depends(get_private_db)):
    if len(req.profile_md) > 20000:
        raise HTTPException(status_code=400, detail="画像文档过长（>20000 字符）")
    await save_profile(db, user_id, req.profile_md)
    return {"ok": True}


@router.get("/data-summary")
async def data_summary_endpoint(user_id: str = Depends(get_current_user_id),
                                db: AsyncSession = Depends(get_private_db)):
    """AI 看到的数据画像（前端同步展示，人与 AI 同源）。"""
    ensure_tables(DB)
    return await finance_snapshot(db, user_id)


@router.post("/ask")
async def ask_endpoint(req: AskRequest,
                       user_id: str = Depends(get_current_user_id),
                       db: AsyncSession = Depends(get_private_db)):
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")
    if len(q) > 4000:
        raise HTTPException(status_code=400, detail="问题过长（>4000 字符）")
    ensure_tables(DB)
    try:
        return await ask_advisor(db, user_id, q)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
