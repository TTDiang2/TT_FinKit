"""Factor evaluation engine — IC/ICIR tests, quantile portfolios, long-short metrics.

Implements the spec §4 of docs/plans/2026-08-23-factor-library-and-strategy-upgrade.md:
monthly cross-sectional IC (factor exposure vs next-month fund returns), IC decay,
quantile (5-group) returns, long-short portfolio metrics, and screening against
configurable thresholds.  Pure numpy — rank correlations use an average-rank
implementation (no scipy dependency).

Conventions (spec §0.4):
- ic       = Pearson(factor exposures, next-month returns) per month-end
- rank_ic  = Spearman (average ranks, ties handled)
- icir     = mean(IC)/std(IC) (ddof=1); annualized = ×√12
- t_stat   = icir × √N
- win_rate = mean(IC > 0)
- quantiles: 1 = lowest exposure ... 5 = highest (np.quantile cuts)
- long-short = Q5 equal-weight − Q1 equal-weight, monthly rebalance
- benchmark = pool equal-weight fund monthly returns
"""
from __future__ import annotations

import json
import math
from bisect import bisect_right
from dataclasses import dataclass, field, asdict
from datetime import datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.factor import Factor, FactorExposure, FactorValue
from ..models.factor_evaluation import FactorIcPoint, FactorEvaluation
from ..models.research_asset import ResearchAsset, ResearchAssetPrice

PERIODS_PER_YEAR = 12          # monthly IC frequency
MIN_PERIODS = 6                # below this ICIR/t-stat are not meaningful
MIN_CROSS_SECTION = 4          # funds per period to count the period
RISK_FREE = 0.02               # annual, for long-short sharpe

# Default screening thresholds (user-adjustable in UI; only ICIR>0.5 is
# strictly sourced — see spec §0.4 research notes)
DEFAULT_THRESHOLDS = {
    "rank_ic_mean": 0.03,
    "icir_annualized": 0.5,
    "win_rate": 0.6,
    "ls_sharpe": 1.5,
}


# --------------------------------------------------------------- helpers ----

