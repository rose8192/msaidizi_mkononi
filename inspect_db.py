import sqlite3
import os

db_paths = [
    r"c:\Users\user\Desktop\msaidizi_mkononi\backend\data\services.db",
    r"c:\Users\user\Desktop\msaidizi_mkononi\backend\data\db.sqlite"
]

def inspect():
    for db_path in db_paths:
        print(f"\n--- Inspecting {db_path} ---")
        if not os.path.exists(db_path):
            print(f"Error: {db_path} not found")
            continue
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            print(f"\nTable: {table_name}")
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            for col in columns:
                print(f"  {col[1]} ({col[2]})")
                
        conn.close()

if __name__ == "__main__":
    inspect()
