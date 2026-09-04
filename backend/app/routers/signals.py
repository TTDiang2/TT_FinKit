from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_private_db, get_public_db, async_session_maker
from ..config import _resolve_public_url as _pub_url
from ..middleware.auth import get_current_user_id
from ..schemas.signal import SignalResponse, SignalRunResult
from ..services.signal_service import (
    get_active_strategy, get_latest_signal, list_signals, get_signal, save_signal
)
from ..services.signal_engine import generate_signal
from ..models.signal import Signal as SignalModel
from ..models.research_asset import ResearchAsset, ResearchAssetPrice
from ..models.investment import Investment, open_position_cond
import json
import uuid
import datetime as _dt
from collections import defaultdict
from datetime import date

router = APIRouter(prefix="/api/signals", tags=["signals"])

def _signal_to_response(s, strategy_name: str | None = None,
                        name_by_symbol: dict[str, str] | None = None,
                        strategy_version_note: str | None = None) -> SignalResponse:
    tw = json.loads(s.target_weights or "{}")
    detail = [
        {"symbol": sym, "name": (name_by_symbol or {}).get(sym, sym), "weight": w}
        for sym, w in sorted(tw.items(), key=lambda kv: -kv[1])
    ] if tw else None
    return SignalResponse(
        id=s.id,
        strategy_id=s.strategy_id,
        strategy_version=s.strategy_version,
        strategy_name=strategy_name,
        strategy_version_note=strategy_version_note,
        run_date=s.run_date,
        as_of_date=s.as_of_date,
        next_rebalance_date=s.next_rebalance_date,
        target_weights=tw,
        weights_detail=detail,
        risk_status=json.loads(s.risk_status) if s.risk_status else None,
        backtest_id=s.backtest_id,
        created_at=str(s.created_at),
    )


async def _strategy_meta(pub: AsyncSession, strategy_id: str) -> tuple[str | None, str | None]:
    """(name, version_note) —— version_note 是作者声明的语义版本，如 v3.0-balanced-50-45。"""
    from app.models.strategy import Strategy as StrategyModel
    row = await pub.get(StrategyModel, strategy_id)
    return (row.name if row else None, row.version_note if row else None)


async def _symbol_names(pub: AsyncSession, symbols: list[str]) -> dict[str, str]:
    if not symbols:
        return {}
    rows = (await pub.execute(select(ResearchAsset).where(
        ResearchAsset.symbol.in_(symbols)))).scalars().all()
    # 同 symbol 多行时取任一名称即可
    return {r.symbol: r.name for r in rows}

async def _current_weights_from_holdings(db: AsyncSession, pub: AsyncSession, user_id: str) -> dict[str, float]:
    """按最新净值把用户未清仓投资折算成 {symbol: weight}，供信号引擎做持仓感知决策。"""
    assets = (await pub.execute(select(ResearchAsset).where(
        ))).scalars().all()
    by_symbol = {a.symbol: a for a in assets}
    invs = (await db.execute(select(Investment).where(
        Investment.user_id == user_id, open_position_cond()))).scalars().all()
    holdings = [i for i in invs if (i.quantity or 0) > 0]
    if not holdings:
        return {}
    needed = {i.symbol or "" for i in holdings} & set(by_symbol)
    navs: dict[str, float] = {}
    if needed:
        rows = (await pub.execute(
            select(ResearchAssetPrice.asset_id, ResearchAssetPrice.close)
            .where(ResearchAssetPrice.asset_id.in_([by_symbol[s].id for s in needed]))
            .order_by(ResearchAssetPrice.date.asc()))).all()
        id_to_sym = {a.id: a.symbol for a in assets}
        for aid, close in rows:
            navs[id_to_sym[aid]] = float(close)
    mv: dict[str, float] = {}
    for i in holdings:
        sym = i.symbol or ""
        nav = navs.get(sym) or (i.current_price or 0)
        mv[sym] = mv.get(sym, 0) + (i.quantity or 0) * nav
    total = sum(mv.values())
    if total <= 0:
        return {}
    return {s: w / total for s, w in mv.items() if w > 0}