def rankdata_avg(x: list[float] | np.ndarray) -> np.ndarray:
    """Average ranks (ties share the mean rank) — scipy.stats.rankdata equivalent."""
    arr = np.asarray(x, dtype=float)
    n = len(arr)
    if n == 0:
        return arr
    order = np.argsort(arr, kind="mergesort")
    ranks = np.empty(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and arr[order[j + 1]] == arr[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0          # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 2:
        return None
    sa, sb = a.std(), b.std()
    if sa < 1e-12 or sb < 1e-12:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 2:
        return None
    return pearson(rankdata_avg(a), rankdata_avg(b))


def ols_alpha_beta(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    """OLS y = alpha + beta*x; returns (alpha_per_period, beta)."""
    X = np.column_stack([np.ones(len(x)), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(coef[0]), float(coef[1])


def max_drawdown(nav: np.ndarray) -> float:
    if len(nav) < 2:
        return 0.0
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1.0
    return float(dd.min())


def assign_quantiles(values: np.ndarray, q: int = 5) -> np.ndarray:
    """Quantile assignment 1..q (1 = lowest). Falls back to fewer distinct cuts
    when values are highly discrete (small pools)."""
    n = len(values)
    if n < q:
        # not enough names: rank-based split so each bucket gets >=1 when possible
        order = np.argsort(values, kind="mergesort")
        out = np.empty(n, dtype=int)
        for pos, idx in enumerate(order):
            out[idx] = min(q, pos * q // max(n, 1) + 1)
        return out
    try:
        cuts = np.quantile(values, [i / q for i in range(1, q)])
        return np.digitize(values, cuts, right=False) + 1
    except Exception:
        return np.ones(n, dtype=int)


# ------------------------------------------------------- core computation ----

@dataclass
class EvalOutcome:
    ic_points: list[dict] = field(default_factory=list)   # {date, ic, rank_ic, n}
    n_periods: int = 0
    ic_mean: float | None = None
    ic_std: float | None = None
    rank_ic_mean: float | None = None
    icir: float | None = None
    icir_annualized: float | None = None
    t_stat: float | None = None
    win_rate: float | None = None
    ic_autocorr_lag1: float | None = None
    ic_decay_1: float | None = None
    ic_decay_2: float | None = None
    ic_decay_3: float | None = None
    quantile_returns: dict | None = None                  # {"q1":..,"q5":..,"spread":..}
    ls_nav: list[dict] = field(default_factory=list)      # [{date, nav}]
    ls_ann_return: float | None = None
    ls_vol: float | None = None
    ls_sharpe: float | None = None
    ls_max_dd: float | None = None
    ls_calmar: float | None = None
    ls_alpha: float | None = None
    ls_beta: float | None = None
    ls_ir: float | None = None


def evaluate_series(
    period_dates: list[str],
    exposures: dict[str, list[float]],      # asset_id -> beta per period (aligned to period_dates)
    fwd_returns: dict[str, list[float | None]],  # asset_id -> next-1/2/3-period returns (None gaps)
    benchmark: list[float | None],
) -> EvalOutcome:
    """Pure computation from aligned per-period arrays.  ``fwd_returns[a][i]``
    is asset a's return from period i to period i+1 (None when missing);
    ``fwd_returns2/3`` variants for IC decay are derived via the 2/3-step keys."""
    out = EvalOutcome()
    n_periods = len(period_dates)
    ics: list[float] = []
    rank_ics: list[float] = []
    ic_rows: list[dict] = []
    decay2: list[float] = []
    decay3: list[float] = []

    for i in range(n_periods):
        xs, rs = [], []
        for a in exposures:
            x = exposures[a][i]
            r = fwd_returns[a][i] if i < len(fwd_returns[a]) else None
            if x is None or r is None:
                continue
            xs.append(x)
            rs.append(r)
        if len(xs) < MIN_CROSS_SECTION:
            ic_rows.append({"date": period_dates[i], "ic": None, "rank_ic": None, "n": len(xs)})
            continue
        xa, ra = np.array(xs), np.array(rs)
        ic = pearson(xa, ra)
        ric = spearman(xa, ra)
        ics.append(ic) if ic is not None else None
        rank_ics.append(ric) if ric is not None else None
        ic_rows.append({"date": period_dates[i], "ic": ic, "rank_ic": ric, "n": len(xs)})

        # IC decay: exposure at t vs return t -> t+2 / t+3
        for lag, sink in ((2, decay2), (3, decay3)):
            xs2, rs2 = [], []
            for a in exposures:
                x = exposures[a][i]
                r = None
                seq = fwd_returns[a]
                # compound lag consecutive period returns
                if all(i + k < len(seq) and seq[i + k] is not None for k in range(lag)):
                    r = 1.0
                    for k in range(lag):
                        r *= (1.0 + seq[i + k])
                    r -= 1.0
                if x is None or r is None:
                    continue
                xs2.append(x)
                rs2.append(r)
            if len(xs2) >= MIN_CROSS_SECTION:
                v = spearman(np.array(xs2), np.array(rs2))
                if v is not None:
                    sink.append(v)

    out.ic_points = ic_rows
    out.n_periods = len(ics)
    if len(ics) >= MIN_PERIODS:
        ia = np.array(ics)
        out.ic_mean = float(ia.mean())
        out.ic_std = float(ia.std(ddof=1)) if len(ia) > 1 else None
        out.rank_ic_mean = float(np.mean(rank_ics)) if rank_ics else None
        if out.ic_std and out.ic_std > 1e-12:
            out.icir = out.ic_mean / out.ic_std
            out.icir_annualized = out.icir * math.sqrt(PERIODS_PER_YEAR)
            out.t_stat = out.icir * math.sqrt(len(ia))
        out.win_rate = float((ia > 0).mean())
        if len(ia) > 2:
            a0 = ia[:-1] - ia[:-1].mean()
            a1 = ia[1:] - ia[1:].mean()
            denom = math.sqrt(float((a0 * a0).sum() * (a1 * a1).sum()))
            if denom > 1e-12:
                out.ic_autocorr_lag1 = float((a0 * a1).sum() / denom)
    out.ic_decay_1 = out.rank_ic_mean
    out.ic_decay_2 = float(np.mean(decay2)) if decay2 else None
    out.ic_decay_3 = float(np.mean(decay3)) if decay3 else None

    # ---- quantile portfolios + long-short ----
    q_sums: dict[int, list[float]] = {q: [] for q in range(1, 6)}
    ls_dates: list[str] = []                # as_of date of each PAIRED period (Q1&Q5 both present)
    ls_q5: list[float] = []
    ls_q1: list[float] = []
    bench_vals: list[float] = []
    for i in range(n_periods):
        xs, rs, keep = [], [], []
        for a in exposures:
            x = exposures[a][i]
            r = fwd_returns[a][i] if i < len(fwd_returns[a]) else None
            if x is not None and r is not None:
                xs.append(x)
                rs.append(r)
                keep.append(a)
        if len(xs) < MIN_CROSS_SECTION:
            continue
        xa, ra = np.array(xs), np.array(rs)
        groups = assign_quantiles(xa, 5)
        means = {}
        for q in range(1, 6):
            mask = groups == q
            if mask.any():
                means[q] = float(ra[mask].mean())
                q_sums[q].append(means[q])
        if 1 in means and 5 in means:
            ls_dates.append(period_dates[i])
            ls_q5.append(means[5])
            ls_q1.append(means[1])
            b = benchmark[i] if i < len(benchmark) else None
            bench_vals.append(b)

    if q_sums[1] and q_sums[5]:
        qr = {f"q{q}": float(np.mean(v)) for q, v in q_sums.items() if v}
        qr["spread"] = qr.get("q5", 0.0) - qr.get("q1", 0.0)
        out.quantile_returns = qr

        ls = np.array([h - l for h, l in zip(ls_q5, ls_q1)])
        nav = np.cumprod(1.0 + ls)
        out.ls_nav = [
            {"date": ls_dates[i], "nav": float(nav[i])}
            for i in range(len(ls))
        ]
        ann = float(ls.mean() * PERIODS_PER_YEAR)
        vol = float(ls.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR)) if len(ls) > 1 else None
        out.ls_ann_return = ann
        out.ls_vol = vol
        if vol and vol > 1e-12:
            out.ls_sharpe = (ann - RISK_FREE) / vol
        mdd = max_drawdown(nav)
        out.ls_max_dd = mdd
        if mdd < -1e-9:
            out.ls_calmar = ann / abs(mdd)
        if len(bench_vals) == len(ls):
            ba = np.array(bench_vals)
            alpha_p, beta = ols_alpha_beta(ls, ba)
            out.ls_alpha = float((1.0 + alpha_p) ** PERIODS_PER_YEAR - 1.0)
            out.ls_beta = beta
            excess = ls - ba
            es = float(excess.std(ddof=1)) if len(excess) > 1 else None
            if es and es > 1e-12:
                out.ls_ir = float(excess.mean() / es * math.sqrt(PERIODS_PER_YEAR))
    return out


def screen(outcome: EvalOutcome, thresholds: dict) -> dict:
    return {
        "rank_ic_mean": (outcome.rank_ic_mean is not None
                         and abs(outcome.rank_ic_mean) > thresholds["rank_ic_mean"]),
        "icir_annualized": (outcome.icir_annualized is not None
                            and abs(outcome.icir_annualized) > thresholds["icir_annualized"]),
        "win_rate": (outcome.win_rate is not None and outcome.win_rate > thresholds["win_rate"]),
        "ls_sharpe": (outcome.ls_sharpe is not None and outcome.ls_sharpe > thresholds["ls_sharpe"]),
    }


# ------------------------------------------------------- DB orchestration ----

async def evaluate_all_factors(
    db: AsyncSession,
    user_id: str,
    thresholds: dict | None = None,
    asset_symbols: list[str] | None = None,
) -> dict:
    """Recompute evaluations for every factor that has exposure history.

    Returns {"evaluated": [keys], "skipped": [{key, reason}]}.
    ``asset_symbols`` 下推过滤：随重算范围联动（2026-09-02 事故——选 5 只标的
    重算时本函数仍全池加载 4.23M 暴露行 + 数百万价格行，请求必然超时）。
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    factors = (await db.execute(select(Factor).where(Factor.active.is_(True)))).scalars().all()
    factor_by_id = {f.id: f for f in factors}

    aq = select(ResearchAsset).where(ResearchAsset.status == "pooled")
    if asset_symbols:
        aq = aq.where(ResearchAsset.symbol.in_(asset_symbols))
    assets = (await db.execute(aq)).scalars().all()
    asset_ids = [a.id for a in assets]

    # 列查询替代 ORM 实体加载（只需要 4 列；ORM 实体在百万行级别内存/构造都重数倍）
    exp_rows = (await db.execute(
        select(FactorExposure.factor_id, FactorExposure.asset_id,
               FactorExposure.as_of_date, FactorExposure.beta)
        .where(FactorExposure.asset_id.in_(asset_ids))
    )).all() if asset_ids else []

    # prices for monthly returns between as_of anchors
    price_rows = (await db.execute(
        select(ResearchAssetPrice.asset_id, ResearchAssetPrice.date, ResearchAssetPrice.close)
        .where(ResearchAssetPrice.asset_id.in_(asset_ids))
        .order_by(ResearchAssetPrice.date)
    )).all() if asset_ids else []
    close_by_asset: dict[str, dict[str, float]] = {}
    dates_by_asset: dict[str, list[str]] = {}
    for aid, d, c in price_rows:
        close_by_asset.setdefault(aid, {})[d] = float(c)
        dates_by_asset.setdefault(aid, []).append(d)   # 查询已按 date 排序

    # global grid of as_of month-ends (union)
    all_as_of = sorted({as_of for (_fid, _aid, as_of, _b) in exp_rows})
    evaluated, skipped = [], []

    # group exposures by factor
    by_factor: dict[str, list[tuple[str, str, str, float]]] = {}
    for e in exp_rows:
        by_factor.setdefault(e[0], []).append(e)

    for fid, rows in by_factor.items():
        f = factor_by_id.get(fid)
        if not f or not f.key:
            continue
        # exposures: asset -> {as_of: beta}
        expo: dict[str, dict[str, float]] = {}
        for (_fid, aid, as_of, beta) in rows:
            expo.setdefault(aid, {})[as_of] = beta

        # per-asset month returns between consecutive grid points covering its as_ofs
        grid = [d for d in all_as_of]
        fwd: dict[str, list[float | None]] = {}
        for aid in expo:
            cmap = close_by_asset.get(aid, {})
            series: list[float | None] = []
            for i, d in enumerate(grid):
                nxt = grid[i + 1] if i + 1 < len(grid) else None
                if nxt is None:
                    series.append(None)
                    continue
                # month return = last close on/before nxt / last close on/before d − 1
                dlist = dates_by_asset.get(aid, [])
                p0 = _last_close_on_or_before(dlist, cmap, d)
                p1 = _last_close_on_or_before(dlist, cmap, nxt)
                series.append((p1 / p0 - 1.0) if (p0 and p1) else None)
            fwd[aid] = series

        # benchmark: equal-weight mean of available fund returns per period
        bench: list[float | None] = []
        for i in range(len(grid)):
            vals = [fwd[a][i] for a in fwd if i < len(fwd[a]) and fwd[a][i] is not None]
            bench.append(float(np.mean(vals)) if vals else None)

        exposures_aligned = {
            aid: [expo[aid].get(d) for d in grid] if aid in expo else [None] * len(grid)
            for aid in expo
        }
        outcome = evaluate_series(grid, exposures_aligned, fwd, bench)

        if outcome.n_periods == 0:
            skipped.append({"key": f.key, "reason": "无有效暴露截面（先重算暴露）"})
            continue

        # persist IC points (batch upsert: 一次预载该因子全部已有 IC 点，
        # 替代逐行 SELECT 的 N+1 —— 60 因子 × 数十期曾意味着上千次往返)
        existing_pts = (await db.execute(
            select(FactorIcPoint).where(
                FactorIcPoint.user_id == user_id,
                FactorIcPoint.factor_key == f.key,
            )
        )).scalars().all()
        pt_by_date = {p.date: p for p in existing_pts}
        for row in outcome.ic_points:
            existing = pt_by_date.get(row["date"])
            if existing:
                existing.ic = row["ic"]
                existing.rank_ic = row["rank_ic"]
                existing.n = row["n"]
            else:
                db.add(FactorIcPoint(
                    user_id=user_id, factor_key=f.key,
                    date=row["date"], ic=row["ic"], rank_ic=row["rank_ic"], n=row["n"],
                ))
                pt_by_date[row["date"]] = None  # 防同批重复插入

        # upsert evaluation row
        ev = (await db.execute(
            select(FactorEvaluation).where(
                FactorEvaluation.user_id == user_id, FactorEvaluation.factor_key == f.key)
        )).scalar_one_or_none()
        if ev is None:
            ev = FactorEvaluation(user_id=user_id, factor_key=f.key)
            db.add(ev)
        ev.window_start = grid[0]
        ev.window_end = grid[-1]
        ev.n_periods = outcome.n_periods
        ev.ic_mean = outcome.ic_mean
        ev.ic_std = outcome.ic_std
        ev.rank_ic_mean = outcome.rank_ic_mean
        ev.icir = outcome.icir
        ev.icir_annualized = outcome.icir_annualized
        ev.t_stat = outcome.t_stat
        ev.win_rate = outcome.win_rate
        ev.ic_autocorr_lag1 = outcome.ic_autocorr_lag1
        ev.ic_decay_1 = outcome.ic_decay_1
        ev.ic_decay_2 = outcome.ic_decay_2
        ev.ic_decay_3 = outcome.ic_decay_3
        ev.quantile_returns = json.dumps(outcome.quantile_returns, ensure_ascii=False) if outcome.quantile_returns else None
        ev.ls_nav = json.dumps(outcome.ls_nav, ensure_ascii=False) if outcome.ls_nav else None
        ev.ls_ann_return = outcome.ls_ann_return
        ev.ls_vol = outcome.ls_vol
        ev.ls_sharpe = outcome.ls_sharpe
        ev.ls_max_dd = outcome.ls_max_dd
        ev.ls_calmar = outcome.ls_calmar
        ev.ls_alpha = outcome.ls_alpha
        ev.ls_beta = outcome.ls_beta
        ev.ls_ir = outcome.ls_ir
        ev.screen_result = json.dumps(screen(outcome, thresholds), ensure_ascii=False)
        ev.computed_at = datetime.utcnow().isoformat()
        evaluated.append(f.key)
        # 分因子提交：整个作业一个巨型事务会长时间持有 SQLite 写锁，
        # 把 UI 的所有写请求卡到 busy timeout（实际事故 2026-08-29）
        await db.commit()

    await db.commit()
    return {"evaluated": evaluated, "skipped": skipped}


def _last_close_on_or_before(dates: list[str], cmap: dict[str, float], d: str) -> float | None:
    """Close at or before date d.  ``dates`` 为与 cmap 同源的有序日期列表。

    曾用线性扫描（"small maps ~1000 acceptable"），但全池评估时
    资产数 × 网格点 × 2 次调用放大成数亿次迭代——2026-09-02 重算卡死热点之一。
    """
    idx = bisect_right(dates, d)         # O(log n)
    if idx == 0:
        return None
    return cmap[dates[idx - 1]]


def evaluation_to_dict(ev: FactorEvaluation) -> dict:
    return {
        "factor_key": ev.factor_key,
        "window_start": ev.window_start,
        "window_end": ev.window_end,
        "n_periods": ev.n_periods,
        "ic_mean": ev.ic_mean,
        "ic_std": ev.ic_std,
        "rank_ic_mean": ev.rank_ic_mean,
        "icir": ev.icir,
        "icir_annualized": ev.icir_annualized,
        "t_stat": ev.t_stat,
        "win_rate": ev.win_rate,
        "ic_autocorr_lag1": ev.ic_autocorr_lag1,
        "ic_decay_1": ev.ic_decay_1,
        "ic_decay_2": ev.ic_decay_2,
        "ic_decay_3": ev.ic_decay_3,
        "quantile_returns": json.loads(ev.quantile_returns) if ev.quantile_returns else None,
        "ls_nav": json.loads(ev.ls_nav) if ev.ls_nav else None,
        "ls_ann_return": ev.ls_ann_return,
        "ls_vol": ev.ls_vol,
        "ls_sharpe": ev.ls_sharpe,
        "ls_max_dd": ev.ls_max_dd,
        "ls_calmar": ev.ls_calmar,
        "ls_alpha": ev.ls_alpha,
        "ls_beta": ev.ls_beta,
        "ls_ir": ev.ls_ir,
        "screen_result": json.loads(ev.screen_result) if ev.screen_result else None,
        "computed_at": ev.computed_at,
    }
