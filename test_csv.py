import csv

csv_path = "data/huduma_centres.csv"

try:
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        print("Headers:", reader.fieldnames)
        try:
            first_row = next(reader)
            print("First row:", first_row)
        except StopIteration:
            print("CSV has headers but NO data rows")
except FileNotFoundError:
    print(f"File not found: {csv_path}")
except Exception as e:
    print(f"Error: {e}")