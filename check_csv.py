import csv
import os  # ← this was missing!

CSV_PATH = r"C:\Users\user\Desktop\msaidizi_mkononi\data\huduma_centres.csv"

print(f"Checking file: {CSV_PATH}")
print(f"File exists? {os.path.exists(CSV_PATH)}")

if os.path.exists(CSV_PATH):
    with open(CSV_PATH, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        print("Headers:", reader.fieldnames)
        try:
            first = next(reader)
            print("First row:", first)
        except StopIteration:
            print("CSV has headers but NO data rows")
else:
    print("File NOT found!")