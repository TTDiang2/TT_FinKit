import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _sqlite_url(p: Path) -> str:
    """Windows 绝对路径 -> SQLAlchemy URL（统一正斜杠，空格转义）。"""
    return "sqlite+aiosqlite:///" + p.as_posix().replace(" ", "%20")


def _frozen_data_dir() -> Path | None:
    """PyInstaller 打包后：<root>/backend/FinKitBackend.exe -> <root>/data。"""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent.parent / "data"


def _auto_split_paths() -> tuple[str, str]:
    """未显式配置时自动发现已拆好的双库文件。

    优先级：冻结包的 data/ 目录 > backend/ 目录。
    public 存在即启用双库；private 允许不存在（首次启动由 create_all 建空库）。
    """
    candidates = []
    frozen = _frozen_data_dir()
    if frozen:
        candidates.append(frozen)
    candidates.append(BACKEND_DIR)

    for base in candidates:
        pub = base / "finkit_public.db"
        prv = base / "finkit_private.db"
        if pub.exists():
            return _sqlite_url(pub), _sqlite_url(prv)
    return "", ""


_AUTO_PUBLIC, _AUTO_PRIVATE = _auto_split_paths()


class Settings(BaseSettings):
    # env_file 用绝对路径：无论从哪个 cwd 起服务都能读到 backend/.env
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    # 双库拆分：public（标/因子/策略骨架） + private（用户/交易/持仓/回测结果/信号）。
    # 未设置时自动发现 backend/ 下（或冻结包 data/ 下）的 finkit_public.db /
    # finkit_private.db，都找不到才回退单库 DATABASE_URL（开发期兼容）。
    PUBLIC_DATABASE_URL: str = ""
    PRIVATE_DATABASE_URL: str = ""
    DATABASE_URL: str = _sqlite_url(BACKEND_DIR / "finkit.db")

    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    ENCRYPTION_KEY: str = "dev-encryption-key-change-in-production"


settings = Settings()

# 显式环境变量优先级最高，其次 backend/.env，最后自动发现。
if not settings.PUBLIC_DATABASE_URL and not os.environ.get("PUBLIC_DATABASE_URL"):
    settings.PUBLIC_DATABASE_URL = _AUTO_PUBLIC
if not settings.PRIVATE_DATABASE_URL and not os.environ.get("PRIVATE_DATABASE_URL"):
    settings.PRIVATE_DATABASE_URL = _AUTO_PRIVATE


def _resolve_public_url() -> str:
    return settings.PUBLIC_DATABASE_URL or settings.DATABASE_URL


def _resolve_private_url() -> str:
    return settings.PRIVATE_DATABASE_URL or settings.DATABASE_URL


def is_split_mode() -> bool:
    pub = _resolve_public_url()
    prv = _resolve_private_url()
    return bool(pub and prv and pub != prv)


def describe_db_mode() -> str:
    """启动日志用：一行说清当前连的哪两个库。"""
    if is_split_mode():
        return (f"[db] 双库模式 | public={_resolve_public_url()} "
                f"| private={_resolve_private_url()}")
    return f"[db] 单库模式 | {_resolve_public_url()}"
