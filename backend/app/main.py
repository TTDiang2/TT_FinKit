from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .database import engine, Base
from .routers import auth, accounts, categories, tags, transactions, statistics, reports, settings, assets, investments, ai_presets, ai_export, ai_investment, reconciliation, research_asset_ai, research_assets, research_statistics, factors, strategies, backtests, signals, monitor, ai_advisor

# Built frontend (frontend/dist) — served by the backend so the whole app
# runs on a single port (http://127.0.0.1:8100). Used by the desktop build.
# Ports are offset from TT_Calendar (backend 8000 / Vite 5173) so both apps
# can run side by side.
# 冻结包（PyInstaller）里 dist 被打进 _MEIPASS/frontend/dist，路径随之改变；
# 桌面壳 FinKit.exe 打开的正是这个端口，所以这里必须能找到 SPA。
def _resolve_frontend_dist() -> Path:
    import sys
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "frontend" / "dist")
    candidates.append(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist")
    for c in candidates:
        if c.is_dir() and (c / "index.html").is_file():
            return c
    return candidates[-1]


FRONTEND_DIST = _resolve_frontend_dist()

app = FastAPI(title="FinKit API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5180", "http://localhost:3000", "http://127.0.0.1:5180"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(tags.router)
app.include_router(transactions.router)
app.include_router(statistics.router)
app.include_router(reports.router)
app.include_router(settings.router)
app.include_router(assets.router)
app.include_router(investments.router)
app.include_router(ai_presets.router)
app.include_router(ai_export.router)
app.include_router(ai_investment.router)
app.include_router(reconciliation.router)
app.include_router(research_asset_ai.router)   # BEFORE research_assets so /ai-reports/{id} isn't shadowed
app.include_router(research_assets.router)
app.include_router(research_statistics.router)  # /api/research/stats/snapshot
app.include_router(factors.router)
app.include_router(strategies.router)
app.include_router(backtests.router)
app.include_router(signals.router)
app.include_router(ai_advisor.router)
app.include_router(monitor.router)


@app.on_event("startup")
async def on_startup():
    from .database import (
        Base, public_engine, private_engine, _resolve_public_url, _resolve_private_url
    )
    from .migrations import run_lightweight_migrations

    # 标记公开表（在模型 import 完毕、create_all 之前）
    from .models._flags import _mark_public_tables
    _mark_public_tables()

    # 双库模式检测：两个 URL 都设置了且不等 → 按 public/private flag 分发建表
    pub_url = _resolve_public_url()
    prv_url = _resolve_private_url()
    from .config import describe_db_mode
    print(describe_db_mode(), flush=True)

    is_split = bool(pub_url and prv_url and pub_url != prv_url)

    public_tables = [t for t in Base.metadata.sorted_tables if t.info.get("public")]
    private_tables = [t for t in Base.metadata.sorted_tables if t not in public_tables]

    def _create_subset_sync(conn, tables):
        for tbl in tables:
            tbl.create(conn, checkfirst=True)

    if is_split:
        async with public_engine.begin() as conn:
            await conn.run_sync(_create_subset_sync, public_tables)
        async with private_engine.begin() as conn:
            await conn.run_sync(_create_subset_sync, private_tables)
    else:
        async with private_engine.begin() as conn:
            await conn.run_sync(_create_subset_sync, Base.metadata.sorted_tables)

    async with private_engine.begin() as conn:
        await conn.run_sync(Base.metadata.reflect)
        await run_lightweight_migrations(conn)

    # 每日自动信号（用户拍板 2026-08-29）：当日未跑过且有持仓 → 后台补跑。
    # 延迟执行不阻塞启动；失败静默（信号页可手动重跑）。
    import asyncio as _asyncio
    from .services.signal_run import maybe_run_daily_signal
    _asyncio.create_task(maybe_run_daily_signal())

    # 回测孤儿清扫：pending > 10min（子进程被 OOM/被杀卡死）→ 标 failed。
    # 防“永远卡在 pending”再次出现（用户 2026-08-30 那条 7714 只永久 pending 即此 bug）。
    from sqlalchemy import update as _upd, text as _txt
    from .database import async_session_maker
    from .models.backtest import Backtest as _Bt
    import datetime as _dt
    async def _sweep():
        cutoff = (_dt.datetime.utcnow() - _dt.timedelta(minutes=10)).isoformat()
        async with async_session_maker() as s:
            await s.execute(_upd(_Bt).where(_Bt.status == "pending", _Bt.created_at < cutoff)
                              .values(status="failed",
                                      error="启动清扫：pending 超过 10 分钟（子进程可能 OOM/被杀）",
                                      progress=0))
            await s.commit()
    _asyncio.create_task(_sweep())


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ---- Frontend (SPA) serving -------------------------------------------
# API routers are registered above, so they take precedence over the
# catch-all below. Unknown paths fall back to index.html (Vue Router).
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            # 带 hash 的静态资源（vite 输出，文件名即指纹）：长缓存
            if full_path.startswith("assets/"):
                return FileResponse(candidate, headers={
                    "Cache-Control": "public, max-age=31536000, immutable"
                })
            return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
        # index.html fallback：绝不缓存，保证每次拿到引用最新 chunk hash 的版本
        return FileResponse(FRONTEND_DIST / "index.html",
                            headers={"Cache-Control": "no-cache, must-revalidate"})
else:
    @app.get("/", include_in_schema=False)
    async def frontend_missing():
        return {"message": "Frontend not built. Run: cd frontend && npm run build"}