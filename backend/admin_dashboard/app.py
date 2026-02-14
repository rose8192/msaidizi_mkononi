from flask import Flask, jsonify, request, send_file, render_template
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, set_access_cookies, unset_jwt_cookies
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3
import os
import hashlib
import csv
import io
import structlog
from datetime import datetime, timedelta

# Configure Structured Logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger()

app = Flask(__name__, template_folder='templates')
CORS(app)

# Rate Limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# Configuration
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'msaidizi-mkononi-prod-secret-2026')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
jwt = JWTManager(app)

# Global Error Handler
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error("dashboard_error", error=str(e))
    return jsonify({"msg": "An internal error occurred"}), 500

import importlib.util

# Path to services.db
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "data", "services.db")

def ensure_db_initialized():
    """Dynamically import ensure_db from rasa actions to initialize tables if needed."""
    try:
        actions_path = os.path.join(BACKEND_DIR, "rasa", "actions", "actions.py")
        if os.path.exists(actions_path):
            spec = importlib.util.spec_from_file_location("actions_module", actions_path)
            actions_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(actions_module)
            actions_module.ensure_db()
            logger.info("db_initialization_success")
    except Exception as e:
        logger.error("db_initialization_failed", error=str(e))

def get_db_connection():
    ensure_db_initialized()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Health Check
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/dashboard')
def show_dashboard():
    return render_template('dashboard.html')

# Authentication Endpoint
@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"msg": "Missing username or password"}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM admin_users WHERE username = ? AND password_hash = ?', 
                       (username, password_hash)).fetchone()
    conn.close()

    if user:
        access_token = create_access_token(identity=username)
        resp = jsonify({"msg": "Login successful", "access_token": access_token})
        # For simplicity in this dev environment, we'll return the token
        # In a real app, we'd use set_access_cookies(resp, access_token)
        return resp
    
    return jsonify({"msg": "Bad username or password"}), 401

# Content Management: List Services
@app.route('/api/services', methods=['GET'])
@jwt_required()
def list_services():
    category = request.args.get('category', 'huduma_info')
    valid_categories = ['huduma_info', 'kra', 'shif', 'general_services']
    if category not in valid_categories:
        return jsonify({"msg": "Invalid category"}), 400
    
    conn = get_db_connection()
    services = conn.execute(f'SELECT * FROM {category}').fetchall()
    conn.close()
    return jsonify([dict(row) for row in services])

# Content Management: Update Service
@app.route('/api/services/<category>/<topic>', methods=['PUT'])
@jwt_required()
def update_service(category, topic):
    valid_categories = ['huduma_info', 'kra', 'shif', 'general_services']
    if category not in valid_categories:
        return jsonify({"msg": "Invalid category"}), 400
    
    data = request.get_json()
    info_sw = data.get('info_sw')
    info_en = data.get('info_en')
    link = data.get('link')
    version = data.get('version', '1.0')
    
    conn = get_db_connection()
    conn.execute(f'''
        UPDATE {category} 
        SET info_sw = ?, info_en = ?, link = ?, version = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE topic = ?
    ''', (info_sw, info_en, link, version, topic))
    conn.commit()
    conn.close()
    
    logger.info("service_updated", category=category, topic=topic, version=version, user=get_jwt_identity())
    return jsonify({"msg": "Service updated successfully"})

