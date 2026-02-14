# dashboard.py - run with: python dashboard.py
from flask import Flask, render_template_string
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)

DB_PATH = "data/services.db"  # same as Rasa

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def dashboard():
    conn = get_db_connection()

    # Create analytics table if not exists (you can run this once)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            service TEXT,
            county TEXT,
            user_id TEXT,
            message TEXT
        )
    ''')
    conn.commit()

    # Most asked services
    most_services = pd.read_sql_query("""
        SELECT service, COUNT(*) as count 
        FROM usage_log 
        GROUP BY service 
        ORDER BY count DESC 
        LIMIT 10
    """, conn)

    # Popular counties
    popular_counties = pd.read_sql_query("""
        SELECT county, COUNT(*) as count 
        FROM usage_log 
        WHERE county IS NOT NULL 
        GROUP BY county 
        ORDER BY count DESC 
        LIMIT 10
    """, conn)

    # Usage over time (last 30 days)
    usage_time = pd.read_sql_query("""
        SELECT DATE(timestamp) as date, COUNT(*) as messages 
        FROM usage_log 
        WHERE timestamp >= DATE('now', '-30 days')
        GROUP BY DATE(timestamp)
        ORDER BY date
    """, conn)

    conn.close()

    html = f"""
    <html>
    <head>
        <title>Msaidizi Mkononi Analytics Dashboard</title>
        <style>
            body {{ font-family: Arial; margin: 40px; }}
            h1 {{ color: #2c3e50; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 40px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .chart {{ height: 300px; background: #f9f9f9; margin-bottom: 40px; }}
        </style>
    </head>
    <body>
        <h1>Msaidizi Mkononi – Admin Analytics Dashboard</h1>
        <p>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <h2>Most Asked Services</h2>
        {most_services.to_html(index=False)}

        <h2>Popular Counties</h2>
        {popular_counties.to_html(index=False)}

        <h2>Usage Over Last 30 Days</h2>
        <div class="chart">
            <!-- Simple text representation – you can replace with Chart.js later -->
            <pre>{usage_time.to_string(index=False)}</pre>
        </div>

        <p><small>Note: Logging must be enabled in actions.py to collect data.</small></p>
    </body>
    </html>
    """

    return render_template_string(html)

if __name__ == '__main__':
    app.run(debug=True, port=8080)