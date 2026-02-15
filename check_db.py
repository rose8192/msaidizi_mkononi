import sqlite3
import os

db_path = 'analytics.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = c.fetchall()
    for table in tables:
        print(f"Table: {table[0]}")
        c.execute(f"PRAGMA table_info({table[0]})")
        columns = c.fetchall()
        for col in columns:
            print(f"  Column: {col[1]} ({col[2]})")
    conn.close()
else:
    print("Database not found")
