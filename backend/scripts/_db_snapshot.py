"""Consistent SQLite snapshot via the online backup API (lock-free).

Usage: python _db_snapshot.py <src.db> <dst.db>
The running backend may hold locks on src; backup() copies around them.
"""
import sqlite3
import sys

src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(src)
d = sqlite3.connect(dst)
with d:
    s.backup(d)
d.close()
s.close()
