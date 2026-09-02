"""Factor exposure & contribution engine (Phase 2, self-built per ADR-3/ADR-6..9).

Time-series regression methodology follows docs/plans/2026-08-21-investment-research-system.md §8:
default 500-trading-day (~24-month) daily window, monthly as_of refresh, VIF>5 auto-switch
to ridge (alpha=0.1), quality gates R2>0.3 / |t|>1.5.  Pure-numpy implementation — no
statsmodels dependency, closed-form OLS/ridge with classic standard-error estimates
(ridge t-stats are the standard engineering approximation of a biased estimator).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.factor import Factor, FactorExposure, FactorValue
from ..models.research_asset import ResearchAsset, ResearchAssetPrice

TRADING_DAYS_PER_YEAR = 252
DEFAULT_WINDOW_DAYS = 500          # ~24 months of daily returns (ADR methodology option B)
DEFAULT_RIDGE_ALPHA = 0.1
VIF_SWITCH_THRESHOLD = 5.0         # collinearity gate -> ridge (methodology §8)
MIN_SAMPLE_RATIO = 0.8             # <24-month history assets get no exposure (methodology §5.3)


def _month_ends(dates: list[str]) -> list[str]:
    """Last calendar date per YYYY-MM group from a sorted list of ISO dates."""
    ends: list[str] = []
    for d in dates:
        if not ends or ends[-1][:7] != d[:7]:
            ends.append(d)
        else:
            ends[-1] = d
    return ends


def _vif_max(factors_matrix: np.ndarray) -> float:
    """Max variance inflation factor across columns.

    Uses the identity VIF_j = diag(inv(corr(X)))_j — one matrix inversion
    replaces k per-column regressions (57-factor windows were the hot spot).
    A singular correlation matrix (constant/collinear column) means infinite VIF.
    """
    n, k = factors_matrix.shape
    if k < 2:
        return 1.0
    std = factors_matrix.std(axis=0)
    if np.any(std <= 0):
        return float("inf")            # constant factor column: perfectly collinear
    xs = (factors_matrix - factors_matrix.mean(axis=0)) / std
    corr = (xs.T @ xs) / n
    try:
        inv = np.linalg.inv(corr)
    except np.linalg.LinAlgError:
        return float("inf")
    diag = np.diag(inv)
    if np.any(diag <= 0):
        return float("inf")
    return float(np.max(diag))


def compute_exposure(
    asset_returns: list[tuple[str, float]],
    factor_returns: dict[str, list[tuple[str, float]]],
    window_days: int = DEFAULT_WINDOW_DAYS,
    ridge_alpha: float = DEFAULT_RIDGE_ALPHA,
) -> dict | None:
    """Run one time-series regression of asset daily returns on factor daily returns.

    Returns None when aligned samples < window_days*MIN_SAMPLE_RATIO.  Dates are
    inner-joined across asset + all factors, so QDII publication lag simply drops
    to common trading days (risk R3).  Beta signs are raw return sensitivities
    (no standardization) so contribution = beta * factor return stays additive.
    """
    factor_ids = sorted(factor_returns.keys())
    if not factor_ids:
        return None

    asset_map = dict(asset_returns)
    factor_maps = {fid: dict(factor_returns[fid]) for fid in factor_ids}
    # true INNER JOIN across asset + every factor: a date missing from any
    # single factor must drop out, otherwise fm[d] raises KeyError
    common_set = set(asset_map)
    for m in factor_maps.values():
        common_set &= set(m)
    common_dates = sorted(common_set)

    min_samples = int(window_days * MIN_SAMPLE_RATIO)
    if len(common_dates) < min_samples:
        return None
    use_dates = common_dates[-window_days:]

    y = np.array([asset_map[d] for d in use_dates], dtype=float)
    X = np.column_stack([
        np.ones(len(use_dates)),
        *[np.array([factor_maps[fid][d] for d in use_dates], dtype=float) for fid in factor_ids],
    ])
    n, k = X.shape
    dof = n - k
    if dof <= 0:
        return None

    vif = _vif_max(X[:, 1:])
    method = "ridge" if vif > VIF_SWITCH_THRESHOLD else "ols"

    xtx = X.T @ X
    if method == "ridge":
        penalty = np.eye(k) * ridge_alpha
        penalty[0, 0] = 0.0                   # intercept is never penalized
        xtx_inv = np.linalg.inv(xtx + penalty)
    else:
        xtx_inv = np.linalg.inv(xtx)
    beta_vec = xtx_inv @ (X.T @ y)

    resid = y - X @ beta_vec
    rss = float(resid @ resid)
    tss = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - rss / tss if tss > 0 else 0.0
    sigma2 = rss / dof
    se = np.sqrt(np.maximum(sigma2 * np.diag(xtx_inv), 0.0))

    betas = {fid: float(beta_vec[i + 1]) for i, fid in enumerate(factor_ids)}
    t_stats = {
        fid: (float(beta_vec[i + 1] / se[i + 1]) if se[i + 1] > 0 else None)
        for i, fid in enumerate(factor_ids)
    }
    return {
        "as_of": use_dates[-1],
        "betas": betas,
        "t_stats": t_stats,
        "alpha_daily": float(beta_vec[0]),
        "r2": float(r2),
        "method": method,
        "n_samples": n,
        "vif_max": vif,
        "factor_ids": factor_ids,
    }


async def recompute_exposures(
    db: AsyncSession,
    user_id: str,
    full: bool = False,
    window_days: int = DEFAULT_WINDOW_DAYS,
    ridge_alpha: float = DEFAULT_RIDGE_ALPHA,
    asset_symbols: list[str] | None = None,
) -> dict:
    """Recompute monthly factor exposures for pooled research assets.

    mmf assets regress against is_market factors only (ADR-10).  ``full=True``
    recomputes every attainable month-end as_of in the covered history; the
    default only fills the latest month (daily refresh auto-fills on the first
    run of a month).  ``asset_symbols`` restricts the run to specific symbols
    (None = every pooled asset).  Upsert keyed on (asset, as_of, factor).
    """
    q = select(ResearchAsset).where(ResearchAsset.user_id == user_id, ResearchAsset.status == "pooled")
    if asset_symbols:
        q = q.where(ResearchAsset.symbol.in_(asset_symbols))
    assets = (await db.execute(q)).scalars().all()
    factors = (await db.execute(select(Factor).where(Factor.active.is_(True)))).scalars().all()
    if not assets or not factors:
        return {"assets": 0, "factors": len(factors), "months": 0, "regressions": 0, "skipped": []}

    factor_ids = [f.id for f in factors]

    # 池内最早/最晚价格日（SQL 聚合，不全量加载）：最早价格日是因子值查询的
    # 精确下界——共同交易日必须同时是资产收益日，早于它的因子行永远进不了
    # 任何回归窗口（full 回填也成立）。
    asset_filter = [ResearchAsset.user_id == user_id, ResearchAsset.status == "pooled"]
    if asset_symbols:
        asset_filter.append(ResearchAsset.symbol.in_(asset_symbols))
    aid_subq = select(ResearchAsset.id).where(*asset_filter)
    bounds = (await db.execute(
        select(func.min(ResearchAssetPrice.date), func.max(ResearchAssetPrice.date))
        .where(ResearchAssetPrice.asset_id.in_(aid_subq))
    )).first()
    min_price_date, max_price_date = (bounds[0], bounds[1]) if bounds else (None, None)

    fv_q = (
        select(FactorValue.factor_id, FactorValue.date, FactorValue.value)
        .where(FactorValue.factor_id.in_(factor_ids), FactorValue.kind == "return")
        .order_by(FactorValue.date)
    )
    if min_price_date:
        fv_q = fv_q.where(FactorValue.date >= min_price_date)
    if not full and max_price_date:
        # 只回填最新月末：窗口最多回看 window_days 个交易日（≈ window_days*1.16
        # 日历天），因子行留 2 倍日历余量即可完整覆盖，再早的行裁掉
        # （26.8 万行全量 → 数万行；2026-09-02 用户选 5 只标的卡死 300s 的另一根因）。
        cut = (datetime.fromisoformat(max_price_date) - timedelta(days=window_days * 2)).date().isoformat()
        fv_q = fv_q.where(FactorValue.date >= cut)
    fv_rows = (await db.execute(fv_q)).all()
    factor_series: dict[str, list[tuple[str, float]]] = {fid: [] for fid in factor_ids}
    for fid, d, v in fv_rows:
        factor_series[fid].append((d, float(v)))

    market_ids = [f.id for f in factors if f.is_market]
    written = 0
    months_done = set()
    skipped: list[dict] = []

    # 一次加载该用户全部现有暴露行，避免每 (asset, month, factor) 一条 SELECT
    # 的 N+1 地狱 —— 全量回填时那是上万次往返、请求必然超时。
    # asset_symbols 时必须下推过滤：否则小范围重算也会全量加载 400 万+ 行
    # （2026-09-02 用户选 5 只标的卡死 300s 的根因）。
    exp_q = (
        select(FactorExposure)
        .join(ResearchAsset, FactorExposure.asset_id == ResearchAsset.id)
        .where(ResearchAsset.user_id == user_id)
    )
    if asset_symbols:
        exp_q = exp_q.where(ResearchAsset.symbol.in_(asset_symbols))
    exp_rows = (await db.execute(exp_q)).scalars().all()
    existing_map: dict[tuple[str, str, str], FactorExposure] = {
        (e.asset_id, e.as_of_date, e.factor_id): e for e in exp_rows
    }

    # 价格分块批量加载（N+1 → 每 chunk 一条 IN 查询，内存只保留一个 chunk）
    CHUNK = 200
    for ci in range(0, len(assets), CHUNK):
        chunk = assets[ci:ci + CHUNK]
        prows = (await db.execute(
            select(ResearchAssetPrice.asset_id, ResearchAssetPrice.date, ResearchAssetPrice.close)
            .where(ResearchAssetPrice.asset_id.in_([a.id for a in chunk]))
            .order_by(ResearchAssetPrice.asset_id, ResearchAssetPrice.date)
        )).all()
        price_by_asset: dict[str, list[tuple[str, float]]] = {}
        for aid, d, c in prows:
            price_by_asset.setdefault(aid, []).append((d, float(c)))
        for asset in chunk:
            price_rows = price_by_asset.get(asset.id, [])
            if len(price_rows) < 2:
                skipped.append({"symbol": asset.symbol, "name": asset.name, "reason": "无价格数据（先到标的页同步历史净值）"})
                continue
            closes = [(d, float(c)) for d, c in price_rows]
            asset_returns: list[tuple[str, float]] = []
            prev_c = closes[0][1]
            for d, c in closes[1:]:
                if prev_c > 0:
                    asset_returns.append((d, c / prev_c - 1.0))
                prev_c = c
            asset_map = dict(asset_returns)

            use_factors = {fid: factor_series[fid] for fid in (market_ids if (asset.is_money_market and market_ids) else factor_ids) if factor_series[fid]}
            if not use_factors:
                skipped.append({"symbol": asset.symbol, "name": asset.name, "reason": "因子无收益数据（先同步因子库）"})
                continue

            factor_maps = {fid: dict(s) for fid, s in use_factors.items()}
            sample_floor = int(window_days * MIN_SAMPLE_RATIO)
            # 贪心因子选择：覆盖天数多的因子先纳入；纳入某因子会使
            # (资产∩已选因子) 交集跌破最小样本时跳过该稀疏因子，
            # 避免"一个坏因子掏空整个交集"（全量 intersection 的副作用）
            common_set = set(asset_map)
            selected: dict[str, dict[str, float]] = {}
            for fid in sorted(factor_maps, key=lambda f: -len(factor_maps[f])):
                fm = factor_maps[fid]
                if not fm:
                    continue
                trial = common_set & set(fm)
                if not selected or len(trial) >= sample_floor:
                    common_set = trial
                    selected[fid] = fm
            factor_maps = selected
            common_dates = sorted(common_set)
            if len(common_dates) < sample_floor or not factor_maps:
                skipped.append({"symbol": asset.symbol, "name": asset.name,
                                "reason": f"与因子共同交易日不足{sample_floor}"})
                continue
            # month-end as_of candidates whose trailing window can still meet the sample floor
            cd_index = {d: i for i, d in enumerate(common_dates)}
            as_of_candidates = []
            for me in _month_ends(common_dates):
                idx = cd_index.get(me)
                if idx is not None and idx + 1 >= sample_floor:
                    as_of_candidates.append((me, idx + 1))
            if not as_of_candidates:
                skipped.append({"symbol": asset.symbol, "name": asset.name, "reason": f"共同交易日不足{sample_floor}（历史太短）"})
                continue
            if not full:
                as_of_candidates = as_of_candidates[-1:]

            for me, n_avail in as_of_candidates:
                window_slice = common_dates[max(0, n_avail - window_days):n_avail]
                ar = [(d, asset_map[d]) for d in window_slice]
                fr = {fid: [(d, fm[d]) for d in window_slice] for fid, fm in factor_maps.items()}
                res = compute_exposure(ar, fr, window_days=window_days, ridge_alpha=ridge_alpha)
                if res is None:
                    continue
                months_done.add((asset.id, me))
                for fid in res["betas"]:
                    key = (asset.id, me, fid)
                    existing = existing_map.get(key)
                    # params 快照不再逐行存储：同一配置 2.96M 行 × 2.2KB 曾吃掉 6.6GB
                    # （2026-08-29 事故）。回归配置由 window_days 列 + 调用参数可完全还原。
                    if existing is not None:
                        existing.beta = res["betas"][fid]
                        existing.t_stat = res["t_stats"][fid]
                        existing.r2 = res["r2"]
                        existing.method = res["method"]
                        existing.window_days = res["n_samples"]
                        existing.params = None
                    else:
                        new_row = FactorExposure(
                            asset_id=asset.id, as_of_date=me, factor_id=fid,
                            beta=res["betas"][fid], t_stat=res["t_stats"][fid], r2=res["r2"],
                            method=res["method"], window_days=res["n_samples"], params=None,
                        )
                        db.add(new_row)
                        existing_map[key] = new_row
                    written += 1
    await db.commit()
    return {"assets": len(assets), "factors": len(factors), "months": len(months_done),
            "regressions": len(months_done), "rows_written": written, "skipped": skipped}


async def compute_contribution(
    db: AsyncSession,
    asset_id: str,
    start: str,
    end: str,
    view: str = "return",
) -> dict:
    """Realtime contribution analysis (ADR-8: never persisted).

    return view: daily contribution_i = beta_i * factor_return_i summed over the
    window on common dates; total return R = prod(1+r)-1; alpha = R - sum(contrib)
    so the identity sum(contrib)+alpha == R holds exactly (acceptance gate #2).
    risk view: RC_i = beta_i^2 sigma_i^2 / sum_j beta_j^2 sigma_j^2 (methodology §8).
    """
    asset = (await db.execute(select(ResearchAsset).where(ResearchAsset.id == asset_id))).scalar_one_or_none()
    if asset is None:
        raise ValueError("asset not found")

    exp_rows = (await db.execute(
        select(FactorExposure, Factor)
        .join(Factor, FactorExposure.factor_id == Factor.id)
        .where(FactorExposure.asset_id == asset_id, FactorExposure.as_of_date <= end)
        .order_by(FactorExposure.as_of_date.desc())
    )).all()
    if not exp_rows:
        raise ValueError(
            f"标的「{asset.name}({asset.symbol})」在 {end} 之前没有因子暴露数据。"
            f"请先在「因子分析」页点击「重算暴露」（会深度回填历史月份），"
            f"并确认该标的已同步历史净值。"
        )
    latest_as_of = exp_rows[0][0].as_of_date
    beta_by_factor: dict[str, float] = {}
    factor_names: dict[str, str] = {}
    for fe, f in exp_rows:
        if fe.as_of_date != latest_as_of:
            continue
        beta_by_factor[f.id] = fe.beta
        factor_names[f.id] = f.name

    fv_rows = (await db.execute(
        select(FactorValue)
        .where(
            FactorValue.factor_id.in_(list(beta_by_factor.keys())),
            FactorValue.kind == "return",
            FactorValue.date > start,
            FactorValue.date <= end,
        )
        .order_by(FactorValue.date)
    )).scalars().all()
    factor_daily: dict[str, dict[str, float]] = {fid: {} for fid in beta_by_factor}
    for fv in fv_rows:
        factor_daily[fv.factor_id][fv.date] = fv.value

    price_rows = (await db.execute(
        select(ResearchAssetPrice.date, ResearchAssetPrice.close)
        .where(ResearchAssetPrice.asset_id == asset_id, ResearchAssetPrice.date > start,
               ResearchAssetPrice.date <= end)
        .order_by(ResearchAssetPrice.date)
    )).all()

    if view == "risk":
        sigmas = {}
        for fid in beta_by_factor:
            rets = list(factor_daily[fid].values())
            if len(rets) < 2:
                continue
            sigma_ann = float(np.std(rets, ddof=1)) * np.sqrt(TRADING_DAYS_PER_YEAR)
            if sigma_ann > 0:
                sigmas[fid] = sigma_ann
        denom = sum((beta_by_factor[fid] ** 2) * (s ** 2) for fid, s in sigmas.items())
        items = []
        for fid, sigma in sigmas.items():
            rc = (beta_by_factor[fid] ** 2) * (sigma ** 2) / denom if denom > 0 else 0.0
            items.append({
                "factor_id": fid, "factor_name": factor_names[fid],
                "beta": beta_by_factor[fid], "sigma_ann": sigma, "risk_contribution": rc,
            })
        items.sort(key=lambda x: -x["risk_contribution"])
        return {
            "view": "risk", "asset_id": asset_id, "asset_name": asset.name,
            "start": start, "end": end, "as_of": latest_as_of,
            "explained_vol": float(np.sqrt(denom)) if denom > 0 else 0.0,
            "items": items,
        }

    # return view: common dates across asset prices and all factors in window
    close_map = {d: float(c) for d, c in price_rows}
    asset_daily: dict[str, float] = {}
    prev = None
    for d in sorted(close_map):
        if prev is not None and close_map[prev] > 0:
            asset_daily[d] = close_map[d] / close_map[prev] - 1.0
        prev = d
    common_dates = sorted(set(asset_daily) & set().union(*(set(v) for v in factor_daily.values())))
    if not common_dates:
        raise ValueError("no common factor/asset dates in window")

    total_return = 1.0
    for d in common_dates:
        total_return *= (1.0 + asset_daily[d])
    total_return -= 1.0

    contrib = {fid: sum(beta_by_factor[fid] * factor_daily[fid][d] for d in common_dates if d in factor_daily[fid])
               for fid in beta_by_factor}
    alpha = total_return - sum(contrib.values())
    items = []
    for fid in beta_by_factor:
        items.append({
            "factor_id": fid, "factor_name": factor_names[fid],
            "beta": beta_by_factor[fid], "contribution": contrib[fid],
        })
    items.sort(key=lambda x: -abs(x["contribution"]))
    return {
        "view": "return", "asset_id": asset_id, "asset_name": asset.name,
        "start": start, "end": end, "as_of": latest_as_of,
        "n_days": len(common_dates),
        "total_return": total_return, "alpha": alpha,
        "sum_contributions": sum(contrib.values()),
        "identity_residual": (sum(contrib.values()) + alpha) - total_return,
        "items": items,
    }
