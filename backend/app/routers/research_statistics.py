"""Research asset statistics snapshot — one endpoint feeding all 9 charts in the
标的 → 统计 sub-tab.

计算实现统一在 app/services/stats_compute.py（compute_payload），
本路由只做缓存编排（serve-stale-while-revalidate，用户拍板 2026-08-29：
"统计 tab 只呈现，至少隔天再重算"）与后台重算调度：
- 开发态：子进程 scripts/compute_stats_snapshot.py（大循环不占事件循环）
- PyInstaller 打包态：asyncio.to_thread（无独立解释器，spawn exe 只会
  再拉起一个后端实例）
"""
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_public_db
from ..middleware.auth import get_current_user_id
from ..services.stats_compute import (  # noqa: F401  (re-export：老 import 路径兼容)
    compute_payload,
    _var_cvar,
    _max_drawdown_path,
    _rolling_return,
)
from ..services import stats_compute as _sc

router = APIRouter(prefix="/api/research/stats", tags=["research-stats"])

_stats_cache: dict = {}
_CACHE_TTL = 86400


def _spawn_recompute(key: str, days: int, assets: Optional[str], user_id: str) -> None:
    """后台重算（busy 锁防并发）：完成后写回 _stats_cache。

    过期回旧值 / 无缓存回 pending 骨架 / refresh=1 强制重算，三条路共用。
    """
    if _stats_cache.get(f"busy:{key}"):
        return
    _stats_cache[f"busy:{key}"] = True

    async def _run() -> None:
        try:
            data: dict | None = None
            if getattr(sys, "frozen", False):
                data = await asyncio.to_thread(
                    _sc.run_compute_blocking, days, assets, user_id)
            else:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "scripts/compute_stats_snapshot.py",
                    str(days), assets or "all", user_id,
                    cwd=str(Path(__file__).resolve().parents[2]),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(proc.wait(), timeout=600)
                cache_file = _sc.cache_file_for(user_id, days, assets)
                if cache_file.exists():
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data is not None:
                _stats_cache[key] = {"ts": time.time(), "data": data}
        except Exception:  # noqa: BLE001
            pass
        finally:
            _stats_cache[f"busy:{key}"] = False

    asyncio.create_task(_run())


@router.get("/snapshot")
async def stats_snapshot_cached(
    days: int = Query(365, ge=30, le=3650),
    assets: Optional[str] = Query(None),
    refresh: int = Query(0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    key = f"{user_id}:{days}:{assets or 'all'}"
    now = time.time()
    cached = _stats_cache.get(key)
    if cached and (now - cached["ts"] < _CACHE_TTL) and not refresh:
        return cached["data"]
    if cached:
        # 过期或 refresh=1：回旧值 + 后台重算（serve-stale / 强制刷新同一条路）
        _spawn_recompute(key, days, assets, user_id)
        return cached["data"]
    # 完全无缓存：返回空骨架 + 后台重算（慢算绝不能挡在请求路径上）
    _spawn_recompute(key, days, assets, user_id)
    if key not in _stats_cache:
        _stats_cache[key] = {"ts": now - _CACHE_TTL, "data": {
            "window": {"begin": None, "end": None, "days": days},
            "assets": [], "correlation": {"labels": [], "matrix": []},
            "frontier": {"assets": [], "samples": []},
            "pending": True,
        }}  # 标记为已过期：计算期间后续请求继续拿 pending 骨架
    return _stats_cache[key]["data"]


@router.get("/snapshot/_fresh")
async def stats_snapshot(
    days: int = Query(365, ge=30, le=3650),
    assets: Optional[str] = Query(None),       # comma-separated symbols (optional filter)
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    return await compute_payload(db=db, days=days, assets=assets, user_id=user_id)
