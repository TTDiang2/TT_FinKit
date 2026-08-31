from typing import List, Optional

import asyncio
import json
import re
from calendar import monthrange
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text

import logging as _importlog
_importlog.getLogger("uvicorn.error").info("[factors] MODULE IMPORTED (new code)")
print("[factors] MODULE IMPORTED (new code)", flush=True)
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_public_db, async_session_maker
from ..models.factor import Factor, FactorValue, FactorExposure
from ..models.research_asset import ResearchAsset
from ..schemas.factor import (
    AgentFactorCandidate,
    AgentGenerateRequest,
    AgentPreviewRequest,
    AgentPreviewResult,
    ContributionResult,
    ExposureCell,
    ExposureHistoryPoint,
    ExposureMatrix,
    AssetExposureRow,
    FactorConfig,
    FactorCreate,
    FactorDetail,
    FactorResponse,
    FactorStat,
    FactorSyncResult,
    FactorUpdate,
    FactorValuePoint,
)
from ..middleware.auth import get_current_user_id
from ..services import ifind_client
from ..services.factor_store import (
    factor_stats,
    refresh_all_factors,
    seed_preset_factors,
    sync_factor_values,
)
from ..services.factor_engine import compute_contribution, recompute_exposures
from ..services import factor_sync as fs_sync

router = APIRouter(prefix="/api/research/factors", tags=["research-factors"])

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _expand_month_bound(s: str) -> tuple[str, str]:
    """'YYYY-MM' -> ('YYYY-MM-01', 'YYYY-MM-last'); full dates pass through.

    Frontend month pickers send YYYY-MM; exposures are stored at the LAST
    trading day of a month (e.g. 2026-08-20), so an exact-equality or
    first-of-month comparison would never match.  Month semantics: any as_of
    within that calendar month.
    """
    if _MONTH_RE.match(s or ""):
        y, m = int(s[:4]), int(s[5:7])
        return f"{s}-01", f"{s}-{monthrange(y, m)[1]:02d}"
    return s, s


async def _respond(db: AsyncSession, factor: Factor) -> FactorResponse:
    latest_return, latest_level, latest_date, rows = await factor_stats(db, factor)
    cfg = None
    if factor.config:
        try:
            cfg = FactorConfig.model_validate_json(factor.config)
        except Exception:
            cfg = None
    return FactorResponse(
        id=factor.id,
        name=factor.name,
        key=factor.key or "",
        category=factor.category,
        definition=factor.definition,
        code=factor.code,
        data_source=factor.data_source or "",
        frequency=factor.frequency or "daily",
        proxy_symbol=factor.proxy_symbol or "",
        config=cfg,
        is_market=bool(factor.is_market),
        active=bool(factor.active),
        version=factor.version or 1,
        data_status=factor.data_status or "ok",
        stats=FactorStat(
            latest_value=latest_return,
            latest_level=latest_level,
            latest_date=latest_date,
            rows=rows,
        ),
    )


async def _get_factor(factor_id: str, db: AsyncSession) -> Factor:
    factor = await db.get(Factor, factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="因子不存在")
    return factor


# ---------------- list / create (static) ----------------


@router.get("", response_model=List[FactorResponse])
async def list_factors(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_public_db),
):
    await seed_preset_factors(db)
    q = select(Factor).order_by(Factor.category, Factor.created_at)
    if category:
        q = q.where(Factor.category == category)
    factors = (await db.execute(q)).scalars().all()
    return [await _respond(db, f) for f in factors]


@router.post("", response_model=FactorResponse)
async def create_factor(
    body: FactorCreate,
    db: AsyncSession = Depends(get_public_db),
):
    exists = (await db.execute(select(Factor).where(Factor.name == body.name))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail=f"因子 {body.name} 已存在")
    factor = Factor(
        name=body.name,
        category=body.category,
        definition=body.definition,
        data_source=body.data_source or "ifind/eastmoney",
        proxy_symbol=body.config.symbol or "",
        config=body.config.model_dump_json(exclude_none=True),
        is_market=body.is_market,
    )
    db.add(factor)
    await db.commit()
    return await _respond(db, factor)


# ---------------- aggregate operations (static, before /{factor_id}) ----------------