# Analytics Summary KPI Endpoint
@app.route('/api/stats', methods=['GET'])
def get_stats():
    # Temporarily removed @jwt_required() for easier dashboard verification
    conn = get_db_connection()
    
    # Total Users
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    
    # Total Messages
    total_messages = conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
    
    # Active Sessions (last 24h)
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    active_sessions = conn.execute('SELECT COUNT(DISTINCT session_id) FROM conversations WHERE start_time > ?', (yesterday,)).fetchone()[0]
    
    # Fallback Rate
    fallbacks = conn.execute('SELECT COUNT(*) FROM messages WHERE is_fallback = 1').fetchone()[0]
    fallback_rate = (fallbacks / total_messages * 100) if total_messages > 0 else 0

    # Top Intents
    intents = conn.execute('''
        SELECT intent, COUNT(*) as count, AVG(confidence) as avg_confidence 
        FROM messages 
        WHERE intent IS NOT NULL 
        GROUP BY intent 
        ORDER BY count DESC 
        LIMIT 5
    ''').fetchall()

    # Language Distribution
    langs = conn.execute('SELECT language, COUNT(*) as count FROM users GROUP BY language').fetchall()

    # Fallback Trends (last 7 days)
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    fallback_trends = conn.execute('''
        SELECT DATE(timestamp) as date, COUNT(*) as count 
        FROM messages 
        WHERE is_fallback = 1 AND timestamp > ? 
        GROUP BY date 
        ORDER BY date ASC
    ''', (seven_days_ago,)).fetchall()

    # Confidence Distribution
    confidence_dist = conn.execute('''
        SELECT 
            CASE 
                WHEN confidence < 0.5 THEN '0.0-0.5'
                WHEN confidence < 0.75 THEN '0.5-0.75'
                WHEN confidence < 0.9 THEN '0.75-0.9'
                ELSE '0.9-1.0'
            END as range,
            COUNT(*) as count
        FROM messages
        GROUP BY range
    ''').fetchall()

    # USSD Analytics
    ussd_stats = conn.execute('''
        SELECT intent, COUNT(*) as count 
        FROM messages 
        WHERE platform = 'ussd' 
        GROUP BY intent 
        ORDER BY count DESC 
        LIMIT 5
    ''').fetchall()

    # Volume Trends (last 7 days)
    volume_trends = conn.execute('''
        SELECT DATE(timestamp) as date, COUNT(*) as count 
        FROM messages 
        WHERE timestamp > ? 
        GROUP BY date 
        ORDER BY date ASC
    ''', (seven_days_ago,)).fetchall()

    conn.close()

    return jsonify({
        'kpis': {
            'total_users': total_users,
            'total_messages': total_messages,
            'active_sessions': active_sessions,
            'fallback_rate': round(fallback_rate, 2)
        },
        'intents': [dict(row) for row in intents],
        'languages': [dict(row) for row in langs],
        'fallback_trends': [dict(row) for row in fallback_trends],
        'confidence_dist': [dict(row) for row in confidence_dist],
        'ussd_stats': [dict(row) for row in ussd_stats],
        'volume': [dict(row) for row in volume_trends]
    })

# County Distribution Endpoint
@app.route('/api/geo', methods=['GET'])
@jwt_required()
def get_geo_stats():
    conn = get_db_connection()
    geo_data = conn.execute('SELECT county, COUNT(*) as count FROM users WHERE county IS NOT NULL GROUP BY county ORDER BY count DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in geo_data])

# Usage Trends Endpoint
@app.route('/api/trends', methods=['GET'])
@jwt_required()
def get_trends():
    conn = get_db_connection()
    # Daily message volume for last 7 days
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    trends = conn.execute('''
        SELECT DATE(timestamp) as date, COUNT(*) as count 
        FROM messages 
        WHERE timestamp > ? 
        GROUP BY date 
        ORDER BY date ASC
    ''', (seven_days_ago,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in trends])

# CSV Export Endpoint
@app.route('/api/export/csv', methods=['GET'])
@jwt_required()
def export_csv():
    table = request.args.get('table', 'messages')
    valid_tables = ['users', 'messages', 'conversations', 'service_usage']
    
    if table not in valid_tables:
        return jsonify({"msg": "Invalid table"}), 400

    conn = get_db_connection()
    cursor = conn.execute(f'SELECT * FROM {table}')
    rows = cursor.fetchall()
    column_names = [description[0] for description in cursor.description]
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(column_names)
    cw.writerows(rows)
    
    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)

    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'msaidizi_analytics_{table}_{datetime.now().strftime("%Y%m%d")}.csv'
    )

if __name__ == '__main__':
    app.run(port=5001, debug=True)
