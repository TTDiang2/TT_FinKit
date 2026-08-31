from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_private_db, get_public_db
from ..schemas.backtest import BacktestCreate, BacktestResponse, BacktestResult
from ..services.backtest_service import (
    create_backtest, get_backtest, list_backtests, update_backtest_status, delete_backtest
)
from ..services.backtest_engine import run_backtest_in_subprocess, load_benchmark_series
import json

router = APIRouter(prefix="/api/backtests", tags=["backtests"])

# Keep strong references to in-flight background tasks so the event loop
# does not garbage-collect them mid-run.
_background_tasks: set = set()


_HEAVY_RESULT_KEYS = ("nav_series", "weight_history", "rebalance_records",
                      "factor_exposure_series", "risk_view", "benchmark")


def _backtest_to_response(bt, strategy_name: str | None = None,
                          factor_keys: list[str] | None = None,
                          group_meta: list[dict] | None = None,
                          heavy: bool = False) -> BacktestResponse:
    from ..schemas.backtest import BacktestGroupMeta
    results = json.loads(bt.results) if bt.results else None
    if results and not heavy:
        # 列表场景只留指标与轻量元信息。曾因返回全量 nav/weights（27 条回测
        # ≈8.8MB、60s 计算）把 UI 轮询和数据库一起拖死（2026-08-29）。
        results = {k: v for k, v in results.items() if k not in _HEAVY_RESULT_KEYS}
    group_ids = json.loads(bt.group_ids) if getattr(bt, "group_ids", None) else []
    resp = BacktestResponse(
        id=bt.id,
        strategy_id=bt.strategy_id,
        strategy_name=strategy_name,
        strategy_version=bt.strategy_version,
        params=json.loads(bt.params or "{}"),
        universe=json.loads(bt.universe or "[]"),
        universe_count=getattr(bt, "universe_count", 0) or len(json.loads(bt.universe or "[]")),
        group_ids=group_ids,
        group_names=[BacktestGroupMeta(**g) for g in (group_meta or [])],
        start_date=bt.start_date,
        end_date=bt.end_date,
        rebalance_freq=bt.rebalance_freq,
        data_as_of=bt.data_as_of,
        status=bt.status,
        progress=int(round((getattr(bt, "progress", 0) or 0) * 100)),
        error=bt.error,
        results=results,
        factor_keys=factor_keys,
        created_at=str(bt.created_at),
        updated_at=str(bt.updated_at),
    )
    return resp

@router.get("", response_model=list[BacktestResponse])
async def list_backtests_endpoint(limit: int = Query(50),
                                  heavy: bool = Query(False,
                                      description="true=返回全量结果（详情页用）；默认只回指标"),
                                  db: AsyncSession = Depends(get_private_db),
                                  pub: AsyncSession = Depends(get_public_db)):
    backtests = await list_backtests(db, limit)
    # Batch-load strategy names + factor_keys for all backtests
    strat_ids = list({bt.strategy_id for bt in backtests})
    strats = {}
    if strat_ids:
        from app.models.strategy import Strategy
        rows = (await pub.execute(
            select(Strategy.id, Strategy.name, Strategy.factor_keys)
            .where(Strategy.id.in_(strat_ids))
        )).all()
        strats = {r[0]: (r[1], json.loads(r[2]) if r[2] else None) for r in rows}
    out = []
    for bt in backtests:
        name, fkeys = strats.get(bt.strategy_id, (None, None))
        gmeta = await _resolve_group_meta(db, json.loads(bt.group_ids) if getattr(bt, "group_ids", None) else [])
        out.append(_backtest_to_response(bt, strategy_name=name, factor_keys=fkeys,
                                        group_meta=gmeta, heavy=heavy))
    return out


async def _resolve_group_meta(db: AsyncSession, group_ids: list[str]) -> list[dict]:
    """把 group_id 列表解析为 {id, name, member_count} 元信息；不存在则跳过。"""
    if not group_ids:
        return []
    from ..models.research_group import ResearchGroup
    rows = (await db.execute(
        select(ResearchGroup).where(ResearchGroup.id.in_(group_ids))
    )).scalars().all()
    out = []
    for g in rows:
        out.append({"id": g.id, "name": g.name, "member_count": len(g.asset_ids)})
    return sorted(out, key=lambda x: group_ids.index(x["id"]) if x["id"] in group_ids else 999)


def _universe_hard_cap() -> int:
    """回测标的池硬上限，可用环境变量 FINKIT_BACKTEST_UNIVERSE_CAP 覆盖。

    默认 25000：覆盖当前全池（18891 只）并留余量。
    数量大不再禁止，只给提示；这里拦的是明显手误/异常量级。
    """
    import os
    try:
        return max(1000, int(os.environ.get("FINKIT_BACKTEST_UNIVERSE_CAP", "25000")))
    except ValueError:
        return 25000


