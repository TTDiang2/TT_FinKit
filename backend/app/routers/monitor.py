from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user_id
from ..services.monitor_service import (
    get_monitor_overview,
    get_monitor_settings,
    update_monitor_settings,
)

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


class MonitorSettingsUpdate(BaseModel):
    weight_deviation_pp: Optional[float] = None
    exposure_drift: Optional[float] = None
    drawdown_alert_pct: Optional[float] = None


@router.get("/overview")
async def get_overview(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await get_monitor_overview(db, user_id)


@router.get("/settings")
async def get_settings(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await get_monitor_settings(db, user_id)


@router.put("/settings")
async def put_settings(
    req: MonitorSettingsUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await update_monitor_settings(db, user_id, req.model_dump(exclude_unset=True))
