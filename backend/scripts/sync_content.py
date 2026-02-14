import sqlite3
import os
import sys
import json
from datetime import datetime

# Path setup
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("SERVICES_DB", os.path.join(BACKEND_DIR, "data", "services.db"))

def sync_service_content(table_name, content_list):
    """
    Syncs content for a specific service table. 
    Adds new records, updates existing ones if content changed, 
    and handles versioning.
    """
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    sync_count = 0
    update_count = 0
    
    try:
        for item in content_list:
            topic = item.get('topic')
            info_sw = item.get('info_sw')
            info_en = item.get('info_en')
            link = item.get('link', '')
            
            # Check if record exists
            cur.execute(f"SELECT info_sw, info_en, link, version FROM {table_name} WHERE topic = ?", (topic,))
            row = cur.fetchone()
            
            if not row:
                # Insert new record
                cur.execute(
                    f"INSERT INTO {table_name} (topic, info_sw, info_en, link, version, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (topic, info_sw, info_en, link, "1.0", datetime.now().isoformat())
                )
                sync_count += 1
            else:
                # Check if content changed
                old_sw, old_en, old_link, old_version = row
                if old_sw != info_sw or old_en != info_en or old_link != link:
                    # Update existing record and increment version
                    try:
                        v_num = float(old_version) + 0.1
                        new_version = f"{v_num:.1f}"
                    except:
                        new_version = "1.1"
                        
                    cur.execute(
                        f"UPDATE {table_name} SET info_sw = ?, info_en = ?, link = ?, version = ?, updated_at = ? WHERE topic = ?",
                        (info_sw, info_en, link, new_version, datetime.now().isoformat(), topic)
                    )
                    update_count += 1
        
        conn.commit()
        print(f"Table '{table_name}': {sync_count} new, {update_count} updated.")
        return True
    except Exception as e:
        print(f"Error syncing table {table_name}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    # Example usage: can be extended to read from JSON files or API
    print("Starting content sync...")
    # This script can be called with arguments to sync specific content
    pass