def _universe_warning(count: int) -> str | None:
    """标的数量分级提示——只如实告知耗时/内存，不阻止执行。"""
    if count > 10000:
        return (
            f"⚠ 标的池 {count} 只（接近全市场），预计占用 4GB 以上内存、"
            f"耗时可能达数十分钟。期间请勿关闭窗口；内存不足 16GB 建议分批回测。"
        )
    if count > 2000:
        return (
            f"⚠ 标的池 {count} 只较大，可能占用 1~4GB 内存，回测耗时分钟级。"
        )
    if count > 500:
        return f"标的池 {count} 只较多，预计耗时数十秒到数分钟。"
    return None


@router.post("", response_model=BacktestResponse)
async def create_backtest_endpoint(req: BacktestCreate,
                                   db: AsyncSession = Depends(get_private_db),
                                   pub: AsyncSession = Depends(get_public_db)):
    from ..models.research_asset import ResearchAsset
    from ..models.research_group import ResearchGroupMember
    from ..models.strategy import Strategy

    strat = (await pub.execute(
        select(Strategy).where(Strategy.id == req.strategy_id, Strategy.version == req.strategy_version)
    )).scalar_one_or_none()
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # 多组合优先于单组合（group_ids 非空时覆盖 group_id）
    group_ids: list[str] = list(req.group_ids) if req.group_ids else ([req.group_id] if req.group_id else [])
    universe = list(req.universe)

    # 「全部入池标的」：直接按状态展开，前端不必传上万个代码
    if req.all_pooled:
        rows = await pub.execute(
            select(ResearchAsset.symbol).where(ResearchAsset.status == "pooled")
        )
        universe = sorted({r[0] for r in rows.all()})
    elif not universe and group_ids:
        rows = await pub.execute(
            select(ResearchAsset.symbol)
            .join(ResearchGroupMember, ResearchGroupMember.asset_id == ResearchAsset.id)
            .where(ResearchGroupMember.group_id.in_(group_ids),
                   ResearchAsset.status == "pooled")
        )
        universe = sorted({r[0] for r in rows.all()})
    if not universe:
        raise HTTPException(
            status_code=400,
            detail="universe 为空：请选择至少一个组合，或确认所选组合内有已入池标的",
        )

    if not group_ids and not req.all_pooled and req.universe:
        known = set((await pub.execute(
            select(ResearchAsset.symbol).where(ResearchAsset.symbol.in_(req.universe))
        )).scalars().all())
        unknown = [s for s in req.universe if s not in known]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"标的代码不存在或未入池：{', '.join(unknown)}（universe 请使用标的代码如 000300）",
            )

    cap = _universe_hard_cap()
    if len(universe) > cap:
        raise HTTPException(
            status_code=400,
            detail=f"标的池 {len(universe)} 只超过硬上限 {cap}。",
        )

    warning = _universe_warning(len(universe))

    bt = await create_backtest(
        db, strategy_id=req.strategy_id, strategy_version=req.strategy_version,
        params=req.params, universe=universe, start_date=req.start_date,
        end_date=req.end_date, rebalance_freq=req.rebalance_freq,
        group_ids=group_ids,
    )

    gmeta = await _resolve_group_meta(pub, group_ids)

    import asyncio
    task = asyncio.create_task(_run_backtest_async(
        bt.id, strat.code, req.params, universe, req.start_date,
        req.end_date, req.rebalance_freq,
    ))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    resp = _backtest_to_response(bt, group_meta=gmeta)
    if warning:
        resp.warning = warning
    return resp


async def _run_backtest_async(backtest_id: str, strategy_code: str, params: dict,
                             universe: list[str], start_date: str, end_date: str,
                             rebalance_freq: str):
    """带进度的回测执行：sync 线程里 _run_backtest_sync 通过 daemon 线程读子进程
    progress 文件 → 回调 on_progress(p)；此协程起独立线程把进度周期写库。
    """
    import threading
    import time
    progress_state = {"value": 0.0}

    def _on_progress(p: float):
        progress_state["value"] = p

    def _persist_loop():
        last = -1.0
        while True:
            time.sleep(3)
            p = progress_state["value"]
            if p == last:
                if p >= 1.0:
                    break
                continue
            last = p
            try:
                await_progress(backtest_id, p)
            except Exception:
                pass
            if p >= 1.0:
                break

    progress_thread = threading.Thread(target=_persist_loop, daemon=True)
    progress_thread.start()

    from ..database import async_session_maker
    async with async_session_maker() as db:
        try:
            result = await run_backtest_in_subprocess(
                strategy_code=strategy_code,
                params=params,
                universe=universe,
                start_date=start_date,
                end_date=end_date,
                rebalance_freq=rebalance_freq,
                db_path="finkit.db",
                backtest_id=backtest_id,
                on_progress=_on_progress,
            )
            progress_state["value"] = 1.0
            if result.get("status") == "ok":
                await update_backtest_status(db, backtest_id, "done", results=result, progress=1.0)
            else:
                await update_backtest_status(db, backtest_id, "failed",
                                              error=result.get("error", "backtest failed"))
        except Exception as e:
            await update_backtest_status(db, backtest_id, "failed", error=str(e))


