# -*- coding: utf-8 -*-
"""tri_core v2 网格优化: 组合级回撤熔断 + 参数网格 + 邻域稳健性.

v1 病根(诊断确认): 2024-2026 牛市中各核动量恒正 → 独立开关零触发 →
恒满仓金/油/红利/海外 → 2026-03 四资产同步回撤 -12.9% 无防护。
v2: 合成三核等权指数, 其 60d 峰值回撤超阈值 → 整体缩仓退债(组合级熔断).
"""
import asyncio
import sys
import os
import itertools
import json

sys.path.insert(0, r"E:\TT_FinKit\backend")
os.chdir(r"E:\TT_FinKit\backend")
import warnings; warnings.filterwarnings("ignore")

from app.services.backtest_engine import run_backtest_in_subprocess

PUBLIC_DB = r"E:\TT_FinKit\backend\finkit_public.db"
START, END = "2024-01-01", "2026-09-01"

STRATEGY_TEMPLATE = '''
"""tri_core v2: 三核独立开关 + 组合级回撤熔断."""
from finkit_strategy import Strategy, StrategyContext

CORE_GROUPS = {
    "黄金核": ["000217", "002611", "002963", "004253", "021740"],
    "油气核": ["023145", "020406", "021620", "021823", "019828"],
    "红利核": ["022888", "021514", "017536"],
}
RISK_GROUPS = {
    "权益": ["001549", "001593", "002903", "001589", "002977", "004408", "012757"],
    "海外": ["160141"],
    "科技": ["024070", "023829", "020900"],
    "有色": ["004433"],
}
BOND_BUFFER = "006485"

class TriCoreV2Strategy(Strategy):
    name = "三核宏观动量v2"
    rebalance_freq = "monthly"
    params_schema = {
        "lookback_days": {"type": "int", "default": 250},
        "core_budget": {"type": "float", "default": 0.75},
        "risk_budget": {"type": "float", "default": 0.25},
        "dd_soft": {"type": "float", "default": 0.06},
        "dd_hard": {"type": "float", "default": 0.15},
    }

    def _window(self, series, date, n):
        dates = sorted(d for d in series.keys() if d <= date)
        vals = []
        for d in dates[-(n + 1):]:
            px = series.get(d)
            if px and px > 0:
                vals.append(float(px))
        return vals

    def _ret(self, series, date, days):
        vals = self._window(series, date, days)
        if len(vals) < 2 or vals[0] <= 0:
            return None
        return vals[-1] / vals[0] - 1.0

    def _core_dd(self, ctx, date, lookback):
        core_syms = []
        for grp in CORE_GROUPS.values():
            bs, bm = None, -9e9
            for sym in grp:
                if sym in ctx.prices and len(ctx.prices[sym]) > 60:
                    m = self._ret(ctx.prices[sym], date, lookback)
                    if m is not None and m > bm:
                        bs, bm = sym, m
            if bs:
                core_syms.append(bs)
        if not core_syms:
            return 0.0
        dates = sorted(ctx.prices[core_syms[0]].keys())
        dates = [d for d in dates if d <= date][-65:]
        if len(dates) < 30:
            return 0.0
        nav = []
        for d in dates:
            vals = [ctx.prices[s].get(d) for s in core_syms if s in ctx.prices]
            vals = [float(v) for v in vals if v]
            nav.append(sum(vals) / len(vals) if vals else None)
        nav = [v for v in nav if v]
        if len(nav) < 30:
            return 0.0
        peak = nav[0]
        dd = 0.0
        for v in nav:
            peak = max(peak, v)
            dd = min(dd, v / peak - 1.0)
        return dd

    def target_weights(self, ctx, date):
        pool = {a["symbol"] for a in ctx.pool}
        lookback = self.params["lookback_days"]

        def best(group):
            bs, bm = None, -9e9
            for sym in group:
                if sym not in pool:
                    continue
                m = self._ret(ctx.prices.get(sym, {}), date, lookback)
                if m is not None and m > bm:
                    bs, bm = sym, m
            return bs, bm

        weights = {}
        cores = {}
        for cname, grp in CORE_GROUPS.items():
            s, m = best(grp)
            if s is not None and m > 0.0:
                cores[s] = m
        n_on = len(cores)
        if n_on:
            per = self.params["core_budget"] * 3 / n_on
            for s in cores:
                weights[s] = weights.get(s, 0.0) + per

        risk_best = None
        for cname, grp in RISK_GROUPS.items():
            s, m = best(grp)
            if s is not None and m > 0.0:
                if risk_best is None or m > risk_best[1]:
                    risk_best = (s, m)
        if risk_best:
            weights[risk_best[0]] = weights.get(risk_best[0], 0.0) + self.params["risk_budget"]

        # 组合级熔断: 三核等权指数回撤超阈值 → 整体缩仓
        dd = self._core_dd(ctx, date, lookback)
        scale = 1.0
        if dd < -self.params["dd_hard"]:
            scale = 0.25
        elif dd < -self.params["dd_soft"]:
            scale = 0.5
        weights = {s: w * scale for s, w in weights.items()}
        weights[BOND_BUFFER] = weights.get(BOND_BUFFER, 0.0) + (1.0 - sum(weights.values()))
        return {s: w for s, w in weights.items() if w > 1e-6}
'''


