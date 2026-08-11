"""Inspect real holdings to ground the brainstorm in actual data."""
import sqlite3, sys, io
sys.stdout = io.open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)
conn = sqlite3.connect(r"finkit.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
UID = "4481a5f7-6e5a-483e-972f-edcfa0f288df"

print("=== INVESTMENTS (user's products) ===")
rows = cur.execute("SELECT name, investment_type, underlying_asset_type, symbol, exchange, quantity, purchase_price, current_price, sell_date FROM investments WHERE user_id=? ORDER BY sell_date IS NULL DESC, created_at", (UID,)).fetchall()
for r in rows:
    active = "" if r["sell_date"] else " [ACTIVE]"
    print(f"  {r['name']:<20} type={r['investment_type']:<7} under={r['underlying_asset_type'] or '-':<6} {r['exchange'] or '-':<8} {r['symbol'] or '-':<10} qty={r['quantity']:<8} cost={r['purchase_price']:<9} cur={r['current_price']}{active}")
print(f"  TOTAL: {len(rows)} products, ACTIVE: {sum(1 for r in rows if not r['sell_date'])}")

print("\n=== TYPE / EXCHANGE distribution (active only) ===")
for r in cur.execute("SELECT investment_type, exchange, COUNT(*) c, SUM(quantity*current_price) val FROM investments WHERE user_id=? AND sell_date IS NULL GROUP BY investment_type, exchange", (UID,)).fetchall():
    print(f"  {r['investment_type']:<7} {r['exchange'] or '-':<8} count={r['c']} value={r['val'] or 0:.0f}")

print("\n=== UNDERLYING distribution (active only) ===")
for r in cur.execute("SELECT underlying_asset_type, COUNT(*) c FROM investments WHERE user_id=? AND sell_date IS NULL GROUP BY underlying_asset_type", (UID,)).fetchall():
    print(f"  {r['underlying_asset_type'] or '(未分类)':<10} {r['c']}")

print("\n=== TX ledger summary ===")
for r in cur.execute("SELECT event_type, COUNT(*) c, SUM(amount) amt FROM investment_transactions WHERE user_id=? GROUP BY event_type", (UID,)).fetchall():
    print(f"  {r['event_type']:<11} count={r['c']} sum_amount={r['amt'] or 0:.0f}")

print("\n=== NAV snapshots count ===")
print("  ", cur.execute("SELECT COUNT(*) FROM investment_nav_snapshots WHERE user_id=?", (UID,)).fetchone()[0])
conn.close()
