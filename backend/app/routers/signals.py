from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_private_db, get_public_db
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
from datetime import date

router = APIRouter(prefix="/api/signals", tags=["signals"])

def _signal_to_response(s, strategy_name: str | None = None,
                        name_by_symbol: dict[str, str] | None = None) -> SignalResponse:
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
        run_date=s.run_date,
        as_of_date=s.as_of_date,
        next_rebalance_date=s.next_rebalance_date,
        target_weights=tw,
        weights_detail=detail,
        risk_status=json.loads(s.risk_status) if s.risk_status else None,
        backtest_id=s.backtest_id,
        created_at=str(s.created_at),
    )


async def _strategy_name(pub: AsyncSession, strategy_id: str) -> str | None:
    from app.models.strategy import Strategy as StrategyModel
    row = await pub.get(StrategyModel, strategy_id)
    return row.name if row else None


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
        ResearchAsset.user_id == user_id))).scalars().all()
    by_symbol = {a.symbol: a for a in assets}
    invs = (await db.execute(select(Investment).where(
        Investment.user_id == user_id, open_position_cond()))).scalars().all()
    holdings = [i for i in invs if (i.quantity or 0) > 0]
    if not holdings:
        return {}
    needed = {i.symbol or "" for i in holdings} & set(by_symbol)
    navs: dict[str, float] = {}
    if needed:
        rows = (await db.execute(
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


@router.post("/run", response_model=SignalRunResult)
async def run_signal_endpoint(db: AsyncSession = Depends(get_private_db),
                              pub: AsyncSession = Depends(get_public_db),
                              user_id: str = Depends(get_current_user_id)):
    """Run the active strategy to generate a new signal."""
    # Get active strategy (latest imported or the one set as active)
    # For now: use the most recently created strategy
    strat = await get_active_strategy(pub)
    if not strat:
        raise HTTPException(status_code=404, detail="No active strategy found. Please import or activate a strategy first.")

    # Load strategy params from active (or use defaults)
    active_params = {}

    # Get universe: 策略绑定的标的组合成员 ∩ 已入池；未绑定 → 全部入池
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

    try:
        current_weights = await _current_weights_from_holdings(db, pub, user_id)
        signal_result = generate_signal(
            strategy_code=strat.code,
            params=active_params,
            universe=universe,
            rebalance_freq=strat.rebalance_freq or "monthly",
            current_weights=current_weights,
            db_path=_pub_url().split("///")[-1],
        )
    except Exception as e:
        return SignalRunResult(signal_id="", status="error", error=str(e))

    if signal_result["status"] != "ok":
        return SignalRunResult(signal_id="", status="error", error=signal_result.get("error"))

    # Save signal
    sig = await save_signal(
        db,
        strategy_id=strat.id,
        strategy_version=strat.version,
        run_date=date.today().isoformat(),
        as_of_date=signal_result["as_of_date"],
        next_rebalance_date=signal_result["next_rebalance_date"],
        target_weights=signal_result["target_weights"],
        risk_status=signal_result["risk_status"],
    )

    return SignalRunResult(signal_id=sig.id, status="ok")

@router.get("/current", response_model=SignalResponse | None)
async def get_current_signal_endpoint(db: AsyncSession = Depends(get_private_db),
                                      pub: AsyncSession = Depends(get_public_db)):
    sig = await get_latest_signal(db)
    if not sig:
        return None
    sname = await _strategy_name(pub, sig.strategy_id)
    tw = json.loads(sig.target_weights or "{}")
    names = await _symbol_names(pub, list(tw))
    return _signal_to_response(sig, strategy_name=sname, name_by_symbol=names)

@router.get("", response_model=list[SignalResponse])
async def list_signals_endpoint(limit: int = Query(50), db: AsyncSession = Depends(get_private_db),
                                pub: AsyncSession = Depends(get_public_db)):
    signals = await list_signals(db, limit)
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
    sig = await get_latest_signal(db)
    targets: dict[str, float] = json.loads(sig.target_weights) if sig else {}

    assets = (await pub.execute(select(ResearchAsset).where(
        ResearchAsset.user_id == user_id))).scalars().all()
    by_symbol = {a.symbol: a for a in assets}

    invs = (await db.execute(select(Investment).where(
        Investment.user_id == user_id, open_position_cond()))).scalars().all()
    holdings = [i for i in invs if (i.quantity or 0) > 0]

    # Navs only for symbols that matter (targets ∪ holdings) — an IN clause over
    # the full 19k-asset pool stalls SQLite.
    needed = set(targets) | {i.symbol or "" for i in holdings}
    wanted_ids = [by_symbol[s].id for s in needed if s in by_symbol]
    navs: dict[str, float] = {}
    if wanted_ids:
        rows = (await db.execute(
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

    total_value = sum(mv_by_symbol.values())
    invested_value = total_value
    additional_cash = max(0.0, float(additional_cash or 0))
    total_value += additional_cash
    today = date.today()
    rows_out: list[dict] = []

    for sym in sorted(set(targets) | set(mv_by_symbol)):
        a = by_symbol.get(sym)
        name = (a.name if a else None) or inv_name.get(sym) or sym
        target_w = float(targets.get(sym) or 0)
        mv = mv_by_symbol.get(sym, 0)
        current_w = mv / total_value if total_value > 0 else 0
        delta = target_w * total_value - mv

        row = {
            "symbol": sym, "name": name,
            "current_weight": round(current_w, 4),
            "target_weight": round(target_w, 4),
            "current_mv": round(mv, 2), "target_mv": round(target_w * total_value, 2),
            "action": "hold", "amount": 0.0, "est_fee_pct": None,
            "est_fee_amount": 0.0, "t_plus": None, "arrive_date": None,
            "warnings": [],
        }
        # 缓冲带：差额既小于金额线也小于比例线 → 保持不动，避免摩擦损耗
        if abs(delta) < _TRADE_MIN_AMOUNT or abs(delta / total_value) < _TRADE_MIN_RATIO:
            rows_out.append(row)
            continue

        if delta > 0 and target_w > 0:
            row.update(action="buy", amount=round(delta, 2))
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
        elif delta < 0 and mv > 0:
            amount = min(-delta, mv)
            row.update(action="sell", amount=round(amount, 2))
            if i_hold := next((i for i in holdings if i.symbol == sym), None):
                try:
                    held = (today - _dt.date.fromisoformat(str(i_hold.purchase_date)[:10])).days
                except (ValueError, TypeError):
                    held = 9999
                if a:
                    fee_pct, note = _redeem_fee_for(a.redeem_rules, held)
                    row["est_fee_pct"] = fee_pct
                    row["est_fee_amount"] = round(amount * (fee_pct or 0) / 100, 2)
                    if fee_pct is None:
                        row["warnings"].append(note)
                    elif held < _PENALTY_DAYS:
                        row["warnings"].append(note)
                    t_plus = a.redeem_t_days
                    if t_plus:
                        row["t_plus"] = f"T+{t_plus}"
                        row["arrive_date"] = _add_business_days(today, int(t_plus))
        rows_out.append(row)

    return {
        "signal_id": sig.id if sig else None,
        "run_date": sig.run_date if sig else None,
        "next_rebalance_date": sig.next_rebalance_date if sig else None,
        "invested_value": round(invested_value, 2),
        "additional_cash": round(additional_cash, 2),
        "total_value": round(total_value, 2),
        "rows": rows_out,
    }


@router.get("/trade-plan")
async def trade_plan_endpoint(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db),
    additional_cash: float = Query(0.0, ge=0.0, description="本次调仓计划新投入的现金金额"),
):
    """调仓清单。赎回费按 purchase_date 单笔近似（未做跨笔 FIFO 混合）。

    additional_cash > 0 时按「现有市值 + 新增现金」计算目标结构，
    新增部分按目标权重买入（每月发工资定投场景）。
    """
    return await compute_trade_plan(db, pub, user_id, additional_cash=additional_cash)
@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal_endpoint(signal_id: str, db: AsyncSession = Depends(get_private_db),
                              pub: AsyncSession = Depends(get_public_db)):
    sig = await get_signal(db, signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    sname = await _strategy_name(pub, sig.strategy_id)
    tw = json.loads(sig.target_weights or "{}")
    names = await _symbol_names(pub, list(tw))
    return _signal_to_response(sig, strategy_name=sname, name_by_symbol=names)


