import os
import sqlite3

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "data", "services.db")

def main():
    if not os.path.exists(DB_PATH):
        print("DB_NOT_FOUND", DB_PATH)
        return
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("TABLES", [t[0] for t in tables])
    for (t,) in tables:
        print("\nTABLE", t)
        schema = cur.execute(f"PRAGMA table_info({t})").fetchall()
        print("SCHEMA", schema)
        try:
            rows = cur.execute(f"SELECT * FROM {t} LIMIT 5").fetchall()
            print("ROWS", rows)
        except Exception as e:
            print("ERR", str(e))
    con.close()

if __name__ == "__main__":
    main()
