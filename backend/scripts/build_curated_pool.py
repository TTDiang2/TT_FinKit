"""Build a curated "clean pool" from the pooled research universe.

Motivation (playbook TEC-20/21): raw large-pool momentum ranking is
poisoned by dirty-data funds whose NAV series jump >15% in a day
(018060/020412/021556/017103) -- they fake-momentum to the top and
destroy any momentum strategy run on the raw pool.

Hard rules (a fund must pass ALL):
  R1 no |daily nav move| > 15% anywhere in the last 2 years
  R2 >= 500 nav rows (~2y) -- enough for a 250d lookback
  R3 last nav within 7 days of the latest global date (alive)
  R4 annualized vol (250d) in [0.5%, 45%] -- kills money-market-like
     flatlines and insane-vol garbage
  R5 |latest nav - 1.0| sanity: not required (funds can be anywhere)

Soft tag: category via name keywords (index/industry/bond/gold/oil/QDII/
money) for the human review file.

Usage (from backend/):
  python scripts/build_curated_pool.py                # build + write md/csv
  python scripts/build_curated_pool.py --print-only   # show summary only
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB = Path(__file__).resolve().parents[1] / "finkit_public.db"
OUT_MD = Path(__file__).resolve().parents[1].parent / "docs" / "curated_pool.md"
OUT_CSV = Path(__file__).resolve().parents[1].parent / "docs" / "curated_pool.csv"

JUMP_LIMIT = 0.15          # R1
MIN_ROWS = 260             # R2 (~1y, enough for a 250d momentum lookback + buffer)
ALIVE_WINDOW_D = 7         # R3
VOL_LO, VOL_HI = 0.005, 0.45   # R4 annualized

CATEGORY_RULES: list[tuple[str, str]] = [
    ("money",   r"货币|现金|理财|添利|增利|快线|钱包"),
    ("bond",    r"债|利率|信用|存单|同业"),
    ("gold",    r"黄金|贵金属|金ETF|上海金"),
    ("oil",     r"原油|油气|石油|能源化工|石化"),
    ("qdii",    r"QDII|纳指|纳斯达克|标普|道琼斯|日经|越南|印度|香港|恒生|海外|全球|美元|美国"),
    ("index",   r"指数|ETF|联接|沪深300|中证|上证|创业板|科创|A500|红利"),
    ("industry", r"医药|医疗|生物|半导体|芯片|军工|新能源|光伏|白酒|消费|银行|证券|地产|科技|人工智能|机器人|算力"),
    ("equity",  r"混合|成长|价值|均衡|精选|优选|龙头|主题|量化"),
]


def classify(name: str) -> str:
    n = (name or "").strip()
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, n):
            return cat
    return "other"


def fmt(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-only", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    assets = conn.execute(
        "SELECT id, symbol, name, status FROM research_assets WHERE status='pooled' "
        "ORDER BY symbol"
    ).fetchall()
    print(f"pooled assets: {len(assets)}", flush=True)

    global_last = conn.execute("SELECT MAX(date) FROM research_prices").fetchone()[0]
    print("global latest nav date:", global_last, flush=True)
    horizon = (date.today() - timedelta(days=2 * 365 + 15)).isoformat()

    rows_out = []
    stats = {k: 0 for k in ("jump", "rows", "dead", "vol_lo", "vol_hi", "ok")}
    cat_count: dict[str, int] = {}

    for aid, sym, name, status in assets:
        prices = [r[0] for r in conn.execute(
            "SELECT close FROM research_prices WHERE asset_id=? AND date>=? ORDER BY date",
            (aid, horizon)).fetchall()]
        n = len(prices)
        if n < MIN_ROWS:
            stats["rows"] += 1
            continue
        last_d = conn.execute(
            "SELECT MAX(date) FROM research_prices WHERE asset_id=?", (aid,)).fetchone()[0]
        if last_d < (date.today() - timedelta(days=ALIVE_WINDOW_D)).isoformat():
            stats["dead"] += 1
            continue
        # R1 daily jumps anywhere in window
        jump_hit = False
        for i in range(1, n):
            if prices[i - 1] > 0:
                r1 = prices[i] / prices[i - 1] - 1.0
                if abs(r1) > JUMP_LIMIT:
                    jump_hit = True
                    break
        if jump_hit:
            stats["jump"] += 1
            continue
        rets = [prices[i] / prices[i - 1] - 1.0 for i in range(1, n) if prices[i - 1] > 0]
        if len(rets) < 250:
            stats["rows"] += 1
            continue
        m = sum(rets) / len(rets)
        vol = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1)) * math.sqrt(252)
        if vol < VOL_LO:
            stats["vol_lo"] += 1
            continue
        if vol > VOL_HI:
            stats["vol_hi"] += 1
            continue
        cat = classify(name)
        cat_count[cat] = cat_count.get(cat, 0) + 1
        stats["ok"] += 1
        rows_out.append({
            "symbol": sym, "name": name, "category": cat,
            "ann_vol_pct": round(vol * 100, 2),
            "ann_ret_pct": round(((1 + m) ** 252 - 1) * 100, 2),
            "rows": n,
        })

    conn.close()
    rows_out.sort(key=lambda r: (r["category"], -r["ann_ret_pct"]))
    print("filter stats:", stats, flush=True)
    print("category counts:", cat_count, flush=True)
    print("PASS:", len(rows_out), flush=True)

    if args.print_only:
        return

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)

    lines = [
        "# 精选标的池（Curated Pool）",
        "",
        f"> 生成时间：{date.today().isoformat()} · 筛选自 {len(assets)} 只入池标的",
        "",
        "## 筛选标准（假动量防线）",
        "",
        f"- R1 近两年无单日净值跳变 |ret|>{JUMP_LIMIT:.0%}（剔脏数据假动量源）",
        f"- R2 净值行数 ≥ {MIN_ROWS}（~1 年，保证 250d 动量窗口有效）",
        f"- R3 近 {ALIVE_WINDOW_D} 天有净值（活着）",
        f"- R4 年化波动 ∈ [{VOL_LO:.1%}, {VOL_HI:.0%}]（剔货币类平坦线与异动垃圾）",
        "",
        "## 分类统计",
        "",
        "| 类别 | 数量 |",
        "|---|---|",
    ]
    for c in sorted(cat_count, key=lambda x: -cat_count[x]):
        lines.append(f"| {c} | {cat_count[c]} |")
    lines += ["", "## 全量清单", "",
              "| 代码 | 名称 | 类别 | 年化波动% | 年化收益% | 行数 |",
              "|---|---|---|---|---|---|"]
    for r in rows_out:
        lines.append(
            f"| {r['symbol']} | {r['name']} | {r['category']} | "
            f"{r['ann_vol_pct']} | {r['ann_ret_pct']} | {r['rows']} |")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT_MD, flush=True)
    print("wrote", OUT_CSV, flush=True)


if __name__ == "__main__":
    main()
