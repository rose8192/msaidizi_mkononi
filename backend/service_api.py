from fastapi import FastAPI, HTTPException, Form, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import sqlite3
import time
import requests
import pandas as pd
import structlog
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

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

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*args, **kwargs):
        return None

load_dotenv()
ROOT_PATH = os.path.dirname(os.path.dirname(__file__))
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "MsaidiziMkononiBot")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
USSD_SANDBOX_URL = os.getenv("USSD_SANDBOX_URL", "https://account.africastalking.com/apps/sandbox")
USSD_SHORT_CODE = os.getenv("USSD_SHORT_CODE", "1184")
RASA_URL = os.getenv("RASA_URL", "http://localhost:5005")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "db.sqlite")
HOSPITALS_CSV = os.getenv("HOSPITALS_CSV", os.path.join(ROOT_PATH, "data", "clean_hospitals.csv"))
HUDUMA_CSV = os.getenv("HUDUMA_CSV", os.path.join(ROOT_PATH, "data", "huduma_centres.csv"))
SERVICES_DB = os.path.join(ROOT_PATH, "data", "services.db")

app = FastAPI()

# Global Error Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"message": "The service is temporarily unavailable. Please try again shortly."}
    )

# Health Check Endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": time.time()}

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Retry logic for external API calls
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def safe_post(url: str, json_data: Dict[str, Any], timeout: int = 5):
    start_time = time.time()
    try:
        r = requests.post(url, json=json_data, timeout=timeout)
        latency = time.time() - start_time
        logger.info("api_call", url=url, status_code=r.status_code, latency=latency)
        r.raise_for_status()
        return r
    except Exception as e:
        logger.error("api_call_failed", url=url, error=str(e))
        raise

class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    text: str
    lang: Optional[str] = "en"

def ensure_db():
    os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS interactions (ts INTEGER, user_id TEXT, text TEXT, intent TEXT, response TEXT, lang TEXT)"
    )
    conn.commit()
    conn.close()

import hashlib

