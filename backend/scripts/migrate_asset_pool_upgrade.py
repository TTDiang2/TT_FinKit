"""One-off migration for the asset pool upgrade (2026-08-23 plan).

Adds:
  - research_assets.sales_service_fee  (REAL, nullable)
  - research_assets.redeem_rules       (TEXT default '[]')
  - table research_asset_ai_reports
  - table research_asset_holdings

Idempotent — safe to re-run. Run: python scripts/migrate_asset_pool_upgrade.py [db_path]
"""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "finkit.db")


def _parse_legacy_redeem_note(note: str):
    """Best-effort parse of old free-text like '<7天 1.5%，≥30天 0' → rules JSON."""
    if not note or not note.strip():
        return None
    rules = []
    # matches pairs: (<|≤|满)?N(天|日)? ... pct
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*天[^，,;；]*?(\d+(?:\.\d+)?)\s*%", note):
        days = int(float(m.group(1)))
        fee = float(m.group(2))
        rules.append({"days": days, "fee_rate": fee})
    if not rules:
        return None
    # sort by days asc, append fallback 0 if the last tier isn't 0
    rules.sort(key=lambda r: r["days"])
    if rules[-1]["fee_rate"] != 0:
        rules.append({"days": None, "fee_rate": 0.0})
    return rules


def main() -> None:
    if not os.path.exists(DB):
        print(f"DB not found: {DB}")
        return
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cols = [r[1] for r in cur.execute("PRAGMA table_info(research_assets)")]
    if "sales_service_fee" not in cols:
        cur.execute("ALTER TABLE research_assets ADD COLUMN sales_service_fee REAL")
        print("added research_assets.sales_service_fee")
    if "redeem_rules" not in cols:
        cur.execute("ALTER TABLE research_assets ADD COLUMN redeem_rules TEXT DEFAULT '[]'")
        print("added research_assets.redeem_rules")

    # Backfill redeem_rules from redeem_fee_note where empty
    rows = cur.execute(
        "SELECT id, redeem_fee_note, redeem_rules FROM research_assets"
    ).fetchall()
    for aid, note, rules in rows:
        if rules and rules not in ("[]", "null"):
            continue
        parsed = _parse_legacy_redeem_note(note or "")
        if parsed:
            cur.execute("UPDATE research_assets SET redeem_rules=? WHERE id=?",
                        (json.dumps(parsed, ensure_ascii=False), aid))
            print(f"  backfilled redeem_rules for {aid}: {parsed}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_asset_ai_reports (
            id VARCHAR PRIMARY KEY,
            asset_id VARCHAR NOT NULL REFERENCES research_assets(id) ON DELETE CASCADE,
            user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            asset_name VARCHAR NOT NULL,
            asset_symbol VARCHAR NOT NULL,
            query TEXT NOT NULL DEFAULT '',
            analysis TEXT NOT NULL,
            raw_articles TEXT NOT NULL,
            search_backend VARCHAR DEFAULT '',
            llm_preset_id VARCHAR REFERENCES ai_presets(id) ON DELETE SET NULL,
            llm_model VARCHAR DEFAULT '',
            error TEXT,
            generated_at DATETIME
        )
    """)
    print("ensured research_asset_ai_reports")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_asset_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id VARCHAR NOT NULL REFERENCES research_assets(id) ON DELETE CASCADE,
            report_date VARCHAR NOT NULL,
            kind VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            ratio REAL,
            raw TEXT,
            updated_at DATETIME,
            UNIQUE (asset_id, report_date, kind, name)
        )
    """)
    print("ensured research_asset_holdings")

    conn.commit()
    conn.close()
    print("done")


if __name__ == "__main__":
    main()