async def run_one(params: dict, universe):
    res = await run_backtest_in_subprocess(
        strategy_code=STRATEGY_TEMPLATE, params=params, universe=universe,
        start_date=START, end_date=END, rebalance_freq="monthly",
        db_path=PUBLIC_DB, cost_config={}, timeout=180, max_total_s=600)
    if res.get("status") != "ok":
        print("   err:", (res.get("error") or "")[:120], flush=True)
        return None
    m = res["metrics"]
    navs = res["nav_series"]
    sub = [p for p in navs if p["date"] >= "2025-01-01"]
    sub_ret = (sub[-1]["nav"] / sub[0]["nav"] - 1) * 100 if len(sub) > 1 else float("nan")
    return dict(ann=m.get("ann_return", 0) * 100, vol=m.get("ann_volatility", 0) * 100,
                sharpe=m.get("sharpe", 0), mdd=m.get("max_drawdown", 0) * 100, sub=sub_ret)


async def main():
    universe = sorted({s for grp in (
        ["000217", "002611", "002963", "004253", "021740"],
        ["023145", "020406", "021620", "021823", "019828"],
        ["022888", "021514", "017536"],
        ["001549", "001593", "002903", "001589", "002977", "004408", "012757"],
        ["160141"], ["024070", "023829", "020900"], ["004433"],
        ["021959", "021874"], ["006485"],
    ) for s in grp})

    grid = list(itertools.product(
        [0.60, 0.75, 0.90],
        [0.15, 0.25, 0.35],
        [0.06],
        [0.15],
    ))
    print(f"grid size: {len(grid)}", flush=True)
    rows = []
    OUT = r"E:\\TT_FinKit\\backend\\tri_core_v2_grid.json"
    try:
        with open(OUT, encoding="utf-8") as f:
            rows = json.load(f)
        print(f"resume: {len(rows)} done", flush=True)
    except Exception:
        pass
    done_keys = {(r["cb"], r["rb"], r["ds"], r["dh"]) for r in rows}
    for i, (cb, rb, ds, dh) in enumerate(grid):
        if (cb, rb, ds, dh) in done_keys:
            continue
        params = {"lookback_days": 250, "core_budget": cb, "risk_budget": rb,
                  "risk_scale": 1.0, "buffer": 0,
                  "dd_soft": ds, "dd_hard": dh}
        r = await run_one(params, universe)
        if r is None:
            print(f"[{i+1}/{len(grid)}] cb={cb} rb={rb} soft={ds} hard={dh} FAILED", flush=True)
            continue
        rows.append(dict(cb=cb, rb=rb, ds=ds, dh=dh, **r))
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        print(f"[{i+1}/{len(grid)}] cb={cb} rb={rb} soft={ds} hard={dh} "
              f"ann={r['ann']:.1f}% sh={r['sharpe']:.2f} mdd={r['mdd']:.1f}% "
              f"25+={r['sub']:.0f}%", flush=True)

    if not rows:
        return
    rows.sort(key=lambda r: -r["sharpe"])
    print("\n=== TOP 10 by sharpe ===", flush=True)
    for r in rows[:10]:
        print(f"  cb={r['cb']} rb={r['rb']} soft={r['ds']} hard={r['dh']} "
              f"ann={r['ann']:.1f}% sh={r['sharpe']:.2f} mdd={r['mdd']:.1f}% 25+={r['sub']:.0f}%",
              flush=True)

    best = rows[0]
    neigh = [r for r in rows
             if abs(r["cb"] - best["cb"]) <= 0.15 and abs(r["rb"] - best["rb"]) <= 0.10]
    if neigh:
        shs = [r["sharpe"] for r in neigh]
        mdds = [r["mdd"] for r in neigh]
        print(f"\nrobustness around best ({len(neigh)} pts): "
              f"sharpe min={min(shs):.2f} max={max(shs):.2f} | mdd min={min(mdds):.1f}% max={max(mdds):.1f}%",
              flush=True)
    with open(r"E:\TT_FinKit\backend\tri_core_v2_grid.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print("saved tri_core_v2_grid.json", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
