"""One-shot migration: add asset_class / benchmark_symbol / benchmark_exchange to investments."""
import sqlite3, sys, io
sys.stdout = io.open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

DB = r"finkit.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()
cols = {row[1] for row in cur.execute("PRAGMA table_info(investments)").fetchall()}
added = []
for col in ("asset_class", "benchmark_symbol", "benchmark_exchange"):
    if col not in cols:
        cur.execute(f"ALTER TABLE investments ADD COLUMN {col} TEXT DEFAULT ''")
        added.append(col)
conn.commit()
# Verify
cols2 = {row[1] for row in cur.execute("PRAGMA table_info(investments)").fetchall()}
print("investments columns now:", sorted(cols2))
print("Added:", added if added else "(none — already present)")
conn.close()