_SIGNAL_JOB_RUNNING = False


def _run_signal_job(strategy_code: str, params: dict, universe: list[str],
                    rebalance_freq: str, current_weights: dict, db_path: str,
                    strategy_id: str, strategy_version: int, user_id: str) -> None:
    """后台线程执行全池信号生成（7714 标的可能耗时数分钟，不能占住请求）。"""
    global _SIGNAL_JOB_RUNNING
    import asyncio
    try:
        result = generate_signal(
            strategy_code=strategy_code,
            params=params,
            universe=universe,
            rebalance_freq=rebalance_freq,
            current_weights=current_weights,
            db_path=db_path,
        )
        if result.get("status") != "ok":
            return

        async def _save():
            async with async_session_maker() as s:
                await save_signal(
                    s,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    run_date=date.today().isoformat(),
                    as_of_date=result["as_of_date"],
                    next_rebalance_date=result["next_rebalance_date"],
                    target_weights=result["target_weights"],
                    risk_status=result.get("risk_status"),
                )
        asyncio.run(_save())
    except Exception:
        import logging
        logging.getLogger("uvicorn.error").exception("background signal job failed")
    finally:
        _SIGNAL_JOB_RUNNING = False


@router.post("/run", response_model=SignalRunResult)
async def run_signal_endpoint(background_tasks: BackgroundTasks,
                              db: AsyncSession = Depends(get_private_db),
                              pub: AsyncSession = Depends(get_public_db),
                              user_id: str = Depends(get_current_user_id)):
    """Run the active strategy to generate a new signal.

    全池 universe 计算耗时可能数分钟，改为后台任务：立即返回 running，
    前端轮询 /signals/current 直到出现新 signal。
    """
    global _SIGNAL_JOB_RUNNING
    if _SIGNAL_JOB_RUNNING:
        return SignalRunResult(signal_id="", status="running",
                               error="已有信号生成任务进行中，请稍候")
    strat = await get_active_strategy(pub)
    if not strat:
        raise HTTPException(status_code=404, detail="No active strategy found. Please import or activate a strategy first.")

    active_params: dict = {}

    from app.models.research_asset import ResearchAsset
    universe_q = select(ResearchAsset).where(ResearchAsset.status == "pooled")
    if strat.group_id:
        from app.models.research_group import ResearchGroupMember
        member_ids = select(ResearchGroupMember.asset_id).where(
            ResearchGroupMember.group_id == strat.group_id)
        universe_q = universe_q.where(ResearchAsset.id.in_(member_ids))
    result = await pub.execute(universe_q)
    assets = list(result.scalars().all())
    universe = [a.symbol for a in assets]
    if not universe:
        raise HTTPException(
            status_code=400,
            detail="策略绑定的标的组合中没有已入池标的——请先在标的面板把这些组合成员入池",
        )

    current_weights = await _current_weights_from_holdings(db, pub, user_id)
    _SIGNAL_JOB_RUNNING = True
    background_tasks.add_task(
        _run_signal_job,
        strat.code, dict(active_params), universe,
        strat.rebalance_freq or "monthly", current_weights,
        _pub_url().split("///")[-1],
        strat.id, strat.version, user_id,
    )
    return SignalRunResult(signal_id="", status="running")

@router.get("/current", response_model=SignalResponse | None)
async def get_current_signal_endpoint(db: AsyncSession = Depends(get_private_db),
                                      pub: AsyncSession = Depends(get_public_db),
                                      user_id: str = Depends(get_current_user_id)):
    sig = await get_latest_signal(db, user_id)
    if not sig:
        return None
    sname, vnote = await _strategy_meta(pub, sig.strategy_id)
    tw = json.loads(sig.target_weights or "{}")
    names = await _symbol_names(pub, list(tw))
    return _signal_to_response(sig, strategy_name=sname, name_by_symbol=names,
                               strategy_version_note=vnote)

@router.get("", response_model=list[SignalResponse])
async def list_signals_endpoint(limit: int = Query(50), db: AsyncSession = Depends(get_private_db),
                                pub: AsyncSession = Depends(get_public_db),
                                user_id: str = Depends(get_current_user_id)):
    signals = await list_signals(db, user_id, limit)
    return [_signal_to_response(s) for s in signals]

