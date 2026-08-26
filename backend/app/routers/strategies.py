from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas.strategy import (
    StrategyCreate, StrategyResponse,
    StrategyImportResult, StrategyParseRequest, StrategyMoveRequest,
    ActiveStrategySet, ActiveStrategyResponse,
)
from ..services.strategy_service import (
    list_strategies, get_strategy, import_strategy,
    delete_strategy_version, validate_strategy_code,
)
from ..services.strategy_meta import parse_strategy_docstring
from ..models.backtest import Backtest
from ..models.strategy import Strategy
import datetime
import json

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

# 策略文件夹扫描路径（P4 约定，见 docs/plans/2026-08-23-... P4.2）。
# 动态定位到仓库根下的 strategies/（避免硬编码绝对路径在换机器后失效）。
STRATEGIES_DIR = Path(__file__).resolve().parents[3] / "strategies"


def _factor_keys_from_str(raw: str | None) -> list[str]:
    """把 strategies.factor_keys 的 JSON 字符串解析为 list[str]。"""
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except Exception:
        return []


async def _latest_backtest(db: AsyncSession, strategy_id: str) -> dict | None:
    """查询该策略最新一条 done 状态回测，摘取 metrics 摘要。"""
    result = await db.execute(
        select(Backtest)
        .where(Backtest.strategy_id == strategy_id, Backtest.status == "done")
        .order_by(desc(Backtest.created_at))
        .limit(1)
    )
    bt = result.scalar_one_or_none()
    if not bt:
        return None
    metrics = {}
    try:
        metrics = (json.loads(bt.results or "{}") or {}).get("metrics") or {}
    except Exception:
        metrics = {}
    return {
        "id": bt.id,
        "created_at": str(bt.created_at),
        "ann_return": metrics.get("ann_return"),
        "ann_volatility": metrics.get("ann_volatility"),
        "sharpe": metrics.get("sharpe"),
        "max_drawdown": metrics.get("max_drawdown"),
    }


def _strategy_to_response(s, latest_backtest: dict | None = None) -> StrategyResponse:
    return StrategyResponse(
        id=s.id, name=s.name, description=s.description,
        version=s.version,
        params_schema=json.loads(s.params_schema or "{}"),
        rebalance_freq=s.rebalance_freq,
        is_builtin=s.is_builtin,
        folder=s.folder or "",
        factor_keys=_factor_keys_from_str(s.factor_keys),
        source_file=s.source_file,
        activated_at=str(s.activated_at) if s.activated_at else None,
        version_note=getattr(s, "version_note", None),
        logic=getattr(s, "logic", None),
        latest_backtest=latest_backtest,
        created_at=str(s.created_at), updated_at=str(s.updated_at),
    )


@router.get("", response_model=list[StrategyResponse])
async def list_strategies_endpoint(
    folder: str | None = None,
    sort: str = "created_at_desc",
    db: AsyncSession = Depends(get_db),
):
    """List all strategies. Returns latest version per strategy name.

    - folder: 精确匹配过滤（None 时不过滤，前端自行分组）
    - sort: created_at_asc | created_at_desc（默认 desc），先按 created_at 排序再按 name 去重保最新版本
    """
    all_versions = await list_strategies(db, folder=folder, sort=sort)
    # deduplicate by name, keep latest version (first occurrence wins after sort)
    seen = {}
    for s in all_versions:
        if s.name not in seen:
            seen[s.name] = s
    result = []
    for s in seen.values():
        lb = await _latest_backtest(db, s.id)
        result.append(_strategy_to_response(s, latest_backtest=lb))
    return result


def _merge_meta_fields(req: StrategyCreate, doc_meta: dict) -> tuple[str, str, str, list[str]]:
    """表单值非空则表单优先，否则采用 docstring 解析值。

    返回 (name, description, rebalance_freq, factor_keys_deduped)。
    """
    name = req.name.strip() or (doc_meta.get("name") or "").strip() or "未命名策略"
    description = req.description.strip() or (doc_meta.get("description") or "")
    rebalance_freq = req.rebalance_freq or (doc_meta.get("rebalance_freq") or "monthly")
    # factor_keys 取并集去重
    merged: list[str] = []
    seen: set[str] = set()
    for key in (list(req.factor_keys or []) + list(doc_meta.get("factor_keys") or [])):
        key = str(key).strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(key)
    return name, description, rebalance_freq, merged


