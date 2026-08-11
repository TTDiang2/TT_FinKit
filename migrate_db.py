import sqlite3

conn = sqlite3.connect('backend/finkit.db')
c = conn.cursor()

def get_columns(table):
    c.execute(f'PRAGMA table_info([{table}])')
    return {col[1] for col in c.fetchall()}

migrations = [
    ('categories', 'is_necessary', 'BOOLEAN DEFAULT 0'),
    ('categories', 'pl_section', "VARCHAR DEFAULT ''"),
    ('categories', 'cf_section', "VARCHAR DEFAULT ''"),
    ('accounts', 'account_type', "VARCHAR DEFAULT 'cash'"),
    ('investments', 'underlying_asset_type', "VARCHAR DEFAULT ''"),
]

for table, column, col_type in migrations:
    existing = get_columns(table)
    if column not in existing:
        c.execute(f'ALTER TABLE [{table}] ADD COLUMN [{column}] {col_type}')
        print(f'  Added {table}.{column}')
    else:
        print(f'  Skip {table}.{column} already exists')

conn.commit()
conn.close()
print('Done! All data preserved.')
