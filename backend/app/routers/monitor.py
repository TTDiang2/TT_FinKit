import json
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_private_db, get_public_db
from ..middleware.auth import get_current_user_id
from ..services.monitor_service import (
    get_monitor_overview,
    get_monitor_settings,
    update_monitor_settings,
)
from ..services.strategy_health import strategy_health
from sqlalchemy import text

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


class RebalanceLogRequest(BaseModel):
    date: Optional[str] = None       # 默认今天
    note: Optional[str] = None


@router.get("/events")
async def events_endpoint(limit: int = 100, asset_class: Optional[str] = None):
    """驱动事件（RSS 原型）：近期财经新闻事件流。"""
    from ..services.event_feed import list_events
    return list_events(limit=limit, asset_class=asset_class)


@router.post("/events/collect")
async def events_collect_endpoint():
    """手动触发一次 RSS 采集（后续可挂定时）。"""
    from ..services.event_feed import collect
    import asyncio
    return await asyncio.to_thread(collect)


@router.get("/strategy-health")
async def strategy_health_endpoint(user_id: str = Depends(get_current_user_id),
                                   db: AsyncSession = Depends(get_private_db)):
    """实盘策略健康：失效判定（默认阈值）/ 调仓冷却 / 数据新鲜度提醒。"""
    return await strategy_health(db, user_id)


@router.post("/rebalance-log")
async def record_rebalance(req: RebalanceLogRequest,
                           user_id: str = Depends(get_current_user_id),
                           db: AsyncSession = Depends(get_private_db)):
    """手动记录「我已完成调仓」——冷却期与重复提示的依据。

    存 user_settings.monitor_thresholds JSON 的 last_manual_rebalance 键
    （该列本就是监控相关的 JSON 扩展位）。
    """
    from ..models.user_settings import UserSettings
    d = req.date or __import__("datetime").date.today().isoformat()
    row = (await db.execute(select(UserSettings).where(
        UserSettings.user_id == user_id))).scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user_id)
        db.add(row)
    current: dict = {}
    if row.monitor_thresholds:
        try:
            current = json.loads(row.monitor_thresholds)
        except (ValueError, TypeError):
            current = {}
    current["last_manual_rebalance"] = d
    row.monitor_thresholds = json.dumps(current, ensure_ascii=False)
    await db.commit()
    return {"ok": True, "date": d}


@router.get("/rebalance-log")
async def get_rebalance_log(user_id: str = Depends(get_current_user_id),
                            db: AsyncSession = Depends(get_private_db)):
    from ..models.user_settings import UserSettings
    row = (await db.execute(select(UserSettings).where(
        UserSettings.user_id == user_id))).scalar_one_or_none()
    data: dict = {}
    if row and row.monitor_thresholds:
        try:
            data = json.loads(row.monitor_thresholds)
        except (ValueError, TypeError):
            data = {}
    return {"last_manual_rebalance": data.get("last_manual_rebalance")}


class MonitorSettingsUpdate(BaseModel):
    weight_deviation_pp: Optional[float] = None
    exposure_drift: Optional[float] = None
    drawdown_alert_pct: Optional[float] = None


@router.get("/overview")
async def get_overview(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
    pub: AsyncSession = Depends(get_public_db),
):
    return await get_monitor_overview(db, pub, user_id)


@router.get("/settings")
async def get_settings(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    return await get_monitor_settings(db, user_id)


@router.put("/settings")
async def put_settings(
    req: MonitorSettingsUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
):
    return await update_monitor_settings(db, user_id, req.model_dump(exclude_unset=True))