def log_analytics(user_id: Optional[str], text: str, intent_data: Dict[str, Any], platform: str, lang: Optional[str], session_id: Optional[str] = None):
    try:
        # Anonymize User ID (Compliance with Kenya Data Protection Act)
        hashed_id = "anon"
        if user_id:
            hashed_id = hashlib.sha256(str(user_id).encode()).hexdigest()[:16]
        
        # Determine Fallback
        intent_name = intent_data.get("name")
        confidence = intent_data.get("confidence", 0.0)
        is_fallback = intent_name == "nlu_fallback" or confidence < 0.75 # Production threshold

        logger.info("analytics_event", 
                    user_id=hashed_id, 
                    intent=intent_name, 
                    confidence=confidence, 
                    is_fallback=is_fallback,
                    platform=platform)

        conn = sqlite3.connect(SERVICES_DB)
        cur = conn.cursor()
        
        # 1. Update/Insert User (Anonymized)
        cur.execute("""
            INSERT INTO users (user_id, language, platform, last_seen)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET 
                language=excluded.language, 
                platform=excluded.platform,
                last_seen=CURRENT_TIMESTAMP
        """, (hashed_id, lang or "en", platform))

        # 2. Log Message
        cur.execute("""
            INSERT INTO messages (session_id, user_id, message_text, intent, confidence, is_fallback, language, platform)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id or hashed_id, hashed_id, text, intent_name, confidence, is_fallback, lang or "en", platform))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("analytics_logging_failed", error=str(e))

def rasa_parse_detailed(text: str) -> Dict[str, Any]:
    try:
        r = safe_post(f"{RASA_URL}/model/parse", {"text": text}, timeout=5)
        if r.status_code == 200:
            return r.json().get("intent", {"name": None, "confidence": 0.0})
    except Exception:
        pass
    return {"name": None, "confidence": 0.0}

def get_anon_id(sender_id: str) -> str:
    return hashlib.sha256(str(sender_id).encode()).hexdigest()[:16]

def get_user_lang(uid: str) -> str:
    try:
        con = sqlite3.connect(SERVICES_DB)
        cur = con.cursor()
        anon_id = get_anon_id(uid)
        row = cur.execute("SELECT language FROM users WHERE user_id = ?", (anon_id,)).fetchone()
        con.close()
        if row and row[0]:
            return str(row[0]).strip().lower()
    except Exception:
        pass
    return "en"

def set_user_lang(uid: str, lang: str) -> None:
    try:
        con = sqlite3.connect(SERVICES_DB)
        cur = con.cursor()
        anon_id = get_anon_id(uid)
        cur.execute("""
            INSERT INTO users (user_id, language, last_seen)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET 
                language=excluded.language, 
                last_seen=CURRENT_TIMESTAMP
        """, (anon_id, lang))
        con.commit()
        con.close()
    except Exception:
        pass

def query_service(table: str, topic: str, lang: str) -> str:
    try:
        con = sqlite3.connect(SERVICES_DB)
        cur = con.cursor()
        row = cur.execute(f"SELECT topic, info_sw, info_en, link FROM {table} WHERE LOWER(topic) LIKE ?", (f"%{topic.lower()}%",)).fetchone()
        con.close()
        if not row:
            return "No matching information found."
        t, sw, en, link = row
        info = sw if lang == "sw" else en
        return f"{t}:\n{info}" + (f"\nMore: {link}" if link else "")
    except Exception:
        return "Service database unavailable."

def rasa_parse(text: str) -> Optional[str]:
    try:
        r = requests.post(f"{RASA_URL}/model/parse", json={"text": text}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data.get("intent", {}).get("name")
    except Exception:
        return None
    return None

def rasa_reply(sender: str, text: str) -> List[str]:
    try:
        r = safe_post(
            f"{RASA_URL}/webhooks/rest/webhook",
            {"sender": sender, "message": text},
            timeout=10, # Production timeout
        )
        if r.status_code == 200:
            out = []
            for m in r.json():
                if "text" in m:
                    out.append(m["text"])
            return out or ["Ninaendelea kukuhudumia."]
    except Exception as e:
        logger.error("rasa_reply_failed", error=str(e))
        return []
    return []

def telegram_send_message(chat_id: int, text: str) -> None:
    if not TELEGRAM_TOKEN:
        return
    try:
        safe_post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            {"chat_id": chat_id, "text": text},
            timeout=5,
        )
    except Exception as e:
        logger.error("telegram_send_failed", error=str(e), chat_id=chat_id)

def read_csv_safe(path: str) -> Optional[pd.DataFrame]:
    try:
        if not os.path.exists(path):
            return None
        return pd.read_csv(path)
    except Exception:
        return None

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c: c for c in df.columns}
    lower = {c.lower(): c for c in df.columns}
    if "centre name" in lower:
        cols[lower["centre name"]] = "name"
    if "facility name" in lower:
        cols[lower["facility name"]] = "name"
    if "hospital name" in lower:
        cols[lower["hospital name"]] = "name"
    if "name of facility" in lower:
        cols[lower["name of facility"]] = "name"
    if "opening hours" in lower:
        cols[lower["opening hours"]] = "opening_hours"
    if "county" in lower:
        cols[lower["county"]] = "county"
    if "location" in lower:
        cols[lower["location"]] = "location"
    if "level" in lower:
        cols[lower["level"]] = "level"
    else:
        for k in lower:
            if "level" in k:
                cols[lower[k]] = "level"
                break
    return df.rename(columns=cols)

@app.post("/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    ensure_db()
    intent_data = rasa_parse_detailed(req.text)
    intent = intent_data.get("name")
    replies = rasa_reply(req.user_id or "anonymous", req.text)
    if not replies:
        if req.lang == "sw":
            replies = ["Samahani, siwezi kujibu hilo kwa sasa."]
        else:
            replies = ["Sorry, I cannot answer that right now."]
    
    log_analytics(req.user_id, req.text, intent_data, "app", req.lang)
    return {"intent": intent, "replies": replies}

@app.get("/hospitals/search")
def hospitals_search(county: str, level: Optional[str] = None) -> Dict[str, Any]:
    df = read_csv_safe(HOSPITALS_CSV)
    if df is None:
        raise HTTPException(status_code=404, detail="Hospitals dataset not found")
    df = normalize_columns(df)
    if "county" not in df.columns or "name" not in df.columns:
        raise HTTPException(status_code=400, detail="Unexpected hospitals CSV schema")
    filt = df[df["county"].astype(str).str.lower() == county.strip().lower()]
    if level:
        if "level" in df.columns:
            filt = filt[filt["level"].astype(str).str.lower() == str(level).strip().lower()]
    cols = [c for c in ["name", "level", "county"] if c in filt.columns]
    records = filt[cols].to_dict(orient="records")
    return {"results": records}

@app.get("/huduma/locate")
def huduma_locate(county: str) -> Dict[str, Any]:
    df = read_csv_safe(HUDUMA_CSV)
    if df is None:
        raise HTTPException(status_code=404, detail="Huduma centres dataset not found")
    df = normalize_columns(df)
    if "county" not in df.columns or "name" not in df.columns:
        raise HTTPException(status_code=400, detail="Unexpected Huduma CSV schema")
    filt = df[df["county"].astype(str).str.lower() == county.strip().lower()]
    cols = [c for c in ["name", "location", "opening_hours", "county"] if c in filt.columns]
    records = filt[cols].to_dict(orient="records")
    return {"results": records}

@app.get("/analytics/overview")
def analytics_overview() -> Dict[str, Any]:
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM interactions")
    total = c.fetchone()[0]
    c.execute("SELECT text, COUNT(*) as cnt FROM interactions GROUP BY text ORDER BY cnt DESC LIMIT 10")
    top_q = [{"text": row[0], "count": row[1]} for row in c.fetchall()]
    c.execute("SELECT intent, COUNT(*) as cnt FROM interactions GROUP BY intent ORDER BY cnt DESC LIMIT 10")
    top_intents = [{"intent": row[0], "count": row[1]} for row in c.fetchall()]
    conn.close()
    return {"total": total, "top_questions": top_q, "top_intents": top_intents}

@app.get("/launch/telegram")
def launch_telegram() -> Dict[str, str]:
    return {"url": f"https://t.me/{TELEGRAM_BOT_USERNAME}?start=welcome"}

@app.get("/launch/ussd")
def launch_ussd() -> Dict[str, str]:
    return {"url": USSD_SANDBOX_URL}

@app.post("/telegram/webhook")
def telegram_webhook(update: Dict[str, Any]) -> Dict[str, Any]:
    ensure_db()
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text") or ""
    if not chat_id or not text:
        return {"ok": True}
    lang = get_user_lang(str(chat_id))
    if lang not in ["en", "sw"]:
        if text.strip() in ["1", "2"]:
            lang = "sw" if text.strip() == "1" else "en"
            set_user_lang(str(chat_id), lang)
            if lang == "sw":
                telegram_send_message(chat_id, "Asante! Tutazungumza kwa Kiswahili sasa.\nChagua huduma:\n1. Hospitali\n2. Huduma Centre\n3. KRA\n4. SHIF\n5. Toka")
            else:
                telegram_send_message(chat_id, "Thanks! We'll chat in English.\nChoose service:\n1. Hospitals\n2. Huduma Centre\n3. KRA\n4. SHIF\n5. Exit")
            return {"ok": True}
        else:
            telegram_send_message(chat_id, "Karibu Msaidizi Mkononi!\nChagua lugha / Choose language:\n1. Kiswahili\n2. English")
            return {"ok": True}
    intent_data = rasa_parse_detailed(text)
    replies = rasa_reply(str(chat_id), text) or (["Samahani, siwezi kujibu hilo kwa sasa."] if lang == "sw" else ["Sorry, I cannot answer that right now."])
    for rep in replies:
        telegram_send_message(chat_id, rep)
    
    log_analytics(str(chat_id), text, intent_data, "telegram", lang)
    return {"ok": True}

USSD_SESSIONS: Dict[str, Dict[str, Any]] = {}

def ussd_menu(state: Dict[str, Any]) -> str:
    step = state.get("step", 0)
    if step == 0:
        return "CON Msaidizi Mkononi\n1. Kiswahili\n2. English"
    lang = state.get("lang", "en")
    if step == 1:
        if lang == "sw":
            return "CON Chagua huduma:\n1. Hospitali\n2. Huduma\n3. KRA\n4. SHIF"
        return "CON Choose service:\n1. Hospitals\n2. Huduma Services\n3. KRA\n4. SHIF"
    if state.get("flow") == "hospitals":
        if step == 1:
            return "CON Weka County" if state.get("lang") == "sw" else "CON Enter County"
        if step == 2:
            return "CON Weka Level (mf. 4) au 0 kuruka" if state.get("lang") == "sw" else "CON Enter Level (e.g., 4) or 0 to skip"
    if state.get("flow") == "huduma":
        if step == 1:
            if state.get("lang") == "sw":
                return "CON Huduma:\n1. Cheti cha Kuzaliwa\n2. Mahitaji ya ID\n3. Pasipoti\n4. Huduma Centre Locator"
            return "CON Huduma:\n1. Birth Certificate\n2. ID Application Requirements\n3. Passport Application\n4. Huduma Centre Locator"
        if step == 2:
            return "CON Weka County" if state.get("lang") == "sw" else "CON Enter County"
    if state.get("flow") == "kra":
        if step == 1:
            return "CON 1. Huduma za PIN\n2. Tax Returns\n3. iTax Link" if state.get("lang") == "sw" else "CON 1. PIN Services\n2. Tax Returns\n3. iTax Link"
    if state.get("flow") == "shif":
        if step == 1:
            return "CON 1. Usajili\n2. Hali\n3. Michango" if state.get("lang") == "sw" else "CON 1. Registration\n2. Status\n3. Contributions"
    return "END Goodbye"

def ussd_process(session_id: str, text: str) -> str:
    state = USSD_SESSIONS.get(session_id, {"step": 0})
    if not text:
        state["step"] = 0
        USSD_SESSIONS[session_id] = state
        return ussd_menu(state)
    parts = text.split("*")
    if len(parts) == 1 and parts[0] in ["1", "2"] and state.get("step", 0) == 0:
        state["lang"] = "sw" if parts[0] == "1" else "en"
        state["step"] = 1
        USSD_SESSIONS[session_id] = state
        return ussd_menu(state)
    if len(parts) == 1 and parts[0] in ["1", "2", "3", "4"] and state.get("step") == 1:
        choice = parts[0]
        if choice == "1":
            state = {"flow": "hospitals", "step": 1}
        elif choice == "2":
            state = {"flow": "huduma", "step": 1}
        elif choice == "3":
            state = {"flow": "kra", "step": 1}
        elif choice == "4":
            state = {"flow": "shif", "step": 1}
        state["lang"] = USSD_SESSIONS.get(session_id, {}).get("lang", "en")
        USSD_SESSIONS[session_id] = state
        return ussd_menu(state)
    state = USSD_SESSIONS.get(session_id, {"step": 0})
    flow = state.get("flow")
    if flow == "hospitals":
        if state["step"] == 1 and len(parts) >= 2:
            county = parts[1]
            state["county"] = county
            state["step"] = 2
            USSD_SESSIONS[session_id] = state
            return ussd_menu(state)
        if state["step"] == 2 and len(parts) >= 3:
            level = parts[2]
            df = read_csv_safe(HOSPITALS_CSV)
            if df is None:
                return "END Hospitals dataset not found"
            df = normalize_columns(df)
            filt = df[df["county"].str.lower() == state["county"].strip().lower()]
            if level and level != "0":
                filt = filt[filt["level"].astype(str).str.lower() == str(level).strip().lower()]
            if filt.empty:
                return "END Hakuna hospitali" if state.get("lang") == "sw" else "END No hospitals found"
            out = []
            for _, row in filt[["name", "level", "county"]].head(5).iterrows():
                out.append(f"{row['name']} (L{row['level']}, {row['county']})")
            return "END " + "\n".join(out)
    if flow == "huduma":
        if state["step"] == 1 and len(parts) >= 2:
            opt = parts[1]
            lang = state.get("lang", "en")
            if opt == "1":
                return "END " + query_service("huduma", "birth", lang)
            if opt == "2":
                return "END " + query_service("huduma", "id", lang)
            if opt == "3":
                return "END " + query_service("huduma", "passport", lang)
            if opt == "4":
                state["step"] = 2
                USSD_SESSIONS[session_id] = state
                return ussd_menu(state)
            return "END Goodbye"
        if state["step"] == 2 and len(parts) >= 3:
            county = parts[2]
            df = read_csv_safe(HUDUMA_CSV)
            if df is None:
                return "END Huduma centres dataset not found"
            df = normalize_columns(df)
            filt = df[df["county"].astype(str).str.lower() == county.strip().lower()]
            if filt.empty:
                return "END Hakuna Huduma centre" if state.get("lang") == "sw" else "END No Huduma centre found"
            out = []
            cols = [c for c in ["name", "location", "opening_hours"] if c in filt.columns]
            for _, row in filt[cols].head(5).iterrows():
                if "opening_hours" in cols:
                    out.append(f"{row['name']} - {row['location']} ({row['opening_hours']})")
                else:
                    out.append(f"{row['name']} - {row['location']}")
            return "END " + "\n".join(out)
    if flow == "kra":
        if state["step"] == 1 and len(parts) >= 2:
            opt = parts[1]
            lang = state.get("lang", "en")
            if opt == "1":
                return "END " + query_service("kra", "pin", lang)
            if opt == "2":
                return "END " + query_service("kra", "return", lang)
            if opt == "3":
                return "END " + query_service("kra", "itax", lang)
            return "END Goodbye"
    if flow == "shif":
        if state["step"] == 1 and len(parts) >= 2:
            opt = parts[1]
            lang = state.get("lang", "en")
            if opt == "1":
                return "END " + query_service("shif", "register", lang)
            if opt == "2":
                return "END " + query_service("shif", "status", lang)
            if opt == "3":
                return "END " + query_service("shif", "contrib", lang)
            return "END Goodbye"
    return ussd_menu(state)

@app.post("/ussd")
def ussd(sessionId: str = Form(...), serviceCode: str = Form(...), phoneNumber: str = Form(...), text: str = Form("")):
    resp = ussd_process(sessionId, text or "")
    
    # Log USSD Analytics
    parts = (text or "").split("*")
    last_input = parts[-1] if parts else ""
    
    # Create a pseudo-intent for USSD
    intent_data = {"name": f"ussd_step_{len(parts)}", "confidence": 1.0}
    lang = "en"
    if sessionId in USSD_SESSIONS:
        lang = USSD_SESSIONS[sessionId].get("lang", "en")
        
    log_analytics(phoneNumber, last_input, intent_data, "ussd", lang, sessionId)
    
    return PlainTextResponse(resp)
