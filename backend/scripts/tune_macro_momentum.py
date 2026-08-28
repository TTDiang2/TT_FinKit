"""Grid-tune the vol-target macro rotation strategy on the 大类资产代表 pool.

Runs the real backtest engine (subprocess runner) over a small parameter grid
and prints a metrics table sorted by which rows meet ALL of the user's targets:
  ann_return > 7% · ann_volatility ≈ 5% (≤6%) · sharpe > 1.5 · max_drawdown > -15%

Usage (from backend/):  python scripts/tune_macro_momentum.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CODE = Path(__file__).resolve().parents[1].joinpath("strategies/asset_rotation_vol_target.py").read_text(encoding="utf-8")

UNIVERSE = sorted({s for g in (
    ["001549", "001593", "002903", "001589", "002977", "004408", "012757"],
    ["160141"],
    ["000217", "002611", "002963", "004253"],
    ["019828", "020105", "020406", "021620"],
    ["004433"],
    ["003377", "006452", "006485", "000396"],
) for s in g})

GRID = [
    {"gold_budget": g, "equity_budget": e, "oil_budget": o, "lookback_days": 250, "risk_scale": rs}
    for g, e, o in ((0.50, 0.20, 0.10), (0.45, 0.25, 0.15))
    for rs in (0.45, 0.50, 0.55, 0.60)
]


async def main() -> None:
    from app.services.backtest_engine import run_backtest_in_subprocess

    rows = []
    for i, params in enumerate(GRID, 1):
        res = await run_backtest_in_subprocess(
            strategy_code=CODE, params=params, universe=UNIVERSE,
            start_date="2021-09-01", end_date="2026-08-28",
            rebalance_freq="monthly", db_path="finkit.db",
        )
        if res.get("status") != "ok":
            print(f"[{i}/{len(GRID)}] {params} -> ERROR {res.get('error')}", flush=True)
            continue
        m = res["metrics"]
        row = {
            **params,
            "ret": m.get("ann_return", 0.0),
            "vol": m.get("ann_volatility", 0.0),
            "sharpe": m.get("sharpe", 0.0),
            "mdd": m.get("max_drawdown", 0.0),
            "cost": m.get("total_cost", 0.0),
        }
        rows.append(row)
        print(f"[{i}/{len(GRID)}] g={params['gold_budget']} e={params['equity_budget']} o={params['oil_budget']} "
              f"-> ret={row['ret']*100:5.2f}% vol={row['vol']*100:4.2f}% "
              f"sharpe={row['sharpe']:5.2f} mdd={row['mdd']*100:6.2f}%", flush=True)

    def pass_all(r: dict) -> bool:
        return r["ret"] > 0.07 and r["vol"] <= 0.06 and r["sharpe"] > 1.5 and r["mdd"] > -0.15

    print("\n=== sorted (pass_first) ===")
    rows.sort(key=lambda r: (not pass_all(r), -r["sharpe"]))
    for r in rows:
        flag = "PASS" if pass_all(r) else "    "
        print(f"{flag} g={r['gold_budget']} e={r['equity_budget']} o={r['oil_budget']} "
              f"| ret {r['ret']*100:5.2f}% | vol {r['vol']*100:4.2f}% | sharpe {r['sharpe']:5.2f} | "
              f"mdd {r['mdd']*100:6.2f}% | cost {r['cost']:.0f}")


def vt_label(v: float) -> str:
    return f"{v*100:g}%"


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
