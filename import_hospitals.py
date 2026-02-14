import sqlite3
import csv

DB_PATH = "data/services.db"
CSV_PATH = "clean_hospitals.csv"  # Your new file

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Drop old hospitals table
c.execute("DROP TABLE IF EXISTS hospitals")

# Create new table (matching new CSV columns, phone is not in CSV so default to empty)
c.execute('''CREATE TABLE hospitals (
             id INTEGER PRIMARY KEY,
             name TEXT,
             county TEXT,
             level TEXT,
             ownership TEXT,
             phone TEXT)''')  # Added ownership, phone empty

hospitals = []

with open(CSV_PATH, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = row.get('hospital_name') or "Unknown"
        county = row.get('county') or "Unknown"
        level = row.get('level') or "Unknown"
        ownership = row.get('ownership') or "Unknown"
        phone = ""  # No phone in new CSV, so empty
        hospitals.append((name.strip(), county.strip(), level.strip(), ownership.strip(), phone))

c.executemany("INSERT INTO hospitals (name, county, level, ownership, phone) VALUES (?, ?, ?, ?, ?)", hospitals)

conn.commit()
conn.close()
print(f"Successfully imported {len(hospitals)} hospitals!")