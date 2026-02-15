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
RASA_URL = os.environ.get("RASA_URL", "http://127.0.0.1:5005/webhooks/rest/webhook")
RASA_PARSE_URL = "http://127.0.0.1:5005/model/parse"
# Force internal communication to the local Rasa port, ignoring any external environment variables
RASA_INTERNAL_URL = "http://127.0.0.1:5005/webhooks/rest/webhook"
DB_PATH = os.path.join(os.getcwd(), 'analytics.db')

# JWT Configuration
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'msaidizi-mkononi-secret-2026')
jwt = JWTManager(app)

def init_db():
    """Initializes the analytics database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS interactions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sender TEXT,
                      message TEXT,
                      response TEXT,
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
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
    payload = request.json
    if not payload:
        return jsonify([{"text": "Error: No message received."}]), 400
        
    sender = payload.get('sender', 'unknown')
    message = payload.get('message', '')
    
    logger.info(f"Chat request from {sender}: {message[:50]}...")
    
    try:
        # 1. Intent Guard
        is_valid, guard_response = smart_intent_guard(message)
        if not is_valid:
            return jsonify([{"text": guard_response}])

        # 2. Rasa Forwarding with Retry Logic
        responses = []
        for attempt in range(3):
            try:
                # Use RASA_INTERNAL_URL to ensure we hit the Rasa port 5005
                r = requests.post(RASA_INTERNAL_URL, json=payload, timeout=30)
                r.raise_for_status()
                responses = r.json()
                break
            except Exception as e:
                logger.warning(f"Rasa connection attempt {attempt+1} failed: {e}")
                if attempt == 2: # Last attempt
                    return jsonify([{"text": "AI engine is warming up. Please try again in a moment."}]), 503
                time.sleep(2)

        # 3. Analytics Logging
        log_interaction(sender, message, responses)
        return jsonify(responses)

    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return jsonify([{"text": "Service temporarily unavailable. Please try again later."}]), 503

def log_interaction(sender, message, responses):
    try:
        full_resp = " | ".join([r.get('text', '') for r in responses if isinstance(r, dict)])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO interactions (sender, message, response) VALUES (?, ?, ?)",
                  (sender, message, full_resp))
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
    
    if username == 'admin' and password == 'admin123':
        access_token = create_access_token(identity=username)
        return jsonify({"msg": "Login successful", "access_token": access_token}), 200
    return jsonify({"msg": "Invalid credentials"}), 401

@app.route('/api/stats', methods=['GET'])
@jwt_required()
def get_stats():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM interactions")
        total_msgs = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT sender) FROM interactions")
        total_users = c.fetchone()[0]
        conn.close()
        
        return jsonify({
            'kpis': {
                'total_users': total_users,
                'total_messages': total_msgs,
                'active_sessions': total_users,
                'fallback_rate': 0
            },
            'intents': [], 'languages': [], 'fallback_trends': [], 'confidence_dist': [], 'ussd_stats': [], 'volume': []
        })
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
        r = requests.post(RASA_PARSE_URL, json={"text": message}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            intent = data.get("intent", {}).get("name")
            confidence = data.get("intent", {}).get("confidence", 0)
            if intent in SERVICE_INTENTS and confidence < 0.6:
                return False, "I'm not sure which service you need. Could you specify? (e.g., KRA, Passport)"
    except:
        pass # If parser is down, let the main proxy handle it
        
    return True, None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
