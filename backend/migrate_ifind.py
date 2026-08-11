"""One-shot migration: add ifind_username / ifind_password to user_settings."""
import sqlite3, sys, io
sys.stdout = io.open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

DB = r"finkit.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()
cols = {row[1] for row in cur.execute("PRAGMA table_info(user_settings)").fetchall()}
added = []
for col in ("ifind_username", "ifind_password"):
    if col not in cols:
        cur.execute(f"ALTER TABLE user_settings ADD COLUMN {col} TEXT DEFAULT ''")
        added.append(col)
conn.commit()
# Verify
cols2 = {row[1] for row in cur.execute("PRAGMA table_info(user_settings)").fetchall()}
print("user_settings columns now:", sorted(cols2))
print("Added:", added if added else "(none — already present)")
conn.close()
