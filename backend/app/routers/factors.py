from typing import List, Optional

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
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

router = APIRouter(prefix="/api/research/factors", tags=["research-factors"])


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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
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
async def exposure_matrix(
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD month-end; default latest"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await seed_preset_factors(db)
    factors = (await db.execute(
        select(Factor).where(Factor.active.is_(True)).order_by(Factor.category, Factor.created_at)
    )).scalars().all()
    assets = (await db.execute(
        select(ResearchAsset).where(
            ResearchAsset.user_id == user_id, ResearchAsset.status == "pooled"
        ).order_by(ResearchAsset.created_at)
    )).scalars().all()
    if not factors or not assets:
        return ExposureMatrix()

    q = select(FactorExposure).where(FactorExposure.asset_id.in_([a.id for a in assets]))
    if as_of:
        q = q.where(FactorExposure.as_of_date == as_of)
    else:
        latest = (await db.execute(
            select(FactorExposure.as_of_date).order_by(FactorExposure.as_of_date.desc()).limit(1)
        )).scalar()
        if latest is None:
            return ExposureMatrix()
        q = q.where(FactorExposure.as_of_date == latest)
    rows = (await db.execute(q)).scalars().all()

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
    )


@router.get("/exposure-history", response_model=List[ExposureHistoryPoint])
async def exposure_history(
    asset_id: str = Query(...),
    factor_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
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
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await recompute_exposures(db, user_id, full=full)


@router.get("/contribution", response_model=ContributionResult)
async def contribution(
    asset_id: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    view: str = Query("return", pattern="^(return|risk)$"),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await compute_contribution(db, asset_id, start, end, view=view)
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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
):
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    return await _preview_config(body.candidate.config, ifind_user, ifind_pass)


@router.post("/agent/confirm", response_model=FactorResponse)
async def agent_confirm(
    body: AgentPreviewRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
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


# ---------------- per-factor routes (dynamic) ----------------


@router.get("/{factor_id}", response_model=FactorDetail)
async def factor_detail(
    factor_id: str,
    days: int = Query(365, ge=30, le=10000),
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
):
    factor = await _get_factor(factor_id, db)
    ifind_user, ifind_pass = await ifind_client.get_credentials(db, user_id)
    return await sync_factor_values(db, factor, ifind_user, ifind_pass, full=full)
