"""Cross-sectional IC analysis over a research-asset universe.

For each rebalance date (month-end / Friday), computes per-asset trailing
signals and their cross-sectional Spearman IC against forward returns.
Tells you WHICH signal actually ranks assets before you build a rotation.

Signals:
  mom5/10/21/63/126/252   trailing window return
  vol63                   trailing 63d annualized vol (negative-IC = low-vol anomaly)
  dd252                   drawdown from 252d high
  mom21_vol               mom21 / ann vol (risk-adjusted short momentum)

Usage:
  python scripts/agent_ic_analysis.py --preset industry --freq monthly
  python scripts/agent_ic_analysis.py --preset pooled --freq monthly --horizon 63
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

DB = str(BACKEND / "finkit.db")
GROUP_PRESETS = {"industry": "grp_industry", "macro": "grp_macro_asset"}


def load_universe(preset: str) -> list[str]:
    conn = sqlite3.connect(DB)
    if preset in GROUP_PRESETS:
        rows = conn.execute(
            "SELECT DISTINCT ra.symbol FROM research_group_members m "
            "JOIN research_assets ra ON ra.id=m.asset_id WHERE m.group_id=?",
            (GROUP_PRESETS[preset],)).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM research_assets WHERE status='pooled'").fetchall()
    conn.close()
    return sorted(r[0] for r in rows)


def load_prices(symbols: list[str]) -> dict[str, dict[str, float]]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    ph = ",".join("?" for _ in symbols)
    rows = conn.execute(
        "SELECT ra.symbol, rp.date, rp.close FROM research_prices rp "
        f"JOIN research_assets ra ON ra.id=rp.asset_id WHERE ra.symbol IN ({ph}) "
        "ORDER BY ra.symbol, rp.date", symbols).fetchall()
    conn.close()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        out.setdefault(r["symbol"], {})[r["date"]] = float(r["close"])
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 5:
        return float("nan")
    rx = sorted(range(n), key=lambda i: xs[i])
    ry = sorted(range(n), key=lambda i: ys[i])
    rkx = [0.0] * n
    rky = [0.0] * n
    for r_, i in enumerate(rx):
        rkx[i] = float(r_)
    for r_, i in enumerate(ry):
        rky[i] = float(r_)
    mx, my = sum(rkx) / n, sum(rky) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rkx, rky))
    vx = sum((a - mx) ** 2 for a in rkx) ** 0.5
    vy = sum((b - my) ** 2 for b in rky) ** 0.5
    return cov / (vx * vy) if vx > 0 and vy > 0 else float("nan")


def window_ret(series: dict[str, float], dates: list[str], i: int, w: int) -> float | None:
    if i - w < 0:
        return None
    p0, p1 = series[dates[i - w]], series[dates[i]]
    return p1 / p0 - 1.0 if p0 > 0 else None


def window_vol(series: dict[str, float], dates: list[str], i: int, w: int) -> float | None:
    if i - w < 1:
        return None
    rets = [series[dates[j]] / series[dates[j - 1]] - 1.0
            for j in range(i - w + 1, i + 1) if series[dates[j - 1]] > 0]
    if len(rets) < 10:
        return None
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var * 252)


def dd_from_high(series: dict[str, float], dates: list[str], i: int, w: int) -> float | None:
    if i - w < 0:
        return None
    seg = [series[dates[j]] for j in range(i - w, i + 1) if series[dates[j]] > 0]
    if not seg:
        return None
    high = max(seg)
    return seg[-1] / high - 1.0 if high > 0 else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--preset", default="industry")
    p.add_argument("--freq", default="monthly", choices=["monthly", "weekly"])
    p.add_argument("--start", default="2021-09-01")
    p.add_argument("--end", default="2026-08-28")
    p.add_argument("--horizon", type=int, default=21, help="forward return horizon in trading days")
    args = p.parse_args()

    symbols = load_universe(args.preset)
    prices = load_prices(symbols)
    all_days = sorted(set().union(*(set(s) for s in prices.values())))
    if args.freq == "monthly":
        bym: dict[str, list[str]] = {}
        for d in all_days:
            bym.setdefault(d[:7], []).append(d)
        rebal = [v[-1] for v in bym.values()]
    else:
        rebal = [d for d in all_days if __import__("datetime").date.fromisoformat(d).weekday() == 4]
    day_idx = {d: i for i, d in enumerate(all_days)}

    signals = ["mom5", "mom10", "mom21", "mom63", "mom126", "mom252",
               "vol63", "dd252", "mom21_vol"]
    ics: dict[str, list[float]] = {s: [] for s in signals}
    for rd in rebal:
        if rd < args.start or rd > args.end:
            continue
        sig_rows: dict[str, list[float]] = {s: [] for s in signals}
        fwd_rows: list[float] = []
        for sym in symbols:
            ser = prices.get(sym, {})
            full = sorted(ser)
            dates = [d for d in full if d <= rd]
            i = len(dates) - 1
            if i < 130:
                continue
            # forward horizon uses the asset's own future dates (full list)
            i_all = full.index(dates[i])
            if i_all + args.horizon >= len(full):
                continue
            fwd = ser[full[i_all + args.horizon]] / ser[full[i_all]] - 1.0
            vals = {}
            for w in (5, 10, 21, 63, 126, 252):
                vals[f"mom{w}"] = window_ret(ser, dates, i, w)
            v63 = window_vol(ser, dates, i, 63)
            vals["vol63"] = v63
            vals["dd252"] = dd_from_high(ser, dates, i, 252)
            if vals["mom21"] is not None and v63:
                vals["mom21_vol"] = vals["mom21"] / max(v63, 0.05)
            for s in signals:
                if vals.get(s) is not None:
                    sig_rows[s].append(vals[s])
            fwd_rows.append(fwd)
        if len(fwd_rows) < 10:
            continue
        for s in signals:
            if len(sig_rows[s]) >= 10:
                ic = spearman(sig_rows[s], fwd_rows)
                if not math.isnan(ic):
                    ics[s].append(ic)

    print(f"universe={args.preset} ({len(symbols)} assets)  freq={args.freq}  "
          f"horizon={args.horizon}d  n_periods={len(ics['mom21'])}")
    print(f"{'signal':<12} {'IC mean':>9} {'ICIR':>7} {'IC>0':>6} {'t-ish':>7}")
    for s in signals:
        v = ics[s]
        if not v:
            continue
        mu = sum(v) / len(v)
        sd = (sum((x - mu) ** 2 for x in v) / (len(v) - 1)) ** 0.5
        icir = mu / sd * math.sqrt(12) if sd > 0 else 0.0  # annualized like the panel
        win = sum(1 for x in v if x > 0) / len(v)
        t = mu / sd * math.sqrt(len(v)) if sd > 0 else 0.0
        print(f"{s:<12} {mu:9.4f} {icir:7.2f} {win*100:5.0f}% {t:7.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