# --------------------------------------------------------------------------- #
# Trade plan: current holdings vs latest signal target → concrete rebalance list
# --------------------------------------------------------------------------- #

_TRADE_MIN_AMOUNT = 100.0
_TRADE_MIN_RATIO = 0.01
_PENALTY_DAYS = 7


def _add_business_days(d: date, n: int) -> str:
    """T+N arrival estimate; weekends skipped, holidays ignored (约到账)."""
    cur, left = d, n
    while left > 0:
        cur += _dt.timedelta(days=1)
        if cur.weekday() < 5:
            left -= 1
    return cur.isoformat()


def _redeem_fee_for(rules_json: str | None, holding_days: int):
    try:
        rules = json.loads(rules_json) if rules_json else []
    except (json.JSONDecodeError, ValueError):
        rules = []
    tiers = [(r.get("days"), float(r.get("fee_rate") or 0)) for r in rules
             if isinstance(r, dict)]
    if not tiers:
        return None, "未录入赎回费规则"
    for days, fee in sorted(tiers, key=lambda t: (t[0] is None, t[0] or 0)):
        if days is None or holding_days < int(days):
            tag = f"持有{holding_days}天档" + ("（<7天惩罚费率）" if holding_days < _PENALTY_DAYS else "")
            return fee, tag
    return tiers[-1][1], f"持有{holding_days}天兜底档"


