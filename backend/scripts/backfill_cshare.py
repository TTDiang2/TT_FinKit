"""Backfill 5y NAV history for all C-share funds — eastmoney batch, never iFinD.

User-approved (2026-08-28): C-share universe only (name ends with C, same rule
as backfill_navs.is_c_share), 5-year window, moderate throttle:
1-2s jitter, 60s pause every 100 fetches, no night window (~8h for ~8k funds).

Main loop is eastmoney-only (pingzhongdata, 1 request = full history, so the
date window affects stored rows but not fetch count). Failures are logged to
_cshare_failures.jsonl and retried at the end through the full service chain
(akshare fallback included), because that fallback costs ~50s per fund.

Resumable: DB state = progress (begin = last price date + 1 day).
Priority order: pooled assets → research-group members → rest by symbol.

Usage (from backend/):
  python scripts/backfill_cshare.py --dry-run
  python scripts/backfill_cshare.py                   # main pass
  python scripts/backfill_cshare.py --retry-failures  # refetch logged failures
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backfill_navs import is_c_share, upsert_prices

DB_PATH = Path(__file__).resolve().parents[1] / "finkit.db"
YEARS_BACK = 5
FETCH_MIN_S, FETCH_MAX_S = 1.0, 2.0
PAUSE_EVERY_N = 100
PAUSE_SECONDS = 60
FAIL_LOG = Path(__file__).resolve().parent / "_cshare_failures.jsonl"


def build_queue(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, symbol, name, status FROM research_assets WHERE exchange = 'FUND_CN'"
    ).fetchall()
    latest = dict(conn.execute(
        "SELECT asset_id, MAX(date) FROM research_prices GROUP BY asset_id"
    ).fetchall())
    grouped = {aid for (aid,) in conn.execute(
        "SELECT DISTINCT asset_id FROM research_group_members")}
    queue = []
    for aid, sym, name, status in rows:
        if not is_c_share(name or ""):
            continue
        queue.append({
            "id": aid, "symbol": sym, "name": name or sym,
            "pooled": status == "pooled",
            "in_group": aid in grouped,
            "last": latest.get(aid),
        })
    queue.sort(key=lambda r: (not r["pooled"], not r["in_group"], r["symbol"]))
    return queue


async def fetch_eastmoney(symbol: str, begin: str, end: str) -> list[dict]:
    from app.services.nav_history import _eastmoney_history
    series, _src = await _eastmoney_history(symbol, "FUND_CN", begin, end)
    return series


async def fetch_full_chain(symbol: str, begin: str, end: str) -> tuple[list[dict], str]:
    from app.services.nav_history import fetch_history_series
    return await fetch_history_series(symbol, "FUND_CN", begin, end,
                                      ifind_user=None, ifind_pass=None)


def default_begin(last: str | None) -> str:
    if last:
        return (date.fromisoformat(last) + timedelta(days=1)).isoformat()
    return (date.today() - timedelta(days=int(YEARS_BACK * 365.25))).isoformat()


async def run(queue: list[dict], full_chain: bool) -> None:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    end = date.today().isoformat()
    t0 = time.time()
    done = skipped = inserted_total = 0
    failures: list[dict] = []
    mode = "full-chain(retry)" if full_chain else "eastmoney-only"
    print(f"queue={len(queue)} mode={mode} end={end}", flush=True)
    try:
        for i, r in enumerate(queue, 1):
            begin = default_begin(r["last"])
            if begin >= end:
                skipped += 1
                continue
            try:
                if full_chain:
                    series, src = await fetch_full_chain(r["symbol"], begin, end)
                else:
                    series = await fetch_eastmoney(r["symbol"], begin, end)
                    src = "eastmoney"
                n = upsert_prices(conn, r["id"], series)
                inserted_total += n
                done += 1
                if done <= 10 or done % 25 == 0:
                    rate = done / max(time.time() - t0, 1)
                    eta_min = (len(queue) - i) / max(rate, 1e-9) / 60
                    print(f"[{i}/{len(queue)}] {r['symbol']} {r['name'][:18]} +{n} rows "
                          f"({rate * 60:.0f}/min, eta {eta_min:.0f}m)", flush=True)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                failures.append({"symbol": r["symbol"], "name": r["name"],
                                 "begin": begin, "error": f"{type(e).__name__}: {e}"})
                print(f"[{i}/{len(queue)}] {r['symbol']} FAIL {type(e).__name__}: {e}", flush=True)
            if done and done % PAUSE_EVERY_N == 0:
                print(f"[pause] {done} fetched, resting {PAUSE_SECONDS}s", flush=True)
                time.sleep(PAUSE_SECONDS)
            time.sleep(random.uniform(FETCH_MIN_S, FETCH_MAX_S))
    except KeyboardInterrupt:
        print("\n[interrupt] safe to stop — re-run resumes from DB state", flush=True)
    mins = (time.time() - t0) / 60
    print(f"done: fetched={done} skipped-current={skipped} inserted={inserted_total} "
          f"failures={len(failures)} in {mins:.0f} min", flush=True)
    if not full_chain and failures:
        with open(FAIL_LOG, "a", encoding="utf-8") as f:
            for rec in failures:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"failures appended to {FAIL_LOG.name} (retry with --retry-failures)", flush=True)
    conn.close()


async def run_retry_pass() -> None:
    """Refetch everything logged in FAIL_LOG via the full service chain
    (eastmoney → akshare), then clear the log. No-op when nothing failed."""
    if not FAIL_LOG.exists():
        print("[retry] no failure log, nothing to retry", flush=True)
        return
    recs = [json.loads(l) for l in FAIL_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    conn = sqlite3.connect(DB_PATH, timeout=30)
    latest = dict(conn.execute(
        "SELECT asset_id, MAX(date) FROM research_prices GROUP BY asset_id").fetchall())
    id_by_symbol = dict(conn.execute(
        "SELECT symbol, id FROM research_assets WHERE exchange='FUND_CN'").fetchall())
    conn.close()
    queue = []
    for rec in recs:
        aid = id_by_symbol.get(rec["symbol"])
        if aid:
            queue.append({"id": aid, "symbol": rec["symbol"], "name": rec["name"],
                          "pooled": False, "in_group": False, "last": latest.get(aid)})
    FAIL_LOG.unlink()
    print(f"[retry] {len(queue)} logged failures, full-chain refetch", flush=True)
    await run(queue, full_chain=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--retry-failures", action="store_true")
    args = ap.parse_args()

    if args.retry_failures:
        await run_retry_pass()
        return

    conn = sqlite3.connect(DB_PATH, timeout=30)
    queue = build_queue(conn)
    conn.close()
    missing = sum(1 for r in queue if not r["last"])
    print(f"C-share universe: {len(queue)} funds ({missing} without any data yet, "
          f"{len(queue) - missing} incremental)", flush=True)
    if args.dry_run:
        for r in queue[:15]:
            tags = (" [pooled]" if r["pooled"] else "") + (" [group]" if r["in_group"] else "")
            print(f"  {r['symbol']} {r['name'][:26]:<26} last={r['last'] or '-'}{tags}")
        print("  ...")
        return
    if args.limit:
        queue = queue[:args.limit]
    await run(queue, full_chain=False)
    await run_retry_pass()


if __name__ == "__main__":
    asyncio.run(main())
