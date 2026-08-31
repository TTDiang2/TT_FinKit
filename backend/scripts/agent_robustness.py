"""Parameter-immunity check (STRATEGY_PLAYBOOK IDEA-10 / PRO-04 tooling).

Runs a strategy at a parameter CENTER plus automatic neighborhood perturbations
(budgets ±0.05, vol_target ±0.01, risk_top_k ±1, min_history ±40 …) and reports
neighborhood stability: mean/std/min sharpe + how many neighbors keep passing.

A parameter set is "immune" when the neighborhood does not collapse — the
delivered strategies were selected this way (平台中心, not grid peaks).

Usage (from backend/):
  python scripts/agent_robustness.py --strategy-file ../strategies/max_sharpe.py \
      --universe-preset pooled --bench 005216 \
      --targets '{"ret":0.10,"sharpe":1.5}'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_batch_backtest import (  # noqa: E402
    END, START, bench_stats, load_preset, run_one,
)


def perturbations(center: dict) -> list[tuple[str, dict]]:
    """Generate ±1-step perturbations around the center params."""
    out: list[tuple[str, dict]] = []
    budgets = {
        "gold_budget": ("gold_budget", 0.05),
        "risk_budget": ("risk_budget", 0.05),
        "vol_target": ("vol_target", 0.01),
        "risk_top_k": ("risk_top_k", 1),
        "min_history": ("min_history", 40),
        "gate_window": ("gate_window", 50),
        "gold_floor": ("gold_floor", 0.02),
        "risk_floor": ("risk_floor", 0.02),
    }
    for key, (_k, step) in budgets.items():
        if key not in center:
            continue
        val = center[key]
        if isinstance(val, int) or key in ("risk_top_k", "min_history", "gate_window"):
            lo, hi = int(val) - int(step), int(val) + int(step)
            lo = max(1, lo)
        else:
            lo, hi = round(val - step, 4), round(val + step, 4)
        for tag, v in (("lo", lo), ("hi", hi)):
            p = dict(center)
            p[key] = v
            out.append((f"{key}={v}({tag})", p))
    return out


async def main_async(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy-file", required=True)
    p.add_argument("--universe-preset", default="pooled")
    p.add_argument("--params", default="{}", help="center params JSON")
    p.add_argument("--bench", default=None)
    p.add_argument("--targets", default="{}")
    p.add_argument("--start", default=START)
    p.add_argument("--end", default=END)
    p.add_argument("--concurrency", type=int, default=6)
    args = p.parse_args(argv)

    center = json.loads(args.params)
    targets = json.loads(args.targets)
    runs = [{"label": "CENTER", "strategy_file": args.strategy_file,
             "universe_preset": args.universe_preset, "params": dict(center),
             "targets": targets, "bench": args.bench,
             "start": args.start, "end": args.end}]
    for label, params in perturbations(center):
        runs.append({"label": label, "strategy_file": args.strategy_file,
                     "universe_preset": args.universe_preset, "params": params,
                     "targets": targets, "bench": args.bench,
                     "start": args.start, "end": args.end})

    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*[run_one(r, sem) for r in runs])

    ok = [r for r in results if "sharpe" in r]
    errs = [r for r in results if "sharpe" not in r]
    sh = [r["sharpe"] for r in ok if r["label"] != "CENTER"]
    anns = [r["ann"] for r in ok if r["label"] != "CENTER"]
    mdds = [r["mdd"] for r in ok if r["label"] != "CENTER"]
    passes = [r["pass_all"] for r in ok if r["label"] != "CENTER"]

    print(f"{'label':<28} {'ann%':>7} {'shp':>6} {'mdd%':>7} pass")
    for r in ok:
        print(f"{r['label']:<28} {r['ann']*100:7.2f} {r['sharpe']:6.3f} "
              f"{r['mdd']*100:7.1f} {'YES' if r['pass_all'] else 'no'}")
    for r in errs:
        print(f"{r['label']:<28} ERROR {r.get('error', '')[:80]}")
    if sh:
        c = next((r for r in ok if r["label"] == "CENTER"), None)
        print(f"\nCENTER: sharpe={c['sharpe']:.3f} ann={c['ann']*100:.2f}%"
              if c else "\nCENTER: failed")
        print(f"NEIGHBORHOOD: n={len(sh)} sharpe mean={statistics.mean(sh):.3f} "
              f"std={statistics.stdev(sh) if len(sh) > 1 else 0:.3f} "
              f"min={min(sh):.3f} | ann mean={statistics.mean(anns)*100:.2f}% "
              f"min={min(anns)*100:.2f}% | mdd worst={min(mdds)*100:.1f}%")
        print(f"neighbors still passing: {sum(passes)}/{len(passes)}")
        verdict = "IMMUNE" if (c and min(sh) >= c["sharpe"] - 0.10 and all(passes)) else \
                  "STABLE" if (sh and statistics.mean(sh) >= (c['sharpe'] if c else 0) - 0.15) else "FRAGILE"
        print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(sys.argv[1:])))
