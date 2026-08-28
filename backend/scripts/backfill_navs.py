"""Backfill NAV history for research assets — eastmoney only, never iFinD.

Selection strategy (user-approved):
  L0  pooled assets first
  L1  one representative per "family", C-share preferred
  Non-representative family members are never fetched.

A family = normalized name (share-class suffix, currency words, 发起式/联接/
ETF/LOF stripped). Money-market funds are skipped (flat NAV). Assets whose
data already covers ~5y are skipped (resumable re-run safe).

Throttle (conservative tier): serial, 2-4s random jitter, 5-minute pause
every 50 fetches, nightly pause 23:30-07:30. Ctrl+C is always safe —
progress lives in the DB itself.

Usage (from backend/):
  python scripts/backfill_navs.py --dry-run     # show plan, no network
  python scripts/backfill_navs.py               # run all representatives
  python scripts/backfill_navs.py --limit 100   # cap fetch count this run
"""
from __future__ import annotations

import argparse
import asyncio
import random
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB_PATH = Path(__file__).resolve().parents[1] / "finkit.db"
YEARS_BACK = 5
FETCH_MIN_S, FETCH_MAX_S = 2.0, 4.0
PAUSE_EVERY_N = 50
PAUSE_SECONDS = 300
NIGHT_START, NIGHT_END = (23, 30), (7, 30)

_SHARE_SUFFIX = re.compile(r"[（(]?(人民币|美元现汇|港元|发起式|联接基金?|ETF|LOF)[）)]?$")
_CLASS_TOKEN = re.compile(r"[（(]?\s*([ABCEIHO])\s*[类]?[）)]?$")
_TRAILING_CLASS = re.compile(r"([ACEIHO])$")


def normalize_family_name(name: str) -> str:
    s = (name or "").strip().upper()
    s = re.sub(r"\s+", "", s)
    for _ in range(3):
        s2 = _CLASS_TOKEN.sub("", s)
        s2 = _SHARE_SUFFIX.sub("", s2)
        if s2 == s:
            break
        s = s2
    return s


def is_c_share(name: str) -> bool:
    return bool(_TRAILING_CLASS.search((name or "").strip().upper()))


def build_plan(conn: sqlite3.Connection) -> list[dict]:
    """Ordered fetch plan: L0 pooled, L1 C-share reps, L2 other reps."""
    rows = conn.execute(
        "SELECT id, symbol, exchange, name, status, is_money_market "
        "FROM research_assets WHERE exchange = 'FUND_CN'"
    ).fetchall()
    latest = dict(conn.execute(
        "SELECT asset_id, MAX(date) FROM research_prices GROUP BY asset_id"
    ).fetchall())
    horizon = (date.today() - timedelta(days=int(YEARS_BACK * 365.25) - 14)).isoformat()

    candidates, skipped_mm, skipped_fresh = [], 0, 0
    for aid, sym, exch, name, status, mm in rows:
        if mm:
            skipped_mm += 1
            continue
        if latest.get(aid) and latest[aid] <= horizon:
            skipped_fresh += 1
            continue
        candidates.append({
            "id": aid, "symbol": sym, "exchange": exch or "FUND_CN",
            "name": name or sym, "pooled": status == "pooled",
            "last": latest.get(aid),
        })

    fams: dict[str, dict] = {}
    for c in candidates:
        key = normalize_family_name(c["name"])
        fam = fams.setdefault(key, {"key": key, "members": []})
        fam["members"].append(c)

    reps: list[dict] = []
    for fam in sorted(fams.values(), key=lambda f: min(m["symbol"] for m in f["members"])):
        ms = fam["members"]
        pooled_m = [m for m in ms if m["pooled"]]
        cs = [m for m in ms if is_c_share(m["name"])]
        if pooled_m:
            rep = min(pooled_m, key=lambda m: m["symbol"])
        elif cs:
            rep = min(cs, key=lambda m: m["symbol"])
        else:
            rep = min(ms, key=lambda m: m["symbol"])
        rep["tier"] = 0 if rep["pooled"] else (1 if is_c_share(rep["name"]) else 2)
        reps.append(rep)

    reps.sort(key=lambda r: (0 if r["tier"] == 0 else 1, r["symbol"]))
    stats = {"money_market": skipped_mm, "fresh": skipped_fresh,
             "families": len(fams), "non_representative": len(candidates) - len(reps)}
    return reps, stats


