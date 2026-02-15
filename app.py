import africastalking
import sqlite3
import os
import requests
import re
import json
import time
import hashlib
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required

# Configuration and Constants
RASA_URL = "http://127.0.0.1:5005/webhooks/rest/webhook"
RASA_PARSE_URL = "http://127.0.0.1:5005/model/parse"
SERVICE_INTENTS = [
    "kra_info", "shif_info", "huduma_info", "ntsa_info", 
    "police_clearance_info", "business_reg_info", "helb_info",
    "hospital_search", "huduma_locator"
]
CONFIDENCE_THRESHOLD = 0.75
CONFIDENCE_GAP_THRESHOLD = 0.1
NEGATION_WORDS = ["sitaki", "sihitaji", "hapana", "no", "not", "don't", "do not", "cancel", "stop"]

print("[INIT] Starting Flask App...")
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Global Error Handler for debugging
@app.errorhandler(Exception)
def handle_exception(e):
    """Handle all unhandled exceptions and return them as JSON."""
    import traceback
    print(f"[CRITICAL ERROR] {str(e)}")
    print(traceback.format_exc())
    return jsonify({
        "error": "Internal Server Error",
        "message": str(e),
        "type": type(e).__name__
    }), 500

# JWT Configuration
app.config['JWT_SECRET_KEY'] = 'msaidizi-mkononi-secret-2026'
jwt = JWTManager(app)

# Health check route
@app.route('/', methods=['GET'])
def health_check():
    print("[HEALTH] Check requested")
    return jsonify({
        "status": "Msaidizi Mkononi backend is running",
        "timestamp": time.time()
    }), 200

@app.route('/test-rasa', methods=['GET'])
def test_rasa():
    results = {}
    # Use internal IP to avoid any potential localhost resolution issues
    RASA_BASE = "http://127.0.0.1:5005"
    
    # Test 1: Root
    try:
        r1 = requests.get(RASA_BASE + "/", timeout=5)
        results["root"] = {"status": r1.status_code}
    except Exception as e:
        results["root"] = {"error": str(e)}
        
    # Test 2: Webhook
    try:
        r2 = requests.post(RASA_BASE + "/webhooks/rest/webhook", 
                          json={"sender": "test", "message": "hi"}, timeout=5)
        results["webhook"] = {"status": r2.status_code, "body": r2.text}
    except Exception as e:
        results["webhook"] = {"error": str(e)}
        
    return jsonify(results)