def await_progress(backtest_id: str, progress: float) -> None:
    """独立线程入口：同步跑一个迷你 asyncio loop 写库。
    父协程被 to_thread 阻塞，无法 await；这里起一次性 loop 直连 DB。"""
    import asyncio as _aio
    from ..database import async_session_maker
    from ..services.backtest_service import update_backtest_status
    from datetime import datetime
    from sqlalchemy import select
    from ..models.backtest import Backtest

    async def _go():
        async with async_session_maker() as db:
            await update_backtest_status(db, backtest_id, "running", progress=progress)
            bt = (await db.execute(
                select(Backtest).where(Backtest.id == backtest_id)
            )).scalar_one_or_none()
            if bt:
                bt.last_heartbeat = datetime.utcnow()
                await db.commit()
    _aio.run(_go())

@router.get("/benchmark")
async def get_benchmark(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
):
    """CSI300 benchmark series for a date range.

    Lets OLD backtest results (created before benchmark was embedded) render
    the excess-return / rolling-alpha-beta charts without a re-run.
    """
    bench = load_benchmark_series("finkit.db", start, end)
    if not bench:
        raise HTTPException(status_code=404, detail="基准因子(equity)无该区间数据")
    return bench


@router.get("/{backtest_id}", response_model=BacktestResponse)
async def get_backtest_endpoint(backtest_id: str,
                                parts: str = Query("core",
                                    description="core=轻量（指标+摘要）| all=全量（旧客户端兼容）"),
                                db: AsyncSession = Depends(get_private_db)):
    """回测详情分段加载：parts=core 只回指标与轻量视图（毫秒级）；
    nav/weights/trades 等重载荷由 /{id}/part/{name} 按需拉取。"""
    bt = await get_backtest(db, backtest_id)
    if not bt:
        raise HTTPException(status_code=404, detail="Backtest not found")
    # Fetch strategy name + factor_keys for detail page
    from app.models.strategy import Strategy
    strat = (await pub.execute(
        select(Strategy.name, Strategy.factor_keys).where(Strategy.id == bt.strategy_id)
    )).first()
    sname = strat[0] if strat else None
    fkeys = json.loads(strat[1]) if strat and strat[1] else None
    heavy = parts == "all"
    resp = _backtest_to_response(bt, strategy_name=sname, factor_keys=fkeys, heavy=not heavy)
    if not heavy:
        # core 模式附带分段可用性标记，前端据此按需拉取
        resp.results = resp.results or {}
        resp.results["available_parts"] = sorted(
            k for k in resp.results.keys() if k not in ("available_parts",))
    return resp

@router.get("/{backtest_id}/part/{name}")
async def get_backtest_part(backtest_id: str, name: str,
                            db: AsyncSession = Depends(get_private_db)):
    """按需拉取单个重载荷：nav_series / weight_history / rebalance_records /
    factor_exposure_series / risk_view / benchmark。"""
    allowed = {"nav_series", "weight_history", "rebalance_records",
               "factor_exposure_series", "risk_view", "benchmark"}
    if name not in allowed:
        raise HTTPException(status_code=400, detail=f"未知 part：{name}")
    bt = await get_backtest(db, backtest_id)
    if not bt:
        raise HTTPException(status_code=404, detail="Backtest not found")
    results = json.loads(bt.results) if bt.results else {}
    return {name: results.get(name)}


@router.get("/{backtest_id}/status")
async def get_backtest_status_endpoint(backtest_id: str, db: AsyncSession = Depends(get_private_db)):
    bt = await get_backtest(db, backtest_id)
    if not bt:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return {"status": bt.status, "error": bt.error}

@router.delete("/{backtest_id}")
async def delete_backtest_endpoint(backtest_id: str, db: AsyncSession = Depends(get_private_db)):
    ok = await delete_backtest(db, backtest_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return {"status": "ok"}
