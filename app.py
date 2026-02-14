import africastalking
import sqlite3
import os
import requests
import re
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# Health check route
@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "Msaidizi Mkononi backend is running"}), 200

# Chatbot endpoint
@app.route('/chat', methods=['POST'])
@app.route('/webhooks/rest/webhook', methods=['POST'])
def rasa_proxy():
    try:
        payload = request.json
        sender = payload.get('sender', 'unknown')
        message = payload.get('message', '')
        
        # Apply Smart Intent Guard to the message
        is_valid, guard_response = smart_intent_guard(message)
        if not is_valid:
            return jsonify([{"text": guard_response}])

        # Forward to Rasa
        r = requests.post(RASA_URL, json=payload, timeout=30)
        responses = r.json()
        
        # Log to Analytics Database
        log_interaction(sender, message, responses)
        
        return jsonify(responses)
    except Exception as e:
        print(f"[PROXY ERROR] {e}")
        return jsonify([{"text": "Error: Backend unreachable"}]), 503

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
    # Simple hardcoded admin check for demo purposes
    # In production, use Flask-Login or JWT
    auth = request.authorization
    if not auth or not (auth.username == 'admin' and auth.password == 'admin123'):
        return jsonify({"error": "Unauthorized"}), 401
        
    try:
        db_path = os.path.join(os.getcwd(), 'analytics.db')
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

# Africa's Talking Credentials
username = "sandbox"
api_key = "atsk_dded8ac724083e406d34a52e1a4cd8020c8865b3840547111c690faf845c0f77a1ed799f"
africastalking.initialize(username, api_key)

SHORTCODE = "1184"
RASA_URL = "https://msaidizi-mkononi-rasa.onrender.com/webhooks/rest/webhook"
RASA_PARSE_URL = "https://msaidizi-mkononi-rasa.onrender.com/model/parse"

# Configuration for Smart Intent Guard
SERVICE_INTENTS = [
    "kra_info", "shif_info", "huduma_info", "ntsa_info", 
    "police_clearance_info", "business_reg_info", "helb_info",
    "hospital_search", "huduma_locator"
]
CONFIDENCE_THRESHOLD = 0.75
CONFIDENCE_GAP_THRESHOLD = 0.1
NEGATION_WORDS = ["sitaki", "sihitaji", "hapana", "no", "not", "don't", "do not", "cancel", "stop"]

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
        r = requests.post(RASA_PARSE_URL, json=parse_payload, timeout=5)
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
