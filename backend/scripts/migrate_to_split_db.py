"""一次性把单库 finkit.db 拆成 finkit_public.db + finkit_private.db。

用法（backend/ 下）:
    python scripts/migrate_to_split_db.py [--source finkit.db]

步骤:
  1. backup() 源库两份 → finkit_public.db / finkit_private.db
  2. public 库 DROP 全部私有表; private 库 DROP 全部公开表
  3. VACUUM 两库
  4. 打印两侧行数对照（源 vs 拆分后），校验总行数一致

之后在 backend/.env 里设置:
    PUBLIC_DATABASE_URL=sqlite+aiosqlite:///finkit_public.db
    PRIVATE_DATABASE_URL=sqlite+aiosqlite:///finkit_private.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models._flags import PUBLIC_TABLE_NAMES  # noqa: E402

PRIVATE_TABLE_NAMES = {
    "users", "accounts", "transactions", "investments",
    "investment_transactions", "investment_cash_flows",
    "investment_nav_snapshots", "investment_ai_reports",
    "ai_presets", "report_archives", "reconciliation_records",
    "user_settings", "signals", "backtests",
    "research_asset_ai_reports",
    "categories", "tags", "assets",
    "ai_export", "ai_advisor", "advisor_chats",
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _user_tables(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")]


def _drop_tables(conn: sqlite3.Connection, tables: list[str]) -> int:
    dropped = 0
    for t in tables:
        if _table_exists(conn, t):
            conn.execute(f"DROP TABLE IF EXISTS [{t}]")
            dropped += 1
    conn.commit()
    return dropped


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            for t in _user_tables(conn) if _table_exists(conn, t)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="finkit.db")
    args = ap.parse_args()

    src_path = Path(args.source)
    if not src_path.exists():
        raise SystemExit(f"源库不存在: {src_path}")
    pub_path = src_path.parent / "finkit_public.db"
    prv_path = src_path.parent / "finkit_private.db"

    print(f"[split] source={src_path} -> {pub_path.name} + {prv_path.name}")

    src = sqlite3.connect(src_path)
    src_counts = _counts(src)

    for target in (pub_path, prv_path):
        if target.exists():
            target.unlink()
        dst = sqlite3.connect(target)
        src.backup(dst)
        dst.close()

    pub = sqlite3.connect(pub_path)
    dropped_pub = _drop_tables(pub, [t for t in _user_tables(pub)
                                     if t not in PUBLIC_TABLE_NAMES])
    pub.execute("VACUUM")
    pub_counts = _counts(pub)
    pub.close()

    prv = sqlite3.connect(prv_path)
    dropped_prv = _drop_tables(prv, [t for t in _user_tables(prv)
                                     if t in PUBLIC_TABLE_NAMES])
    prv.execute("VACUUM")
    prv_counts = _counts(prv)
    prv.close()

    mismatches = []
    for t, n in src_counts.items():
        if t in PUBLIC_TABLE_NAMES:
            got = pub_counts.get(t, 0)
        else:
            got = prv_counts.get(t, 0)
        if got != n:
            mismatches.append((t, n, got))

    print(f"[split] public: dropped {dropped_pub} private tables, "
          f"{sum(pub_counts.values())} rows kept")
    print(f"[split] private: dropped {dropped_prv} public tables, "
          f"{sum(prv_counts.values())} rows kept")
    if mismatches:
        print("[split] MISMATCH:")
        for t, n, got in mismatches:
            print(f"   {t}: src={n} split={got}")
        raise SystemExit(1)
    print("[split] all row counts match ✓")
    print("[split] 下一步: 在 backend/.env 设置 PUBLIC_DATABASE_URL / "
          "PRIVATE_DATABASE_URL 指向两个文件")


if __name__ == "__main__":
    main()
