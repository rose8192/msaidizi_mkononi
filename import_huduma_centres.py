import sqlite3
import csv
import os

DB_PATH = os.path.join("data", "services.db")
CSV_PATH = os.path.join("data", "huduma_centres.csv")

print(f"DB: {os.path.abspath(DB_PATH)}")
print(f"CSV: {os.path.abspath(CSV_PATH)}")

if not os.path.exists(CSV_PATH):
    print("CSV NOT FOUND!")
    exit()

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Ensure table exists (with correct columns)
c.execute('''
CREATE TABLE IF NOT EXISTS huduma_centres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    county TEXT NOT NULL,
    location TEXT,
    services TEXT
)
''')

# Optional: clear old data
# c.execute("DELETE FROM huduma_centres")

imported = 0
skipped = 0
with open(CSV_PATH, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    print("CSV Headers:", reader.fieldnames)

    for row in reader:
        name = row.get('Centre Name', '').strip()
        county = row.get('County', '').strip()  # ← matches your CSV
        location = row.get('Location', '').strip()
        services = row.get('Opening Hours', '').strip()  # or rename column later if needed

        print(f"Row: name='{name}', county='{county}', loc='{location}', serv='{services}'")  # debug

        if name and county:
            c.execute(
                "INSERT OR IGNORE INTO huduma_centres (name, county, location, services) VALUES (?, ?, ?, ?)",
                (name, county, location, services)
            )
            imported += 1
        else:
            skipped += 1

conn.commit()
conn.close()

print(f"\nImport finished!")
print(f"Imported rows: {imported}")
print(f"Skipped rows: {skipped}")
print("\nNow check contents:")
print("python -c \"import sqlite3; conn=sqlite3.connect('data/services.db'); c=conn.cursor(); c.execute('SELECT * FROM huduma_centres LIMIT 5'); print(c.fetchall()); conn.close()\"")