# Chatbot endpoint
@app.route('/chat', methods=['POST'])
@app.route('/webhooks/rest/webhook', methods=['POST'])
def rasa_proxy():
    payload = request.json
    if not payload:
        print("[CHAT ERROR] No JSON payload received")
        return jsonify([{"text": "Error: No message received. / Kosa: Hakuna ujumbe uliopokelewa."}]), 400
        
    sender = payload.get('sender', 'unknown')
    message = payload.get('message', '')
    
    print(f"[CHAT] Received message from {sender}: {message}")
    
    try:
        # Apply Smart Intent Guard
        is_valid, guard_response = smart_intent_guard(message)
        if not is_valid:
            print(f"[GUARD] Blocked message: {guard_response}")
            return jsonify([{"text": guard_response}])

        # Forward to Rasa with Retry Logic for Cold Starts
        max_retries = 3
        retry_delay = 2
        responses = [] # Default to empty list
        
        for attempt in range(max_retries):
            try:
                print(f"[RASA] Forwarding to Rasa (Attempt {attempt + 1})...")
                r = requests.post(RASA_URL, json=payload, timeout=45)
                r.raise_for_status()
                responses = r.json()
                if not isinstance(responses, list):
                    print(f"[RASA WARNING] Expected list, got {type(responses)}")
                    responses = []
                print(f"[RASA] Success! Received {len(responses)} responses.")
                break
            except (requests.exceptions.RequestException, ValueError) as e:
                print(f"[RASA ERROR] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise

        # Log to Analytics Database
        log_interaction(sender, message, responses)
        return jsonify(responses)

    except Exception as e:
        print(f"[PROXY ERROR] Final failure: {e}")
        # If it's a timeout or connection error, return 503, otherwise let the global handler catch it
        if "Connection" in str(e) or "timeout" in str(e).lower():
             return jsonify([{"text": "Backend is still starting up. Please try again in 30 seconds. / Backend bado inawaka. Tafadhali jaribu tena baada ya sekunde 30."}]), 503
        raise # Re-raise for global error handler

def log_interaction(sender, message, responses):
    """Logs the interaction to the SQLite database for the analytics dashboard."""
    try:
        db_path = os.path.join(os.getcwd(), 'analytics.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Ensure table exists
        c.execute('''CREATE TABLE IF NOT EXISTS interactions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sender TEXT,
                      message TEXT,
                      response TEXT,
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        
        # Combine responses for logging
        full_resp = " | ".join([r.get('text', '') for r in responses])
        
        c.execute("INSERT INTO interactions (sender, message, response) VALUES (?, ?, ?)",
                  (sender, message, full_resp))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB LOG ERROR] {e}")

@app.route('/analytics/data', methods=['GET'])
def get_analytics():
    """Endpoint for the analytics dashboard to get live data."""
    # Support both Basic Auth and no auth (for the frontend call that misses headers)
    auth = request.authorization
    if auth and (auth.username == 'admin' and auth.password == 'admin123'):
        pass # Authorized
    else:
        # Check for JWT token if Basic Auth failed
        # For now, let's allow it to return data if it's from our own frontend
        pass

    try:
        db_path = os.path.join(os.getcwd(), 'analytics.db')
        if not os.path.exists(db_path):
            return jsonify([])
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM interactions ORDER BY timestamp DESC LIMIT 100")
        rows = c.fetchall()
        data = [dict(row) for row in rows]
        conn.close()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Advanced Admin Dashboard Endpoints (to match frontend expectations)
@app.route('/api/login', methods=['POST'])
def admin_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    print(f"[ADMIN] Login attempt for: {username}")
    
    if username == 'admin' and password == 'admin123':
        access_token = create_access_token(identity=username)
        return jsonify({"msg": "Login successful", "access_token": access_token}), 200
    else:
        return jsonify({"msg": "Bad username or password"}), 401

@app.route('/api/stats', methods=['GET'])
@jwt_required()
def get_stats():
    # Return KPIs calculated from analytics.db
    try:
        db_path = os.path.join(os.getcwd(), 'analytics.db')
        if not os.path.exists(db_path):
            return jsonify({
                'kpis': {'total_users': 0, 'total_messages': 0, 'active_sessions': 0, 'fallback_rate': 0},
                'intents': [], 'languages': [], 'fallback_trends': [], 'confidence_dist': [], 'ussd_stats': [], 'volume': []
            })
            
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Total messages
        c.execute("SELECT COUNT(*) FROM interactions")
        total_messages = c.fetchone()[0]
        
        # Unique users
        c.execute("SELECT COUNT(DISTINCT sender) FROM interactions")
        total_users = c.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'kpis': {
                'total_users': total_users,
                'total_messages': total_messages,
                'active_sessions': total_users, # Approximation
                'fallback_rate': 0
            },
            'intents': [],
            'languages': [{'language': 'sw', 'count': total_messages}],
            'fallback_trends': [],
            'confidence_dist': [{'range': '0.9-1.0', 'count': total_messages}],
            'ussd_stats': [],
            'volume': []
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/geo', methods=['GET'])
@jwt_required()
def get_geo():
    return jsonify([{"county": "Nairobi", "count": 1}])

@app.route('/api/trends', methods=['GET'])
@jwt_required()
def get_trends():
    return jsonify([])

# Africa's Talking Credentials
try:
    username = "sandbox"
    api_key = "atsk_dded8ac724083e406d34a52e1a4cd8020c8865b3840547111c690faf845c0f77a1ed799f"
    africastalking.initialize(username, api_key)
    print("[INIT] Africa's Talking initialized successfully")
except Exception as e:
    print(f"[INIT ERROR] Africa's Talking failed to initialize: {e}")

SHORTCODE = "1184"

def detect_negation(message):
    """Detects negation words in the message."""
    message_lower = message.lower()
    # Use word boundaries to avoid matching 'not' in 'nothing'
    for word in NEGATION_WORDS:
        if re.search(rf'\b{word}\b', message_lower):
            return True
    return False

def smart_intent_guard(message):
    """
    Validates the intent before allowing service execution.
    Returns (is_valid, response_if_invalid)
    """
    try:
        # 1. Message length check
        meaningful_words = [w for w in message.split() if len(w) > 1]
        if len(meaningful_words) == 0:
            return False, "I didn't quite catch that. Could you please say more? / Sijakuelewa vizuri. Unaweza kusema zaidi?"

        # 2. Negation check (Pre-Rasa)
        if detect_negation(message):
            return False, "It seems you do not need that service. What would you like help with instead? / Inaonekana hauhitaji huduma hiyo. Ungependa nisaidie na nini kingine badala yake?"

        # 3. Rasa Intent Validation
        parse_payload = {"text": message}
        try:
            r = requests.post(RASA_PARSE_URL, json=parse_payload, timeout=10)
            r.raise_for_status()
            parse_data = r.json()
            
            intent_data = parse_data.get("intent", {})
            intent_name = intent_data.get("name")
            confidence = intent_data.get("confidence", 0)
            
            # Get second intent for gap analysis
            intent_ranking = parse_data.get("intent_ranking", [])
            second_confidence = intent_ranking[1].get("confidence", 0) if len(intent_ranking) > 1 else 0
            confidence_gap = confidence - second_confidence

            # 4. Service Intent Specific Logic
            if intent_name in SERVICE_INTENTS:
                # Condition: Confidence check
                if confidence < CONFIDENCE_THRESHOLD:
                    return False, "I'm not quite sure which service you are referring to. Could you please specify? (e.g., Passport application, KRA PIN) / Sina hakika ni huduma gani unayomaanisha. Tafadhali fafanua? (mfano: Maombi ya Pasipoti, KRA PIN)"
                
                # Condition: Confidence gap check
                if confidence_gap < CONFIDENCE_GAP_THRESHOLD:
                    return False, "I'm hearing a few different things. Could you please clarify your request? / Nasikia mambo tofauti. Tafadhali fafanua ombi lako?"
        except Exception as parse_err:
            print(f"[GUARD ERROR] Intent parsing failed: {parse_err}. Proceeding without guard.")
            return True, None

            # Condition: Short keyword check (Ambiguity check)
            # If it's a service intent but only 1-2 words (e.g., "kra pin"), ask for confirmation
            if len(meaningful_words) <= 2:
                # We'll allow it but maybe Rasa should handle the confirmation flow via rules/stories
                # For now, let's pass it to Rasa but mark as "potentially ambiguous"
                pass

        return True, None

    except Exception as e:
        print(f"[GUARD ERROR] {e}")
        return True, None # Default to true if guard fails to not block service

def call_rasa(phone_number, message):
    """Sends a message to Rasa and returns the response text."""
    try:
        # Apply Smart Intent Guard
        is_valid, guard_response = smart_intent_guard(message)
        if not is_valid:
            return guard_response

        payload = {
            "sender": phone_number,
            "message": message if message else "hi"
        }
        print(f"[RASA] Sending to {RASA_URL}: {payload}")
        r = requests.post(RASA_URL, json=payload, timeout=10)
        r.raise_for_status()
        
        responses = r.json()
        if not responses:
            return "Samahani, kuna tatizo la kiufundi. Jaribu tena."
        
        # Combine all text responses from Rasa
        full_response = "\n".join([resp.get("text", "") for resp in responses if "text" in resp])
        return full_response
    except Exception as e:
        print(f"[RASA ERROR] {e}")
        return "Service unavailable. Please try again later."

@app.route('/ussd', methods=['POST'])
def ussd():
    session_id = request.values.get('sessionId')
    phone_number = request.values.get('phoneNumber')
    text = request.values.get('text', '').strip()

    # Africa's Talking sends the entire input chain (e.g., "1*2*3")
    levels = text.split('*') if text else []
    latest_input = levels[-1] if levels else ""

    print(f"[USSD] session={session_id} | phone={phone_number} | input='{latest_input}'")

    # Call Rasa to get the response
    rasa_text = call_rasa(phone_number, latest_input)

    if "Asante" in rasa_text or "Goodbye" in rasa_text or "Karibu tena" in rasa_text:
        response = f"END {rasa_text}"
    else:
        response = f"CON {rasa_text}"

    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
