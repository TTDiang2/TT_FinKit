"""Standalone stats-snapshot compute — runs OUTSIDE the backend event loop.

The in-process recompute froze the entire server (pure-Python loop over
millions of price rows blocks asyncio). This subprocess writes the result
JSON to cache/stats_snapshot_<key>.json; the API just reads that file.

Usage: python scripts/compute_stats_snapshot.py <days> <assets_or_all> <user_id>
"""
import json
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DB = str(BACKEND / "finkit_public.db")
CACHE = BACKEND / "cache"
CACHE.mkdir(exist_ok=True)

# 与 app/routers/research_statistics.py 的 stats_snapshot 输出同构的最小实现：
# 读价格 → 算相关矩阵/前沿/每标的指标（窗口内）。


def compute(days: int, assets: str | None, user_id: str) -> dict:
    end = date.today()
    begin = end - timedelta(days=days)
    begin_s, end_s = begin.isoformat(), end.isoformat()

    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row
    q = "SELECT id, symbol, name FROM research_assets WHERE user_id=?"
    params: list = [user_id]
    if assets and assets != "all":
        syms = [s.strip() for s in assets.split(",") if s.strip()]
        q += f" AND symbol IN ({','.join('?' * len(syms))})"
        params += syms
    asset_rows = conn.execute(q + " ORDER BY created_at", params).fetchall()
    ids = [r["id"] for r in asset_rows]
    id_meta = {r["id"]: (r["symbol"], r["name"]) for r in asset_rows}

    out_assets = []
    closes_by: dict[str, list[tuple[str, float]]] = {}
    if ids:
        ph = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT asset_id, date, close FROM research_prices "
            f"WHERE asset_id IN ({ph}) AND date >= ? ORDER BY asset_id, date",
            [*ids, begin_s]).fetchall()
        for r in rows:
            closes_by.setdefault(r["asset_id"], []).append((r["date"], float(r["close"])))
    conn.close()

    for aid in ids:
        ser = closes_by.get(aid, [])
        if len(ser) < 30:
            continue
        closes = [c for _, c in ser]
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0]
        if len(rets) < 30:
            continue
        years = len(rets) / 252.0
        ann = (closes[-1] / closes[0]) ** (1 / years) - 1 if years > 0 and closes[0] > 0 else None
        mu = sum(rets) / len(rets)
        vol = (sum((x - mu) ** 2 for x in rets) / (len(rets) - 1)) ** 0.5
        sharpe = (ann - 0.02) / vol if ann is not None and vol > 1e-9 else None
        peak, mdd = closes[0], 0.0
        for v in closes:
            peak = max(peak, v)
            if peak > 0:
                mdd = min(mdd, v / peak - 1.0)
        sym, name = id_meta[aid]
        tail = ser[-260:]

        out_assets.append({
            "asset_id": aid, "symbol": sym, "name": name,
            "ret_window": closes[-1] / closes[0] - 1.0 if closes[0] > 0 else None,
            "ann_return": ann, "ann_volatility": vol, "sharpe": sharpe,
            "max_drawdown": mdd,
            "dates": [d for d, _ in tail],
            "nav": ([round(cc / tail[0][1], 6) for _, cc in tail]
                    if (tail and tail[0][1] > 0) else []),
        })
    out_assets.sort(key=lambda a: -(a["sharpe"] or -9))

    # 相关矩阵（前 25 只，日收益）
    import math
    sel = out_assets[:25]
    ret_map: dict[str, list[float]] = {}
    for a in sel:
        closes = None
        for aid in ids:
            if aid == a["asset_id"]:
                closes = [c for _, c in closes_by[aid]]
                break
        if closes and len(closes) > 60:
            ret_map[a["asset_id"]] = [closes[i] / closes[i - 1] - 1.0
                                      for i in range(1, len(closes)) if closes[i - 1] > 0][-250:]
    labels = [a["symbol"] for a in sel if a["asset_id"] in ret_map]
    matrix = []
    keys = list(ret_map)
    for i, k1 in enumerate(keys):
        row = []
        for j, k2 in enumerate(keys):
            if j > i:
                row.append(None)
                continue
            if k1 == k2:
                row.append(1.0)
                continue
            x, y = ret_map[k1], ret_map[k2]
            n = min(len(x), len(y))
            x, y = x[-n:], y[-n:]
            mx, my = sum(x) / n, sum(y) / n
            cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
            vx = math.sqrt(sum((a - mx) ** 2 for a in x))
            vy = math.sqrt(sum((b - my) ** 2 for b in y))
            row.append(round(cov / (vx * vy), 4) if vx > 0 and vy > 0 else None)
        matrix.append(row)
    # 补全下三角（对称）
    for i in range(len(matrix)):
        for j in range(len(matrix)):
            if matrix[i][j] is None and matrix[j][i] is not None:
                matrix[i][j] = matrix[j][i]

    return {
        "window": {"begin": begin_s, "end": end_s, "days": days},
        "assets": out_assets,
        "correlation": {"labels": labels, "matrix": matrix},
        "frontier": {"assets": labels, "samples": []},
    }


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    assets = sys.argv[2] if len(sys.argv) > 2 else "all"
    user_id = sys.argv[3]
    t0 = time.time()
    data = compute(days, assets, user_id)
    key = f"{user_id}_{days}_{assets or 'all'}".replace(":", "_").replace(",", "-")
    out = CACHE / f"stats_snapshot_{key}.json"
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"done in {time.time()-t0:.0f}s -> {out} ({out.stat().st_size/1e3:.0f} KB)")


if __name__ == "__main__":
    main()
