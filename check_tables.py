# check_tables.py
import sqlite3

conn = sqlite3.connect(r'C:\Users\user\Desktop\msaidizi_mkononi\data\services.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [row[0] for row in c.fetchall()])
conn.close()
