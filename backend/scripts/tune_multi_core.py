# -*- coding: utf-8 -*-
"""对比回测: tri_core / dynamic_core / trinity vs 高夏普v3 基准.

Universe = 三策略 GROUPS 并集 (~35 只, 全部有5年或部分历史).
窗口 2024-01-01 ~ 2026-09-01, 月频.
直接调用 backtest_engine (subprocess 模式, 不写 DB).
"""
import sys
import json
import tempfile
import os

sys.path.insert(0, r"E:\TT_FinKit\backend")
os.chdir(r"E:\TT_FinKit\backend")

from app.services.backtest_engine import run_backtest_in_subprocess

PUBLIC_DB = r"E:\TT_FinKit\backend\finkit_public.db"
START, END = "2024-01-01", "2026-09-01"

import importlib.util
def load_code(path):
    return open(path, encoding="utf-8-sig").read()

CANDIDATES = {
    "tri_core": (r"E:\TT_FinKit\strategies\tri_core_momentum.py", {}),
    "dynamic_core": (r"E:\TT_FinKit\strategies\dynamic_core_macro.py", {}),
    "trinity": (r"E:\TT_FinKit\strategies\trinity_sandwich.py", {}),
}

ALL_SYMS = [
    "000217", "002611", "002963", "004253", "021740",
    "023145", "020406", "021620", "021823", "019828",
    "022888", "021514", "017536",
    "001549", "001593", "002903", "001589", "002977", "004408", "012757",
    "160141", "024070", "023829", "020900", "004433",
    "021959", "021874",
    "006485",
]


def flat_syms(path):
    """提取策略文件里的全部 symbol 字面量，与 ALL_SYMS 并集。"""
    import re
    code = load_code(path)
    syms = set(re.findall(r'"(\d{6})"', code))
    return sorted(syms)


async def main():
    results = {}
    # 基准: 高夏普 v3 (从 public db strategies 表取 code)
    import sqlite3
    conn = sqlite3.connect(PUBLIC_DB, timeout=30)
    row = conn.execute(
        "SELECT code FROM strategies WHERE name LIKE '%高夏普%' AND version=3").fetchone()
    conn.close()
    if row:
        results["baseline_high_sharpe_v3"] = (row[0], ALL_SYMS)

    for name, (path, params) in CANDIDATES.items():
        code = load_code(path)
        results[name] = (code, flat_syms(path))

    for name, (code, universe) in results.items():
        print(f"--- {name} (universe {len(universe)}) ---", flush=True)
        try:
            res = await run_backtest_in_subprocess(
                strategy_code=code, params={}, universe=universe,
                start_date=START, end_date=END, rebalance_freq="monthly",
                db_path=PUBLIC_DB, cost_config={}, timeout=180, max_total_s=600,
            )
            if res.get("status") != "ok":
                print("  ERROR:", (res.get("error") or "")[:150], flush=True)
                continue
            m = res["metrics"]
            navs = res["nav_series"]
            sub = [p for p in navs if p["date"] >= "2025-01-01"]
            sub_ret = (sub[-1]["nav"] / sub[0]["nav"] - 1) * 100 if len(sub) > 1 else float("nan")
            print(f"  ann={m.get('ann_return', 0)*100:.2f}%  vol={m.get('ann_volatility', 0)*100:.2f}%"
                  f"  sharpe={m.get('sharpe', 0):.2f}  mdd={m.get('max_drawdown', 0)*100:.1f}%"
                  f"  2025+段收益={sub_ret:.1f}%", flush=True)
        except Exception as e:
            print("  EXC:", type(e).__name__, str(e)[:150], flush=True)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
