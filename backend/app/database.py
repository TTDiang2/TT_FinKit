from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from .config import settings, _resolve_public_url, _resolve_private_url


def _make_engine(url: str):
    return create_async_engine(
        url, echo=False, future=True,
        connect_args={"timeout": 30}, pool_pre_ping=True, pool_recycle=1800,
    )


public_engine = _make_engine(_resolve_public_url())
private_engine = _make_engine(_resolve_private_url())
public_session_maker = async_sessionmaker(public_engine, class_=AsyncSession, expire_on_commit=False)
private_session_maker = async_sessionmaker(private_engine, class_=AsyncSession, expire_on_commit=False)
# 兼容别名：保留旧代码里的 `from app.database import engine`/`async_session_maker`。
# 拆库前所有路由都连 private（含信号/回测），所以别名指向 private。
engine = private_engine
async_session_maker = private_session_maker

# 单一 Base 包含所有 model（按 __public__ / __private__ 标记路由到不同 engine）。
# 单库模式下两 engine 都指向同一文件，IF NOT EXISTS 自然去重；
# 多库运行时 public 表随 public_session_maker 走、private 表走 private。
Base = declarative_base()
PublicBase = Base
PrivateBase = Base


def _is_split() -> bool:
    """是否双库运行时：两个 URL 配置且不全相等。"""
    pub = settings.PUBLIC_DATABASE_URL or settings.DATABASE_URL
    prv = settings.PRIVATE_DATABASE_URL or settings.DATABASE_URL
    return bool(pub and prv and pub != prv)


async def get_public_db():
    """公共库 session（标/因子/策略骨架）—— 可随 release 发出去。"""
    async with public_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_private_db():
    """私人库 session（用户/交易/持仓/回测结果/信号）—— 永不 release。"""
    async with private_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# 兼容：开发单库模式下 get_db 默认走 private（私人表是多数路径）。
# 发行模式下 router 按 path 前缀选 get_public_db 或 get_private_db。
get_db = get_private_db


async def create_all_tables():
    """双引擎建表：单库模式下两引擎指向同一文件，IF NOT EXISTS 自然去重；
    多库模式下按 model.__public__ 标记分发到对应 engine。

    单 Base metadata 同时持有所有表元数据；create_all 只创建带 flag 的表。
    双库模式下：先 private engine 建非公开表，再 public engine 建公开表；
    同一个 Sqlite 文件被两个 engine 连两次时，同名表 IF NOT EXISTS 自动跳过。
    """
    # 公开表子集
    public_tables = [t for t in Base.metadata.sorted_tables
                     if getattr(t, "info", {}).get("public")]
    # 私有表 = 其余
    private_tables = [t for t in Base.metadata.sorted_tables
                      if t not in public_tables]

    def _create_subset(conn, tables):
        # 临时替换 metadata.create_all 行为：只创建指定子集
        # SQLAlchemy 没提供 partial create；通过反射临时修改 metadata 的 tables 集合
            # 更稳：直接对每个表执行 ensure create
        from sqlalchemy import Table as _T
        for tbl in tables:
            tbl.create(conn.sync_engine, checkfirst=True)

    async with private_engine.begin() as conn:
        await conn.run_sync(_create_subset, private_tables)
    async with public_engine.begin() as conn:
        await conn.run_sync(_create_subset, public_tables)