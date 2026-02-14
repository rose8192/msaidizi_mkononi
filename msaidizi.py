# msaidizi.py - CONSOLE CHATBOT FOR MSAIDIZI MKONONI
import sqlite3
import json
import re
import os
from difflib import SequenceMatcher

# === PATHS ===
DB_PATH = "data/services.db"
INTENTS_PATH = "intents/intents.json"

# === LOAD INTENTS ===
with open(INTENTS_PATH, 'r', encoding='utf-8') as f:
    intents_data = json.load(f)["intents"]

# === LANGUAGE DETECTION & SIMILARITY ===
def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def detect_language(text):
    swahili = ["habari", "asante", "tafadhali", "karibu", "nataka", "hospitali", "kra", "huduma"]
    sheng = ["mabuda", "poa", "noma", "kuja", "sasa", "mambo", "vipi"]
    english = ["hello", "help", "hospital", "kra", "huduma", "shif"]

    text_lower = text.lower()
    if any(word in text_lower for word in sheng):
        return "sheng"
    elif any(word in text_lower for word in swahili):
        return "swahili"
    elif any(word in text_lower for word in english):
        return "english"
    else:
        return "swahili"  # default

def get_intent(user_input):
    best_match = None
    highest_score = 0.5
    context = {}

    user_lower = user_input.lower()

    # Extract county & level
    county_match = re.search(r'\b(nairobi|kisumu|mombasa|nakuru|eldoret|nyeri|kakamega|meru|embu|machakos|thika|kiambu|garissa|wajir|lamu|malindi|voi|kericho|kitale|bungoma|busia|homa bay|migori|siaya|kisii|nyamira|bomet|narok|kajiado|turkana|samburu|isiolo|marsabit|mandera|tana river|kwale|kilifi|taita taveta)\b', user_lower)
    level_match = re.search(r'level\s*([456])', user_lower)

    context["county"] = county_match.group(1).capitalize() if county_match else None
    context["level"] = level_match.group(1) if level_match else None

    for intent in intents_data:
        for pattern in intent["patterns"]:
            score = similar(user_lower, pattern.lower())
            if score > highest_score:
                highest_score = score
                best_match = intent
                best_match["context"] = context

    return best_match

# === DATABASE QUERIES ===
def search_hospitals(county=None, level=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = "SELECT name, phone, location, services FROM hospitals WHERE 1=1"
    params = []
    if level:
        query += " AND level = ?"
        params.append(f"Level {level}")
    if county:
        query += " AND county = ?"
        params.append(county)
    query += " LIMIT 5"
    c.execute(query, params)
    results = c.fetchall()
    conn.close()
    return results

def get_kra_service(service_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT steps_sw FROM kra WHERE service LIKE ?", (f"%{service_name}%",))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def search_huduma(county=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = "SELECT name, services, phone FROM huduma"
    params = []
    if county:
        query += " WHERE county = ?"
        params.append(county)
    c.execute(query, params)
    results = c.fetchall()
    conn.close()
    return results

def get_shif_info(topic):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT info_sw FROM shif WHERE topic LIKE ?", (f"%{topic}%",))
    result = c.fetchone()
    conn.close()
    return result[0] if result else "Samahani, sijaona maelezo hayo kuhusu SHIF. Jaribu kuuliza kwa njia nyingine."

# === RESPONSE GENERATOR ===
def generate_response(intent, context):
    tag = intent["tag"]
    lang = detect_language(context.get("raw_input", ""))

    if tag == "greeting":
        return intent["responses"][0]

    elif tag == "help":
        return intent["responses"][0]

    elif tag == "goodbye":
        return intent["responses"][0]

    elif tag == "hospital_search":
        county = context.get("county")
        level = context.get("level")
        hospitals = search_hospitals(county, level)
        if hospitals:
            msg = f"Hapa kuna hospitali"
            if county: msg += f" {county}"
            if level: msg += f" Level {level}"
            msg += ":\n"
            for name, phone, loc, serv in hospitals:
                msg += f"• {name}\n  ☎ {phone}\n  📍 {loc}\n\n"
            msg += "Unataka maelezo zaidi au booking?"
            return msg
        else:
            return "Samahani, sijaona hospitali inayolingana. Jaribu tena au sema 'menu'."

    elif tag == "kra_pin":
        steps = get_kra_service("PIN")
        return steps or "Samahani, sijaona maelezo ya KRA PIN."

    elif tag == "kra_tax":
        steps = get_kra_service("Ushuru")
        return steps or "Samahani, sijaona maelezo ya kulipa ushuru."

    elif tag == "huduma_centre":
        county = context.get("county")
        centres = search_huduma(county)
        if centres:
            msg = "Hizi ndizo Huduma Centres"
            if county: msg += f" {county}"
            msg += ":\n"
            for name, serv, phone in centres:
                msg += f"• {name}\n  Huduma: {serv}\n  ☎ {phone}\n\n"
            return msg
        else:
            return "Samahani, sijaona Huduma Centre. Jaribu kaunti nyingine."

    elif tag == "shif_info":
        user_input = context.get("raw_input", "").lower()
        if "michango" in user_input or "lipa" in user_input:
            info = get_shif_info("Michango")
        elif "kujiunga" in user_input or "register" in user_input:
            info = get_shif_info("kujiunga")
        elif "faida" in user_input or "cover" in user_input:
            info = get_shif_info("Faida")
        else:
            info = get_shif_info("SHIF ni nini")
        return info

    else:
        return "Samahani, sielewi. Andika 'menu' kwa orodha ya huduma."


print("MSAIDIZI MKONONI NI HAPA! (Andika 'toka' au 'exit' ili kuondoka)\n")

while True:
    user_input = input("You: ").strip()
    if user_input.lower() in ["toka", "exit", "bye", "kwa heri"]:
        print("Asante! Karibu tena. 🇰🇪")
        break

    if not user_input:
        continue

    intent = get_intent(user_input)
    if not intent:
        print("Samahani, sielewi. Jaribu tena au andika 'menu'.")
        continue

    
    intent["context"]["raw_input"] = user_input

    response = generate_response(intent, intent["context"])
    print(f"Bot: {response}\n")