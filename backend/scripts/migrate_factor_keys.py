"""One-off migration: add factors.key (stable strategy identifier) and fill it.

Run: python scripts/migrate_factor_keys.py
Safe to re-run (idempotent).
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB = os.path.join(os.path.dirname(__file__), "..", "finkit.db")

# stable key per factor, matched by proxy_symbol (fallback: name substring)
KEY_BY_PROXY = {
    "511220": "credit_bond",
    "511010": "bond",
    "000852": "small_cap",
    "000300": "equity",
    "513100": "overseas_equity",
    "518880": "gold",
}
KEY_BY_NAME_PART = {
    "规模": "size",
    "小盘": "small_cap",
}


def main() -> None:
    if not os.path.exists(DB):
        print(f"DB not found: {DB}")
        return
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cols = [r[1] for r in cur.execute("PRAGMA table_info(factors)")]
    if "key" not in cols:
        cur.execute("ALTER TABLE factors ADD COLUMN key TEXT DEFAULT ''")
        print("added column factors.key")

    rows = cur.execute("SELECT id, name, proxy_symbol FROM factors").fetchall()
    for fid, name, proxy in rows:
        key = KEY_BY_PROXY.get(proxy) or next(
            (v for k, v in KEY_BY_NAME_PART.items() if k in (name or "")), ""
        )
        if key:
            cur.execute("UPDATE factors SET key=? WHERE id=?", (key, fid))
            print(f"  {name} (proxy={proxy}) -> key={key}")
        else:
            print(f"  !! {name} (proxy={proxy}) has no key mapping")

    conn.commit()
    conn.close()
    print("done")


if __name__ == "__main__":
    main()
