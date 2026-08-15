from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .database import engine, Base
from .routers import auth, accounts, categories, tags, transactions, statistics, reports, settings, assets, investments, ai_presets, ai_export, ai_investment, reconciliation

# Built frontend (frontend/dist) — served by the backend so the whole app
# runs on a single port (http://127.0.0.1:8000). Used by the desktop build.
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

app = FastAPI(title="FinKit API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
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


@app.on_event("startup")
async def on_startup():
    from .database import engine
    from .migrations import run_lightweight_migrations
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_lightweight_migrations(conn)


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