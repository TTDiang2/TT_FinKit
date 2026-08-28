"""Baseline: run the existing v2 strategy (pure momentum) on clean data."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.backtest_engine import run_backtest_in_subprocess

v2 = Path(__file__).resolve().parent.joinpath("_v2_baseline.py").read_text(encoding="utf-8")
UNI = sorted(["001549", "001593", "002903", "001589", "002977", "004408", "012757",
              "160141", "000217", "002611", "002963", "004253",
              "019828", "020105", "020406", "021620", "004433",
              "003377", "006452", "006485", "000396"])


async def run(code: str, params: dict, freq: str, label: str) -> None:
    r = await run_backtest_in_subprocess(
        strategy_code=code, params=params, universe=UNI,
        start_date="2021-09-01", end_date="2026-08-28",
        rebalance_freq=freq, db_path="finkit.db")
    if r.get("status") != "ok":
        print(label, "ERROR", str(r.get("error"))[:200])
        return
    m = r["metrics"]
    ar = m["ann_return"] * 100
    av = m["ann_volatility"] * 100
    sh = m["sharpe"]
    md = m["max_drawdown"] * 100
    cost = m["total_cost"]
    print(f"{label:<26} ret={ar:6.2f}% vol={av:5.2f}% sharpe={sh:5.2f} mdd={md:7.2f}% cost={cost:.0f}", flush=True)


async def main() -> None:
    for lb, k in ((180, 1), (180, 2), (180, 3), (126, 3), (250, 3), (63, 3)):
        await run(v2, {"symbols": ",".join(UNI), "lookback_days": lb, "top_k": k, "buffer": 1},
                  "monthly", f"v2 monthly lb={lb} k={k}")
    await run(v2, {"symbols": ",".join(UNI), "lookback_days": 180, "top_k": 2, "buffer": 1},
              "weekly", "v2 weekly  lb=180 k=2")


if __name__ == "__main__":
    asyncio.run(main())
