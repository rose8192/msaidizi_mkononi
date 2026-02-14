import sqlite3
import os
import sys

# Add backend to path to use shared constants if needed
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
DB_PATH = os.getenv("SERVICES_DB", os.path.join(BACKEND_DIR, "data", "services.db"))

def verify_database():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database file not found at {DB_PATH}")
        return False

    print(f"Verifying database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    errors = 0
    warnings = 0

    # Tables to check
    content_tables = ["huduma_info", "kra", "shif", "general_services", "hospitals", "huduma_centres"]
    
    for table in content_tables:
        print(f"\nChecking table: {table}")
        
        # Check if table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cur.fetchone():
            print(f"  [ERROR] Table '{table}' does not exist.")
            errors += 1
            continue

        # Check for required columns
        cur.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cur.fetchall()]
        
        required_cols = ["version", "updated_at"]
        for col in required_cols:
            if col not in columns:
                print(f"  [ERROR] Missing column '{col}' in table '{table}'")
                errors += 1

        # Check for empty content
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        if count == 0:
            print(f"  [WARNING] Table '{table}' is empty.")
            warnings += 1
        else:
            print(f"  [OK] Table '{table}' has {count} rows.")

        # Check for null values in critical columns
        try:
            if table in ["huduma_info", "kra", "shif", "general_services"]:
                # Check which columns exist
                cur.execute(f"PRAGMA table_info({table})")
                cols = [col[1] for col in cur.fetchall()]
                
                info_en_col = "info_en" if "info_en" in cols else "steps_en" if "steps_en" in cols else None
                info_sw_col = "info_sw" if "info_sw" in cols else "steps_sw" if "steps_sw" in cols else None
                
                if info_en_col and info_sw_col:
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {info_en_col} IS NULL OR {info_sw_col} IS NULL")
                    null_count = cur.fetchone()[0]
                    if null_count > 0:
                        print(f"  [WARNING] Table '{table}' has {null_count} rows with NULL info fields.")
                        warnings += 1
                else:
                    print(f"  [ERROR] Table '{table}' missing info/steps columns.")
                    errors += 1
        except Exception as e:
            print(f"  [ERROR] Failed to check nulls in {table}: {e}")
            errors += 1

    # Analytics tables check
    analytics_tables = ["users", "messages", "conversations", "intent_analytics", "service_usage"]
    print("\nChecking Analytics Tables:")
    for table in analytics_tables:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cur.fetchone():
            print(f"  [WARNING] Analytics table '{table}' does not exist yet (normal if no chats occurred).")
            warnings += 1
        else:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  [OK] Analytics table '{table}' has {count} rows.")

    conn.close()
    
    print("\n" + "="*30)
    print(f"Verification complete: {errors} Errors, {warnings} Warnings.")
    print("="*30)
    
    return errors == 0

if __name__ == "__main__":
    success = verify_database()
    if not success:
        sys.exit(1)
    sys.exit(0)
