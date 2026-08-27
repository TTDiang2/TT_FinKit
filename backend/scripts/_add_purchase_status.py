"""Add research_assets.purchase_status if missing (run before import_all_funds)."""
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else "finkit.db"
c = sqlite3.connect(db, timeout=60)
cols = {r[1] for r in c.execute("PRAGMA table_info(research_assets)")}
if "purchase_status" not in cols:
    c.execute("ALTER TABLE research_assets ADD COLUMN purchase_status VARCHAR DEFAULT '' NOT NULL")
    c.commit()
    print("purchase_status added")
else:
    print("already exists")
c.close()