@router.post("/import", response_model=StrategyImportResult)
async def import_strategy_endpoint(req: StrategyCreate, db: AsyncSession = Depends(get_db)):
    valid, msg = validate_strategy_code(req.code)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid strategy code: {msg}")

    doc_meta = parse_strategy_docstring(req.code)
    name, description, rebalance_freq, factor_keys = _merge_meta_fields(req, doc_meta)

    strat, status = await import_strategy(
        db, name=name, code=req.code, description=description,
        params_schema=req.params_schema, rebalance_freq=rebalance_freq,
        folder=req.folder or "", factor_keys=factor_keys,
        source_file=req.source_file,
        version_note=doc_meta.get("version_note"),
        logic=doc_meta.get("logic"),
    )
    return StrategyImportResult(strategy_id=strat.id, version=strat.version, status=status)


@router.post("/parse-docstring")
async def parse_docstring_endpoint(req: StrategyParseRequest):
    """轻量解析策略代码 docstring 元数据（只解析不落库）。"""
    return parse_strategy_docstring(req.code)


@router.post("/import-folder")
async def import_folder_endpoint(db: AsyncSession = Depends(get_db)):
    """扫描 strategies/ 目录，逐个导入 *.py 文件。

    返回 {imported: [{file, strategy_id, version, name}], errors: [{file, error}]}。
    """
    strategies_dir = STRATEGIES_DIR
    if not strategies_dir.is_dir():
        strategies_dir.mkdir(parents=True, exist_ok=True)
        return {"imported": [], "errors": []}

    imported: list[dict] = []
    errors: list[dict] = []
    for path in sorted(strategies_dir.glob("*.py")):
        try:
            code = path.read_text(encoding="utf-8", errors="replace")
            valid, msg = validate_strategy_code(code)
            if not valid:
                raise ValueError(f"Invalid strategy code: {msg}")
            doc_meta = parse_strategy_docstring(code)
            name = (doc_meta.get("name") or "").strip() or path.stem
            description = doc_meta.get("description") or ""
            rebalance_freq = doc_meta.get("rebalance_freq") or "monthly"
            factor_keys = [k for k in (doc_meta.get("factor_keys") or []) if k]
            strat, _status = await import_strategy(
                db, name=name, code=code, description=description,
                params_schema={}, rebalance_freq=rebalance_freq,
                folder="", factor_keys=factor_keys, source_file=path.name,
                version_note=doc_meta.get("version_note"),
                logic=doc_meta.get("logic"),
            )
            imported.append({
                "file": path.name,
                "strategy_id": strat.id,
                "version": strat.version,
                "name": strat.name,
            })
        except Exception as e:
            errors.append({"file": path.name, "error": str(e)})
    return {"imported": imported, "errors": errors}


@router.post("/active")
async def set_active_strategy(req: ActiveStrategySet, db: AsyncSession = Depends(get_db)):
    """Activate a strategy (persisted; single-active — the previous one is cleared).

    The live signal engine (POST /api/signals/run) runs THIS strategy.
    """
    strat = await get_strategy(db, req.strategy_id, req.version)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await db.execute(update(Strategy).values(activated_at=None))
    strat.activated_at = datetime.datetime.utcnow()
    await db.commit()
    return {"status": "ok"}

@router.delete("/active")
async def clear_active_strategy(db: AsyncSession = Depends(get_db)):
    """Deactivate whatever strategy is currently active."""
    await db.execute(update(Strategy).values(activated_at=None))
    await db.commit()
    return {"status": "ok"}

@router.get("/active", response_model=ActiveStrategyResponse | None)
async def get_active_strategy(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Strategy)
        .where(Strategy.activated_at.isnot(None))
        .order_by(Strategy.activated_at.desc())
        .limit(1)
    )
    strat = result.scalar_one_or_none()
    if not strat:
        return None
    return ActiveStrategyResponse(
        strategy_id=strat.id, version=strat.version, params={},
        name=strat.name, description=strat.description,
        rebalance_freq=strat.rebalance_freq,
    )

@router.post("/{strategy_id}/move")
async def move_strategy_endpoint(
    strategy_id: str,
    req: StrategyMoveRequest,
    db: AsyncSession = Depends(get_db),
):
    """把策略（同名的所有版本）移动到指定文件夹。

    收纳箱即 folder='__archive__'；移出到根即 folder=''。
    """
    strat = await get_strategy(db, strategy_id)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await db.execute(
        update(Strategy).where(Strategy.name == strat.name).values(folder=req.folder)
    )
    await db.commit()
    updated = await get_strategy(db, strategy_id)
    lb = await _latest_backtest(db, strategy_id)
    return _strategy_to_response(updated, latest_backtest=lb)

@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy_endpoint(
    strategy_id: str,
    version: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    strat = await get_strategy(db, strategy_id, version)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")
    lb = await _latest_backtest(db, strategy_id)
    return _strategy_to_response(strat, latest_backtest=lb)

@router.delete("/{strategy_id}/{version}")
async def delete_strategy_version_endpoint(
    strategy_id: str, version: int,
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_strategy_version(db, strategy_id, version)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot delete this version")
    return {"status": "ok"}