@router.post("/refresh-all", response_model=List[FactorSyncResult])
async def refresh_all(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    await seed_preset_factors(db)
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    results = await refresh_all_factors(db, ifind_user, ifind_pass)

    # monthly auto-fill: if this calendar month has no exposure rows at all,
    # run the latest-month recompute (first daily refresh of the month)
    month_prefix = date.today().strftime("%Y-%m")
    has_current = (await db.execute(
        select(FactorExposure.id).where(FactorExposure.as_of_date.like(f"{month_prefix}%")).limit(1)
    )).first()
    exposure_summary = None
    if not has_current:
        exposure_summary = await recompute_exposures(db, user_id, full=False)
    return results


@router.get("/exposure-matrix", response_model=ExposureMatrix)
@router.get("/exposure-months")
async def exposure_months(user_id: str = Depends(get_current_user_id),
                          db: AsyncSession = Depends(get_public_db)):
    """可用的暴露快照月份（倒序）——供前端月份选择器。"""
    rows = (await db.execute(
        text("SELECT as_of_date, COUNT(*) AS n FROM factor_exposures GROUP BY as_of_date "
             "HAVING n >= 1000 ORDER BY as_of_date DESC")
    )).all()
    months = sorted({str(r[0])[:7] for r in rows}, reverse=True)
    latest = rows[0][0] if rows else None
    return {"months": months, "latest": latest}


async def exposure_matrix(
    as_of: Optional[str] = Query(None, description="YYYY-MM（该月任一月末）或 YYYY-MM-DD；默认最新"),
    symbols: Optional[str] = Query(None, description="逗号分隔标的代码，优先于 group/search/limit"),
    group_id: Optional[str] = Query(None, description="标的组合 id"),
    search: Optional[str] = Query(None, description="名称/代码模糊搜索"),
    limit: int = Query(50, ge=1, le=500, description="单页资产数（矩阵行数）"),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    from ..services.matrix_debug import debug_log
    debug_log(f"called as_of={as_of!r} symbols={symbols!r} group={group_id!r} search={search!r} limit={limit} offset={offset}")
    await seed_preset_factors(db)
    factors = (await db.execute(
        select(Factor).where(Factor.active.is_(True)).order_by(Factor.category, Factor.created_at)
    )).scalars().all()
    debug_log(f"factors={len(factors)}")

    # 资产筛选：symbols > group_id > search，全部命中后按 limit/offset 分页。
    # 全池 3813 资产 × 70 因子的全量矩阵曾把响应撑到几十 MB/分钟级（UI 15s 必超时，
    # 用户看到的是"暂无暴露数据"——实为 axios 静默吞了超时）。
    aq = select(ResearchAsset).where(
        ResearchAsset.user_id == user_id, ResearchAsset.status == "pooled")
    sym_list = [x.strip() for x in (symbols or "").split(",") if x.strip()]
    if sym_list:
        aq = aq.where(ResearchAsset.symbol.in_(sym_list))
    elif group_id:
        from app.models.research_group import ResearchGroupMember
        member_ids = select(ResearchGroupMember.asset_id).where(
            ResearchGroupMember.group_id == group_id)
        aq = aq.where(ResearchAsset.id.in_(member_ids))
    elif search:
        like = f"%{search}%"
        aq = aq.where((ResearchAsset.name.like(like)) | (ResearchAsset.symbol.like(like)))
    total_assets = (await db.execute(
        select(func.count()).select_from(aq.subquery()))).scalar_one()
    assets = (await db.execute(
        aq.order_by(ResearchAsset.created_at).offset(offset).limit(limit)
    )).scalars().all()
    debug_log(f"total_assets={total_assets} page_assets={len(assets)}")
    if not factors or not assets:
        return ExposureMatrix(as_of=as_of, factors=list(factors), assets=[],
                              total_assets=total_assets)

    q = select(FactorExposure).where(FactorExposure.asset_id.in_([a.id for a in assets]))
    if as_of and _MONTH_RE.match(as_of):
        # month semantics: any month-end as_of inside that calendar month;
        # resolve to the LATEST one present so the matrix shows one snapshot
        month_first, month_last = _expand_month_bound(as_of)
        q = q.where(FactorExposure.as_of_date >= month_first,
                    FactorExposure.as_of_date <= month_last)
    elif as_of:
        q = q.where(FactorExposure.as_of_date == as_of)
    else:
        # "最新"= 行数充足的最大日期（每日自动补录会造出只有几行的杂散 as_of，
        # 直接 MAX 会选中它们导致矩阵看似为空）
        latest = (await db.execute(
            text("SELECT as_of_date FROM factor_exposures GROUP BY as_of_date "
                 "HAVING COUNT(*) >= 1000 ORDER BY as_of_date DESC LIMIT 1")
        )).scalar()
        if latest is None:
            return ExposureMatrix()
        q = q.where(FactorExposure.as_of_date == latest)
    rows = (await db.execute(q)).scalars().all()
    if as_of and _MONTH_RE.match(as_of) and rows:
        used = max(r.as_of_date for r in rows)
        rows = [r for r in rows if r.as_of_date == used]

    by_asset: dict[str, AssetExposureRow] = {}
    for a in assets:
        by_asset[a.id] = AssetExposureRow(
            asset_id=a.id, asset_name=a.name, symbol=a.symbol,
            is_money_market=bool(a.is_money_market),
        )
    for r in rows:
        row = by_asset.get(r.asset_id)
        if row is None:
            continue
        row.r2 = r.r2
        row.method = r.method
        row.n_samples = r.window_days
        row.cells[r.factor_id] = ExposureCell(
            beta=r.beta,
            t_stat=r.t_stat,
            significant=r.t_stat is not None and abs(r.t_stat) > 1.5,
        )
    used_as_of = as_of or (rows[0].as_of_date if rows else None)
    return ExposureMatrix(
        as_of=used_as_of,
        factors=[await _respond(db, f) for f in factors],
        assets=[r for r in by_asset.values() if r.cells],
        total_assets=total_assets,
    )


@router.get("/exposure-history", response_model=List[ExposureHistoryPoint])
async def exposure_history(
    asset_id: str = Query(...),
    factor_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_public_db),
):
    q = (
        select(FactorExposure, Factor)
        .join(Factor, FactorExposure.factor_id == Factor.id)
        .where(FactorExposure.asset_id == asset_id)
    )
    if factor_id:
        q = q.where(FactorExposure.factor_id == factor_id)
    rows = (await db.execute(q.order_by(FactorExposure.as_of_date))).all()
    return [
        ExposureHistoryPoint(
            as_of_date=fe.as_of_date,
            factor_id=fe.factor_id,
            factor_name=f.name,
            beta=fe.beta,
            t_stat=fe.t_stat,
            r2=fe.r2,
            method=fe.method,
        )
        for fe, f in rows
    ]


@router.post("/recompute-exposures")
async def recompute_exposures_endpoint(
    full: bool = Query(False),
    window_days: int = Query(252, ge=21, le=1260,
                            description="OLS 回归窗口长度 (trading days)。默认 252 ≈ 1 年"),
    asset_symbols: str = Query("", description="逗号分隔的标的 symbol；空 = 全部入池标的"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    symbols = [s.strip() for s in asset_symbols.split(",") if s.strip()] or None
    result = await recompute_exposures(db, user_id, full=full, window_days=window_days,
                                       asset_symbols=symbols)
    # chain factor evaluation (IC/ICIR) — pure numpy, fast after exposures exist
    from ..services.factor_evaluation import evaluate_all_factors
    try:
        eval_summary = await evaluate_all_factors(db, user_id)
        result["evaluation"] = eval_summary
    except Exception as e:
        result["evaluation"] = {"evaluated": [], "skipped": [], "error": f"{type(e).__name__}: {e}"}
    result["window_days"] = window_days
    return result


@router.post("/evaluate-all")
async def evaluate_all_factors_endpoint(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    from ..services.factor_evaluation import evaluate_all_factors
    return await evaluate_all_factors(db, user_id)


@router.get("/evaluations")
async def list_evaluations(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    from ..services.factor_evaluation import evaluation_to_dict, DEFAULT_THRESHOLDS
    from ..models.factor_evaluation import FactorEvaluation
    rows = (await db.execute(
        select(FactorEvaluation).where(FactorEvaluation.user_id == user_id)
    )).scalars().all()
    return {
        "thresholds": DEFAULT_THRESHOLDS,
        "evaluations": [evaluation_to_dict(r) for r in rows],
    }


@router.get("/contribution", response_model=ContributionResult)
async def contribution(
    asset_id: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    view: str = Query("return", pattern="^(return|risk)$"),
    db: AsyncSession = Depends(get_public_db),
):
    # 'YYYY-MM' month semantics: start -> month first day, end -> month LAST day
    # (exposures live at month-end trading days; a first-of-month end would find
    # no exposure rows on or before it for the current month)
    start_expanded, _ = _expand_month_bound(start)
    _, end_expanded = _expand_month_bound(end)
    try:
        return await compute_contribution(db, asset_id, start_expanded, end_expanded, view=view)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------- agent flows (static) ----------------

_AGENT_SYSTEM_PROMPT = """你是基金研究系统的因子构建助手。用户会用自然语言描述一个因子，你把它转换为结构化 JSON 定义。

只输出一个 JSON 对象（不要 markdown 代码块），字段：
- name: 因子名称，中文，带交易所代码后缀的形式如 "价值(中证价值)"
- category: asset_class | style | macro | custom 之一
- definition: 一句话中文定义，说明代理标的与计算口径
- config: {"type":"proxy","symbol":"<6位代码>","exchange":"SH"} 或 {"type":"spread","long":{"type":"proxy","symbol":"...","exchange":"SH"},"short":{"type":"proxy","symbol":"...","exchange":"SH"}}

规则：
- 只能使用中国场内可交易的指数或 ETF 代码（6 位数字，exchange 只能是 SH 或 SZ）
- proxy：单一标的日收益率就是因子收益率，适合大类资产因子（如 沪深300=权益、511010=利率债、518880=黄金）
- spread：long 日收益减 short 日收益，适合风格价差因子（如 小盘000852 减 大盘000300 = 规模）
- 不要编造不确定的代码；如果用户描述无法映射到具体代码，在 definition 里说明并选择最接近的流动性好的 ETF

示例1 — "帮我加一个中证500的中盘因子"：
{"name":"中盘(中证500)","category":"asset_class","definition":"A 股中盘权益因子，中证500 指数日收益率","config":{"type":"proxy","symbol":"000905","exchange":"SH"}}

示例2 — "加一个价值减成长的风格因子"：
{"name":"价值-成长(价差)","category":"style","definition":"价值风格价差因子：价值风格 ETF 日收益率减成长风格 ETF 日收益率","config":{"type":"spread","long":{"type":"proxy","symbol":"510050","exchange":"SH"},"short":{"type":"proxy","symbol":"510330","exchange":"SH"}}}
（示例2的代码仅为格式示意，实际请按你的知识选择合适标的）"""


@router.post("/agent/generate", response_model=AgentFactorCandidate)
async def agent_generate(
    body: AgentGenerateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    from ..services.ai_investment import _call_llm, _pick_preset

    preset = await _pick_preset(db, user_id)
    if preset is None:
        raise HTTPException(status_code=400, detail="未配置 AI 预设，请先在设置中添加")
    try:
        raw = await _call_llm(preset, _AGENT_SYSTEM_PROMPT, body.prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}")

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        obj = json.loads(text)
        candidate = AgentFactorCandidate.model_validate(obj)
    except Exception:
        raise HTTPException(status_code=422, detail=f"LLM 输出无法解析为因子定义: {raw[:500]}")

    exists = (await db.execute(select(Factor).where(Factor.name == candidate.name))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail=f"同名因子已存在: {candidate.name}")
    return candidate


async def _preview_config(
    cfg: FactorConfig,
    ifind_user: Optional[str],
    ifind_pass: Optional[str],
) -> AgentPreviewResult:
    from ..services.factor_store import _pull, _returns_from_levels

    begin = (date.today() - timedelta(days=90)).isoformat()
    end = date.today().strftime("%Y-%m-%d")
    try:
        if cfg.type == "proxy":
            if not cfg.symbol:
                return AgentPreviewResult(ok=False, error="proxy config missing symbol")
            levels, source = await _pull(cfg.symbol, cfg.exchange, begin, end, ifind_user, ifind_pass)
        else:
            if cfg.long is None or cfg.short is None:
                return AgentPreviewResult(ok=False, error="spread config missing long/short")
            long_levels, _ = await _pull(cfg.long.symbol, cfg.long.exchange, begin, end, ifind_user, ifind_pass)
            short_levels, _ = await _pull(cfg.short.symbol, cfg.short.exchange, begin, end, ifind_user, ifind_pass)
            long_map, short_map = dict(long_levels), dict(short_levels)
            common = sorted(set(long_map) & set(short_map))
            levels = [(d, long_map[d] - short_map[d]) for d in common]
            source = "spread"
    except Exception as e:
        return AgentPreviewResult(ok=False, error=f"数据拉取失败: {e}")

    if not levels:
        return AgentPreviewResult(ok=False, error=f"区间 {begin}~{end} 未取到数据，请检查代码")
    returns = _returns_from_levels(levels)
    return AgentPreviewResult(
        ok=True,
        sample_days=len(levels),
        first_date=levels[0][0],
        last_date=levels[-1][0],
        latest_level=levels[-1][1],
        latest_return=returns[-1][1] if returns else None,
        source=source,
    )


@router.post("/agent/preview", response_model=AgentPreviewResult)
async def agent_preview(
    body: AgentPreviewRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    return await _preview_config(body.candidate.config, ifind_user, ifind_pass)


@router.post("/agent/confirm", response_model=FactorResponse)
async def agent_confirm(
    body: AgentPreviewRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    candidate = body.candidate
    exists = (await db.execute(select(Factor).where(Factor.name == candidate.name))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail=f"同名因子已存在: {candidate.name}")
    factor = Factor(
        name=candidate.name,
        category=candidate.category,
        definition=candidate.definition,
        data_source="ifind/eastmoney",
        proxy_symbol=candidate.config.symbol or "",
        config=candidate.config.model_dump_json(exclude_none=True),
    )
    db.add(factor)
    await db.commit()

    # first full sync right away so the new factor is immediately usable
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    await sync_factor_values(db, factor, ifind_user, ifind_pass, full=True)
    return await _respond(db, factor)



# ---------------- factor sync engine (P1.2) ----------------

_sync_state: dict = {"running": False, "report": None}


def _serialize_report(report):
    if report is None:
        return None
    return {
        "per_factor": {
            k: {"rows": v.get("rows", 0), "first_date": v.get("first_date"),
                "error": v.get("error")}
            for k, v in (report.per_factor or {}).items()
        },
        "started_at": report.started_at.isoformat() if report.started_at else None,
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
        "pca": report.pca,
    }


async def _factor_sync_task(user_id: str) -> None:
    """Background factor sync - own session (request one is closed)."""
    try:
        report = await fs_sync.sync_all_factors(async_session_maker, user_id)
        _sync_state["report"] = report
        print(f"[factor_sync] done: {len(report.per_factor)} factors", flush=True)
    except Exception as e:
        print(f"[factor_sync] FAILED: {type(e).__name__}: {e}", flush=True)
    finally:
        _sync_state["running"] = False


@router.post("/sync-all")
async def sync_all(
    user_id: str = Depends(get_current_user_id),
):
    """Kick off a background factor sync; returns immediately."""
    if _sync_state["running"]:
        return {"started": True}
    _sync_state["running"] = True
    _sync_state["report"] = None
    asyncio.create_task(_factor_sync_task(user_id))
    return {"started": True}


@router.get("/sync-status")
async def sync_status():
    return {"running": _sync_state["running"],
            "last_report": _serialize_report(_sync_state["report"])}


# ---------------- per-factor routes (dynamic) ----------------


@router.get("/{factor_id}", response_model=FactorDetail)
async def factor_detail(
    factor_id: str,
    days: int = Query(365, ge=30, le=10000),
    db: AsyncSession = Depends(get_public_db),
):
    factor = await _get_factor(factor_id, db)
    base = await _respond(db, factor)
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    levels = (await db.execute(
        select(FactorValue)
        .where(FactorValue.factor_id == factor_id, FactorValue.kind == "level",
               FactorValue.date >= cutoff)
        .order_by(FactorValue.date)
    )).scalars().all()
    return FactorDetail(
        **base.model_dump(),
        level_series=[FactorValuePoint(date=v.date, value=v.value) for v in levels],
    )


@router.put("/{factor_id}", response_model=FactorResponse)
async def update_factor(
    factor_id: str,
    body: FactorUpdate,
    db: AsyncSession = Depends(get_public_db),
):
    factor = await _get_factor(factor_id, db)
    definition_changed = False
    if body.definition is not None and body.definition != factor.definition:
        factor.definition = body.definition
        definition_changed = True
    if body.config is not None:
        factor.config = body.config.model_dump_json(exclude_none=True)
        factor.proxy_symbol = body.config.symbol or factor.proxy_symbol
        definition_changed = True
    if body.active is not None:
        factor.active = body.active
    if body.is_market is not None:
        factor.is_market = body.is_market
    if definition_changed:
        factor.version = (factor.version or 1) + 1
    await db.commit()
    return await _respond(db, factor)


@router.delete("/{factor_id}", response_model=FactorResponse)
async def deactivate_factor(
    factor_id: str,
    db: AsyncSession = Depends(get_public_db),
):
    factor = await _get_factor(factor_id, db)
    factor.active = False
    await db.commit()
    return await _respond(db, factor)


@router.post("/{factor_id}/refresh", response_model=FactorSyncResult)
async def refresh_factor(
    factor_id: str,
    full: bool = Query(False),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    factor = await _get_factor(factor_id, db)
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    return await sync_factor_values(db, factor, ifind_user, ifind_pass, full=full)
