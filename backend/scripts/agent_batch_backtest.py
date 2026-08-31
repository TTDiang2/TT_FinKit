"""Agent batch backtest tool — concurrent engine runs + benchmark comparison.

Runs many (strategy, params, universe) combos through the REAL backtest engine
in parallel subprocesses, then prints one compact table row per run with:

  * engine metrics (ann/vol/sharpe/mdd/cost/turnover)
  * benchmark comparison: excess ann return & excess sharpe vs ANY pooled
    benchmark symbol (e.g. 006574 / 005216), computed from the same DB prices
    with the same metric definitions as the engine
  * PASS/FAIL against declarative targets (ret>=x, sharpe>=y, vol<=z, mdd>=-w,
    excess>=e)

Usage
-----
  # single run
  python scripts/agent_batch_backtest.py \
      --strategy-file ../strategies/xxx.py --universe-preset industry \
      --params '{"top_k":3}' --label "base"

  # batch: a JSON file with a list of runs
  python scripts/agent_batch_backtest.py --config grid.json --out results.json

Config format (list of run dicts; every key optional except strategy_file):
  [
    {"label": "k3", "strategy_file": "../strategies/industry_rotation.py",
     "universe_preset": "industry", "params": {"top_k": 3}, "freq": "monthly",
     "start": "2021-09-01", "end": "2026-08-28",
     "bench": "006574",
     "targets": {"ret": 0.15, "sharpe": 1.5}}
  ]

Universe presets: "industry" (行业代表), "pooled" (全部入池), "macro" (大类资产代表),
or "sym1,sym2,..." literal list.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.backtest_engine import run_backtest_in_subprocess  # noqa: E402

DB = str(BACKEND / "finkit.db")
START, END = "2021-09-01", "2026-08-28"

GROUP_PRESETS: dict[str, str] = {
    "industry": "grp_industry",
    "macro": "grp_macro_asset",
}


def load_preset(symbols_or_preset: str) -> list[str]:
    if symbols_or_preset in GROUP_PRESETS:
        gid = GROUP_PRESETS[symbols_or_preset]
        conn = sqlite3.connect(DB)
        rows = conn.execute(
            "SELECT DISTINCT ra.symbol FROM research_group_members m "
            "JOIN research_assets ra ON ra.id=m.asset_id WHERE m.group_id=? "
            "ORDER BY ra.symbol", (gid,)).fetchall()
        conn.close()
        return [r[0] for r in rows]
    if symbols_or_preset == "pooled":
        conn = sqlite3.connect(DB)
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM research_assets WHERE status='pooled' "
            "ORDER BY symbol").fetchall()
        conn.close()
        return [r[0] for r in rows]
    return [s.strip() for s in symbols_or_preset.split(",") if s.strip()]


def bench_stats(symbol: str, start: str, end: str) -> dict | None:
    """Same metric definitions as the engine (rf=2%, ann by 252/count)."""
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT rp.date, rp.close FROM research_prices rp "
        "JOIN research_assets ra ON ra.id=rp.asset_id "
        "WHERE ra.symbol=? AND rp.date>=? AND rp.date<=? ORDER BY rp.date",
        (symbol, start, end)).fetchall()
    conn.close()
    if len(rows) < 60:
        return None
    navs = [r[1] for r in rows]
    rets = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs))]
    n = len(rets)
    ann = (navs[-1] / navs[0]) ** (252 / n) - 1
    mu = sum(rets) / n
    vol = math.sqrt(sum((r - mu) ** 2 for r in rets) / (n - 1)) * math.sqrt(252)
    peak, mdd = navs[0], 0.0
    for v in navs:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return {"symbol": symbol, "ann": ann, "vol": vol,
            "sharpe": (ann - 0.02) / vol if vol > 0 else 0.0, "mdd": mdd}


def check_targets(m: dict, targets: dict, bench: dict | None) -> str:
    flags = []
    if "ret" in targets:
        flags.append(("ret", m["ann_return"] >= targets["ret"]))
    if "sharpe" in targets:
        flags.append(("shp", m["sharpe"] >= targets["sharpe"]))
    if "vol" in targets:
        flags.append(("vol", m["ann_volatility"] <= targets["vol"]))
    if "mdd" in targets:
        flags.append(("mdd", m["max_drawdown"] >= -targets["mdd"]))
    if "excess" in targets and bench:
        flags.append(("exc", m["ann_return"] - bench["ann"] >= targets["excess"]))
    return "".join("Y" if ok else "." for _, ok in flags)


async def run_one(cfg: dict, sem: asyncio.Semaphore) -> dict:
    code_path = (Path(cfg["strategy_file"]).resolve())
    code = code_path.read_text(encoding="utf-8")
    uni = load_preset(cfg.get("universe_preset", "pooled"))
    start, end = cfg.get("start", START), cfg.get("end", END)
    bench_sym = cfg.get("bench")
    async with sem:
        try:
            r = await run_backtest_in_subprocess(
                strategy_code=code, params=cfg.get("params", {}), universe=uni,
                start_date=start, end_date=end,
                rebalance_freq=cfg.get("freq", "monthly"), db_path=DB,
                timeout=cfg.get("timeout", 300))
        except Exception as e:  # noqa: BLE001
            r = {"status": "error", "error": str(e)}
    out = {"label": cfg.get("label", code_path.stem), "params": cfg.get("params", {}),
           "freq": cfg.get("freq", "monthly"), "universe_preset": cfg.get("universe_preset", "pooled")}
    if r.get("status") != "ok":
        out["error"] = str(r.get("error"))[:300]
        return out
    m = r["metrics"]
    bench = bench_stats(bench_sym, start, end) if bench_sym else None
    out.update({
        "ann": m["ann_return"], "vol": m["ann_volatility"], "sharpe": m["sharpe"],
        "mdd": m["max_drawdown"], "cost": m["total_cost"],
        "cost_ratio": m.get("total_cost_ratio"), "turnover": m.get("turnover_annual"),
        "calmar": m.get("calmar"), "sortino": m.get("sortino"),
        "win_rate": m.get("win_rate"), "nav_final": (r["nav_series"] or [{}])[-1].get("nav"),
    })
    if bench:
        out["bench"] = bench["symbol"]
        out["bench_ann"] = bench["ann"]
        out["bench_sharpe"] = bench["sharpe"]
        out["excess_ann"] = m["ann_return"] - bench["ann"]
        out["excess_sharpe"] = m["sharpe"] - bench["sharpe"]
    sa = r.get("stagnant_analysis") or {}
    out["stagnant"] = [
        {"s": p["start"], "e": p["end"]} for p in (sa.get("merged_periods") or [])]
    tg = cfg.get("targets") or {}
    out["targets"] = tg
    out["pass_flags"] = check_targets(m, tg, bench) if tg else ""
    flags_str = check_targets(m, tg, bench)
    out["pass_all"] = bool(tg) and len(flags_str) == len(tg) and all(c == "Y" for c in flags_str)
    if cfg.get("keep_full"):
        out["nav_series"] = r.get("nav_series")
        out["weight_history"] = r.get("weight_history")
        out["rebalance_records"] = r.get("rebalance_records")
    return out


def print_table(rows: list[dict]) -> None:
    ok_rows = [r for r in rows if "error" not in r]
    err_rows = [r for r in rows if "error" in r]
    hdr = (f"{'label':<28} {'freq':<7} {'ann%':>7} {'vol%':>6} {'shp':>6} "
           f"{'mdd%':>7} {'cost':>6} {'to':>5} {'excA%':>6} {'excS':>5} {'flags':>6} pass")
    print(hdr)
    print("-" * len(hdr))
    for r in ok_rows:
        exc_a = f"{r['excess_ann']*100:6.2f}" if "excess_ann" in r else " " * 6
        exc_s = f"{r['excess_sharpe']:5.2f}" if "excess_sharpe" in r else " " * 5
        print(f"{r['label'][:27]:<28} {r['freq'][:6]:<7} {r['ann']*100:7.2f} "
              f"{r['vol']*100:6.2f} {r['sharpe']:6.2f} {r['mdd']*100:7.1f} "
              f"{r['cost']:6.0f} {r['turnover']:5.1f} {exc_a} {exc_s} "
              f"{r['pass_flags']:>6} {'YES' if r['pass_all'] else 'no'}")
    for r in err_rows:
        print(f"{r['label'][:27]:<28} ERROR {r['error'][:110]}")
    # best by sharpe among passing
    passing = [r for r in ok_rows if r["pass_all"]]
    if passing:
        best = max(passing, key=lambda r: r["sharpe"])
        print(f"\nBEST PASSING: {best['label']}  ann={best['ann']*100:.2f}% "
              f"vol={best['vol']*100:.2f}% sharpe={best['sharpe']:.3f} mdd={best['mdd']*100:.1f}%")
    elif ok_rows:
        best = max(ok_rows, key=lambda r: r["sharpe"])
        print(f"\n(no row passes all targets; best sharpe overall: {best['label']} "
              f"sharpe={best['sharpe']:.3f})")


async def main_async(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--config", help="JSON file with list of run dicts")
    p.add_argument("--strategy-file")
    p.add_argument("--universe-preset", default="pooled")
    p.add_argument("--params", default="{}")
    p.add_argument("--freq", default="monthly")
    p.add_argument("--start", default=START)
    p.add_argument("--end", default=END)
    p.add_argument("--bench", default=None)
    p.add_argument("--label", default=None)
    p.add_argument("--targets", default=None,
                   help='JSON e.g. {"ret":0.15,"sharpe":1.5}')
    p.add_argument("--out", help="write full results JSON here")
    p.add_argument("--concurrency", type=int, default=6)
    args = p.parse_args(argv)

    if args.config:
        cfgs = json.loads(Path(args.config).read_text(encoding="utf-8"))
    else:
        if not args.strategy_file:
            p.error("need --config or --strategy-file")
        cfgs = [{
            "strategy_file": args.strategy_file,
            "universe_preset": args.universe_preset,
            "params": json.loads(args.params),
            "freq": args.freq, "start": args.start, "end": args.end,
            "bench": args.bench, "label": args.label,
            "targets": json.loads(args.targets) if args.targets else {},
        }]

    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*[run_one(c, sem) for c in cfgs])
    rows = list(results)
    print_table(rows)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, default=str),
                                  encoding="utf-8")
        print(f"\nfull results -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(sys.argv[1:])))
