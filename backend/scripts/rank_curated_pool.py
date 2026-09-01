"""Step 3 helper: from the curated pool (5990 clean funds), rank per
category by risk-adjusted quality and emit ready-to-import top-N lists
(md + a combined symbols file for backtests).

Quality ranking inside a category: 2y sharpe (rf=2%), min rows 400,
still subject to the same jump/alive gates (they were applied upstream).
"""
from __future__ import annotations

import csv
import math
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB = Path(__file__).resolve().parents[1] / "finkit_public.db"
CSV_IN = Path(__file__).resolve().parents[1].parent / "docs" / "curated_pool.csv"
OUT_MD = Path(__file__).resolve().parents[1].parent / "docs" / "curated_pool_top.md"

TOP_N = 20


def sharpe(prices: list[float]) -> tuple[float, float]:
    rets = [prices[i] / prices[i - 1] - 1.0 for i in range(1, len(prices)) if prices[i - 1] > 0]
    if len(rets) < 200:
        return 0.0, 0.0
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1))
    if sd < 1e-9:
        return 0.0, 0.0
    rf = 0.02 / 252
    return (m - rf) / sd * math.sqrt(252), (1 + m) ** 252 - 1


def main() -> None:
    rows = list(csv.DictReader(open(CSV_IN, encoding="utf-8-sig")))
    print("curated rows:", len(rows))
    conn = sqlite3.connect(str(DB), timeout=30)
    horizon = (date.today() - timedelta(days=2 * 365 + 15)).isoformat()

    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        aid = conn.execute(
            "SELECT id FROM research_assets WHERE symbol=?", (r["symbol"],)).fetchone()
        if not aid:
            continue
        prices = [x[0] for x in conn.execute(
            "SELECT close FROM research_prices WHERE asset_id=? AND date>=? ORDER BY date",
            (aid[0], horizon)).fetchall()]
        if len(prices) < 400:
            continue
        sp, ann = sharpe(prices)
        # NAV peak-to-trough over the window
        peak, mdd = prices[0], 0.0
        for p in prices:
            peak = max(peak, p)
            if peak > 0:
                mdd = min(mdd, p / peak - 1.0)
        by_cat.setdefault(r["category"], []).append({
            **r, "sharpe": round(sp, 2), "ann2y_pct": round(ann * 100, 1),
            "mdd_pct": round(mdd * 100, 1),
        })
    conn.close()

    lines = [
        "# 精选池 · 分类 Top-N（按 2 年夏普）",
        "",
        f"> 生成时间 {date.today().isoformat()} · 上游：curated_pool（5990 只干净标的）",
        "> 排名口径：近 2 年日频夏普（rf=2%），要求 ≥400 行",
        "",
    ]
    for cat in ("index", "industry", "bond", "gold", "oil", "qdii", "equity", "money", "other"):
        items = sorted(by_cat.get(cat, []), key=lambda x: -x["sharpe"])[:TOP_N]
        if not items:
            continue
        lines += [f"## {cat} · Top{len(items)}", "",
                  "| 代码 | 名称 | 夏普 | 2年年化% | 最大回撤% | 年化波动% |", "|---|---|---|---|---|---|"]
        for it in items:
            lines.append(f"| {it['symbol']} | {it['name']} | {it['sharpe']} | "
                         f"{it['ann2y_pct']} | {it['mdd_pct']} | {it['ann_vol_pct']} |")
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT_MD)


if __name__ == "__main__":
    main()
