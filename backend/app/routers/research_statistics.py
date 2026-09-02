"""Research asset statistics snapshot — one endpoint feeding all 9 charts in the
标的 → 统计 sub-tab.

All computations share ONE window and ONE common-trading-date alignment so the
charts never contradict each other (implementation plan §3.6).
"""
import math
from datetime import date, timedelta
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_public_db
from ..models.research_asset import ResearchAsset, ResearchAssetPrice
from ..middleware.auth import get_current_user_id

router = APIRouter(prefix="/api/research/stats", tags=["research-stats"])

TRADING_DAYS = 252
MIN_OBS = 60              # minimum aligned daily returns for risk charts
ZERO_VOL_EPS = 0.005      # annualized vol below this → excluded from risk charts
VAR_CONF = 0.95


def _annualize_mu(daily_rets: list[float]) -> float:
    return float(np.mean(daily_rets)) * TRADING_DAYS if daily_rets else 0.0


def _annualize_sigma(daily_rets: list[float]) -> float:
    if len(daily_rets) < 2:
        return 0.0
    return float(np.std(daily_rets, ddof=1)) * math.sqrt(TRADING_DAYS)


def _max_drawdown_path(nav: list[float]) -> list[float]:
    peak = -math.inf
    out = []
    for v in nav:
        peak = max(peak, v)
        out.append((v - peak) / peak if peak > 0 else 0.0)
    return out


def _rolling_return(daily_rets: list[float], window: int = TRADING_DAYS) -> list[float | None]:
    """Rolling cumulative return over a lookback window.

    If the series is shorter than ``window``, the window shrinks to the
    available length so the chart still has data (e.g. a 1-year view has
    ~241 trading days < 252).
    """
    out: list[float | None] = [None] * len(daily_rets)
    if not daily_rets:
        return out
    window = min(window, len(daily_rets))
    for i in range(window - 1, len(daily_rets)):
        chunk = daily_rets[i - window + 1: i + 1]
        out[i] = float(np.prod([1.0 + r for r in chunk]) - 1.0)
    return out


def _var_cvar(daily_rets: list[float], conf: float = VAR_CONF) -> tuple[float, float]:
    if not daily_rets:
        return 0.0, 0.0
    arr = np.sort(np.array(daily_rets))
    idx = max(0, int(round((1 - conf) * len(arr))) - 1)
    var = float(arr[idx])
    below = arr[arr <= var]
    cvar = float(np.mean(below)) if len(below) else var
    return var, cvar


