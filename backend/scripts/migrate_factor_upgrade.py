"""One-off migration for the factor-library + strategy upgrade.

Adds:
- factors.data_status ('ok' | 'stub')
- factor_ic_points / factor_evaluations tables
- strategies.folder / factor_keys / source_file
- Recategorizes the 7 legacy factors into the 7-category taxonomy.

Run: python scripts/migrate_factor_upgrade.py   (from backend/)
Safe to re-run (idempotent).
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB = os.path.join(os.path.dirname(__file__), "..", "finkit.db")

# Legacy factor keys -> new category taxonomy
CATEGORY_REMAP = {
    "equity": "asset_class",
    "bond": "asset_class",
    "credit_bond": "asset_class",
    "gold": "asset_class",
    "small_cap": "style",
    "size": "style",
    "overseas_equity": "country",
}


def add_column(cur, table: str, column: str, ddl_type: str) -> bool:
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]
    if column in cols:
        return False
    cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    print(f"  added {table}.{column}")
    return True


def main() -> None:
    if not os.path.exists(DB):
        print(f"DB not found: {DB}")
        return
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    print("== factors ==")
    add_column(cur, "factors", "data_status", "TEXT DEFAULT 'ok'")

    remapped = 0
    for key, category in CATEGORY_REMAP.items():
        cur.execute("UPDATE factors SET category=? WHERE key=?", (category, key))
        remapped += cur.rowcount if cur.rowcount > 0 else 0
    print(f"  recategorized {remapped} legacy factor rows")

    print("== factor_ic_points ==")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS factor_ic_points (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            factor_key TEXT NOT NULL,
            date TEXT NOT NULL,
            ic REAL,
            rank_ic REAL,
            n INTEGER,
            created_at TEXT
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_uq_factor_ic_point ON factor_ic_points(user_id, factor_key, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_factor_ic_user ON factor_ic_points(user_id)")

    print("== factor_evaluations ==")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS factor_evaluations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            factor_key TEXT NOT NULL,
            window_start TEXT,
            window_end TEXT,
            n_periods INTEGER,
            ic_mean REAL, ic_std REAL, rank_ic_mean REAL,
            icir REAL, icir_annualized REAL, t_stat REAL, win_rate REAL,
            ic_autocorr_lag1 REAL,
            ic_decay_1 REAL, ic_decay_2 REAL, ic_decay_3 REAL,
            quantile_returns TEXT,
            ls_nav TEXT,
            ls_ann_return REAL, ls_vol REAL, ls_sharpe REAL, ls_max_dd REAL, ls_calmar REAL,
            ls_alpha REAL, ls_beta REAL, ls_ir REAL,
            screen_result TEXT,
            computed_at TEXT
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_uq_factor_evaluation ON factor_evaluations(user_id, factor_key)")

    print("== strategies ==")
    add_column(cur, "strategies", "folder", "TEXT DEFAULT ''")
    add_column(cur, "strategies", "factor_keys", "TEXT")
    add_column(cur, "strategies", "source_file", "TEXT")

    conn.commit()
    conn.close()
    print("done")


if __name__ == "__main__":
    main()
