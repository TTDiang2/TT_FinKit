"""私有库云端同步（GitHub Releases 滚动快照）。

双库后 public 库（标的/因子/价格）由用户网盘自行同步；
本模块只同步 finkit_private.db（用户/流水/回测/信号）+ strategies/*.py。
推送/拉取都走 GitHub REST API（httpx），不依赖 git —— 打包 exe 内同样可用。

与 scripts/db_release_push.ps1 / db_release_pull.ps1 同一套滚动快照约定：
release tag 固定（默认 db-snapshot），每次 push 上传新 asset 并只保留最新 4 份。
"""
import asyncio
import io
import json
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

import httpx

from ..config import _resolve_private_url

GITHUB_API = "https://api.github.com"
GITHUB_UPLOAD = "https://uploads.github.com"
DB_NAME_IN_ZIP = "finkit_private.db"
STRATEGY_SUBDIR = "strategies"
KEEP_ASSETS = 4
PUSH_PULL_TIMEOUT = 300.0

_sync_lock = asyncio.Lock()


# ---------------------------------------------------------------- 路径解析

def private_db_path() -> Path:
    """从 private 库 URL 解析出磁盘路径。"""
    url = _resolve_private_url()
    prefix = "sqlite+aiosqlite:///"
    raw = url[len(prefix):] if url.startswith(prefix) else url
    if raw.startswith("/"):
        # /E:/xxx（Windows 绝对）或 /abs/path（POSIX 绝对）
        if len(raw) > 2 and raw[2] == ":":
            raw = raw[1:]
        return Path(raw)
    # 相对路径：相对 backend/（config 默认即相对 backend 解析）
    backend_dir = Path(__file__).resolve().parents[2]
    return (backend_dir / raw).resolve()


def strategies_dir() -> Path | None:
    """仓库根下的 strategies/（与 strategies 路由同规则）；打包环境不存在则 None。"""
    root = Path(__file__).resolve().parents[3] / "strategies"
    return root if root.is_dir() else None


def backups_dir() -> Path:
    return private_db_path().parent / "backups"


# ---------------------------------------------------------------- 配置

def _config_path() -> Path:
    return private_db_path().parent / "sync_config.json"


def get_config() -> dict:
    """读同步配置；token 脱敏（只回尾部 4 位）。"""
    cfg: dict = {}
    p = _config_path()
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            cfg = {}
    token = cfg.get("token") or ""
    return {
        "repo": cfg.get("repo") or "",
        "tag": cfg.get("tag") or "db-snapshot",
        "token_set": bool(token),
        "token_tail": token[-4:] if len(token) >= 8 else "",
    }


def save_config(repo: str, tag: str, token: str | None = None) -> None:
    """写同步配置；token 传 None/空 表示保留原值。"""
    p = _config_path()
    cfg: dict = {}
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            cfg = {}
    cfg["repo"] = (repo or "").strip()
    cfg["tag"] = (tag or "db-snapshot").strip() or "db-snapshot"
    if token:
        cfg["token"] = token.strip()
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _require_ready() -> tuple[str, str, str]:
    cfg = get_config()
    if not cfg["repo"]:
        raise ValueError("未配置同步仓库（repo）")
    full = json.loads(_config_path().read_text(encoding="utf-8")) if _config_path().exists() else {}
    token = full.get("token") or ""
    if not token:
        raise ValueError("未配置 GitHub Token（需要 repo 权限的 PAT）")
    return cfg["repo"], cfg["tag"], token


# ---------------------------------------------------------------- 快照（本地）

def snapshot_private_db(dst: Path) -> None:
    """sqlite backup API 一致性快照：运行中的后端持锁也不受影响。"""
    src = private_db_path()
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    try:
        with d:
            s.backup(d)
    finally:
        d.close()
        s.close()


