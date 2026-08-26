"""Final verification of v3.1 (with VOL_FLOOR) against acceptance gates."""
import asyncio
import sys

sys.path.insert(0, ".")

from app.services.backtest_engine import run_backtest_in_subprocess

CODE = open("../strategies/asset_rotation.py", encoding="utf-8").read()
UNIVERSE = ["000217", "000667", "002910", "006432", "378546"]
SYMS = ",".join(UNIVERSE)
BASE = {"symbols": SYMS, "top_k": 3, "buffer": 1}


async def main() -> None:
    for label, extra in [
        ("FINAL default (floor=-2%)", {"momentum_floor": -0.02}),
        ("FINAL floor=-5%", {"momentum_floor": -0.05}),
    ]:
        r = await run_backtest_in_subprocess(
            strategy_code=CODE, params={**BASE, **extra}, universe=UNIVERSE,
            start_date="2021-09-01", end_date="2026-08-25",
            rebalance_freq="monthly", db_path="finkit.db", timeout=120,
        )
        m = r["metrics"]
        sa = r.get("stagnant_analysis") or {}
        merged = sa.get("merged_periods") or []
        cfa = r.get("custom_factor_analysis") or {}
        top = sorted(cfa.items(), key=lambda kv: -abs(kv[1]["ic_mean"]))[:3]
        fails = []
        if m["ann_return"] <= 0.07: fails.append("ret<=7%")
        if m["sharpe"] <= 1.0: fails.append("sharpe<=1")
        if m["max_drawdown"] < -0.30: fails.append("mdd>30%")
        print(f"{label}: ann={m['ann_return']*100:.2f}% sharpe={m['sharpe']:.3f} "
              f"mdd={m['max_drawdown']*100:.2f}% cost={m['total_cost']:.0f} "
              f"GATES={'PASS' if not fails else 'FAIL:' + ','.join(fails)}")
        spans = ["{}~{}".format(p["start"], p["end"]) for p in merged]
        print("  stagnant({}): {}".format(len(merged), spans))
        print(f"  customIC: {'  '.join(k+':'+format(v['ic_mean'],'+.3f')+'/w'+format(v['win_rate'],'.0%') for k,v in top)}")


asyncio.run(main())