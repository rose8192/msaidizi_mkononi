
import sqlite3
import os

db_path = os.getenv("SERVICES_DB", "data/services.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

tables = ["huduma_info", "kra", "shif", "general_services", "hospitals", "huduma_centres"]

for table in tables:
    print(f"\nSchema for {table}:")
    cur.execute(f"PRAGMA table_info({table})")
    for col in cur.fetchall():
        print(col)

conn.close()
