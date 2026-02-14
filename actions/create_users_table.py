import sqlite3
import os

DB_PATH = os.path.join("data", "services.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS users (
    phone VARCHAR(20) PRIMARY KEY,
    language VARCHAR(2) DEFAULT 'sw'
)
''')

conn.commit()
conn.close()

print("Users table created or already exists!")