def build_snapshot_zip(workdir: Path) -> Path:
    """生成快照 zip：finkit_private.db + strategies/*.py（策略目录缺失则跳过）。"""
    workdir.mkdir(parents=True, exist_ok=True)
    snap_db = workdir / DB_NAME_IN_ZIP
    snapshot_private_db(snap_db)

    sdir = strategies_dir()
    if sdir:
        dst = workdir / STRATEGY_SUBDIR
        dst.mkdir(exist_ok=True)
        for f in sdir.glob("*.py"):
            (dst / f.name).write_bytes(f.read_bytes())

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    zip_path = workdir / f"finkit-private-db-{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(snap_db, DB_NAME_IN_ZIP)
        for f in sorted((workdir / STRATEGY_SUBDIR).glob("*.py")):
            z.write(f, f"{STRATEGY_SUBDIR}/{f.name}")
    return zip_path


def restore_from_zip(zip_path: Path) -> dict:
    """把快照 zip 落地：private db 替换 + strategies 还原。

    调用前必须已 dispose private_engine（见 pull_snapshot）。
    """
    db_path = private_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bdir = backups_dir()
    bdir.mkdir(exist_ok=True)

    # 备份当前库（含 WAL 合并：先 checkpoint 再拷贝）
    backup: str | None = None
    if db_path.exists():
        try:
            con = sqlite3.connect(str(db_path))
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.close()
        except sqlite3.Error:
            pass
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = bdir / f"finkit_private.db.{ts}.bak"
        backup_path.write_bytes(db_path.read_bytes())
        backup = str(backup_path)
        # 只保留最新 20 份
        for old in sorted(bdir.glob("finkit_private.db.*.bak"))[:-20]:
            old.unlink(missing_ok=True)

    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if DB_NAME_IN_ZIP not in names:
            raise ValueError(f"快照包缺少 {DB_NAME_IN_ZIP}")
        # 校验快照完整性后落地
        data = z.read(DB_NAME_IN_ZIP)
        tmp_db = db_path.parent / (db_path.name + ".incoming")
        tmp_db.write_bytes(data)
        con = sqlite3.connect(str(tmp_db))
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        if ok != "ok":
            tmp_db.unlink(missing_ok=True)
            raise ValueError(f"快照库完整性校验失败: {ok}")
        # 清掉旧 sidecar 再替换（stale WAL 残留会让新库读脏数据，必须删）
        for side in (db_path.parent / f"{db_path.name}-wal",
                     db_path.parent / f"{db_path.name}-shm"):
            if side.exists():
                try:
                    side.unlink()
                except OSError as e:
                    tmp_db.unlink(missing_ok=True)
                    raise ValueError(
                        f"无法移除 {side.name}（数据库仍被占用——请先关闭正在运行的 "
                        f"FinKit 实例再拉取）: {e}")
        tmp_db.replace(db_path)

        # 还原 strategies/*.py（目标目录存在才动）
        n_strategies = 0
        sdir = strategies_dir()
        if sdir:
            for n in names:
                if n.startswith(f"{STRATEGY_SUBDIR}/") and n.endswith(".py"):
                    (sdir / Path(n).name).write_bytes(z.read(n))
                    n_strategies += 1

    return {"backup": backup, "strategies_restored": n_strategies}


# ---------------------------------------------------------------- GitHub API

def _headers(token: str, octet: bool = False) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/octet-stream" if octet else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _get_release(client: httpx.AsyncClient, repo: str, tag: str, token: str):
    r = await client.get(f"{GITHUB_API}/repos/{repo}/releases/tags/{tag}",
                         headers=_headers(token))
    if r.status_code == 404:
        return None
    if r.status_code == 401:
        raise ValueError("GitHub Token 无效或已过期（401）")
    if r.status_code == 404:
        raise ValueError(f"仓库不存在或无权限：{repo}")
    r.raise_for_status()
    return r.json()


async def remote_status() -> dict:
    """云端最新快照信息（UI 展示用）。"""
    repo, tag, token = _require_ready()
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        rel = await _get_release(client, repo, tag, token)
    if not rel:
        return {"repo": repo, "tag": tag, "asset": None}
    assets = sorted(rel.get("assets") or [], key=lambda a: a.get("created_at") or "")
    latest = assets[-1] if assets else None
    return {
        "repo": repo, "tag": tag,
        "asset": None if not latest else {
            "name": latest["name"],
            "size_mb": round(latest["size"] / 1048576, 1),
            "created_at": latest["created_at"],
        },
    }


