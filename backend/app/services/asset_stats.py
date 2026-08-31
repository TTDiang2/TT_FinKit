"""Precomputed per-asset statistics — ``research_asset_stats``.

One full scan of research_prices (~6.5M rows, ~2 min) materializes per-asset
windows (21/63/252d returns, 1y & all-time ann/vol/sharpe/mdd) into a small
table. The 标的页 sort/filter, 统计 tab and 热点页 all read this table instead
of re-aggregating raw prices on every request.

Refresh: scripts/refresh_asset_stats.py (manual button / after pooling /
after backfill). Staleness surfaced via computed_at.
"""
from __future__ import annotations

import math
import sqlite3
import time
from datetime import datetime

STATS_FIELDS = [
    "rows", "last_date",
    "ret_21d", "ret_63d", "ret_252d",
    "ann_1y", "vol_1y", "sharpe_1y", "mdd_1y",
    "ann_all", "vol_all", "sharpe_all", "mdd_all",
]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS research_asset_stats (
    asset_id TEXT PRIMARY KEY,
    symbol TEXT,
    name TEXT,
    status TEXT,
    rows INTEGER,
    last_date TEXT,
    ret_21d REAL, ret_63d REAL, ret_252d REAL,
    ann_1y REAL, vol_1y REAL, sharpe_1y REAL, mdd_1y REAL,
    ann_all REAL, vol_all REAL, sharpe_all REAL, mdd_all REAL,
    computed_at TEXT
)
"""

UPSERT_SQL = """
INSERT INTO research_asset_stats (asset_id, symbol, name, status, rows, last_date,
 ret_21d, ret_63d, ret_252d, ann_1y, vol_1y, sharpe_1y, mdd_1y,
 ann_all, vol_all, sharpe_all, mdd_all, computed_at)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(asset_id) DO UPDATE SET
 symbol=excluded.symbol, name=excluded.name, status=excluded.status,
 rows=excluded.rows, last_date=excluded.last_date,
 ret_21d=excluded.ret_21d, ret_63d=excluded.ret_63d, ret_252d=excluded.ret_252d,
 ann_1y=excluded.ann_1y, vol_1y=excluded.vol_1y, sharpe_1y=excluded.sharpe_1y,
 mdd_1y=excluded.mdd_1y, ann_all=excluded.ann_all, vol_all=excluded.vol_all,
 sharpe_all=excluded.sharpe_all, mdd_all=excluded.mdd_all,
 computed_at=excluded.computed_at
"""


def _metrics(closes: list[float], rf: float = 0.02) -> dict:
    n = len(closes)
    out = {"ann": None, "vol": None, "sharpe": None, "mdd": None}
    if n < 30 or closes[0] <= 0:
        return out
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, n) if closes[i - 1] > 0]
    if len(rets) < 10:
        return out
    years = len(rets) / 252.0
    out["ann"] = (closes[-1] / closes[0]) ** (1.0 / years) - 1.0 if years > 0 else None
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
    out["vol"] = math.sqrt(var) * math.sqrt(252)
    out["sharpe"] = (out["ann"] - rf) / out["vol"] if out["ann"] is not None and out["vol"] > 1e-9 else None
    peak, mdd = closes[0], 0.0
    for v in closes:
        if v > peak:
            peak = v
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    out["mdd"] = mdd
    return out


def _window_ret(closes: list[float], n: int) -> float | None:
    if len(closes) <= n or closes[-n - 1] <= 0:
        return None
    return closes[-1] / closes[-n - 1] - 1.0


def refresh_stats(db_path: str, batch_size: int = 500) -> dict:
    """Full refresh: single ordered scan, per-asset compute, batched upserts."""
    t0 = time.time()
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute(CREATE_SQL)
    conn.commit()

    meta = {
        r[0]: (r[1], r[2], r[3])
        for r in conn.execute("SELECT id, symbol, name, status FROM research_assets")
    }

    conn2 = sqlite3.connect(db_path, timeout=60)  # writer connection
    conn2.execute("PRAGMA busy_timeout=60000")
    conn2.execute(CREATE_SQL)

    current_id: str | None = None
    closes: list[float] = []
    last_date: str | None = None
    buffer: list[tuple] = []
    written = 0

    def flush() -> None:
        nonlocal written
        if current_id is None or current_id not in meta:
            return
        sym, name, status = meta[current_id]
        m_all = _metrics(closes)
        recent = closes[-252:]                      # 1y 窗口 = 最近 252 日
        m_1y = _metrics(recent)
        buffer.append((
            current_id, sym, name, status, len(closes), last_date,
            _window_ret(closes, 21), _window_ret(closes, 63), _window_ret(closes, 252),
            m_1y["ann"], m_1y["vol"], m_1y["sharpe"], m_1y["mdd"],
            m_all["ann"], m_all["vol"], m_all["sharpe"], m_all["mdd"],
            datetime.utcnow().isoformat(),
        ))
        written += 1
        if len(buffer) >= batch_size:
            conn2.executemany(UPSERT_SQL, buffer)
            conn2.commit()
            buffer.clear()

    cur = conn.execute(
        "SELECT asset_id, date, close FROM research_prices ORDER BY asset_id, date"
    )
    # cursor.iterfetch to stream in chunks
    while True:
        chunk = cur.fetchmany(200_000)
        if not chunk:
            break
        for asset_id, date, close in chunk:
            if asset_id != current_id:
                flush()
                current_id = asset_id
                closes.clear()
                last_date = None
            if close is not None and close > 0:
                closes.append(close)
            last_date = date
    flush()

    if buffer:
        conn2.executemany(UPSERT_SQL, buffer)
        conn2.commit()
        buffer.clear()
    n = conn2.execute("SELECT COUNT(*) FROM research_asset_stats").fetchone()[0]
    conn.close()
    conn2.close()
    return {"assets": n, "written": written, "seconds": round(time.time() - t0, 1)}