def upsert_prices(conn: sqlite3.Connection, asset_id: str, series: list[dict]) -> int:
    rows = [(asset_id, p["date"], float(p["close"])) for p in series if p.get("date") and p.get("close") is not None]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR IGNORE INTO research_prices (asset_id, date, close) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def wait_if_night() -> None:
    while True:
        now = datetime.now()
        mins = now.hour * 60 + now.minute
        if not (mins >= NIGHT_START[0] * 60 + NIGHT_START[1] or mins < NIGHT_END[0] * 60 + NIGHT_END[1]):
            return
        resume = (datetime(now.year, now.month, now.day, NIGHT_END[0], NIGHT_END[1])
                  if now.hour < 12 else
                  datetime(now.year, now.month, now.day) + timedelta(days=1, hours=NIGHT_END[0], minutes=NIGHT_END[1]))
        print(f"[night-pause] {now:%H:%M} in night window, resume ~{resume:%m-%d %H:%M}", flush=True)
        time.sleep(60)


async def fetch(symbol: str, exchange: str, begin: str, end: str) -> tuple[list[dict], str]:
    from app.services.nav_history import fetch_history_series
    return await fetch_history_series(symbol, exchange, begin, end,
                                      ifind_user=None, ifind_pass=None)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max fetches this run (0=all)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--begin", default="", help="override window begin YYYY-MM-DD")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    reps, stats = build_plan(conn)
    print(f"plan: {len(reps)} representatives | families={stats['families']} "
          f"| skipped mm={stats['money_market']} fresh={stats['fresh']} "
          f"| non-representative={stats['non_representative']}", flush=True)

    if args.dry_run:
        for r in reps[:80]:
            print(f"  T{r['tier']} {r['symbol']} {r['name'][:24]:<24} last={r['last'] or '-'}")
        if len(reps) > 80:
            print(f"  ... and {len(reps) - 80} more")
        return

    end = date.today().isoformat()
    done = errors = inserted_total = 0
    since_run = time.time()
    try:
        for i, r in enumerate(reps, 1):
            wait_if_night()
            if args.limit and done >= args.limit:
                print(f"[stop] --limit {args.limit} reached", flush=True)
                break
            default_begin = (date.today() - timedelta(days=int(YEARS_BACK * 365.25))).isoformat()
            if args.begin:
                begin = args.begin
            elif r["last"]:
                begin = (date.fromisoformat(r["last"]) + timedelta(days=1)).isoformat()
            else:
                begin = default_begin
            if begin >= end:
                continue
            try:
                series, source = await fetch(r["symbol"], r["exchange"], begin, end)
                n = upsert_prices(conn, r["id"], series)
                inserted_total += n
                done += 1
                print(f"[{i}/{len(reps)}] {r['symbol']} {r['name'][:20]} +{n} rows ({source})", flush=True)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                errors += 1
                print(f"[{i}/{len(reps)}] {r['symbol']} ERROR {type(e).__name__}: {e}", flush=True)
            if done and done % PAUSE_EVERY_N == 0:
                print(f"[pause] {done} fetched, resting {PAUSE_SECONDS}s", flush=True)
                time.sleep(PAUSE_SECONDS)
            time.sleep(random.uniform(FETCH_MIN_S, FETCH_MAX_S))
    except KeyboardInterrupt:
        print("\n[interrupt] safe to stop — re-run resumes from DB state", flush=True)
    mins = (time.time() - since_run) / 60
    print(f"done: fetched={done} inserted={inserted_total} errors={errors} in {mins:.0f} min", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