async def compute_trade_plan(db: AsyncSession, pub: AsyncSession, user_id: str,
                             additional_cash: float = 0.0) -> dict:
    sig = await get_latest_signal(db, user_id)
    targets: dict[str, float] = json.loads(sig.target_weights) if sig else {}

    assets = (await pub.execute(select(ResearchAsset).where(
        ))).scalars().all()
    by_symbol = {a.symbol: a for a in assets}

    invs = (await db.execute(select(Investment).where(
        Investment.user_id == user_id, open_position_cond()))).scalars().all()
    holdings = [i for i in invs if (i.quantity or 0) > 0]
    locked = [i for i in holdings if getattr(i, "locked", False)]
    tradable = [i for i in holdings if not getattr(i, "locked", False)]
    locked_syms = {(i.symbol or "").strip() for i in locked if i.symbol}

    # Navs only for symbols that matter (targets ∪ holdings) — an IN clause over
    # the full 19k-asset pool stalls SQLite.
    needed = set(targets) | {i.symbol or "" for i in holdings}
    wanted_ids = [by_symbol[s].id for s in needed if s in by_symbol]
    navs: dict[str, float] = {}
    if wanted_ids:
        rows = (await pub.execute(
            select(ResearchAssetPrice.asset_id, ResearchAssetPrice.close)
            .where(ResearchAssetPrice.asset_id.in_(wanted_ids))
            .order_by(ResearchAssetPrice.date.asc()))).all()
        id_to_sym = {a.id: a.symbol for a in assets}
        for aid, close in rows:
            navs[id_to_sym[aid]] = float(close)

    mv_by_symbol: dict[str, float] = {}
    inv_name: dict[str, str] = {}
    for i in holdings:
        sym = i.symbol or ""
        nav = navs.get(sym) or (i.current_price or 0)
        mv_by_symbol[sym] = mv_by_symbol.get(sym, 0) + (i.quantity or 0) * nav
        inv_name.setdefault(sym, i.name)

    locked_mv = sum(mv for s, mv in mv_by_symbol.items() if s in locked_syms)
    total_value = sum(mv_by_symbol.values())
    invested_value = total_value
    additional_cash = max(0.0, float(additional_cash or 0))
    tradable_budget = total_value - locked_mv + additional_cash

    def _key(sym: str) -> str:
        a = by_symbol.get(sym)
        ac = ((a.asset_class if a else "") or "").strip()
        if not ac:
            for i in holdings:
                if (i.symbol or "").strip() == sym:
                    ac = (i.asset_class or "").strip()
                    break
        if not ac:
            return f"|{sym}"
        rg = ((a.region if a else "") or "").strip()
        return f"{ac}|{rg}"

    t_items = [(s, w) for s, w in targets.items() if s not in locked_syms]
    wsum = sum(w for _, w in t_items)

    tradable_by_key: dict[str, list] = defaultdict(list)
    for i in tradable:
        tradable_by_key[_key((i.symbol or "").strip())].append(i)

    weight_by_key: dict[str, float] = defaultdict(float)
    rep_by_key: dict[str, str] = {}
    for s, w in t_items:
        k = _key(s)
        weight_by_key[k] += w
        if k not in rep_by_key:
            pool = tradable_by_key.get(k)
            rep_by_key[k] = ((pool[0].symbol or "").strip() if pool else s)

    norm = {k: w / wsum for k, w in weight_by_key.items()} if wsum > 0 else {}
    today = date.today()
    rows_out: list[dict] = []

    if wsum > 0:
        for k in sorted(norm, key=lambda kk: -norm[kk]):
            rep = rep_by_key[k]
            a = by_symbol.get(rep)
            name = (a.name if a else None) or inv_name.get(rep) or rep
            target_w = norm[k]
            target_mv = target_w * tradable_budget
            cur_mv = sum(mv for s, mv in mv_by_symbol.items()
                         if s not in locked_syms and _key(s) == k)
            cur_w = cur_mv / tradable_budget if tradable_budget > 0 else 0
            delta = target_mv - cur_mv

            row = {
                "symbol": rep, "name": name,
                "current_weight": round(cur_w, 4),
                "target_weight": round(target_w, 4),
                "current_mv": round(cur_mv, 2), "target_mv": round(target_mv, 2),
                "action": "hold", "amount": 0.0, "est_fee_pct": None,
                "est_fee_amount": 0.0, "t_plus": None, "arrive_date": None,
                "warnings": [],
            }
            same_key = tradable_by_key.get(k, [])
            others = [i for i in same_key if (i.symbol or "").strip() != rep]
            if others:
                row["equiv_holding"] = (others[0].name or others[0].symbol or "")
            if abs(delta) < _TRADE_MIN_AMOUNT or (tradable_budget > 0 and abs(delta / tradable_budget) < _TRADE_MIN_RATIO):
                if others:
                    row["warnings"].append(f"持有同类标的「{row['equiv_holding']}」，视为等效持仓不做换仓")
                rows_out.append(row)
                continue
            if delta > 0 and target_w > 0:
                row.update(action="buy", amount=round(delta, 2))
                if others:
                    row["warnings"].append(f"可继续持有同类标的「{row['equiv_holding']}」代替买入，两者收益高度接近")
                if a:
                    status = a.purchase_status or ""
                    limit = a.purchase_limit
                    if status and status != "开放申购":
                        row["warnings"].append(f"申购状态「{status}」，建议暂缓")
                    fee = a.purchase_fee
                    if fee is not None:
                        row["est_fee_pct"] = fee
                        row["est_fee_amount"] = round(delta * fee / 100, 2)
                    if limit is not None and delta > limit:
                        row["warnings"].append(f"超单日限额 {limit:g} 元，需分日买入或降低目标")
                        row["amount"] = round(min(delta, max(limit, 0)), 2)
            elif delta < 0 and cur_mv > 0:
                amount = min(-delta, cur_mv)
                sell_pool = same_key or tradable
                sell_inv = max(sell_pool, key=lambda i: mv_by_symbol.get((i.symbol or "").strip(), 0))
                sell_sym = (sell_inv.symbol or "").strip()
                sell_name = (sell_inv.name or "") or inv_name.get(sell_sym, sell_sym)
                a_sell = by_symbol.get(sell_sym)
                row.update(action="sell", symbol=sell_sym, name=sell_name, amount=round(amount, 2))
                i_hold = sell_inv
                try:
                    held = (today - _dt.date.fromisoformat(str(i_hold.purchase_date)[:10])).days
                except (ValueError, TypeError):
                    held = 9999
                if a_sell:
                    fee_pct, note = _redeem_fee_for(a_sell.redeem_rules, held)
                    row["est_fee_pct"] = fee_pct
                    row["est_fee_amount"] = round(amount * (fee_pct or 0) / 100, 2)
                    if fee_pct is None:
                        row["warnings"].append(note)
                    elif held < _PENALTY_DAYS:
                        row["warnings"].append(note)
                    t_plus = a_sell.redeem_t_days
                    if t_plus:
                        row["t_plus"] = f"T+{t_plus}"
                        row["arrive_date"] = _add_business_days(today, int(t_plus))
                    status = a_sell.purchase_status or ""
                    limit = a_sell.purchase_limit
                    if (status and status != "开放申购") or (limit is not None and amount > (limit or 0)):
                        est = f"，按限额需约 {int(amount / limit) + 1} 个交易日" if limit else ""
                        row["warnings"].append(
                            f"该标的申购受限（{status or f'限额 {limit:g} 元/日'}），卖出后回补困难{est}且不保证能回补，请谨慎"
                        )
            rows_out.append(row)
    else:
        # 无信号（或目标全为锁定标的）时保持现状展示，不产生任何调仓动作
        for i in tradable:
            sym = (i.symbol or "").strip()
            mv = mv_by_symbol.get(sym, 0)
            rows_out.append({
                "symbol": sym, "name": (i.name or "") or inv_name.get(sym, sym),
                "current_weight": round(mv / total_value, 4) if total_value > 0 else 0,
                "target_weight": 0.0,
                "current_mv": round(mv, 2), "target_mv": round(mv, 2),
                "action": "hold", "amount": 0.0, "est_fee_pct": None,
                "est_fee_amount": 0.0, "t_plus": None, "arrive_date": None,
                "warnings": ["暂无信号，展示当前持仓"],
            })

    for i in sorted(locked, key=lambda i: -mv_by_symbol.get((i.symbol or "").strip(), 0)):
        sym = (i.symbol or "").strip()
        mv = mv_by_symbol.get(sym, 0)
        rows_out.append({
            "symbol": sym, "name": (i.name or "") or inv_name.get(sym, sym),
            "current_weight": round(mv / total_value, 4) if total_value > 0 else 0,
            "target_weight": 0.0,
            "current_mv": round(mv, 2), "target_mv": round(mv, 2),
            "action": "locked", "amount": 0.0, "est_fee_pct": None,
            "est_fee_amount": 0.0, "t_plus": None, "arrive_date": None,
            "warnings": ["已锁定：不参与调仓，其余资产在其之外归一化"],
        })

    return {
        "signal_id": sig.id if sig else None,
        "run_date": sig.run_date if sig else None,
        "next_rebalance_date": sig.next_rebalance_date if sig else None,
        "invested_value": round(invested_value, 2),
        "additional_cash": round(additional_cash, 2),
        "total_value": round(total_value, 2),
        "locked_value": round(locked_mv, 2),
        "tradable_budget": round(tradable_budget, 2),
        "rows": rows_out,
    }


@router.get("/trade-plan")
async def trade_plan_endpoint(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
    pub: AsyncSession = Depends(get_public_db),
    additional_cash: float = Query(0.0, ge=0.0, description="本次调仓计划新投入的现金金额"),
):
    """调仓清单。赎回费按 purchase_date 单笔近似（未做跨笔 FIFO 混合）。

    additional_cash > 0 时按「现有市值 + 新增现金」计算目标结构，
    新增部分按目标权重买入（每月发工资定投场景）。
    """
    return await compute_trade_plan(db, pub, user_id, additional_cash=additional_cash)
@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal_endpoint(signal_id: str, db: AsyncSession = Depends(get_private_db),
                              pub: AsyncSession = Depends(get_public_db),
                              user_id: str = Depends(get_current_user_id)):
    sig = await get_signal(db, signal_id, user_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    sname, vnote = await _strategy_meta(pub, sig.strategy_id)
    tw = json.loads(sig.target_weights or "{}")
    names = await _symbol_names(pub, list(tw))
    return _signal_to_response(sig, strategy_name=sname, name_by_symbol=names,
                               strategy_version_note=vnote)


