# -*- coding: utf-8 -*-
"""Step 3: run the high-sharpe v3 engine on the CURATED pool.

Experiment matrix (2024-01-01 ~ 2026-09-01, monthly):
  A  v3 original whitelist + curated-pool universe  (~90 clean names)
  B  v3 CURATED whitelist (gold top5 / bond top8) + curated universe
  ref  v3 original + 7714 raw pool = 26.19% / 2.49 / -5.8 (user's run)

Answers: does the clean pool keep the risk-satellite picks healthy, and
does re-selecting the core/defensive whitelist from curated tops help?
"""
import asyncio
import csv
import math
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, r"E:\TT_FinKit\backend")
import os
os.chdir(r"E:\TT_FinKit\backend")

from app.services.backtest_engine import run_backtest_in_subprocess

PUBLIC_DB = r"E:\TT_FinKit\backend\finkit_public.db"
CSV_IN = Path(r"E:\TT_FinKit\docs\curated_pool.csv")
START, END = "2024-01-01", "2026-09-01"


def two_y_sharpe(prices: list[float]) -> float:
    rets = [prices[i] / prices[i - 1] - 1.0 for i in range(1, len(prices)) if prices[i - 1] > 0]
    if len(rets) < 200:
        return -99.0
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1))
    if sd < 1e-9:
        return -99.0
    return (m - 0.02 / 252) / sd * math.sqrt(252)


def build_curated_lists() -> dict[str, list[str]]:
    rows = list(csv.DictReader(open(CSV_IN, encoding="utf-8-sig")))
    conn = sqlite3.connect(PUBLIC_DB, timeout=30)
    horizon = (date.today() - timedelta(days=2 * 365 + 15)).isoformat()
    scored: dict[str, list[tuple[float, str]]] = {}
    for r in rows:
        aid = conn.execute("SELECT id FROM research_assets WHERE symbol=?", (r["symbol"],)).fetchone()
        if not aid:
            continue
        prices = [x[0] for x in conn.execute(
            "SELECT close FROM research_prices WHERE asset_id=? AND date>=? ORDER BY date",
            (aid[0], horizon)).fetchall()]
        if len(prices) < 400:
            continue
        scored.setdefault(r["category"], []).append((two_y_sharpe(prices), r["symbol"]))
    conn.close()
    out = {}
    for cat, lst in scored.items():
        lst.sort(reverse=True)
        out[cat] = [s for _, s in lst]
    return out


def us_only(qdii_syms: list[str]) -> list[str]:
    conn = sqlite3.connect(PUBLIC_DB, timeout=30)
    picks = []
    for s in qdii_syms:
        name = conn.execute("SELECT name FROM research_assets WHERE symbol=?", (s,)).fetchone()
        n = name[0] if name else ""
        if any(k in n for k in ("纳斯达克", "纳指", "标普", "美国", "道琼斯")):
            picks.append(s)
    conn.close()
    return picks


def make_curated_v3(code: str, gold: list[str], defensive: list[str]) -> str:
    code = re.sub(
        r'GOLD_CANDIDATES = \[[^\]]*\]',
        "GOLD_CANDIDATES = " + json_dumps(gold), code)
    code = re.sub(
        r'DEFENSIVE_WHITELIST = \[[^\]]*\]',
        "DEFENSIVE_WHITELIST = " + json_dumps(defensive), code)
    return code


def json_dumps(arr: list[str]) -> str:
    import json
    return json.dumps(arr, ensure_ascii=False)


async def run(tag: str, code: str, universe: list[str]) -> None:
    print(f"--- {tag} (universe {len(universe)}) ---", flush=True)
    try:
        res = await run_backtest_in_subprocess(
            strategy_code=code, params={}, universe=universe,
            start_date=START, end_date=END, rebalance_freq="monthly",
            db_path=PUBLIC_DB, cost_config={}, timeout=180, max_total_s=900,
        )
        if res.get("status") != "ok":
            print("  ERROR:", (res.get("error") or "")[:200], flush=True)
            return
        m = res["metrics"]
        navs = res["nav_series"]
        sub = [p for p in navs if p["date"] >= "2025-01-01"]
        sub_ret = (sub[-1]["nav"] / sub[0]["nav"] - 1) * 100 if len(sub) > 1 else float("nan")
        print(f"  ann={m.get('ann_return', 0)*100:.2f}%  vol={m.get('ann_volatility', 0)*100:.2f}%"
              f"  sharpe={m.get('sharpe', 0):.2f}  mdd={m.get('max_drawdown', 0)*100:.1f}%"
              f"  2025+段={sub_ret:.1f}%", flush=True)
    except Exception as e:
        print("  EXC:", type(e).__name__, str(e)[:200], flush=True)


async def main() -> None:
    lists = build_curated_lists()
    gold5 = lists.get("gold", [])[:5]
    bond8 = lists.get("bond", [])[:8]
    idx10 = lists.get("index", [])[:10]
    ind8 = lists.get("industry", [])[:8]
    eq5 = lists.get("equity", [])[:5]
    qd_us = us_only(lists.get("qdii", []))[:5]
    oil = lists.get("oil", [])[:6]

    curated_universe = sorted(set(gold5 + bond8 + idx10 + ind8 + eq5 + qd_us + oil))
    print("curated universe:", len(curated_universe), flush=True)
    print("  gold5:", gold5, flush=True)
    print("  bond8:", bond8, flush=True)

    conn = sqlite3.connect(PUBLIC_DB, timeout=30)
    v3code = conn.execute(
        "SELECT code FROM strategies WHERE name LIKE '%高夏普%' AND version=3").fetchone()[0]
    conn.close()

    await run("A_v3_orig_whitelist + curated_pool", v3code, curated_universe)

    v3_curated = make_curated_v3(v3code, gold5, bond8)
    if v3_curated == v3code:
        print("WARN: whitelist substitution failed", flush=True)
    await run("B_v3_curated_whitelist + curated_pool", v3_curated, curated_universe)

    print("\nref: v3 original + 7714 raw pool = 26.19% / 2.49 / -5.8 (user's run)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
