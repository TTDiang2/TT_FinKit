import sqlite3
conn = sqlite3.connect('backend/finkit.db')
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print('=== Tables ===')
for t in tables:
    name = t[0]
    c.execute(f'SELECT COUNT(*) FROM [{name}]')
    count = c.fetchone()[0]
    print(f'  {name}: {count} rows')

for tbl in ['users', 'accounts', 'categories', 'transactions', 'investments', 'assets']:
    try:
        c.execute(f'PRAGMA table_info([{tbl}])')
        cols = c.fetchall()
        print(f'\n=== {tbl} columns ===')
        for col in cols:
            print(f'  {col[1]} ({col[2]})')
    except Exception as e:
        print(f'\n=== {tbl}: {e}')

conn.close()