@router.get("/snapshot")
async def stats_snapshot_cached(
    days: int = Query(365, ge=30, le=3650),
    assets: Optional[str] = Query(None),
    refresh: int = Query(0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    """统计快照（9 图数据源）+ 24h 缓存：命中直接回；过期/未命中先回旧值、
    后台重算（serve-stale-while-revalidate）。用户拍板 2026-08-29：
    "统计 tab 只呈现，至少隔天再重算"。"""
    import time as _time
    import asyncio as _asyncio
    import sys as _sys
    import json as _json
    from pathlib import Path as _Path
    key = f"{user_id}:{days}:{assets or 'all'}"
    now = _time.time()
    cached = _stats_cache.get(key)
    if cached and (now - cached["ts"] < 86400) and not refresh:
        return cached["data"]
    if cached and not refresh:
        # 回旧值 + 后台重算
        if not _stats_cache.get(f"busy:{key}"):
            _stats_cache[f"busy:{key}"] = True

            async def _recompute() -> None:
                from ..database import public_session_maker
                try:
                    async with public_session_maker() as db2:
                        data = await stats_snapshot(days=days, assets=assets, user_id=user_id, db=db2)
                    _stats_cache[key] = {"ts": _time.time(), "data": data}
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    _stats_cache[f"busy:{key}"] = False

            _asyncio.create_task(_recompute())
        return cached["data"]
    cached = _stats_cache.get(key)
    if cached:
        # 有旧值（哪怕过期）→ 回旧值 + 后台重算（上面分支已处理 refresh）
        return cached["data"]
    # 完全无缓存：返回空骨架 + 后台重算（32s 慢算绝不能挡在请求路径上）
    if not _stats_cache.get(f"busy:{key}"):
        _stats_cache[f"busy:{key}"] = True
        empty = {
            "window": {"begin": None, "end": None, "days": days},
            "assets": [], "correlation": {"labels": [], "matrix": []},
            "frontier": {"assets": [], "samples": []},
            "pending": True,
        }
        _stats_cache[key] = {"ts": now - 86400, "data": empty}  # 标记为已过期

        async def _recompute2() -> None:
            # 子进程计算：纯 Python 循环几百万行如果在事件循环内跑会冻结整个服务
            # （2026-08-30 事故：health 都无响应）。结果落 cache 文件再读入。
            import subprocess as _sp
            try:
                proc = await _asyncio.create_subprocess_exec(
                    _sys.executable, "scripts/compute_stats_snapshot.py",
                    str(days), assets or "all", user_id,
                    cwd=str(Path(__file__).resolve().parents[2] / "backend"),
                    stdout=_asyncio.subprocess.DEVNULL, stderr=_asyncio.subprocess.DEVNULL)
                await _asyncio.wait_for(proc.wait(), timeout=600)
                cache_file = (_Path(__file__).resolve().parents[2] / "backend" / "cache"
                              / f"stats_snapshot_{user_id}_{days}_{assets or 'all'}.json")
                if cache_file.exists():
                    data = _json.loads(cache_file.read_text(encoding="utf-8"))
                    _stats_cache[key] = {"ts": _time.time(), "data": data}
            except Exception:  # noqa: BLE001
                pass
            finally:
                _stats_cache[f"busy:{key}"] = False

        _asyncio.create_task(_recompute2())
    return _stats_cache[key]["data"]


_stats_cache: dict = {}


@router.get("/snapshot/_fresh")
async def stats_snapshot(
    days: int = Query(365, ge=30, le=3650),
    assets: Optional[str] = Query(None),       # comma-separated symbols (optional filter)
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_public_db),
):
    end = date.today()
    begin = end - timedelta(days=days)
    begin_s, end_s = begin.isoformat(), end.isoformat()

    q = select(ResearchAsset).where(ResearchAsset.user_id == user_id)
    if assets:
        syms = [s.strip() for s in assets.split(",") if s.strip()]
        if syms:
            q = q.where(ResearchAsset.symbol.in_(syms))
    asset_rows = (await db.execute(q)).scalars().all()
    if not asset_rows:
        return {"window": {"begin": begin_s, "end": end_s, "days": days}, "assets": [],
                "correlation": {"labels": [], "matrix": []}, "frontier": {"assets": [], "samples": []}}

    # Load all prices in window once
    ids = [a.id for a in asset_rows]
    prices_rows = (await db.execute(
        select(ResearchAssetPrice)
        .where(ResearchAssetPrice.asset_id.in_(ids), ResearchAssetPrice.date >= begin_s)
        .order_by(ResearchAssetPrice.date)
    )).scalars().all()

    # asset_id -> {date: close}
    close_map: dict[str, dict[str, float]] = {a.id: {} for a in asset_rows}
    for p in prices_rows:
        close_map[p.asset_id][p.date] = p.close

    # Common trading dates across all assets
    all_dates = sorted(set().union(*(set(m.keys()) for m in close_map.values())) if close_map else [])
    if not all_dates:
        return {"window": {"begin": begin_s, "end": end_s, "days": days}, "assets": [],
                "correlation": {"labels": [], "matrix": []}, "frontier": {"assets": [], "samples": []}}

    # Daily returns per asset (common-date aligned)
    ret_by_id: dict[str, list[float]] = {}
    nav_by_id: dict[str, list[float]] = {}
    prev_close: dict[str, float] = {}
    for d in all_dates:
        for a in asset_rows:
            c = close_map[a.id].get(d)
            if c is None:
                continue
            if a.id in prev_close and prev_close[a.id] > 0:
                ret_by_id.setdefault(a.id, []).append(c / prev_close[a.id] - 1.0)
            prev_close[a.id] = c
            nav_by_id.setdefault(a.id, []).append(c)

    # Latest factor exposures (for CAPM betas) — reuse factor_exposures table
    from ..models.factor import FactorExposure, Factor
    exposure_rows = (await db.execute(
        select(FactorExposure.asset_id, Factor.key, FactorExposure.beta, FactorExposure.r2)
        .join(Factor, Factor.id == FactorExposure.factor_id)
        .where(FactorExposure.asset_id.in_(ids), Factor.key.in_(["equity", "gold", "bond", "overseas_equity"]))
    )).all() if ids else []
    # latest as_of per (asset, factor) — rows are tuples (asset_id, key, beta, r2)
    expo_latest: dict[tuple[str, str], tuple[float, float]] = {}
    for row in exposure_rows:
        asset_id, fkey, beta, r2 = row
        if fkey and (asset_id, fkey) not in expo_latest:
            expo_latest[(asset_id, fkey)] = (beta, r2)

    # Build per-asset payloads
    assets_out = []
    front_assets = []          # eligible for EF: list of (symbol, mu, sigma)
    corr_labels: list[str] = []
    corr_matrix_rows: list[list[float]] = []

    for a in asset_rows:
        rets = ret_by_id.get(a.id, [])
        nav = nav_by_id.get(a.id, [])
        reasons: list[str] = []
        if a.is_money_market:
            reasons.append("货币基金（净值恒定，风险指标无意义）")
        vol = _annualize_sigma(rets)
        if vol < ZERO_VOL_EPS and rets:
            reasons.append("近零波动（风险指标无意义）")
        if len(rets) < MIN_OBS:
            reasons.append(f"窗口内有效日收益不足 {MIN_OBS} 天")
        eligible = not reasons

        mu = _annualize_mu(rets)
        mdd = min(_max_drawdown_path(nav)) if nav else 0.0
        var, cvar = _var_cvar(rets) if eligible else (0.0, 0.0)

        # benchmark mapping (same as detail panel)
        bench = _benchmark_for(a)

        assets_out.append({
            "symbol": a.symbol,
            "name": a.name,
            "asset_type": a.asset_type,
            "category": a.category,
            "status": a.status,
            "eligible": eligible,
            "excluded_reasons": reasons,
            "returns": dict(zip(all_dates, rets)),
            "nav_normalized": dict(zip(all_dates, [v / nav[0] for v in nav])) if nav and nav[0] else {},
            "ann_return": round(mu, 6),
            "ann_volatility": round(vol, 6),
            "sharpe": round((mu - 0.02) / vol, 4) if eligible and vol > 0 else None,
            "max_drawdown": round(mdd, 6),
            "mdd_series": [{"date": d, "drawdown": round(v, 6)}
                           for d, v in zip(all_dates, _max_drawdown_path(nav))] if nav else [],
            "rolling_30d": [{"date": d, "ret": round(v, 6) if v is not None else None}
                            for d, v in zip(all_dates, _rolling_return(rets, window=30))] if rets else [],
            "var95": round(var, 6),
            "cvar95": round(cvar, 6),
            "beta": {k: round(v, 4) for (aid, k), (v, _r2) in expo_latest.items() if aid == a.id},
            "beta_r2": {k: round(r2, 3) for (aid, k), (_v, r2) in expo_latest.items() if aid == a.id},
            "benchmark": bench,
            "total_annual_cost": round(
                (a.mgmt_fee or 0) + (a.custody_fee or 0) + (a.sales_service_fee or 0), 4
            ),
            "purchase_fee": a.purchase_fee,
            "redeem_fee_note": a.redeem_fee_note or "",
        })

        if eligible:
            front_assets.append((a.symbol, mu, vol))
            corr_labels.append(a.symbol)
            corr_matrix_rows.append(rets)

    # Correlation matrix (Pearson, common dates; eligible assets only)
    corr_matrix: list[list[float]] = []
    if len(corr_labels) >= 2:
        n = min(len(r) for r in corr_matrix_rows)
        X = np.array([r[-n:] for r in corr_matrix_rows])
        corr = np.corrcoef(X)
        corr_matrix = np.nan_to_num(corr, nan=0.0).round(4).tolist()

    # Efficient frontier — Monte Carlo (numpy only, plan §3.6)
    samples: list[dict] = []
    if len(front_assets) >= 2:
        symbols = [s for s, _m, _v in front_assets]
        mus = np.array([m for _s, m, _v in front_assets])
        n = min(len(r) for r in corr_matrix_rows)
        X = np.array([r[-n:] for r in corr_matrix_rows]).T  # T x N
        cov = np.cov(X, rowvar=False) * TRADING_DAYS
        rng = np.random.default_rng(42)
        for _ in range(20000):
            w = rng.dirichlet(np.ones(len(symbols)))
            mu_p = float(w @ mus)
            sigma_p = float(math.sqrt(w @ cov @ w))
            samples.append({"mu": round(mu_p, 6), "sigma": round(sigma_p, 6)})
        # dedupe to keep payload small (bucket by 0.0005 grid)
        seen: set[tuple] = set()
        deduped = []
        for s in samples:
            k = (round(s["mu"], 4), round(s["sigma"], 4))
            if k not in seen:
                seen.add(k)
                deduped.append(s)
            if len(deduped) >= 3000:
                break
        samples = deduped

    return {
        "window": {"begin": begin_s, "end": end_s, "days": days},
        "assets": assets_out,
        "correlation": {"labels": corr_labels, "matrix": corr_matrix},
        "frontier": {
            "assets": [{"symbol": s, "mu": round(m, 6), "sigma": round(v, 6)}
                       for s, m, v in front_assets],
            "samples": samples,
        },
    }


def _benchmark_for(a: ResearchAsset) -> dict:
    """D2 benchmark mapping (mirrors research_assets._pick_benchmark)."""
    if a.is_money_market:
        return {"symbol": None, "name": None, "exchange": None}
    text = f"{a.name or ''} {a.category or ''}"
    if "黄金" in text:
        return {"symbol": "518880", "name": "黄金ETF", "exchange": "SH"}
    if "债" in text:
        return {"symbol": "bench-cnbd", "name": "中债综合财富", "exchange": "IDX"}
    if any(k in text for k in ("海外", "纳指", "标普", "QDII", "美股", "港")):
        return {"symbol": "513100", "name": "纳指ETF", "exchange": "SH"}
    return {"symbol": "000300", "name": "沪深300", "exchange": "SH"}
