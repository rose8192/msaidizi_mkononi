import africastalking
import sqlite3
import os
import requests
import re
import json
import time
import hashlib
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

logger.info("Starting Msaidizi Mkononi Backend...")

app = Flask(__name__)
CORS(app)

# Configuration
RASA_INTERNAL_URL = "http://127.0.0.1:5005/webhooks/rest/webhook"
RASA_URL = os.environ.get("RASA_URL", RASA_INTERNAL_URL)
RASA_PARSE_URL = "http://127.0.0.1:5005/model/parse"
DB_PATH = os.path.join(os.getcwd(), 'analytics.db')

# JWT Configuration
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'msaidizi-mkononi-secret-2026')
jwt = JWTManager(app)

def init_db():
    """Initializes the analytics database with all required tables."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # 1. Interactions/Messages table
        c.execute('''CREATE TABLE IF NOT EXISTS interactions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sender TEXT,
                      message TEXT,
                      response TEXT,
                      intent TEXT,
                      confidence REAL,
                      is_fallback BOOLEAN,
                      platform TEXT DEFAULT 'app',
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        
        # 2. Users table (Anonymized)
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id TEXT PRIMARY KEY,
                      language TEXT,
                      platform TEXT,
                      county TEXT,
                      last_seen DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # 3. Admin Users table
        c.execute('''CREATE TABLE IF NOT EXISTS admin_users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT UNIQUE,
                      password_hash TEXT,
                      role TEXT DEFAULT 'admin')''')

        # Create default admin if not exists (admin/admin123)
        admin_pass = "admin123"
        pass_hash = hashlib.sha256(admin_pass.encode()).hexdigest()
        c.execute("INSERT OR IGNORE INTO admin_users (username, password_hash) VALUES (?, ?)", 
                  ('admin', pass_hash))

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully with all tables")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

# Initialize DB on startup
init_db()

# Global Error Handler
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled Exception: {str(e)}", exc_info=True)
    return jsonify({
        "error": "Internal Server Error",
        "message": "An unexpected error occurred on the server.",
        "details": str(e) if app.debug else "Please contact support."
    }), 500

# Health Check
@app.route('/', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "msaidizi-mkononi-backend",
        "timestamp": time.time(),
        "database": os.path.exists(DB_PATH)
    }), 200

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/test-rasa', methods=['GET'])
def test_rasa():
    try:
        # Check if Rasa is responding at all
        base_url = RASA_URL.replace('/webhooks/rest/webhook', '')
        r = requests.get(base_url, timeout=5)
        return jsonify({
            "rasa_status": "online",
            "status_code": r.status_code,
            "url": RASA_URL
        })
    except Exception as e:
        return jsonify({
            "rasa_status": "offline",
            "error": str(e),
            "url": RASA_URL
        }), 503

@app.route('/chat', methods=['POST'])
def rasa_proxy():
    """
    Proxies requests from Flutter/Frontend to Rasa.
    Ensures correct JSON format: {"sender": "user", "message": "hello"}
    Forwarded to Rasa internal endpoint: /webhooks/rest/webhook
    """
    payload = request.json
    if not payload:
        return jsonify([{"text": "Error: No message received."}]), 400
        
    sender = str(payload.get('sender', 'unknown'))
    message = str(payload.get('message', ''))
    
    # Correct JSON format for Rasa REST API
    rasa_payload = {
        "sender": sender,
        "message": message
    }
    
    logger.info(f"Forwarding to Rasa: {sender} -> {message[:50]}...")
    
    try:
        # Internal container communication on port 5005
        # Correct endpoint is ALWAYS /webhooks/rest/webhook for REST input
        r = requests.post(
            RASA_INTERNAL_URL,
            json=rasa_payload,
            timeout=45 # Increased timeout for slow model cold starts
        )
        
        if r.status_code != 200:
            logger.error(f"Rasa error {r.status_code}: {r.text}")
            return jsonify([{"text": "AI service returned an error. Please try again."}]), 502

        logger.info(f"Rasa raw response: {r.text}")
        responses = r.json()
        
        # Handle empty responses (fallback)
        if not responses:
            logger.warning("Rasa returned empty response list. Triggering fallback.")
            responses = [{"text": "I'm not sure I understood that correctly. Could you rephrase?"}]

        # Log to analytics
        try:
            intent_data = rasa_parse_detailed(message)
            log_interaction(sender, message, responses, intent_data)
        except Exception as log_err:
            logger.error(f"Analytics logging failed: {log_err}")
            
        return jsonify(responses)

    except requests.exceptions.ConnectionError:
        logger.error(f"Could not connect to Rasa server at {RASA_INTERNAL_URL}")
        # Return 200 so the user sees the message in the chat UI
        return jsonify([{"text": "System is initializing (warming up)... please try again in 10 seconds."}]), 200
    except Exception as e:
        logger.error(f"Proxy unexpected error: {e}")
        return jsonify([{"text": "Communication failure. Please try again later."}]), 500

@app.route('/hospitals/search', methods=['GET'])
def hospitals_search():
    county = request.args.get('county')
    level = request.args.get('level')
    # Logic to be implemented or imported
    return jsonify({"results": []})

@app.route('/huduma/locate', methods=['GET'])
def huduma_locate():
    county = request.args.get('county')
    # Logic to be implemented or imported
    return jsonify({"results": []})

def rasa_parse_detailed(text):
    try:
        r = requests.post(RASA_PARSE_URL, json={"text": text}, timeout=5)
        if r.status_code == 200:
            return r.json().get("intent", {"name": None, "confidence": 0.0})
    except:
        pass
    return {"name": None, "confidence": 0.0}

def log_interaction(sender, message, responses, intent_data=None):
    try:
        full_resp = " | ".join([r.get('text', '') for r in responses if isinstance(r, dict)])
        intent_name = intent_data.get("name") if intent_data else None
        confidence = intent_data.get("confidence", 0.0) if intent_data else 0.0
        is_fallback = intent_name == "nlu_fallback" or confidence < 0.6
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO interactions 
                     (sender, message, response, intent, confidence, is_fallback) 
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (sender, message, full_resp, intent_name, confidence, is_fallback))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Logging failed: {e}")

# Admin Endpoints
@app.route('/api/login', methods=['POST'])
def admin_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"msg": "Missing username or password"}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        user = c.execute('SELECT * FROM admin_users WHERE username = ? AND password_hash = ?', 
                         (username, password_hash)).fetchone()
        conn.close()

        if user:
            access_token = create_access_token(identity=username)
            return jsonify({"msg": "Login successful", "access_token": access_token}), 200
    except Exception as e:
        logger.error(f"Login error: {e}")
        
    return jsonify({"msg": "Invalid credentials"}), 401

@app.route('/api/stats', methods=['GET'])
@jwt_required()
def get_stats():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Total Users
        c.execute("SELECT COUNT(DISTINCT sender) FROM interactions")
        total_users = c.fetchone()[0]
        
        # Total Messages
        c.execute("SELECT COUNT(*) FROM interactions")
        total_msgs = c.fetchone()[0]
        
        # Fallback Rate
        c.execute("SELECT COUNT(*) FROM interactions WHERE is_fallback = 1")
        fallbacks = c.fetchone()[0]
        fallback_rate = (fallbacks / total_msgs * 100) if total_msgs > 0 else 0

        # Top Intents
        c.execute("SELECT intent, COUNT(*) as count FROM interactions WHERE intent IS NOT NULL GROUP BY intent ORDER BY count DESC LIMIT 5")
        intents = [{"intent": row[0], "count": row[1]} for row in c.fetchall()]

        conn.close()
        
        return jsonify({
            'kpis': {
                'total_users': total_users,
                'total_messages': total_msgs,
                'active_sessions': total_users,
                'fallback_rate': round(fallback_rate, 2)
            },
            'intents': intents,
            'languages': [{'language': 'en', 'count': total_msgs}], # Simplified
            'fallback_trends': [], 
            'confidence_dist': [], 
            'ussd_stats': [], 
            'volume': []
        })
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/geo', methods=['GET'])
@jwt_required()
def get_geo_stats():
    return jsonify([])

@app.route('/api/trends', methods=['GET'])
@jwt_required()
def get_trends():
    return jsonify([])

@app.route('/api/export/csv', methods=['GET'])
@jwt_required()
def export_csv():
    import io
    import csv
    from flask import send_file
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute('SELECT * FROM interactions')
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
            download_name=f'msaidizi_analytics_{time.strftime("%Y%m%d")}.csv'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/analytics/data', methods=['GET'])
def get_raw_analytics():
    # Simple security for raw data
    auth = request.authorization
    if not auth or not (auth.username == 'admin' and auth.password == 'admin123'):
        # Fallback to check if it's our internal dashboard
        pass 

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM interactions ORDER BY timestamp DESC LIMIT 50")
        data = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(data)
    except Exception as e:
        return jsonify([])

# Africa's Talking USSD
@app.route('/ussd', methods=['POST'])
def ussd():
    session_id = request.values.get('sessionId')
    phone_number = request.values.get('phoneNumber')
    text = request.values.get('text', '').strip()
    
    levels = text.split('*') if text else []
    latest_input = levels[-1] if levels else "hi"
    
    # Simple USSD logic - forward to Rasa
    try:
        payload = {"sender": phone_number, "message": latest_input}
        r = requests.post(RASA_URL, json=payload, timeout=15)
        responses = r.json()
        rasa_text = "\n".join([resp.get("text", "") for resp in responses])
        
        if "Asante" in rasa_text or "Goodbye" in rasa_text:
            return f"END {rasa_text}"
        return f"CON {rasa_text}"
    except:
        return "END Service unavailable. Please try again."

# Smart Intent Guard Logic
SERVICE_INTENTS = ["kra_info", "shif_info", "huduma_info", "ntsa_info", "police_clearance_info", "business_reg_info", "helb_info"]

def smart_intent_guard(message):
    if len(message.strip()) < 2:
        return False, "Please provide more details."
    
    # Optional: Pre-parse with Rasa to check intent confidence
    try:
        # We use a short timeout and ignore errors to avoid blocking the main chat
        r = requests.post(RASA_PARSE_URL, json={"text": message}, timeout=2)
        if r.status_code == 200:
            data = r.json()
            intent = data.get("intent", {}).get("name")
            confidence = data.get("intent", {}).get("confidence", 0)
            if intent in SERVICE_INTENTS and confidence < 0.4: # Lowered threshold
                return True, None # Let Rasa handle it if unsure
    except Exception as e:
        logger.debug(f"Guard parse skipped: {e}")
        
    return True, None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
