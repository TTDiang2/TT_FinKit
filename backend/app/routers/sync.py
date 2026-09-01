"""设置页 - 私有库云端同步（GitHub Releases 滚动快照）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..middleware.auth import get_current_user_id
from ..services import db_sync

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncConfigIn(BaseModel):
    repo: str = ""
    tag: str = "db-snapshot"
    token: str | None = None  # None/空 = 保留已存 token


@router.get("/config")
async def get_sync_config(user_id: str = Depends(get_current_user_id)):
    cfg = db_sync.get_config()
    cfg["private_db"] = str(db_sync.private_db_path())
    sdir = db_sync.strategies_dir()
    cfg["strategies_dir"] = str(sdir) if sdir else None
    return cfg


@router.put("/config")
async def save_sync_config(body: SyncConfigIn, user_id: str = Depends(get_current_user_id)):
    if body.token is None or body.token == "":
        cfg = db_sync.get_config()
        if not cfg["token_set"]:
            raise HTTPException(status_code=400, detail="首次配置必须提供 GitHub Token")
    try:
        db_sync.save_config(body.repo, body.tag, body.token)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"配置写入失败: {e}")
    return db_sync.get_config()


@router.get("/remote")
async def sync_remote_status(user_id: str = Depends(get_current_user_id)):
    try:
        return await db_sync.remote_status()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub 访问失败: {e}")


@router.post("/push")
async def sync_push(user_id: str = Depends(get_current_user_id)):
    try:
        return await db_sync.push_snapshot()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"推送失败: {e}")


@router.post("/pull")
async def sync_pull(user_id: str = Depends(get_current_user_id)):
    """拉取云端快照并落地。会先备份本地库到 backups/；连接池已 dispose，
    新请求自动重连新库，无需重启应用。"""
    try:
        return await db_sync.pull_snapshot()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"拉取失败: {e}")
