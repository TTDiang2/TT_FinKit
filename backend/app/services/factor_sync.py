"""P1.2 factor sync engine.

Pipeline per eligible factor (registry def with a source and ``data_status='ok'``):
  1. fetch raw series via akshare wrappers (``factor_sources``) — every akshare
     call runs inside ``asyncio.to_thread`` behind ``asyncio.Semaphore(3)``,
     with retry/backoff 0.5s / 2s / 8s.
  2. transform into the factor return series (pure numpy functions below).
  3. incremental upsert into ``factor_values`` (kind='return' + kind='level'
     raw rows when available), UNIQUE(factor_id, date, kind) conflict skip.

Moneyflow history accumulation
------------------------------
``stock_individual_fund_flow_rank`` is a daily cross-section snapshot.
``backend/factor_moneyflow_history.json`` accumulates today's aggregate each
sync run; ``flow_zscore`` runs on that accumulated history.  The first runs
(< 40 points) raise NoDataError("资金流历史开始累积，需多次运行").
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.factor import Factor, FactorValue
from ..models.research_asset import ResearchAsset, ResearchAssetPrice
from . import factor_sources as src
from .factor_registry import PRESET_FACTORS_V2, ensure_factors
from .factor_sources import NoDataError

_CONCURRENCY = 3
_MONEYFLOW_SIDECAR = Path(__file__).resolve().parent.parent / "factor_moneyflow_history.json"
_BOND_CHINA_START_YEAR = 2006


@dataclass
class SyncReport:
    """Per-factor sync outcome plus timing.

    ``per_factor`` maps factor key -> {"rows": int, "first_date": str|None,
    "error": str|None}.
    """
    per_factor: dict = field(default_factory=dict)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    global_error: Optional[str] = None
    pca: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# pure transforms (numpy only, unit-testable, no network / no DB)
# --------------------------------------------------------------------------- #

def transform_passthrough(series):
    """pct / index_pct: 数据源已返回日收益，直通。"""
    return [(d, float(v)) for d, v in series]


def transform_proxy_diff(long_series, short_series):
    """proxy_diff: 多头指数日收益 − 空头指数日收益（共同日期对齐）。"""
    lm = {d: v for d, v in long_series}
    sm = {d: v for d, v in short_series}
    common = sorted(set(lm) & set(sm))
    return [(d, lm[d] - sm[d]) for d in common]


def transform_level_diff(level_series):
    """level_diff: 水平序列（收益率%）日差分，÷100 存小数（5bp = 0.0005）。"""
    s = sorted(level_series, key=lambda x: x[0])
    return [(s[i][0], (s[i][1] - s[i - 1][1]) / 100.0) for i in range(1, len(s))]


def transform_level_spread_diff(col_a_series, col_b_series):
    """level_spread_diff: col_a − col_b 水平值（共同日期），再做日差分 ÷100。"""
    am = {d: v for d, v in col_a_series}
    bm = {d: v for d, v in col_b_series}
    common = sorted(set(am) & set(bm))
    spread = [(d, am[d] - bm[d]) for d in common]
    return transform_level_diff(spread)


def transform_credit_spread_diff(curve_a_series, curve_b_series):
    """credit_spread_diff: 中债 AAA中票 − 国债（同期限）水平差，日差分 ÷100。"""
    return transform_level_spread_diff(curve_a_series, curve_b_series)


def transform_level_pct(level_series):
    """level_pct: 水平序列日收益率（如 fx_usd 美元/人民币中间价）。"""
    s = sorted(level_series, key=lambda x: x[0])
    out = []
    for i in range(1, len(s)):
        prev = s[i - 1][1]
        if prev:
            out.append((s[i][0], s[i][1] / prev - 1.0))
    return out


def transform_monthly_ffill(monthly_series):
    """monthly_ffill: 月度值月对月差分 ÷100，只发月度观测点。

    说明：注册表 docstring 写 "ffill 到日频"，但任务规格明确 "emit only
    month-end rows (documented choice; regression tolerates sparse monthly
    series)" —— 因此不发日频平铺，按月观测日期（如 1996-02-01）一发。
    """
    s = sorted(monthly_series, key=lambda x: x[0])
    return [(s[i][0], (s[i][1] - s[i - 1][1]) / 100.0) for i in range(1, len(s))]


def transform_monthly_ffill_diff(monthly_series):
    """monthly_ffill_diff: 月度水平差分 ÷100（同 monthly_ffill 口径）。"""
    return transform_monthly_ffill(monthly_series)


def transform_flow_zscore(flow_series, window: int = 20):
    """flow_zscore: 日度流量/余额 -> 20日滚动均值 -> 日变化 -> 全历史 zscore
    （mean/std ddof=0，方差下限 1e-12）-> ÷10 缩放。

    历史 < 40 点抛 NoDataError("数据不足")。
    """
    s = sorted(flow_series, key=lambda x: x[0])
    dates = [d for d, _ in s]
    vals = np.asarray([v for _, v in s], dtype=float)
    n = len(vals)
    if n < 40:
        raise NoDataError("数据不足")
    cs = np.concatenate([[0.0], np.cumsum(vals)])
    ma = (cs[window:] - cs[:-window]) / window          # rolling mean ending at i+window-1
    chg = ma[1:] - ma[:-1]                              # change of the rolling mean
    std = chg.std(ddof=0)
    z = (chg - chg.mean()) / (std if std >= 1e-12 else 1.0)
    if std < 1e-12:
        z = np.zeros_like(z)
    z = z / 10.0
    out_dates = dates[window:]
    return [(out_dates[i], float(z[i])) for i in range(len(z))]


# --------------------------------------------------------------------------- #
# fetch + transform dispatch
# --------------------------------------------------------------------------- #

def _series_from_df(df, column: str) -> list[tuple[str, float]]:
    import pandas as pd
    out = []
    for _, row in df.iterrows():
        v = row[column]
        if pd.isna(v):
            continue
        out.append((str(row["日期"]), float(v)))
    return sorted(out, key=lambda x: x[0])


def _spread_levels(a, b) -> list[tuple[str, float]]:
    am = {d: v for d, v in a}
    bm = {d: v for d, v in b}
    common = sorted(set(am) & set(bm))
    return [(d, am[d] - bm[d]) for d in common]


def _moneyflow_history(raw) -> list[tuple[str, float]]:
    """Read sidecar, append today's aggregate, write back, return history.

    First runs (history < 40 points) raise NoDataError("资金流历史开始累积，
    需多次运行") — documented; flow_zscore needs a meaningful window.
    """
    hist: list = []
    if _MONEYFLOW_SIDECAR.exists():
        try:
            data = json.loads(_MONEYFLOW_SIDECAR.read_text(encoding="utf-8"))
            hist = data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            hist = []
    existing = {str(d): float(v) for d, v in hist}
    if raw.get("today"):
        for d, v in raw["today"]:
            existing[str(d)] = float(v)
        _MONEYFLOW_SIDECAR.write_text(
            json.dumps(sorted(existing.items()), ensure_ascii=False), encoding="utf-8"
        )
    hist = sorted(existing.items())
    if len(hist) < 40:
        raise NoDataError("资金流历史开始累积，需多次运行")
    return hist


def _fetch_raw(defn) -> dict:
    """Synchronous akshare fetch for one FactorDef (runs inside to_thread)."""
    src_name = defn.source
    cfg = defn.source_config or {}
    if src_name == "index_zh_a_hist":
        if defn.transform == "proxy_diff":
            return {"type": "pair",
                    "a": src.fetch_index_pct(cfg["long"]),
                    "b": src.fetch_index_pct(cfg["short"])}
        return {"type": "series", "series": src.fetch_index_pct(cfg["symbol"])}
    if src_name == "index_hist_sw":
        return {"type": "series", "series": src.fetch_index_pct_sw(cfg["symbol"])}
    if src_name == "index_us_stock_sina":
        return {"type": "series", "series": src.fetch_index_pct_us(cfg["symbol"])}
    if src_name == "index_global_hist_em":
        return {"type": "series", "series": src.fetch_index_pct_global(cfg["symbol"])}
    if src_name == "bond_zh_us_rate":
        return {"type": "df", "df": src.fetch_cn_us_yields()}
    if src_name == "bond_china_yield":
        return {
            "type": "pair",
            "a": src.fetch_china_yield(cfg["curve_a"], cfg["tenor"], _BOND_CHINA_START_YEAR),
            "b": src.fetch_china_yield(cfg["curve_b"], cfg["tenor"], _BOND_CHINA_START_YEAR),
        }
    if src_name == "macro_china_rmb":
        return {"type": "series",
                "series": src.fetch_rmb_mid(cfg.get("item", "美元/人民币_中间价"))}
    if src_name in ("macro_china_cpi_monthly", "macro_china_pmi_yearly"):
        return {"type": "series", "series": src.fetch_macro_monthly(src_name, cfg["item"])}
    if src_name == "stock_hsgt_fund_flow_summary_em":
        return {"type": "series", "series": src.fetch_northbound()}
    if src_name == "stock_margin_szse":
        return {"type": "series", "series": src.fetch_margin_szse(cfg.get("years", 2))}
    if src_name == "stock_individual_fund_flow_rank":
        return {"type": "moneyflow", "today": src.fetch_moneyflow_sum()}
    raise ValueError(f"未知数据源 {src_name}")


def _transform_for_factor(defn, raw):
    """Apply the registry transform. Returns (return_rows, level_rows|None)."""
    t = defn.transform
    cfg = defn.source_config or {}
    if t in ("pct", "index_pct"):
        return transform_passthrough(raw["series"]), None
    if t == "proxy_diff":
        return transform_proxy_diff(raw["a"], raw["b"]), None
    if t == "level_diff":
        s = _series_from_df(raw["df"], cfg["column"])
        return transform_level_diff(s), s
    if t == "level_spread_diff":
        a = _series_from_df(raw["df"], cfg["col_a"])
        b = _series_from_df(raw["df"], cfg["col_b"])
        return transform_level_spread_diff(a, b), _spread_levels(a, b)
    if t == "credit_spread_diff":
        return transform_credit_spread_diff(raw["a"], raw["b"]), _spread_levels(raw["a"], raw["b"])
    if t == "level_pct":
        s = raw["series"]
        return transform_level_pct(s), s
    if t == "monthly_ffill":
        s = raw["series"]
        return transform_monthly_ffill(s), s
    if t == "monthly_ffill_diff":
        s = raw["series"]
        return transform_monthly_ffill_diff(s), s
    if t == "flow_zscore":
        window = int(cfg.get("ma", 20))
        if raw.get("type") == "moneyflow":
            # moneyflow: daily snapshot -> JSON sidecar accumulates history
            history = _moneyflow_history(raw)
        else:
            # northbound / margin: the fetched daily flow series is the history
            history = raw.get("series") or []
        return transform_flow_zscore(history, window=window), history
    if t == "derived":
        return None, None
    raise ValueError(f"未知 transform {t}")


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #

_FETCH_TIMEOUT_S = 180


async def _run_with_retry(fn: Callable, sem: asyncio.Semaphore):
    """Run sync fn in a thread behind the semaphore; retry 0.5s / 2s / 8s.

    ``NoDataError`` is deterministic (snapshot-only source, symbol not found,
    insufficient history) and is NOT retried.  Each attempt is bounded by
    ``_FETCH_TIMEOUT_S`` — akshare carries no request timeout, so one hung
    socket would otherwise stall the whole batch (the abandoned to_thread
    worker is left to die on its own).
    """
    delays = (0.0, 0.5, 2.0, 8.0)
    last_exc: Optional[Exception] = None
    for delay in delays:
        if delay:
            await asyncio.sleep(delay)
        async with sem:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(fn), timeout=_FETCH_TIMEOUT_S
                )
            except NoDataError:
                raise
            except Exception as e:  # noqa: BLE001 — retryable (transient network)
                last_exc = e
    raise last_exc  # type: ignore[misc]


async def _incremental_upsert(db, factor, return_rows, level_rows=None) -> int:
    """Insert only rows newer than the stored max date (per kind); UNIQUE
    conflict skip keeps the operation idempotent. Returns return-kind count.

    Chunked at 500 rows: SQLite caps bound parameters per statement
    ("too many SQL variables") and first-time full pulls exceed it.
    """
    max_return = (
        await db.execute(
            select(func.max(FactorValue.date)).where(
                FactorValue.factor_id == factor.id, FactorValue.kind == "return"
            )
        )
    ).scalar()
    max_level = (
        await db.execute(
            select(func.max(FactorValue.date)).where(
                FactorValue.factor_id == factor.id, FactorValue.kind == "level"
            )
        )
    ).scalar()
    to_insert = []
    for d, v in return_rows:
        if max_return is None or d > max_return:
            to_insert.append({"factor_id": factor.id, "date": d,
                              "value": float(v), "kind": "return"})
    if level_rows:
        for d, v in level_rows:
            if max_level is None or d > max_level:
                to_insert.append({"factor_id": factor.id, "date": d,
                                  "value": float(v), "kind": "level"})
    for i in range(0, len(to_insert), 500):
        await db.execute(
            sqlite_insert(FactorValue)
            .values(to_insert[i:i + 500])
            .on_conflict_do_nothing(index_elements=["factor_id", "date", "kind"])
        )
    return len([r for r in to_insert if r["kind"] == "return"])


async def _sync_factor(db, factor, defn, sem) -> dict:
    try:
        raw = await _run_with_retry(lambda: _fetch_raw(defn), sem)
        return_rows, level_rows = _transform_for_factor(defn, raw)
        if not return_rows:
            return {"rows": 0, "first_date": None, "error": "empty after transform"}
        rows = await _incremental_upsert(db, factor, return_rows, level_rows)
        return {"rows": rows, "first_date": return_rows[0][0], "error": None}
    except Exception as e:  # noqa: BLE001 — one bad factor must not kill the batch
        return {"rows": 0, "first_date": None, "error": f"{type(e).__name__}: {e}"}


async def sync_all_factors(db_factory, user_id) -> SyncReport:
    """Full sync: ensure registry rows, then fetch+transform+upsert every
    eligible factor (data_status='ok' AND source in registry), then PCA."""
    report = SyncReport(per_factor={}, started_at=datetime.now())
    async with db_factory() as db:
        try:
            await ensure_factors(db)
            await db.commit()
            defs = {d.key: d for d in PRESET_FACTORS_V2}
            factors = (await db.execute(select(Factor))).scalars().all()
            sem = asyncio.Semaphore(_CONCURRENCY)
            # skip stubs (data_status='stub', empty source) AND legacy
            # ifind/eastmoney factors whose key is not in the V2 registry
            eligible = [
                f for f in factors
                if f.data_status == "ok"
                and (f.data_source or "") != ""
                and f.key in defs
                and bool(defs[f.key].source)
            ]

            async def _run_one(f):
                return f.key, await _sync_factor(db, f, defs[f.key], sem)

            results = await asyncio.gather(*(_run_one(f) for f in eligible))
            for key, info in results:
                report.per_factor[key] = info
            # PCA is best-effort: a failure must not roll back factor writes
            try:
                report.pca = await compute_statistical_factors(db)
            except Exception as e:  # noqa: BLE001
                report.pca = {"status": "error", "reason": f"{type(e).__name__}: {e}"}
            await db.commit()
        except Exception as e:  # noqa: BLE001
            report.global_error = f"{type(e).__name__}: {e}"
            await db.rollback()
    report.finished_at = datetime.now()
    return report


# --------------------------------------------------------------------------- #
# statistical (PCA) factors
# --------------------------------------------------------------------------- #

async def compute_statistical_factors(db: AsyncSession) -> dict:
    """stat_pca1/2/3: pooled non-mmf fund daily-return matrix on common dates
    (last 750) -> np.cov -> np.linalg.eigh -> top-3 eigenvector daily series.

    Skips (returns a report dict) when < 3 pooled assets have usable data.
    """
    assets = (
        await db.execute(
            select(ResearchAsset).where(
                ResearchAsset.status == "pooled",
                ResearchAsset.is_money_market.is_(False),
            )
        )
    ).scalars().all()
    if len(assets) < 3:
        return {"status": "skipped", "reason": f"非货基入池标的 < 3（{len(assets)}）"}
    prices = (
        await db.execute(
            select(ResearchAssetPrice).where(
                ResearchAssetPrice.asset_id.in_([a.id for a in assets])
            )
        )
    ).scalars().all()
    by_asset: dict = {}
    for p in prices:
        by_asset.setdefault(p.asset_id, {})[p.date] = p.close
    common: Optional[set] = None
    for _, m in by_asset.items():
        ds = set(m.keys())
        common = ds if common is None else (common & ds)
    if not common:
        return {"status": "skipped", "reason": "无共同交易日"}
    common_days = sorted(common)[-750:]
    if len(common_days) < 30:
        return {"status": "skipped", "reason": f"共同交易日仅 {len(common_days)} 天"}
    series = []
    for a in assets:
        m = by_asset.get(a.id)
        if not m:
            continue
        closes = [m[d] for d in common_days]
        rets = []
        ok = True
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            if prev and prev > 0:
                rets.append(closes[i] / prev - 1.0)
            else:
                ok = False
                break
        if ok and len(rets) >= 30:
            series.append(rets)
    if len(series) < 3:
        return {"status": "skipped", "reason": f"有数据的入池标的 < 3（{len(series)}）"}
    X = np.array(series).T  # T x N
    cov = np.cov(X, rowvar=False)
    try:
        eigvals, eigvecs = np.linalg.eigh(cov)
    except np.linalg.LinAlgError as e:
        return {"status": "error", "reason": f"eigh 失败: {e}"}
    order = np.argsort(eigvals)[::-1][:3]
    pca_rows = (
        await db.execute(
            select(Factor).where(Factor.key.in_(["stat_pca1", "stat_pca2", "stat_pca3"]))
        )
    ).scalars().all()
    by_key = {f.key: f for f in pca_rows}
    ret_days = common_days[1:]
    written: dict = {}
    for i, fidx in enumerate(order):
        key = f"stat_pca{i + 1}"
        f = by_key.get(key)
        if f is None:
            continue
        proj = np.dot(X, eigvecs[:, fidx])
        rows = [
            {"factor_id": f.id, "date": ret_days[j], "value": float(proj[j]), "kind": "return"}
            for j in range(len(ret_days))
        ]
        await db.execute(
            sqlite_insert(FactorValue)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["factor_id", "date", "kind"],
                set_={"value": sqlite_insert(FactorValue).excluded.value},
            )
        )
        written[key] = len(rows)
    return {"status": "ok", "assets": len(series), "dates": len(ret_days), "written": written}
