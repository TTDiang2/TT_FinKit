"""AI 财富咨询路由 — 严厉审计师人设的问答 + 画像编辑 + 数据快照 + 对话归档 + 行动清单。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_private_db
from ..middleware.auth import get_current_user_id
from ..config import private_db_path
from ..services.ai_advisor import (
    ask_advisor,
    ensure_tables,
    get_profile,
    save_profile,
    stream_ask_advisor,
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


class ActionCreate(BaseModel):
    title: str
    detail: str | None = None
    category: str = "other"
    target_amount: float | None = None
    due_date: str | None = None


class ActionUpdate(BaseModel):
    title: str | None = None
    detail: str | None = None
    category: str | None = None
    target_amount: float | None = None
    due_date: str | None = None
    status: str | None = None


@router.get("/profile")
async def get_profile_endpoint(default: bool = False,
                               user_id: str = Depends(get_current_user_id),
                               db: AsyncSession = Depends(get_private_db)):
    ensure_tables(DB)
    if default:
        from ..services.ai_advisor import DEFAULT_PROFILE
        return {"profile_md": DEFAULT_PROFILE}
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


@router.post("/ask/stream")
async def ask_stream_endpoint(req: AskRequest,
                              user_id: str = Depends(get_current_user_id),
                              db: AsyncSession = Depends(get_private_db)):
    """SSE 流式问答：LLM 每生成一段即推送，前端增量渲染。"""
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")
    if len(q) > 4000:
        raise HTTPException(status_code=400, detail="问题过长（>4000 字符）")
    ensure_tables(DB)
    return StreamingResponse(
        stream_ask_advisor(db, user_id, q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------- 对话归档（本地存 advisor_chats） ----------------


@router.get("/archive/sessions")
async def archive_sessions_endpoint(user_id: str = Depends(get_current_user_id),
                                    db: AsyncSession = Depends(get_private_db)):
    """会话列表：每个 session 一行，含首问摘要与轮数。"""
    ensure_tables(DB)
    rows = (await db.execute(_text(
        "SELECT session_id, MIN(created_at) AS started_at, MAX(created_at) AS last_at, "
        "COUNT(*) AS msg_count, "
        "(SELECT question FROM advisor_chats c2 WHERE c2.session_id=c.session_id "
        " AND c2.question IS NOT NULL ORDER BY c2.created_at LIMIT 1) AS first_question "
        "FROM advisor_chats c WHERE user_id=:u AND session_id IS NOT NULL "
        "GROUP BY session_id ORDER BY last_at DESC LIMIT 200"
    ), {"u": user_id})).mappings().all()
    return [dict(r) for r in rows]


@router.get("/archive/sessions/{session_id}")
async def archive_session_detail_endpoint(session_id: str,
                                          user_id: str = Depends(get_current_user_id),
                                          db: AsyncSession = Depends(get_private_db)):
    """单个会话的全部消息（含当次快照，供回看 AI 当时看到的数据）。"""
    ensure_tables(DB)
    rows = (await db.execute(_text(
        "SELECT id, role, content, question, snapshot_json, created_at "
        "FROM advisor_chats WHERE user_id=:u AND session_id=:s ORDER BY id"
    ), {"u": user_id, "s": session_id})).mappings().all()
    if not rows:
        raise HTTPException(status_code=404, detail="会话不存在")
    out = []
    for r in rows:
        d = dict(r)
        d["has_snapshot"] = bool(d.pop("snapshot_json"))
        out.append(d)
    return out


@router.get("/archive/sessions/{session_id}/snapshot/{msg_id}")
async def archive_snapshot_endpoint(session_id: str, msg_id: int,
                                    user_id: str = Depends(get_current_user_id),
                                    db: AsyncSession = Depends(get_private_db)):
    row = (await db.execute(_text(
        "SELECT snapshot_json FROM advisor_chats "
        "WHERE id=:i AND user_id=:u AND session_id=:s"
    ), {"i": msg_id, "u": user_id, "s": session_id})).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="快照不存在")
    import json as _json
    try:
        return _json.loads(row)
    except Exception:
        raise HTTPException(status_code=500, detail="快照损坏")


@router.delete("/archive/sessions/{session_id}")
async def archive_session_delete_endpoint(session_id: str,
                                          user_id: str = Depends(get_current_user_id),
                                          db: AsyncSession = Depends(get_private_db)):
    r = await db.execute(_text(
        "DELETE FROM advisor_chats WHERE user_id=:u AND session_id=:s"
    ), {"u": user_id, "s": session_id})
    await db.commit()
    if r.rowcount == 0:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True, "deleted": r.rowcount}


# ---------------- 行动清单 / 目标列表（advisor_actions） ----------------


@router.get("/actions")
async def actions_list_endpoint(user_id: str = Depends(get_current_user_id),
                                db: AsyncSession = Depends(get_private_db)):
    ensure_tables(DB)
    rows = (await db.execute(_text(
        "SELECT * FROM advisor_actions WHERE user_id=:u "
        "ORDER BY (status='todo') DESC, COALESCE(due_date,'9999') ASC, created_at DESC"
    ), {"u": user_id})).mappings().all()
    return [dict(r) for r in rows]


@router.post("/actions")
async def actions_create_endpoint(req: ActionCreate,
                                  user_id: str = Depends(get_current_user_id),
                                  db: AsyncSession = Depends(get_private_db)):
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    if len(title) > 300:
        raise HTTPException(status_code=400, detail="标题过长（>300 字符）")
    if req.category not in ("emergency", "invest", "housing", "spending", "income", "other"):
        raise HTTPException(status_code=400, detail="category 不合法")
    aid = uuid.uuid4().hex
    await db.execute(_text(
        "INSERT INTO advisor_actions (id, user_id, title, detail, category, target_amount, due_date) "
        "VALUES (:id, :u, :t, :d, :c, :a, :dd)"
    ), {"id": aid, "u": user_id, "t": title, "d": req.detail, "c": req.category,
        "a": req.target_amount, "dd": req.due_date})
    await db.commit()
    return {"ok": True, "id": aid}


@router.put("/actions/{action_id}")
async def actions_update_endpoint(action_id: str, req: ActionUpdate,
                                  user_id: str = Depends(get_current_user_id),
                                  db: AsyncSession = Depends(get_private_db)):
    ensure_tables(DB)
    fields, params = [], {"id": action_id, "u": user_id}
    for key in ("title", "detail", "category", "target_amount", "due_date", "status"):
        val = getattr(req, key)
        if val is not None:
            if key == "status" and val not in ("todo", "doing", "done", "dropped"):
                raise HTTPException(status_code=400, detail="status 不合法")
            fields.append(f"{key}=:{key}")
            params[key] = val
    if not fields:
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    if req.status == "done":
        fields.append("completed_at=datetime('now')")
    else:
        fields.append("completed_at=NULL")
    fields.append("updated_at=datetime('now')")
    r = await db.execute(_text(
        f"UPDATE advisor_actions SET {', '.join(fields)} "
        "WHERE id=:id AND user_id=:u"
    ), params)
    await db.commit()
    if r.rowcount == 0:
        raise HTTPException(status_code=404, detail="行动项不存在")
    return {"ok": True}


@router.delete("/actions/{action_id}")
async def actions_delete_endpoint(action_id: str,
                                  user_id: str = Depends(get_current_user_id),
                                  db: AsyncSession = Depends(get_private_db)):
    r = await db.execute(_text(
        "DELETE FROM advisor_actions WHERE id=:id AND user_id=:u"
    ), {"id": action_id, "u": user_id})
    await db.commit()
    if r.rowcount == 0:
        raise HTTPException(status_code=404, detail="行动项不存在")
    return {"ok": True}
