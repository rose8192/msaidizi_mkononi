import sqlite3
import os

DB_PATH = os.path.join("data", "services.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS huduma_centres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    county TEXT NOT NULL,
    location TEXT,
    services TEXT
)
''')

conn.commit()
conn.close()
print("Table 'huduma_centres' is ready.")