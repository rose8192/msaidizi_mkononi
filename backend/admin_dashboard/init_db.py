import sqlite3
import os
import hashlib

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "services.db")

def init_analytics_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Users table (Anonymized)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        language TEXT,
        platform TEXT,
        county TEXT,
        last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Conversations table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        session_id TEXT PRIMARY KEY,
        user_id TEXT,
        start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        end_time DATETIME,
        platform TEXT,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)

    # 3. Messages table (Middleware-level logging)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        user_id TEXT,
        message_text TEXT,
        intent TEXT,
        confidence REAL,
        is_fallback BOOLEAN,
        language TEXT,
        platform TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES conversations(session_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)

    # 4. Service Usage table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS service_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_name TEXT,
        county TEXT,
        platform TEXT,
        user_id TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)

    # 5. Intent Analytics table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS intent_analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        intent_name TEXT UNIQUE,
        usage_count INTEGER DEFAULT 0,
        avg_confidence REAL DEFAULT 0.0,
        last_used DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 6. USSD Analytics table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ussd_analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        menu_traversed TEXT,
        exit_point TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES conversations(session_id)
    )
    """)

    # 7. Admin Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT DEFAULT 'admin'
    )
    """)

    # Create a default admin if not exists (admin/admin123)
    # In production, this should be handled more securely
    admin_user = "admin"
    admin_pass = "admin123"
    pass_hash = hashlib.sha256(admin_pass.encode()).hexdigest()
    
    cur.execute("INSERT OR IGNORE INTO admin_users (username, password_hash) VALUES (?, ?)", (admin_user, pass_hash))

    conn.commit()
    conn.close()
    print("Analytics database initialized successfully.")

if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
    init_analytics_db()
