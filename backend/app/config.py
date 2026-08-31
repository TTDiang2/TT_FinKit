from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 双库拆分：public（标/因子/策略骨架） + private（用户/交易/持仓/回测结果/信号）。
    # 未设置时回退到单库 DATABASE_URL（开发期兼容）。
    PUBLIC_DATABASE_URL: str = ""
    PRIVATE_DATABASE_URL: str = ""
    DATABASE_URL: str = "sqlite+aiosqlite:///finkit.db"

    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    ENCRYPTION_KEY: str = "dev-encryption-key-change-in-production"


settings = Settings()


def _resolve_public_url() -> str:
    return settings.PUBLIC_DATABASE_URL or settings.DATABASE_URL


def _resolve_private_url() -> str:
    return settings.PRIVATE_DATABASE_URL or settings.DATABASE_URL