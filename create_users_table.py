import sqlite3
import os

# Use the SAME path as your app.py
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "services.db")

print(f"Creating 'users' table in: {os.path.abspath(DB_PATH)}")

try:
    if not os.path.exists(DB_PATH):
        print("Database file does NOT exist yet — it will be created.")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        phone VARCHAR(20) PRIMARY KEY,
        language VARCHAR(2) DEFAULT 'sw'
    )
    ''')

    # Optional: insert a test row to confirm
    c.execute("INSERT OR IGNORE INTO users (phone, language) VALUES (?, ?)", ("testphone", "sw"))

    conn.commit()
    conn.close()

    print("SUCCESS: 'users' table is ready.")
    print("Test query:")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users LIMIT 5")
    print(c.fetchall())
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")