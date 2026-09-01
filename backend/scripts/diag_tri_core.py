# -*- coding: utf-8 -*-
"""tri_core 诊断: 分年收益 vs 沪深300 + 回撤月归因 + 核状态时间线."""
import sys, json
sys.path.insert(0, r"E:\TT_FinKit\backend")
import os
os.chdir(r"E:\TT_FinKit\backend")
import warnings; warnings.filterwarnings("ignore")

from app.services.backtest_engine import run_backtest_in_subprocess

PUBLIC_DB = r"E:\TT_FinKit\backend\finkit_public.db"

# tri_core 策略
code = open(r"E:\TT_FinKit\strategies\tri_core_momentum.py", encoding="utf-8-sig").read()

# 池子: tri_core 全部标的 + 沪深300联接
UNIVERSE = [
    "000217", "002611", "002963", "004253", "021740",
    "023145", "020406", "021620", "021823", "019828",
    "022888", "021514", "017536",
    "001549", "001593", "002903", "001589", "002977", "004408", "012757",
    "160141", "024070", "023829", "020900", "004433",
    "021959", "021874", "006485",
    "110020",  # 易方达沪深300联接 (若入池)
]
# 沪深300基准系列: 直接从public库读110020/005918/470007之一
import sqlite3
conn = sqlite3.connect(PUBLIC_DB, timeout=15)
hs300 = None
for sym in ("110020", "005918", "470007", "270010", "001549"):
    r = conn.execute(
        "SELECT a.symbol, a.name FROM research_assets a WHERE a.symbol=?", (sym,)).fetchone()
    if r:
        hs300 = (r[0], r[1])
        break
conn.close()
print("HS300 proxy:", hs300, flush=True)


async def main():
    res = await run_backtest_in_subprocess(
        strategy_code=code, params={}, universe=UNIVERSE,
        start_date="2024-01-01", end_date="2026-09-01", rebalance_freq="monthly",
        db_path=PUBLIC_DB, cost_config={}, timeout=180, max_total_s=600)
    assert res.get("status") == "ok", res.get("error")
    navs = res["nav_series"]
    wh = res["weight_history"]

    # 分年收益
    print("\n=== 分年收益 ===", flush=True)
    import collections
    yearly = collections.OrderedDict()
    for p in navs:
        y = p["date"][:4]
        if y not in yearly:
            yearly[y] = [p["nav"], p["nav"]]
        yearly[y][1] = p["nav"]
    prev_nav = None
    for y, (first, last) in yearly.items():
        base = prev_nav if prev_nav else first
        print(f"  {y}: {(last/base-1)*100:+.1f}%")
        prev_nav = last

    # 沪深300代理分年
    if hs300:
        import pandas as pd
        conn = sqlite3.connect(PUBLIC_DB, timeout=15)
        aid = conn.execute("SELECT id FROM research_assets WHERE symbol=?", (hs300[0],)).fetchone()[0]
        rows = conn.execute(
            "SELECT date, close FROM research_prices WHERE asset_id=? AND date>='2023-12-01' ORDER BY date",
            (aid,)).fetchall()
        conn.close()
        s = pd.Series({d: c for d, c in rows})
        s.index = pd.to_datetime(s.index)
        ys = s.resample("YE").last()
        print("\n=== 沪深300代理分年 ===")
        prev = None
        for idx, v in ys.items():
            if prev is not None and idx.year >= 2024:
                print(f"  {idx.year}: {(v/prev-1)*100:+.1f}%")
            prev = v

    # 回撤月: nav 相对峰值的月份 + 当时权重
    print("\n=== 回撤>5%的月份与当月权重 ===", flush=True)
    peak = -1
    in_dd = False
    dd_start = None
    for p in navs:
        peak = max(peak, p["nav"])
        dd = p["nav"] / peak - 1
        if dd < -0.05 and not in_dd:
            in_dd = True
            print(f"  回撤开始 {p['date']} dd={dd*100:.1f}%")
        if dd < -0.05:
            w = next((x["weights"] for x in wh if x["date"] <= p["date"]), {})
            top = sorted(w.items(), key=lambda x: -x[1])[:4]
            print(f"    {p['date']} dd={dd*100:.1f}% weights:", {k: f"{v*100:.0f}%" for k, v in top})
        elif in_dd and dd >= -0.02:
            in_dd = False
            print(f"  回撤修复 {p['date']}")

    # 核状态时间线（月度权重里金/油/红利是否在）
    print("\n=== 核开关时间线（每月） ===", flush=True)
    for x in wh:
        w = x["weights"]
        g = sum(v for k, v in w.items() if k in ("000217","002611","002963","004253","021740"))
        o = sum(v for k, v in w.items() if k in ("023145","020406","021620","021823","019828"))
        d = sum(v for k, v in w.items() if k in ("022888","021514","017536"))
        bond = w.get("006485", 0)
        print(f"  {x['date']} 金={g*100:4.0f}% 油={o*100:4.0f}% 红={d*100:4.0f}% 债={bond*100:4.0f}%", flush=True)


import asyncio
asyncio.run(main())