async def push_snapshot() -> dict:
    """快照 → 上传云端（滚动保留 KEEP_ASSETS 份）。"""
    repo, tag, token = _require_ready()
    async with _sync_lock:
        import tempfile
        workdir = Path(tempfile.mkdtemp(prefix="finkit_sync_"))
        try:
            zip_path = await asyncio.to_thread(build_snapshot_zip, workdir)
            size_mb = round(zip_path.stat().st_size / 1048576, 1)
            async with httpx.AsyncClient(
                    timeout=httpx.Timeout(PUSH_PULL_TIMEOUT, connect=30.0),
                    follow_redirects=True) as client:
                rel = await _get_release(client, repo, tag, token)
                if rel is None:
                    r = await client.post(
                        f"{GITHUB_API}/repos/{repo}/releases",
                        headers=_headers(token),
                        json={"tag_name": tag, "name": "DB snapshots (rolling)",
                              "body": "Auto-managed private-db snapshots pushed from FinKit settings"})
                    if r.status_code == 401:
                        raise ValueError("GitHub Token 无效或已过期（401）")
                    r.raise_for_status()
                    rel = r.json()
                rel_id = rel["id"]
                # 上传前清掉旧 asset（同 ps1 行为：滚动覆盖）
                for a in rel.get("assets") or []:
                    await client.delete(
                        f"{GITHUB_API}/repos/{repo}/releases/assets/{a['id']}",
                        headers=_headers(token))
                up = await client.post(
                    f"{GITHUB_UPLOAD}/repos/{repo}/releases/{rel_id}/assets",
                    params={"name": zip_path.name},
                    headers={**_headers(token), "Content-Type": "application/zip"},
                    content=zip_path.read_bytes())
                up.raise_for_status()
                # 只保留最新 KEEP_ASSETS 份
                lst = await client.get(
                    f"{GITHUB_API}/repos/{repo}/releases/{rel_id}/assets",
                    params={"per_page": 100}, headers=_headers(token))
                lst.raise_for_status()
                assets = sorted(lst.json(), key=lambda a: a.get("created_at") or "")
                for a in assets[:-KEEP_ASSETS]:
                    await client.delete(
                        f"{GITHUB_API}/repos/{repo}/releases/assets/{a['id']}",
                        headers=_headers(token))
            return {"asset": zip_path.name, "size_mb": size_mb}
        finally:
            import shutil
            shutil.rmtree(workdir, ignore_errors=True)


async def pull_snapshot() -> dict:
    """下载云端最新快照 → 备份本地 → 替换 private db + 还原 strategies。

    替换前 dispose private_engine：连接池全部断开后 Windows 才允许
    替换文件；新请求会自动重连到新文件（无需重启应用）。
    """
    repo, tag, token = _require_ready()
    async with _sync_lock:
        import tempfile
        async with httpx.AsyncClient(
                timeout=httpx.Timeout(PUSH_PULL_TIMEOUT, connect=30.0),
                follow_redirects=True) as client:
            rel = await _get_release(client, repo, tag, token)
            if rel is None:
                raise ValueError(f"云端还没有 tag={tag} 的快照 release")
            assets = sorted(rel.get("assets") or [],
                            key=lambda a: a.get("created_at") or "")
            if not assets:
                raise ValueError("云端 release 存在但没有任何快照")
            latest = assets[-1]
            r = await client.get(latest["url"], headers=_headers(token, octet=True))
            r.raise_for_status()
            payload = r.content

        zip_path = Path(tempfile.mkdtemp(prefix="finkit_pull_")) / latest["name"]
        zip_path.write_bytes(payload)

        from ..database import private_engine
        await private_engine.dispose()  # 断开所有连接，允许替换文件
        result = await asyncio.to_thread(restore_from_zip, zip_path)
        import shutil
        shutil.rmtree(zip_path.parent, ignore_errors=True)
        return {"asset": latest["name"],
                "size_mb": round(latest["size"] / 1048576, 1), **result}
