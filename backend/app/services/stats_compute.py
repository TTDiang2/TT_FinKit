"""统计快照计算——唯一实现，供三处调用：

1. 路由 /api/research/stats/snapshot/_fresh（请求路径直算，小组合秒回）
2. 开发态后台重算：子进程 scripts/compute_stats_snapshot.py（薄壳调本模块），
   纯 Python 大循环不占用后端事件循环（2026-08-30 事故）
3. PyInstaller 打包态后台重算：asyncio.to_thread + 本模块（打包态没有独立解释器，
   spawn sys.executable 只会再拉起一个后端实例；线程每 5ms 让出 GIL，单用户可接受）

载荷契约：compute_payload 是 /snapshot/_fresh 的函数体搬出，字段（beta/eligible/
nav_normalized/mdd_series/rolling_30d/frontier 蒙特卡洛样本等）必须与前端
AssetStatsTab.vue 的 9 图严格对应。曾有两份实现（ORM 版 vs 脚本精简版）导致
子进程缓存缺字段、前端图表空——2026-09-02 合并为这一份。

缓存契约：结果 JSON 落在 public 库旁 cache/ 下，文件名统一由 cache_file_for()
提供（user_id 的 ":" → "_"、assets 的 "," → "-"，Windows 文件名安全）。
"""
import asyncio
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.research_asset import ResearchAsset, ResearchAssetPrice

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


def cache_dir() -> Path:
    from ..config import public_db_path
    return Path(public_db_path()).parent / "cache"


def cache_file_for(user_id: str, days: int, assets: str | None) -> Path:
    key = f"{user_id}_{days}_{assets or 'all'}".replace(":", "_").replace(",", "-")
    return cache_dir() / f"stats_snapshot_{key}.json"


async def compute_payload(
    db: AsyncSession, days: int, assets: str | None, user_id: str,
) -> dict:
    """9 图数据源的唯一计算实现（原 /snapshot/_fresh 函数体）。

    All computations share ONE window and ONE common-trading-date alignment
    so the charts never contradict each other (implementation plan §3.6).
    """
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


async def compute_and_cache(days: int, assets: str | None, user_id: str) -> dict:
    """自建会话算完整载荷并落缓存，返回数据（frozen 态线程 / 子进程共享入口）。

    用一次性 engine 且显式 dispose：不能用 app.database 的全局 public_session_maker——
    全局 engine 的 aiosqlite 连接线程（非 daemon）会让子进程算完也不退出，
    路由侧 proc.wait() 永远挂着（2026-09-02 实测：缓存落盘 10 分钟 pending 不消除）。
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from ..config import _resolve_public_url
    from ..database import _make_engine
    eng = _make_engine(_resolve_public_url())
    try:
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker() as db:
            data = await compute_payload(db=db, days=days, assets=assets, user_id=user_id)
    finally:
        await eng.dispose()
    out = cache_file_for(user_id, days, assets)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def run_compute_blocking(days: int, assets: str | None, user_id: str) -> dict:
    """线程安全入口：新开事件循环跑 async 计算（打包态 asyncio.to_thread 用）。"""
    return asyncio.run(compute_and_cache(days, assets, user_id))


def main() -> None:
    """子进程 CLI：python scripts/compute_stats_snapshot.py <days> <assets|all> <user_id>"""
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    assets = sys.argv[2] if len(sys.argv) > 2 else "all"
    user_id = sys.argv[3]
    t0 = time.time()
    data = asyncio.run(compute_and_cache(days, assets, user_id))
    out = cache_file_for(user_id, days, assets)
    print(f"done in {time.time()-t0:.0f}s -> {out} "
          f"({out.stat().st_size/1e3:.0f} KB, {len(data.get('assets') or [])} assets)")


if __name__ == "__main__":
    main()
