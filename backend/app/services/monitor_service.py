"""Monitor service — portfolio monitoring data for Phase 6 (§5.6).

Backs ``GET /api/monitor/overview`` which returns three zones in one payload:

  Zone 1 组合监控:  latest signal target weights vs actual holding weights
          (by symbol), per-asset deviation with alert badge when
          |deviation| >= threshold (default 5pp per ADR-14).
  Zone 2 风险监控:  portfolio NAV drawdown, VaR95 / CVaR95 from daily returns,
          portfolio-level (holding-weighted) factor exposures and per-factor
          risk contribution (RC_i = beta_i^2 * sigma_i^2 / sum_j ...).
  Zone 3 策略偏离:  factor exposure drift (latest vs ~3 months ago, Delta >= 0.3
          alert), time since last signal + next rebalance countdown, and a
          strategy continuity check.

Thresholds are stored in ``user_settings.monitor_thresholds`` (JSON extension
key per §4.9); ``DEFAULT_THRESHOLDS`` applies when the column is empty.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.signal import Signal
from ..models.research_asset import ResearchAsset, ResearchAssetPrice
from ..models.factor import Factor, FactorExposure, FactorValue
from ..models.investment import Investment, open_position_cond
from ..models.user_settings import UserSettings
from ..services.indicators import max_drawdown, annualized_volatility

DEFAULT_THRESHOLDS = {
    "weight_deviation_pp": 5.0,    # |weight deviation| threshold in percentage points
    "exposure_drift": 0.3,         # factor exposure drift threshold
    "drawdown_alert_pct": 10.0,    # drawdown alert threshold in percent
}
STALE_SIGNAL_DAYS = 90
DRIFT_LOOKBACK_DAYS = 90
TRADING_DAYS_PER_YEAR = 252


def _parse_thresholds(row: UserSettings | None) -> dict:
    merged = dict(DEFAULT_THRESHOLDS)
    if row and row.monitor_thresholds:
        try:
            data = json.loads(row.monitor_thresholds)
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict):
            for key in DEFAULT_THRESHOLDS:
                if key in data and data[key] is not None:
                    try:
                        merged[key] = float(data[key])
                    except (TypeError, ValueError):
                        pass
    return merged


async def get_monitor_settings(db: AsyncSession, user_id: str) -> dict:
    row = (await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))).scalar_one_or_none()
    return _parse_thresholds(row)


async def update_monitor_settings(db: AsyncSession, user_id: str, payload: dict) -> dict:
    row = (await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))).scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user_id)
        db.add(row)
    current = _parse_thresholds(row)
    for key in DEFAULT_THRESHOLDS:
        if key in payload and payload[key] is not None:
            try:
                current[key] = float(payload[key])
            except (TypeError, ValueError):
                pass
    row.monitor_thresholds = json.dumps(current)
    await db.commit()
    await db.refresh(row)
    return _parse_thresholds(row)


async def _portfolio_context(db: AsyncSession, pub: AsyncSession, user_id: str) -> dict:
    """Shared context: research assets, open holdings, market values, weights.

    Holding market value = shares (investments.quantity) x latest nav
    (research_prices.close, mapped symbol -> research_assets). Falls back to
    investments.current_price for symbols not in the research pool.
    """
    assets = (await pub.execute(
        select(ResearchAsset).where(ResearchAsset.user_id == user_id)
    )).scalars().all()
    symbol_to_asset = {a.symbol: a for a in assets}
    asset_id_to_asset = {a.id: a for a in assets}

    latest_close: dict[str, float] = {}
    asset_ids = [a.id for a in assets]
    if asset_ids:
        rows = (await pub.execute(
            select(ResearchAssetPrice.asset_id, ResearchAssetPrice.date, ResearchAssetPrice.close)
            .where(ResearchAssetPrice.asset_id.in_(asset_ids))
            .order_by(ResearchAssetPrice.date.asc())
        )).all()
        for aid, _d, close in rows:
            latest_close[aid] = float(close)

    invs = (await db.execute(
        select(Investment).where(Investment.user_id == user_id, open_position_cond())
    )).scalars().all()
    holdings = [inv for inv in invs if (inv.quantity or 0) > 0]

    market_value: dict[str, float] = {}
    name_by_symbol: dict[str, str] = {}
    shares_by_symbol: dict[str, float] = {}
    for inv in holdings:
        asset = symbol_to_asset.get(inv.symbol or "")
        nav = latest_close.get(asset.id) if asset else (inv.current_price or 0)
        shares = float(inv.quantity or 0)
        mv = shares * (nav or 0)
        if mv <= 0:
            continue
        market_value[inv.symbol] = mv
        shares_by_symbol[inv.symbol] = shares
        name_by_symbol[inv.symbol] = (asset.name if asset else "") or inv.name or inv.symbol

    total = sum(market_value.values())
    actual_weight = {sym: mv / total for sym, mv in market_value.items()} if total > 0 else {}

    return {
        "assets": assets,
        "symbol_to_asset": symbol_to_asset,
        "asset_id_to_asset": asset_id_to_asset,
        "latest_close": latest_close,
        "holdings": holdings,
        "shares_by_symbol": shares_by_symbol,
        "market_value": market_value,
        "name_by_symbol": name_by_symbol,
        "total_value": total,
        "actual_weight": actual_weight,
    }


async def _latest_signal(db: AsyncSession) -> Signal | None:
    return (await db.execute(select(Signal).order_by(Signal.created_at.desc()).limit(1))).scalar_one_or_none()


async def _zone1_portfolio(db: AsyncSession, user_id: str, thresholds: dict, ctx: dict) -> dict:
    sig = await _latest_signal(db)
    target_by_asset: dict[str, float] = {}
    if sig and sig.target_weights:
        try:
            tw = json.loads(sig.target_weights)
        except (TypeError, ValueError):
            tw = None
        if isinstance(tw, dict):
            for aid, w in tw.items():
                try:
                    target_by_asset[str(aid)] = float(w)
                except (TypeError, ValueError):
                    pass

    target_by_symbol: dict[str, float] = {}
    target_symbol_to_asset: dict[str, str] = {}
    for aid, w in target_by_asset.items():
        a = ctx["asset_id_to_asset"].get(aid)
        if a:
            target_by_symbol[a.symbol] = w
            target_symbol_to_asset[a.symbol] = aid

    actual_weight = ctx["actual_weight"]
    threshold = float(thresholds.get("weight_deviation_pp", DEFAULT_THRESHOLDS["weight_deviation_pp"])) / 100.0

    items = []
    for sym in sorted(set(actual_weight) | set(target_by_symbol)):
        asset = ctx["symbol_to_asset"].get(sym)
        asset_id = (asset.id if asset else None) or target_symbol_to_asset.get(sym)
        target = target_by_symbol.get(sym, 0.0)
        actual = actual_weight.get(sym, 0.0)
        deviation = abs(actual - target)
        items.append({
            "asset_id": asset_id,
            "symbol": sym,
            "name": ctx["name_by_symbol"].get(sym) or (asset.name if asset else "") or sym,
            "target_weight": round(target, 6),
            "actual_weight": round(actual, 6),
            "deviation": round(deviation, 6),
            "has_alert": deviation >= threshold,
        })
    items.sort(key=lambda it: -it["deviation"])

    alerts = [it["symbol"] for it in items if it["has_alert"]]
    return {
        "items": items,
        "total_actual_value": round(ctx["total_value"], 2),
        "alerts": alerts,
        "suggested_rebalance": [it for it in items if it["has_alert"]],
    }


async def _zone2_risk(db: AsyncSession, pub: AsyncSession, user_id: str, thresholds: dict, ctx: dict) -> dict:
    shares_by_symbol = ctx["shares_by_symbol"]
    symbol_to_asset = ctx["symbol_to_asset"]
    held = [(sym, symbol_to_asset[sym].id) for sym in shares_by_symbol if symbol_to_asset.get(sym)]

    series_map: dict[str, list[tuple[str, float]]] = {}
    if held:
        rows = (await pub.execute(
            select(ResearchAssetPrice.asset_id, ResearchAssetPrice.date, ResearchAssetPrice.close)
            .where(ResearchAssetPrice.asset_id.in_([aid for _, aid in held]))
            .order_by(ResearchAssetPrice.date.asc())
        )).all()
        for aid, d, close in rows:
            series_map.setdefault(aid, []).append((d, float(close)))

    value_series: dict[str, dict[str, float]] = {
        aid: {d: shares_by_symbol[sym] * c for d, c in series_map.get(aid, [])}
        for sym, aid in held
    }
    dates = sorted(set().union(*[set(v) for v in value_series.values()])) if value_series else []
    nav_series: list[float] = []
    last_value: dict[str, float] = {aid: 0.0 for aid in value_series}
    for d in dates:
        total = 0.0
        for aid, v in value_series.items():
            if d in v:
                last_value[aid] = v[d]
            total += last_value[aid]
        nav_series.append(total)

    current_nav = nav_series[-1] if nav_series else ctx["total_value"]
    drawdown = max_drawdown(nav_series)
    dd_alert = -drawdown * 100.0 >= float(thresholds.get("drawdown_alert_pct", DEFAULT_THRESHOLDS["drawdown_alert_pct"]))

    var_95 = cvar_95 = 0.0
    rets = [nav_series[i] / nav_series[i - 1] - 1.0 for i in range(1, len(nav_series)) if nav_series[i - 1] != 0]
    if rets:
        p5 = float(np.percentile(rets, 5))
        below = [r for r in rets if r <= p5]
        var_95 = max(-p5, 0.0)
        cvar_95 = max(-float(np.mean(below)), 0.0) if below else var_95

    return {
        "current_nav": round(current_nav, 2),
        "max_drawdown": round(drawdown, 6),
        "drawdown_alert": dd_alert,
        "annualized_volatility": round(annualized_volatility(nav_series), 6) if len(rets) >= 2 else None,
        "var_95": round(var_95, 6),
        "cvar_95": round(cvar_95, 6),
        "factor_exposures": await _portfolio_factor_exposures(pub, ctx),
    }


async def _portfolio_factor_exposures(pub: AsyncSession, ctx: dict) -> list[dict]:
    weight_by_asset: dict[str, float] = {}
    for sym, w in ctx["actual_weight"].items():
        a = ctx["symbol_to_asset"].get(sym)
        if a:
            weight_by_asset[a.id] = w
    asset_ids = list(weight_by_asset)
    if not asset_ids:
        return []

    exp_rows = (await pub.execute(
        select(FactorExposure, Factor)
        .join(Factor, FactorExposure.factor_id == Factor.id)
        .where(FactorExposure.asset_id.in_(asset_ids))
        .order_by(FactorExposure.as_of_date.desc())
    )).all()
    if not exp_rows:
        return []
    latest_asof = exp_rows[0][0].as_of_date

    factor_names: dict[str, str] = {}
    weighted: dict[str, float] = {}
    for fe, f in exp_rows:
        if fe.as_of_date != latest_asof:
            continue
        factor_names[f.id] = f.name
        weighted[f.id] = weighted.get(f.id, 0.0) + weight_by_asset.get(fe.asset_id, 0.0) * fe.beta

    sigmas: dict[str, float] = {}
    factor_ids = list(weighted)
    if factor_ids:
        fv_rows = (await pub.execute(
            select(FactorValue.factor_id, FactorValue.value)
            .where(FactorValue.factor_id.in_(factor_ids), FactorValue.kind == "return")
        )).all()
        tmp: dict[str, list[float]] = {}
        for fid, v in fv_rows:
            tmp.setdefault(fid, []).append(float(v))
        for fid, rets in tmp.items():
            if len(rets) >= 2:
                sd = float(np.std(rets, ddof=1))
                if sd > 0:
                    sigmas[fid] = sd * np.sqrt(TRADING_DAYS_PER_YEAR)

    denom = sum((weighted[fid] ** 2) * (sigmas.get(fid, 0.0) ** 2) for fid in factor_ids)
    out = []
    for fid in factor_ids:
        rc = ((weighted[fid] ** 2) * (sigmas.get(fid, 0.0) ** 2)) / denom if denom > 0 else 0.0
        out.append({
            "factor_id": fid,
            "factor_name": factor_names.get(fid, fid),
            "weighted_beta": round(weighted[fid], 4),
            "risk_contribution": round(rc, 6),
        })
    out.sort(key=lambda x: -x["risk_contribution"])
    return out


async def _zone3_deviation(db: AsyncSession, pub: AsyncSession, user_id: str, thresholds: dict, ctx: dict) -> dict:
    sig = await _latest_signal(db)
    last_signal_date = sig.run_date if sig else None
    next_rebalance_date = sig.next_rebalance_date if sig else None

    today = date.today()
    days_since_signal = None
    if last_signal_date:
        try:
            days_since_signal = (today - datetime.strptime(last_signal_date, "%Y-%m-%d").date()).days
        except ValueError:
            days_since_signal = None

    if sig is None:
        continuity_status = "no_signal"
    elif days_since_signal is not None and days_since_signal > STALE_SIGNAL_DAYS:
        continuity_status = "stale"
    else:
        continuity_status = "ok"

    return {
        "factor_drifts": await _factor_drift(pub, ctx, thresholds),
        "last_signal_date": last_signal_date,
        "next_rebalance_date": next_rebalance_date,
        "days_since_signal": days_since_signal,
        "continuity_status": continuity_status,
    }


async def _factor_drift(pub: AsyncSession, ctx: dict, thresholds: dict) -> list[dict]:
    weight_by_asset: dict[str, float] = {}
    for sym, w in ctx["actual_weight"].items():
        a = ctx["symbol_to_asset"].get(sym)
        if a:
            weight_by_asset[a.id] = w
    asset_ids = list(weight_by_asset)
    if not asset_ids:
        return []

    exp_rows = (await pub.execute(
        select(FactorExposure, Factor)
        .join(Factor, FactorExposure.factor_id == Factor.id)
        .where(FactorExposure.asset_id.in_(asset_ids))
        .order_by(FactorExposure.as_of_date.desc())
    )).all()
    if not exp_rows:
        return []

    asofs = sorted({fe.as_of_date for fe, _ in exp_rows})
    latest_asof = asofs[-1]

    prev_asof = None
    try:
        cutoff = (datetime.strptime(latest_asof, "%Y-%m-%d").date() - timedelta(days=DRIFT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        for d in asofs:
            if d <= cutoff:
                prev_asof = d
    except ValueError:
        prev_asof = None

    factor_names: dict[str, str] = {}
    latest_beta: dict[str, float] = {}
    prev_beta: dict[str, float] = {}
    for fe, f in exp_rows:
        factor_names[f.id] = f.name
        w = weight_by_asset.get(fe.asset_id, 0.0)
        if fe.as_of_date == latest_asof:
            latest_beta[f.id] = latest_beta.get(f.id, 0.0) + w * fe.beta
        if prev_asof and fe.as_of_date == prev_asof:
            prev_beta[f.id] = prev_beta.get(f.id, 0.0) + w * fe.beta

    threshold = float(thresholds.get("exposure_drift", DEFAULT_THRESHOLDS["exposure_drift"]))
    drifts = []
    for fid in sorted(set(latest_beta) | set(prev_beta)):
        cur = latest_beta.get(fid, 0.0)
        prev = prev_beta.get(fid, 0.0)
        drift = abs(cur - prev)
        drifts.append({
            "factor_id": fid,
            "factor_name": factor_names.get(fid, fid),
            "current_beta": round(cur, 4),
            "prev_beta": round(prev, 4),
            "drift": round(drift, 4),
            "has_alert": drift >= threshold,
        })
    drifts.sort(key=lambda x: -x["drift"])
    return drifts


async def get_monitor_overview(db: AsyncSession, pub: AsyncSession, user_id: str) -> dict:
    thresholds = await get_monitor_settings(db, user_id)
    ctx = await _portfolio_context(db, pub, user_id)
    zone1 = await _zone1_portfolio(db, user_id, thresholds, ctx)
    zone2 = await _zone2_risk(db, pub, user_id, thresholds, ctx)
    zone3 = await _zone3_deviation(db, pub, user_id, thresholds, ctx)

    portfolio_alerts = len(zone1["alerts"])
    risk_alerts = 1 if zone2["drawdown_alert"] else 0
    deviation_alerts = sum(1 for d in zone3["factor_drifts"] if d["has_alert"])

    return {
        "zone1_portfolio": zone1,
        "zone2_risk": zone2,
        "zone3_deviation": zone3,
        "alerts_summary": {
            "total_alerts": portfolio_alerts + risk_alerts + deviation_alerts,
            "portfolio_alerts": portfolio_alerts,
            "risk_alerts": risk_alerts,
            "deviation_alerts": deviation_alerts,
        },
        "last_updated": datetime.now().isoformat(timespec="seconds"),
        "thresholds": thresholds,
    }
