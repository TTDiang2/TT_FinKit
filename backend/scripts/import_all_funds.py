"""One-shot: import the WHOLE eastmoney open-fund universe into the watchlist.

- Single akshare table pull (fund_purchase_em, ~27k rows) — no per-fund network
  calls at all (no fees page, no NAV sync). Fees/NAV are filled lazily later via
  批量更新档案 / 自动审查.
- Tags (kind/asset_class/region/themes) derived purely from name+type.
- Idempotent: existing (user_id, symbol) rows are skipped.

Usage:
    python scripts/import_all_funds.py [--types 指数型,股票型] [--include-suspended]
                                       [--db ../finkit.db] [--dry-run]
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.fund_profile import derive_tags, normalize_daily_limit  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(os.path.dirname(__file__), "..", "finkit.db"))
    ap.add_argument("--types", default="", help="基金类型前缀过滤，逗号分隔。空=除货币/理财外全部")
    ap.add_argument("--exclude-types", default="货币型,理财型")
    ap.add_argument("--include-suspended", action="store_true")
    ap.add_argument("--email", default="", help="目标用户 email；默认取持有标的最多的用户")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import akshare as ak
    print("pulling fund_purchase_em ...")
    df = ak.fund_purchase_em()
    print(f"universe rows: {len(df)}")

    conn = sqlite3.connect(args.db, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    if args.email:
        row = conn.execute("SELECT id FROM users WHERE email=?", (args.email,)).fetchone()
        if not row:
            print(f"no user with email {args.email}")
            return
        user_id = row[0]
    else:
        # 主账号 = research_assets 最多的用户（空表时回退第一个注册用户）
        user_id = conn.execute(
            "SELECT u.id FROM users u LEFT JOIN research_assets r ON r.user_id = u.id "
            "GROUP BY u.id ORDER BY COUNT(r.id) DESC, u.created_at LIMIT 1"
        ).fetchone()[0]
    print(f"target user: {user_id}")
    have = {r[0] for r in conn.execute(
        "SELECT symbol FROM research_assets WHERE user_id=?", (user_id,))}
    print(f"user {user_id}, existing symbols: {len(have)}")

    type_prefixes = [t.strip() for t in args.types.split(",") if t.strip()]
    excl_prefixes = [t.strip() for t in args.exclude_types.split(",") if t.strip()] or []
    now = datetime.utcnow().isoformat(sep=" ")

    rows, skipped_suspended, skipped_type, skipped_dup = [], 0, 0, 0
    for _, r in df.iterrows():
        sym = str(r.get("基金代码") or "").strip()
        name = str(r.get("基金简称") or "").strip()
        ftype = str(r.get("基金类型") or "").strip()
        status = str(r.get("申购状态") or "").strip()
        if not sym.isdigit() or not name:
            continue
        if any(ftype.startswith(p) for p in excl_prefixes):
            skipped_type += 1
            continue
        if type_prefixes and not any(ftype.startswith(p) for p in type_prefixes):
            skipped_type += 1
            continue
        if status != "开放申购" and not args.include_suspended:
            skipped_suspended += 1
            continue
        if sym in have:
            skipped_dup += 1
            continue

        tags = derive_tags(name, ftype)
        rows.append((
            user_id, sym, "FUND_CN", name, "fund", "", "watchlist",
            normalize_daily_limit(r.get("日累计限定金额")),
            status,
            tags["fund_kind"], tags["asset_class"], tags["region"],
            json.dumps(tags["auto_tags"], ensure_ascii=False),
            1 if "货币" in ftype else 0,
            now, now,
        ))
        have.add(sym)

    print(f"to insert: {len(rows)} | dup skip: {skipped_dup} | suspended skip: {skipped_suspended} | type skip: {skipped_type}")
    if args.dry_run:
        for row in rows[:10]:
            print(" ", row[1], row[2], row[3], "|", row[9], row[10], row[11], row[12])
        print("dry-run, nothing written.")
        return

    sql = ("INSERT INTO research_assets "
           "(id, user_id, symbol, exchange, name, asset_type, category, status, purchase_limit, purchase_status,"
           " fund_kind, asset_class, region, auto_tags, is_money_market, created_at, updated_at) "
           "VALUES (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-4'||substr(hex(randomblob(2)),2)||'-'"
           "||substr('89ab',abs(random())%4+1,1)||substr(hex(randomblob(2)),2)||'-'||hex(randomblob(6))),"
           "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
    cur = conn.cursor()
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        cur.executemany(sql, chunk)
        conn.commit()
        print(f"  inserted {min(i + 500, len(rows))}/{len(rows)}")
    conn.close()
    print("done.")


if __name__ == "__main__":
    main()
