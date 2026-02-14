from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction, UserUtteranceReverted
import os
import pandas as pd
import sqlite3
import requests
import hashlib
import re
import structlog
import logging

# Configure Structured Logging for Actions
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger()

ACTIONS_DIR = os.path.dirname(__file__)
RASA_DIR = os.path.dirname(ACTIONS_DIR)
BACKEND_DIR = os.path.dirname(RASA_DIR)
SERVICES_DB = os.getenv("SERVICES_DB", os.path.join(BACKEND_DIR, "data", "services.db"))
HOSPITALS_CSV = os.getenv("HOSPITALS_CSV", os.path.join(BACKEND_DIR, "data", "clean_hospitals.csv"))
HUDUMA_CSV = os.getenv("HUDUMA_CSV", os.path.join(BACKEND_DIR, "data", "huduma_centres.csv"))

def read_csv_safe(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8")
    except Exception:
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            try:
                return pd.read_csv(path, encoding="latin-1")
            except Exception:
                return pd.DataFrame()

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c: c for c in df.columns}
    lower = {c.lower(): c for c in df.columns}
    if "centre name" in lower:
        cols[lower["centre name"]] = "name"
    if "facility name" in lower:
        cols[lower["facility name"]] = "name"
    if "facility_name" in lower:
        cols[lower["facility_name"]] = "name"
    if "hospital name" in lower:
        cols[lower["hospital name"]] = "name"
    if "hospital_name" in lower:
        cols[lower["hospital_name"]] = "name"
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

def get_anon_id(sender_id: Text) -> Text:
    return hashlib.sha256(str(sender_id).encode()).hexdigest()[:16]

def ensure_db() -> None:
    try:
        con = sqlite3.connect(SERVICES_DB)
        cur = con.cursor()
        
        # Check if user_id column exists in users table
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        if columns and "user_id" not in columns:
            # If the table exists but is missing user_id, it's likely using an old schema
            # We'll drop and recreate it for simplicity in this dev environment
            cur.execute("DROP TABLE users")
            
        # Unified users table for analytics and persistence
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                language TEXT,
                platform TEXT,
                county TEXT,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Conversations table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                platform TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)

        # Messages table
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
                FOREIGN KEY(session_id) REFERENCES conversations(session_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)

        # Intent Analytics table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS intent_analytics (
                intent_name TEXT PRIMARY KEY,
                usage_count INTEGER DEFAULT 0,
                avg_confidence REAL DEFAULT 0.0,
                last_used DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Service Usage table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS service_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT,
                county TEXT,
                platform TEXT,
                user_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)

        # Admin Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                username TEXT PRIMARY KEY,
                password_hash TEXT,
                role TEXT DEFAULT 'admin'
            )
        """)
        
        # Add default admin if none exists (password: admin123)
        if cur.execute("SELECT COUNT(1) FROM admin_users").fetchone()[0] == 0:
            admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
            cur.execute("INSERT INTO admin_users (username, password_hash, role) VALUES (?, ?, ?)", ("admin", admin_hash, "superadmin"))

        cur.execute("CREATE TABLE IF NOT EXISTS hospitals (name TEXT, county TEXT, level TEXT, ownership TEXT, version TEXT DEFAULT '1.0', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hospitals_county ON hospitals(county)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hospitals_level ON hospitals(level)")
        cur.execute("CREATE TABLE IF NOT EXISTS huduma_centres (name TEXT, county TEXT, location TEXT, opening_hours TEXT, version TEXT DEFAULT '1.0', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_huduma_county ON huduma_centres(county)")
        cur.execute("CREATE TABLE IF NOT EXISTS huduma_info (topic TEXT PRIMARY KEY, info_sw TEXT, info_en TEXT, link TEXT, version TEXT DEFAULT '1.0', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS kra (topic TEXT PRIMARY KEY, info_sw TEXT, info_en TEXT, link TEXT, version TEXT DEFAULT '1.0', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS shif (topic TEXT PRIMARY KEY, info_sw TEXT, info_en TEXT, link TEXT, version TEXT DEFAULT '1.0', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        
        # Add versioning columns to existing tables if missing
        for table in ["huduma_info", "kra", "shif", "general_services", "hospitals", "huduma_centres"]:
            cur.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cur.fetchall()]
            if columns:
                if "version" not in columns:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN version TEXT DEFAULT '1.0'")
                if "updated_at" not in columns:
                    # SQLite doesn't allow CURRENT_TIMESTAMP as default in ALTER TABLE
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN updated_at DATETIME")
                    cur.execute(f"UPDATE {table} SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")

        # Analytics table setup
        cur.execute("""
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                sender_id TEXT, 
                intent TEXT, 
                confidence REAL,
                is_fallback BOOLEAN,
                entity TEXT, 
                language TEXT, 
                platform TEXT,
                response_time REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cnt = cur.execute("SELECT COUNT(1) FROM hospitals").fetchone()[0]
        if cnt == 0:
            dfh = normalize_columns(read_csv_safe(HOSPITALS_CSV))
            if not dfh.empty:
                name_col = next((c for c in ["name", "hospital_name", "facility_name"] if c in dfh.columns), None)
                own_col = next((c for c in ["ownership"] if c in dfh.columns), None)
                rows = []
                for _, r in dfh.iterrows():
                    n = str(r.get(name_col, "")).strip() if name_col else ""
                    c = str(r.get("county", "")).strip()
                    l = str(r.get("level", "")).strip()
                    o = str(r.get(own_col, "")).strip() if own_col else ""
                    if n and c:
                        rows.append((n, c, l, o))
                if rows:
                    cur.executemany("INSERT INTO hospitals(name, county, level, ownership) VALUES(?,?,?,?)", rows)
        cnt2 = cur.execute("SELECT COUNT(1) FROM huduma_centres").fetchone()[0]
        if cnt2 == 0:
            dfc = normalize_columns(read_csv_safe(HUDUMA_CSV))
            if not dfc.empty:
                rows = []
                for _, r in dfc.iterrows():
                    n = str(r.get("name", "")).strip()
                    c = str(r.get("county", "")).strip()
                    loc = str(r.get("location", "")).strip()
                    hrs = str(r.get("opening_hours", "")).strip()
                    if n and c:
                        rows.append((n, c, loc, hrs))
                if rows:
                    cur.executemany("INSERT INTO huduma_centres(name, county, location, opening_hours) VALUES(?,?,?,?)", rows)
        # Huduma table setup
        hi = cur.execute("SELECT COUNT(1) FROM huduma_info").fetchone()[0]
        if hi == 0:
            cur.executemany(
                "INSERT INTO huduma_info(topic, info_sw, info_en, link, version) VALUES(?,?,?,?,?)",
                [
                    ("id", 
                     "**Kitambulisho cha Taifa (National ID)**\n• **Maelezo**: Kitambulisho rasmi cha raia wa Kenya.\n• **Ustahiki**: Raia wote wa Kenya wenye umri wa miaka 18 na zaidi.\n• **Mahitaji**: Cheti cha kuzaliwa, nakala ya ID za wazazi, na fomu ya maombi (iliyojazwa Huduma Centre).\n• **Gharama**: Bure kwa mara ya kwanza; Sh 1,000 kwa kubadilisha/kupoteza.\n• **Mchakato**: Fika Huduma Centre -> Jaza fomu -> Chukua alama za vidole -> Subiri siku 14-21.\n• **Muda**: Wiki 2 hadi 4.", 
                     "**National ID**\n• **What it is**: Official identification for Kenyan citizens.\n• **Eligibility**: All Kenyan citizens aged 18 and above.\n• **Requirements**: Birth certificate, copies of parents' IDs, and application form (filled at Huduma Centre).\n• **Fees**: Free for first-time; Ksh 1,000 for replacement/duplicate.\n• **Step-by-step**: Visit Huduma Centre -> Fill form -> Capture biometrics -> Wait for notification.\n• **Timeline**: 2 to 4 weeks.", 
                     "https://www.hudumakenya.go.ke", "1.0"),
                    ("passport", 
                     "**Pasipoti (Passport)**\n• **Maelezo**: Hati ya kusafiria nje ya nchi.\n• **Ustahiki**: Raia wote wa Kenya.\n• **Mahitaji**: ID ya taifa, cheti cha kuzaliwa, picha ya pasipoti, na barua ya mdhamini.\n• **Gharama**: Sh 4,550 (kurasa 34), Sh 6,050 (kurasa 50).\n• **Mchakato**: Jisajili eCitizen -> Jaza fomu ya pasipoti -> Lipia -> Chapisha fomu -> Fika ofisi za Uhamiaji/Huduma Centre kwa biometrics.\n• **Muda**: Siku 14 hadi 21 za kazi.", 
                     "**Passport**\n• **What it is**: Travel document for international travel.\n• **Eligibility**: All Kenyan citizens.\n• **Requirements**: National ID, Birth certificate, passport-size photo, and recommender's ID copy.\n• **Fees**: Ksh 4,550 (34 pages), Ksh 6,050 (50 pages).\n• **Step-by-step**: Login to eCitizen -> Fill passport form -> Pay -> Print form -> Visit Immigration/Huduma Centre for biometrics.\n• **Timeline**: 14 to 21 working days.", 
                     "https://www.ecitizen.go.ke", "1.0"),
                    ("birth certificate", 
                     "**Cheti cha Kuzaliwa (Birth Certificate)**\n• **Maelezo**: Rekodi rasmi ya kuzaliwa.\n• **Ustahiki**: Watoto waliozaliwa Kenya au wazazi wa watoto.\n• **Mahitaji**: Notisi ya kuzaliwa (kutoka hospitali) au kadi ya kliniki.\n• **Gharama**: Sh 180 (kawaida), Sh 500-1000 (marekebisho).\n• **Mchakato**: Omba kupitia eCitizen (Civil Registration) -> Pakia nyaraka -> Lipia -> Pakua au chukua cheti.\n• **Muda**: Siku 5 hadi 10 za kazi.", 
                     "**Birth Certificate**\n• **What it is**: Official record of birth.\n• **Eligibility**: Children born in Kenya or parents on behalf of children.\n• **Requirements**: Birth notification (from hospital) or clinic card.\n• **Fees**: Ksh 180 (standard), Ksh 500-1000 (amendments).\n• **Step-by-step**: Apply via eCitizen (Civil Registration) -> Upload docs -> Pay -> Download or collect certificate.\n• **Timeline**: 5 to 10 working days.", 
                     "https://www.ecitizen.go.ke", "1.0"),
                    ("death certificate", 
                     "**Cheti cha Kifo (Death Certificate)**\n• **Maelezo**: Rekodi rasmi ya kifo.\n• **Ustahiki**: Jamaa wa karibu wa marehemu.\n• **Mahitaji**: Notisi ya kifo (kutoka hospitali/polisi) na ID ya marehemu.\n• **Gharama**: Sh 180.\n• **Mchakato**: Fika Huduma Centre au Civil Registration -> Peana notisi -> Lipia -> Subiri uthibitisho.\n• **Muda**: Siku 3 hadi 7 za kazi.", 
                     "**Death Certificate**\n• **What it is**: Official record of death.\n• **Eligibility**: Next of kin of the deceased.\n• **Requirements**: Death notification (hospital/police) and deceased's ID.\n• **Fees**: Ksh 180.\n• **Step-by-step**: Visit Huduma Centre or Civil Registration office -> Submit notification -> Pay -> Wait for processing.\n• **Timeline**: 3 to 7 working days.", 
                     "https://www.hudumakenya.go.ke", "1.0"),
                    ("marriage certificate", 
                     "**Cheti cha Ndoa (Marriage Certificate)**\n• **Maelezo**: Uthibitisho wa kisheria wa ndoa.\n• **Ustahiki**: Wanandoa (miaka 18+).\n• **Mahitaji**: ID za wanandoa, mashahidi wawili, na picha za pasipoti.\n• **Gharama**: Sh 3,900 (Ndoa ya serikali).\n• **Mchakato**: Omba kupitia eCitizen (OAG) -> Toa notisi ya siku 21 -> Fanya sherehe -> Pata cheti.\n• **Muda**: Siku 21 (notisi) + siku ya ndoa.", 
                     "**Marriage Certificate**\n• **What it is**: Legal proof of marriage.\n• **Eligibility**: Couples (18+ years).\n• **Requirements**: IDs of couple, two witnesses, and passport photos.\n• **Fees**: Ksh 3,900 (Civil Marriage).\n• **Step-by-step**: Apply via eCitizen (Office of Attorney General) -> Give 21-day notice -> Solemnize marriage -> Receive certificate.\n• **Timeline**: 21 days (notice period) + ceremony day.", 
                     "https://www.ecitizen.go.ke", "1.0"),
                ]
            )
        
        # Additional services table setup (NTSA, Police, etc.)
        cur.execute("CREATE TABLE IF NOT EXISTS general_services (topic TEXT PRIMARY KEY, info_sw TEXT, info_en TEXT, link TEXT, version TEXT DEFAULT '1.0', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        gs = cur.execute("SELECT COUNT(1) FROM general_services").fetchone()[0]
        if gs == 0:
            cur.executemany(
                "INSERT INTO general_services(topic, info_sw, info_en, link, version) VALUES(?,?,?,?,?)",
                [
                    ("ntsa", 
                     "**Huduma za NTSA (Leseni ya Udereva)**\n• **Maelezo**: Udhibiti wa usafiri and usalama barabarani.\n• **Mahitaji**: ID ya taifa, cheti cha shule ya udereva (kwa mara ya kwanza).\n• **Gharama**: Sh 650 (Renewal mwaka 1), Sh 3,050 (Smart DL).\n• **Mchakato**: Jisajili eCitizen -> Chagua NTSA (New) -> Omba Renewal au Smart DL -> Lipia -> Pata DL.\n• **Muda**: Papo hapo (Renewal), Wiki 2-4 (Smart DL).", 
                     "**NTSA Services (Driving License)**\n• **What it is**: Transport regulation and road safety services.\n• **Requirements**: National ID, Driving school certificate (for first-time).\n• **Fees**: Ksh 650 (1-year renewal), Ksh 3,050 (Smart DL).\n• **Step-by-step**: Login to eCitizen -> Select NTSA (New) -> Apply for Renewal or Smart DL -> Pay -> Receive license.\n• **Timeline**: Instant (Renewal), 2-4 weeks (Smart DL).", 
                     "https://serviceportal.ntsa.go.ke", "1.0"),
                    ("police clearance", 
                     "**Cheti cha Tabia Njema (Police Clearance/Good Conduct)**\n• **Maelezo**: Cheti kinachothibitisha rekodi ya jinai.\n• **Ustahiki**: Raia wote na wageni nchini Kenya.\n• **Mahitaji**: ID ya taifa na barua ya maombi (eCitizen).\n• **Gharama**: Sh 1,050.\n• **Mchakato**: Omba kupitia eCitizen (DCI) -> Lipia -> Pakua fomu -> Fika DCI au Huduma Centre kwa alama za vidole.\n• **Muda**: Siku 7 hadi 14 za kazi.", 
                     "**Certificate of Good Conduct (Police Clearance)**\n• **What it is**: Certificate confirming criminal record status.\n• **Eligibility**: All citizens and residents in Kenya.\n• **Requirements**: National ID and application printout (from eCitizen).\n• **Fees**: Ksh 1,050.\n• **Step-by-step**: Apply via eCitizen (DCI) -> Pay -> Download forms -> Visit DCI or Huduma Centre for fingerprinting.\n• **Timeline**: 7 to 14 working days.", 
                     "https://www.ecitizen.go.ke", "1.0"),
                    ("business registration", 
                     "**Usajili wa Biashara (Business Registration)**\n• **Maelezo**: Kusajili jina la biashara au kampuni.\n• **Ustahiki**: Mjasiriamali yeyote.\n• **Mahitaji**: ID, picha ya pasipoti, na anwani ya biashara.\n• **Gharama**: Sh 850 (Jina la biashara), Sh 10,650 (Kampuni ya kibinafsi).\n• **Mchakato**: eCitizen -> Business Registration Service -> Name Search -> Application -> Payment.\n• **Muda**: Siku 2 hadi 5 za kazi.", 
                     "**Business Registration**\n• **What it is**: Registering a business name or company.\n• **Eligibility**: Any entrepreneur.\n• **Requirements**: ID, passport photo, and business address.\n• **Fees**: Ksh 850 (Business Name), Ksh 10,650 (Private Company).\n• **Step-by-step**: eCitizen -> Business Registration Service -> Name Search -> Application -> Payment.\n• **Timeline**: 2 to 5 working days.", 
                     "https://www.ecitizen.go.ke", "1.0"),
                    ("helb", 
                     "**Bodi ya Mikopo ya Elimu ya Juu (HELB)**\n• **Maelezo**: Mikopo na ufadhili kwa wanafunzi wa vyuo.\n• **Ustahiki**: Wanafunzi wa Kenya katika vyuo vikuu na TVET.\n• **Mahitaji**: ID, barua ya kujiunga na chuo, na maelezo ya mdhamini.\n• **Gharama**: Bure kutuma maombi; Sh 1,000 kwa cheti cha 'Clearance' (kwa wasio na deni).\n• **Mchakato**: Pakua HELB App au eCitizen -> Jaza maombi -> Peana nyaraka mtandaoni au Huduma Centre.\n• **Muda**: Wiki 4 hadi 8 (kulingana na mzunguko wa masomo).", 
                     "**Higher Education Loans Board (HELB)**\n• **What it is**: Loans and bursaries for higher education students.\n• **Eligibility**: Kenyan students in Universities and TVETs.\n• **Requirements**: ID, Admission letter, and guarantor details.\n• **Fees**: Free to apply; Ksh 1,000 for Clearance Certificate (for non-loanees).\n• **Step-by-step**: Download HELB App or use eCitizen -> Fill application -> Submit docs online or at Huduma Centre.\n• **Timeline**: 4 to 8 weeks (depending on academic cycle).", 
                     "https://www.helb.co.ke", "1.0"),
                ]
            )

        # KRA table setup
        kc = cur.execute("SELECT COUNT(1) FROM kra").fetchone()[0]
        if kc == 0:
            cur.executemany(
                "INSERT INTO kra(topic, info_sw, info_en, link) VALUES(?,?,?,?)",
                [
                    ("menu", 
                     "Kenya Revenue Authority (KRA) inashughulikia ushuru na ukusanyaji wa mapato nchini Kenya.\nHuduma kuu:\n• Usajili na upatikanaji wa KRA PIN\n• Kusajili kurudi kwa mapato kila mwaka\n• Kulipa kodi (VAT, PAYE, kodi ya kampuni)\n• Kusimamia wajibu na uzingatiaji", 
                     "Kenya Revenue Authority (KRA) handles tax and revenue collection in Kenya.\nMain services:\n• KRA PIN registration and retrieval\n• Annual tax return filing\n• Tax payments (VAT, PAYE, corporate tax)\n• Managing obligations and compliance", 
                     "https://itax.kra.go.ke"),
                    ("pin registration", 
                     "**KRA PIN Registration**\n• **Maelezo**: Usajili wa namba ya kipekee ya kodi kwa raia na wakazi.\n• **Ustahiki**: Mtu yeyote mwenye ID ya taifa au mgeni mwenye kibali cha kazi.\n• **Mahitaji**: ID ya taifa, anwani ya barua pepe, na namba ya simu.\n• **Gharama**: Bure kwa usajili wa mara ya kwanza.\n• **Mchakato**: Tembelea `https://itax.kra.go.ke` -> Chagua 'New Registration' -> Jaza fomu -> Thibitisha barua pepe -> Pata PIN.\n• **Muda**: Papo hapo ukishamaliza usajili.", 
                     "**KRA PIN Registration**\n• **What it is**: Unique tax identification number for citizens and residents.\n• **Eligibility**: Anyone with a National ID or alien with work permit.\n• **Requirements**: National ID, valid email address, and phone number.\n• **Fees**: Free for first-time registration.\n• **Step-by-step**: Visit `https://itax.kra.go.ke` -> Select 'New Registration' -> Fill form -> Verify email -> Receive PIN certificate.\n• **Timeline**: Instant upon successful completion.", 
                     "https://itax.kra.go.ke"),
                    ("tax returns", 
                     "**Kurejesha Mapato (Tax Returns Filing)**\n• **Maelezo**: Taarifa ya kila mwaka ya mapato na ushuru.\n• **Ustahiki**: Wote wenye KRA PIN (hata kama huna mapato - Nil Return).\n• **Mahitaji**: KRA PIN na namba ya siri ya iTax, P9 form (kwa walioajiriwa).\n• **Gharama**: Bure kutuma maombi; faini hutozwa kwa kuchelewa (baada ya Juni 30).\n• **Mchakato**: Ingia iTax -> Chagua 'Returns' -> 'File Return' -> Jaza fomu au pakia Excel -> Wasilisha.\n• **Muda**: Papo hapo baada ya kuwasilisha.", 
                     "**Tax Returns Filing**\n• **What it is**: Annual declaration of income and tax paid.\n• **Eligibility**: Everyone with a KRA PIN (even for no income - Nil Returns).\n• **Requirements**: KRA PIN and iTax password, P9 form (for employees).\n• **Fees**: Free to file; penalties apply for late filing (after June 30th).\n• **Step-by-step**: Login to iTax -> Select 'Returns' -> 'File Return' -> Fill form or upload Excel -> Submit.\n• **Timeline**: Instant upon submission.", 
                     "https://itax.kra.go.ke"),
                    ("tax payments", 
                     "**Malipo ya Ushuru (Tax Payments)**\n• **Maelezo**: Kulipa kodi mbalimbali kwa serikali kupitia KRA.\n• **Mahitaji**: KRA PIN na maelezo ya malipo (mfano: PRN).\n• **Gharama**: Kulingana na kiasi cha ushuru kinachodaiwa.\n• **Mchakato**: Ingia iTax -> Chagua 'Payments' -> Toa E-slip (PRN) -> Lipia kupitia benki au M-Pesa (Paybill 222222).\n• **Muda**: Rekodi huchukua hadi saa 24 kuonekana kwenye mfumo.", 
                     "**Tax Payments**\n• **What it is**: Paying various taxes to the government via KRA.\n• **Requirements**: KRA PIN and payment details (e.g., PRN).\n• **Fees**: Depends on the tax amount due.\n• **Step-by-step**: Login to iTax -> Select 'Payments' -> Generate E-slip (PRN) -> Pay via bank or M-Pesa (Paybill 222222).\n• **Timeline**: Payment reflects on system within 24 hours.", 
                     "https://itax.kra.go.ke"),
                ],
            )

        # SHIF table setup
        sc = cur.execute("SELECT COUNT(1) FROM shif").fetchone()[0]
        if sc == 0:
            cur.executemany(
                "INSERT INTO shif(topic, info_sw, info_en, link) VALUES(?,?,?,?)",
                [
                    ("menu", "SHIF inaweza kukusaidia na:\n1. Kujiunga na SHIF\n2. Michango ya SHIF\n3. Faida za SHIF", "SHIF can help you with:\n1. SHIF Registration\n2. SHIF Contributions\n3. SHIF Benefits", "https://shif.go.ke"),
                    ("shif registration", 
                     "**Usajili wa SHIF (Social Health Insurance Fund)**\n• **Maelezo**: Bima mpya ya afya ya jamii nchini Kenya.\n• **Ustahiki**: Wakazi wote wa Kenya (wazima na watoto).\n• **Mahitaji**: ID ya taifa, namba ya simu, na maelezo ya wategemezi.\n• **Gharama**: Sh 300 kwa mwezi (kwa wasioajiriwa); 2.75% ya mshahara kwa walioajiriwa.\n• **Mchakato**: Tembelea `https://shif.go.ke` au piga *147# -> Jisajili -> Lipia mchango wa kwanza.\n• **Muda**: Papo hapo.", 
                     "**SHIF Registration (Social Health Insurance Fund)**\n• **What it is**: New universal health insurance for Kenya.\n• **Eligibility**: All residents of Kenya (adults and children).\n• **Requirements**: National ID, phone number, and dependent details.\n• **Fees**: Ksh 300 monthly (non-salaried); 2.75% of gross salary (salaried).\n• **Step-by-step**: Visit `https://shif.go.ke` or dial *147# -> Register -> Pay initial contribution.\n• **Timeline**: Instant.", 
                     "https://shif.go.ke"),
                    ("shif contributions", 
                     "**Michango ya SHIF (Contributions)**\n• **Maelezo**: Malipo ya kila mwezi ili kuendelea kunufaika na bima.\n• **Mahitaji**: Namba ya SHIF au ID.\n• **Gharama**: Kima cha chini ni Sh 300.\n• **Mchakato**: Lipia kupitia M-Pesa (Paybill 222222) au kupitia tovuti ya SHIF.\n• **Muda**: Malipo huonekana papo hapo.", 
                     "**SHIF Contributions**\n• **What it is**: Monthly payments to maintain health cover.\n• **Requirements**: SHIF number or National ID.\n• **Fees**: Minimum Ksh 300.\n• **Step-by-step**: Pay via M-Pesa (Paybill 222222) or through the SHIF portal.\n• **Timeline**: Reflected instantly.", 
                     "https://shif.go.ke"),
                    ("shif benefits", 
                     "**Faida za SHIF (Benefits)**\n• **Maelezo**: Huduma zinazogharamiwa na bima.\n• **Huduma**: Matibabu ya nje (outpatient), kulazwa (inpatient), uzazi, upasuaji, na magonjwa sugu.\n• **Mchakato**: Onyesha kadi ya SHIF au ID kwenye hospitali inayokubali.\n• **Muda**: Inaanza kutumika mara tu baada ya usajili na malipo.", 
                     "**SHIF Benefits**\n• **What it is**: Medical services covered by the fund.\n• **Services**: Outpatient, inpatient, maternity, surgery, and chronic illness management.\n• **How to use**: Present SHIF card or ID at participating hospitals.\n• **Timeline**: Active immediately after registration and payment.", 
                     "https://shif.go.ke"),
                ],
            )

        con.commit()
        con.close()
    except Exception as e:
        print(f"DEBUG: ensure_db error: {e}")
        pass

def query_hospitals(county: Text, level: Text) -> List[Dict[str, Text]]:
    ensure_db()
    try:
        con = sqlite3.connect(SERVICES_DB)
        cur = con.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(hospitals)").fetchall()]
        name_col = "name" if "name" in cols else "hospital_name" if "hospital_name" in cols else "facility_name" if "facility_name" in cols else None
        county_col = "county" if "county" in cols else None
        level_col = "level" if "level" in cols else None
        if not (name_col and county_col):
            con.close()
            return []
        
        # Clean level input: "Level 4" -> "4", "4" -> "4"
        lv_clean = str(level).lower().replace("level", "").strip()
        cy = str(county).lower().strip()
        
        if level_col:
            # Try exact match on county first, then LIKE
            sql = f"""
                SELECT {name_col}, {county_col}, {level_col} 
                FROM hospitals 
                WHERE (LOWER({county_col}) = ? OR LOWER({county_col}) LIKE ?) 
                AND (TRIM(REPLACE(LOWER({level_col}), 'level', '')) = ? OR {level_col} LIKE ?)
                LIMIT 10
            """
            rows = cur.execute(sql, (cy, f"%{cy}%", lv_clean, f"%{lv_clean}%")).fetchall()
        else:
            sql = f"SELECT {name_col}, {county_col} FROM hospitals WHERE LOWER({county_col}) = ? OR LOWER({county_col}) LIKE ? LIMIT 10"
            rows = cur.execute(sql, (cy, f"%{cy}%")).fetchall()
        
        con.close()
        out = []
        for r in rows:
            if level_col:
                out.append({"name": r[0], "county": r[1], "level": r[2]})
            else:
                out.append({"name": r[0], "county": r[1], "level": ""})
        return out
    except Exception as e:
        print(f"DEBUG: query_hospitals error: {e}")
        return []

def is_negation(text: Text) -> bool:
    NEGATION_WORDS = ["sitaki", "sihitaji", "hapana", "no", "not", "don't", "do not", "cancel", "stop", "hatuhitaji", "la"]
    t = str(text).lower().strip()
    # Check for direct matches or word boundaries
    for word in NEGATION_WORDS:
        if re.search(rf"\b{word}\b", t):
            return True
    return False

def get_user_lang(tracker: Tracker) -> Text | None:
    # 1. Check slot
    lang = tracker.get_slot("language")
    if lang:
        return str(lang).lower().strip()
    
    # 2. Check DB
    try:
        con = sqlite3.connect(SERVICES_DB)
        cur = con.cursor()
        anon_id = get_anon_id(tracker.sender_id)
        row = cur.execute("SELECT language FROM users WHERE user_id = ?", (anon_id,)).fetchone()
        con.close()
        if row and row[0]:
            return str(row[0]).strip().lower()
    except Exception:
        pass
    return None

def check_lang_or_ask(tracker: Tracker, dispatcher: CollectingDispatcher) -> bool:
    lang = get_user_lang(tracker)
    if not lang:
        ActionLanguageMenu().run(dispatcher, tracker, {})
        return False
    return True

def format_for_ussd(text: Text, max_len: int = 160) -> Text:
    """
    Cleans and trims text for USSD (160 character limit).
    Removes Markdown bolding, replaces bullets with simple dashes, 
    and truncates to fit the limit.
    """
    if not text:
        return ""
    
    # Remove Markdown bolding
    text = text.replace("**", "")
    
    # Replace bullet points
    text = text.replace("•", "-")
    
    # Replace double newlines with single
    text = text.replace("\n\n", "\n")
    
    # Remove Link: prefix for USSD
    if "Link:" in text:
        text = text.split("Link:")[0].strip()
        
    if len(text) <= max_len:
        return text
        
    return text[:max_len-3] + "..."

def query_service(table: Text, topic: Text, lang: Text, is_ussd: bool = False) -> Text:
    ensure_db()
    try:
        con = sqlite3.connect(SERVICES_DB)
        cur = con.cursor()
        
        # Clean topic: remove "kra", "shif", "huduma", and "nataka" prefixes
        t_clean = str(topic).lower().strip()
        for prefix in ["kra ", "shif ", "huduma ", "huduma centre ", "huduma centres ", "nataka ", "nahitaji ", "i want ", "i need "]:
            if t_clean.startswith(prefix):
                t_clean = t_clean[len(prefix):].strip()
        
        # Mapping for common variations
        synonyms = {
            "pin": "pin registration",
            "kra pin": "pin registration",
            "registration": "pin registration",
            "returns": "tax returns",
            "payments": "tax payments",
            "pay": "tax payments",
            "lipa": "tax payments",
            "kulipa kodi": "tax payments",
            "id": "id",
            "national id": "id",
            "kitambulisho": "id",
            "passport": "passport",
            "pasipoti": "passport",
            "maombi ya pasipoti": "passport",
            "birth": "birth certificate",
            "cheti cha kuzaliwa": "birth certificate",
            "death": "death certificate",
            "cheti cha kifo": "death certificate",
            "marriage": "marriage certificate",
            "cheti cha ndoa": "marriage certificate",
            "kra": "menu",
            "huduma": "menu",
            "ntsa": "ntsa",
            "dl": "ntsa",
            "driving license": "ntsa",
            "good conduct": "police clearance",
            "police clearance": "police clearance",
            "business registration": "business registration",
            "helb": "helb",
            "sha": "shif registration",
            "social health authority": "shif registration",
            "health insurance": "shif registration",
            "medical cover": "shif registration",
            "bima ya afya": "shif registration",
            "michango": "shif contributions",
            "contributions": "shif contributions",
            "faida": "shif benefits",
            "benefits": "shif benefits"
        }
        t_clean = synonyms.get(t_clean, t_clean)

        # Check if table exists
        exists = cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            con.close()
            # If asking for general services and table doesn't exist yet
            if lang == "sw":
                return "Hifadhi ya huduma haipatikani kwa sasa."
            return "Service database unavailable."

        # Get column names to handle different table schemas
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        
        # Detect column names
        topic_col = "topic" if "topic" in cols else "service" if "service" in cols else None
        info_sw_col = "info_sw" if "info_sw" in cols else "steps_sw" if "steps_sw" in cols else None
        info_en_col = "info_en" if "info_en" in cols else "steps_en" if "steps_en" in cols else None
        info_gen_col = "info" if "info" in cols else None
        link_col = "link" if "link" in cols else None
        version_col = "version" if "version" in cols else None
        updated_col = "updated_at" if "updated_at" in cols else None

        if not topic_col:
            con.close()
            if lang == "sw":
                return "Hifadhi ya huduma haipatikani kwa sasa."
            return "Service database unavailable."
        
        select_cols = [topic_col]
        if info_sw_col: select_cols.append(info_sw_col)
        if info_en_col: select_cols.append(info_en_col)
        if info_gen_col: select_cols.append(info_gen_col)
        if link_col: select_cols.append(link_col)
        if version_col: select_cols.append(version_col)
        if updated_col: select_cols.append(updated_col)
        
        # Try exact match first
        q = f"SELECT {', '.join(select_cols)} FROM {table} WHERE LOWER({topic_col}) = ?"
        row = cur.execute(q, (t_clean,)).fetchone()
        
        # If no exact match, try LIKE
        if not row:
            q = f"SELECT {', '.join(select_cols)} FROM {table} WHERE LOWER({topic_col}) LIKE ? OR ? LIKE '%' || LOWER({topic_col}) || '%' LIMIT 1"
            row = cur.execute(q, (f"%{t_clean}%", t_clean)).fetchone()
            
        con.close()
        if not row:
            # Fallback to general_services if not found in current table
            if table != "general_services":
                fallback_res = query_service("general_services", t_clean, lang, is_ussd)
                if "Available services:" not in fallback_res and "Huduma zinazopatikana:" not in fallback_res:
                    return fallback_res
            
            # Log fallback for unmatched service entities
            print(f"DEBUG: Unmatched service entity '{t_clean}' in table '{table}'")
            
            con = sqlite3.connect(SERVICES_DB)
            cur = con.cursor()
            topics = [r[0] for r in cur.execute(f"SELECT {topic_col} FROM {table} WHERE {topic_col} != 'menu' LIMIT 20").fetchall()]
            con.close()
            if not topics:
                if lang == "sw":
                    return "Hifadhi ya huduma haipatikani kwa sasa."
                return "Service database unavailable."
            header = "Huduma zinazopatikana:" if lang == "sw" else "Available services:"
            msg = header + "\n- " + "\n- ".join(topics)
            return format_for_ussd(msg) if is_ussd else msg
            
        # Map row data to variables based on available columns
        data = dict(zip(select_cols, row))
        topic_name = data.get(topic_col, "")
        info_sw = data.get(info_sw_col)
        info_en = data.get(info_en_col)
        info_gen = data.get(info_gen_col)
        link = data.get(link_col)
        
        info = info_sw if lang == "sw" and info_sw else info_en if info_en else info_gen
        
        if is_ussd:
            return format_for_ussd(f"**{topic_name.upper()}**\n{info}")

        if link:
            return f"**{topic_name.upper()}**\n{info}\n\nLink: {link}"
        return f"**{topic_name.upper()}**\n{info}"
    except Exception as e:
        print(f"DEBUG: query_service error: {e}")
        if lang == "sw":
            return "Hifadhi ya huduma haipatikani kwa sasa."
        return "Service database unavailable."

class ActionHospitalSearch(Action):
    def name(self) -> Text:
        return "action_hospital_search"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher):
            return []
        
        lang = get_user_lang(tracker) or "en"
        county = tracker.get_slot("county")
        level = tracker.get_slot("level")
        
        if not county:
            msg = "Tafadhali andika jina la kaunti (mfano: Nyeri, Nairobi, Kisumu):" if lang == "sw" else "Please type the county name (e.g., Nyeri, Nairobi, Kisumu):"
            dispatcher.utter_message(text=msg)
            return []
        if not level:
            msg = "Tafadhali andika level ya hospitali (mfano: Level 5 au 5):" if lang == "sw" else "Please type the hospital level (e.g., Level 5 or 5):"
            dispatcher.utter_message(text=msg)
            return []
            
        res = query_hospitals(county, level)
        if not res:
            msg = f"Hakuna hospitali zilizopatikana katika kaunti ya {county} za level {level}." if lang == "sw" else f"No hospitals found in {county} at level {level}."
            dispatcher.utter_message(text=msg)
            return [SlotSet("county", None), SlotSet("level", None)]
            
        lines = []
        lv_in = str(level).lower().replace("level", "").strip()
        header = f"Hospitali za Level {lv_in} katika {str(county).capitalize()}:" if lang == "sw" else f"Level {lv_in} hospitals in {str(county).capitalize()}:"
        lines.append(header)
        
        for row in res:
            lvl = str(row.get("level", "")).strip()
            lvl_fmt = lvl if lvl.lower().startswith("level") else f"Level {lvl}" if lvl else ""
            if lvl_fmt:
                lines.append(f"- {row['name']} ({lvl_fmt}, {row.get('county','')})")
            else:
                lines.append(f"- {row['name']} ({row.get('county','')})")
        dispatcher.utter_message(text="\n".join(lines))
        return [SlotSet("county", None), SlotSet("level", None)]

class ActionKRAInfo(Action):
    def name(self) -> Text: outcome = "action_kra_info"; return outcome

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher): return []
        lang = get_user_lang(tracker)
        is_ussd = tracker.get_slot("is_ussd")
        
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        if is_negation(text):
            return [FollowupAction("utter_deny_service")]
        
        # Check for ambiguity (short keyword check)
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        meaningful_words = [w for w in text.split() if len(w) > 1]
        current_service = tracker.get_slot("current_service")
        
        # If the user just said "kra" or "kra pin" and we haven't confirmed yet
        if len(meaningful_words) <= 2 and current_service != "kra":
            return [SlotSet("current_service", "kra"), FollowupAction("action_confirm_service")]
        
        # Check if we have a specific service selected (but not the menu itself)
        service = tracker.get_slot("current_service")
        if service and service not in ["kra", "menu", "kra services"]:
            info = query_service("kra", service, lang, is_ussd)
            dispatcher.utter_message(text=info)
            return []
        
        # Otherwise show menu
        msg = query_service("kra", "menu", lang, is_ussd)
        if "Service database unavailable" in msg or "Hifadhi ya huduma haipatikani" in msg:
            if lang == "sw":
                msg = "Huduma za KRA:\n1. Usajili wa PIN\n2. Kurejesha Mapato (Returns)\n3. Malipo ya Ushuru"
            else:
                msg = "KRA services:\n1. PIN Registration\n2. Tax Returns\n3. Tax Payments"
        dispatcher.utter_message(text=msg)
        return [SlotSet("current_service", "kra")]

class ActionSHIFInfo(Action):
    def name(self) -> Text:
        return "action_shif_info"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher):
            return []
        lang = get_user_lang(tracker) or "en"
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        if is_negation(text):
            return [FollowupAction("utter_deny_service")]
            
        meaningful_words = [w for w in text.split() if len(w) > 1]
        current_service = tracker.get_slot("current_service")
        
        # Check for ambiguity (short keyword check)
        if len(meaningful_words) <= 2 and current_service != "shif" and text not in ("1", "2", "3", "4"):
            return [SlotSet("current_service", "shif"), FollowupAction("action_confirm_service")]
        
        # Mapping numeric inputs for SHIF
        shif_map = {
            "1": "shif registration",
            "2": "shif contributions",
            "3": "shif benefits"
        }
        topic = shif_map.get(text, text)
        
        if text in ("shif", "shif services"):
            msg = query_service("shif", "menu", lang)
        else:
            msg = query_service("shif", topic, lang)
            
            # If query_service returned available services list (meaning no match), show menu
            if "Available services:" in msg or "Huduma zinazopatikana:" in msg:
                 msg = query_service("shif", "menu", lang)
            
        if "Service database unavailable" in msg or "Hifadhi ya huduma haipatikani" in msg:
            if lang == "sw":
                msg = "Huduma za SHIF:\n1. Usajili wa SHIF\n2. Michango ya SHIF\n3. Faida za SHIF"
            else:
                msg = "SHIF services:\n1. SHIF Registration\n2. SHIF Contributions\n3. SHIF Benefits"
            
        dispatcher.utter_message(text=msg)
        return [SlotSet("current_service", "shif")]

class ActionHudumaMenu(Action):
    def name(self) -> Text: outcome = "action_huduma_menu"; return outcome

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher): return []
        lang = get_user_lang(tracker)
        is_ussd = tracker.get_slot("is_ussd")
        
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        if is_negation(text):
            return [FollowupAction("utter_deny_service")]
            
        # Check if we have a specific service selected (but not the menu itself)
        service = tracker.get_slot("current_service")
        if service and service not in ["huduma", "menu", "huduma services"]:
            info = query_service("huduma_info", service, lang, is_ussd)
            dispatcher.utter_message(text=info)
            return []

        msg = query_service("huduma_info", "menu", lang, is_ussd)
        if "Service database unavailable" in msg or "Hifadhi ya huduma haipatikani" in msg:
            if lang == "sw":
                msg = "Huduma za Huduma Centre:\n1. Kitambulisho\n2. Pasipoti\n3. Cheti cha Kuzaliwa\n4. Cheti cha Kifo\n5. Cheti cha Ndoa\n6. Mahali zilipo"
            else:
                msg = "Huduma Centre services:\n1. ID\n2. Passport\n3. Birth Certificate\n4. Death Certificate\n5. Marriage Certificate\n6. Locator"
        dispatcher.utter_message(text=msg)
        return [SlotSet("current_service", "huduma")]

class ActionHudumaFlow(Action):
    def name(self) -> Text:
        return "action_huduma_flow"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher):
            return []
        lang = get_user_lang(tracker) or "en"
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        meaningful_words = [w for w in text.split() if len(w) > 1]
        current_service = tracker.get_slot("current_service")
        
        # Check for ambiguity (short keyword check)
        if len(meaningful_words) <= 2 and current_service != "huduma" and text not in ("1", "2", "3", "4", "5", "6", "7"):
            return [SlotSet("current_service", "huduma"), FollowupAction("action_confirm_service")]
        
        # Mapping numeric inputs for Huduma
        huduma_map = {
            "1": "id",
            "2": "passport",
            "3": "birth certificate",
            "4": "death certificate",
            "5": "marriage certificate",
            "6": "locator",
            "7": "other services"
        }
        topic = huduma_map.get(text, text)
        
        # Explicitly show menu for general 'huduma' keywords
        if text in ("huduma", "huduma centre", "huduma centres", "huduma services", "huduma menu"):
            return [FollowupAction("action_huduma_menu")]

        if topic == "locator":
            return [FollowupAction("huduma_locator_form")]

        msg = query_service("huduma_info", topic, lang)
        
        # If no specific info found, show menu
        if "Available services:" in msg or "Huduma zinazopatikana:" in msg:
            return [FollowupAction("action_huduma_menu")]

        # If msg is just the menu from DB, also show it properly
        if "**MENU**" in msg or "Huduma Centre can assist" in msg or "Huduma Centre inaweza" in msg:
            dispatcher.utter_message(text=msg)
            return []

        # Fallback for "Service database unavailable."
        if "Service database unavailable" in msg:
            if lang == "sw":
                msg = "Huduma za Huduma Centre:\n1. Kitambulisho\n2. Pasipoti\n3. Cheti cha Kuzaliwa\n4. Cheti cha Kifo\n5. Cheti cha Ndoa"
            else:
                msg = "Huduma Centre services:\n1. ID\n2. Passport\n3. Birth Certificate\n4. Death Certificate\n5. Marriage Certificate"

        dispatcher.utter_message(text=msg)
        return []

class ActionConfirmService(Action):
    def name(self) -> Text:
        return "action_confirm_service"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        lang = get_user_lang(tracker) or "en"
        current_service = tracker.get_slot("current_service")
        
        # Format the service name for display
        service_display = str(current_service).upper() if current_service else ("huduma hii" if lang == "sw" else "this service")
        
        if lang == "sw":
            msg = f"Nimeona umetaja huduma fulani. Je, ungetaka kujua kuhusu {service_display}? (Ndiyo/Hapana)"
        else:
            msg = f"I noticed you mentioned a service keyword. Did you want to learn about {service_display}? (Yes/No)"
            
        dispatcher.utter_message(text=msg)
        return []

class ActionProcessServiceConfirmation(Action):
    def name(self) -> Text:
        return "action_process_service_confirmation"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        intent = tracker.latest_message.get("intent", {}).get("name")
        current_service = tracker.get_slot("current_service")
        
        if intent == "affirm":
            # Map current_service to its specific action
            service_action_map = {
                "kra": "action_kra_info",
                "shif": "action_shif_info",
                "huduma": "action_huduma_menu",
                "ntsa": "action_ntsa_flow",
                "police clearance": "action_police_clearance_flow",
                "business registration": "action_business_reg_flow",
                "helb": "action_helb_flow"
            }
            followup = service_action_map.get(current_service)
            if followup:
                return [FollowupAction(followup)]
            else:
                return [FollowupAction("action_service_menu")]
        else:
            lang = get_user_lang(tracker) or "en"
            if lang == "sw":
                msg = "Sawa. Ungependa nisaidie na nini kingine?"
            else:
                msg = "Okay. What else would you like help with?"
            dispatcher.utter_message(text=msg)
            return [SlotSet("current_service", None)]

class ActionLanguageMenu(Action):
    def name(self) -> Text:
        return "action_language_menu"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        msg = "1. Kiswahili\n2. English"
        dispatcher.utter_message(text=msg)
        return []

class ActionSetLanguage(Action):
    def name(self) -> Text:
        return "action_set_language"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        # Explicit detection for numeric or keyword selection
        if "1" in text or "kiswahili" in text:
            lang = "sw"
        elif "2" in text or "english" in text:
            lang = "en"
        else:
            # Default fallback if intent was choose_language but text is ambiguous
            # Try to see if previous lang was set
            prev_lang = tracker.get_slot("language")
            lang = prev_lang if prev_lang else "en"
        
        # Log analytics handles user persistence to the analytics DB
        log_analytics(tracker)
            
        if lang == "sw":
            dispatcher.utter_message(text="Asante! Tutazungumza kwa Kiswahili sasa.")
        else:
            dispatcher.utter_message(text="Thanks! We will talk in English now.")
            
        return [SlotSet("language", lang)]

class ActionProvideDisclaimer(Action):
    def name(self) -> Text:
        return "action_provide_disclaimer"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # The disclaimer is now handled by the frontend as a fixed banner.
        # We no longer send it as a chat message to avoid duplication and keep the chat clean.
        return []

class ActionNTSAFlow(Action):
    def name(self) -> Text:
        return "action_ntsa_flow"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher): return []
        lang = get_user_lang(tracker)
        is_ussd = tracker.get_slot("is_ussd")
        
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        if is_negation(text):
            return [FollowupAction("utter_deny_service")]
        
        # Check for ambiguity (short keyword check)
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        meaningful_words = [w for w in text.split() if len(w) > 1]
        current_service = tracker.get_slot("current_service")
        
        if len(meaningful_words) <= 2 and current_service != "ntsa":
            return [SlotSet("current_service", "ntsa"), FollowupAction("action_confirm_service")]
            
        info = query_service("general_services", "ntsa", lang, is_ussd)
        if "Service database unavailable" in info or "Hifadhi ya huduma haipatikani" in info:
            if lang == "sw":
                info = "**Huduma za NTSA**\n- Leseni ya Udereva\n- Usajili wa Magari\nTembelea eCitizen kwa huduma hizi."
            else:
                info = "**NTSA Services**\n- Driving License\n- Vehicle Registration\nVisit eCitizen for these services."
        dispatcher.utter_message(text=info)
        return []

class ActionPoliceClearanceFlow(Action):
    def name(self) -> Text:
        return "action_police_clearance_flow"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher): return []
        lang = get_user_lang(tracker)
        is_ussd = tracker.get_slot("is_ussd")
        
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        if is_negation(text):
            return [FollowupAction("utter_deny_service")]
        
        # Check for ambiguity (short keyword check)
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        meaningful_words = [w for w in text.split() if len(w) > 1]
        current_service = tracker.get_slot("current_service")
        
        if len(meaningful_words) <= 2 and current_service != "police clearance":
            return [SlotSet("current_service", "police clearance"), FollowupAction("action_confirm_service")]
            
        info = query_service("general_services", "police clearance", lang, is_ussd)
        if "Service database unavailable" in info or "Hifadhi ya huduma haipatikani" in info:
            if lang == "sw":
                info = "**Cheti cha Tabia Njema (Police Clearance)**\nInapatikana kupitia eCitizen. Unahitaji ID na fomu ya maombi."
            else:
                info = "**Police Clearance (Good Conduct)**\nAvailable via eCitizen. You need your ID and an application form."
        dispatcher.utter_message(text=info)
        return []

class ActionBusinessRegFlow(Action):
    def name(self) -> Text:
        return "action_business_reg_flow"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher): return []
        lang = get_user_lang(tracker)
        is_ussd = tracker.get_slot("is_ussd")
        
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        if is_negation(text):
            return [FollowupAction("utter_deny_service")]
        
        # Check for ambiguity (short keyword check)
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        meaningful_words = [w for w in text.split() if len(w) > 1]
        current_service = tracker.get_slot("current_service")
        
        if len(meaningful_words) <= 2 and current_service != "business registration":
            return [SlotSet("current_service", "business registration"), FollowupAction("action_confirm_service")]
            
        info = query_service("general_services", "business registration", lang, is_ussd)
        if "Service database unavailable" in info or "Hifadhi ya huduma haipatikani" in info:
            if lang == "sw":
                info = "**Usajili wa Biashara**\nInapatikana kupitia eCitizen (Business Registration Service)."
            else:
                info = "**Business Registration**\nAvailable via eCitizen (Business Registration Service)."
        dispatcher.utter_message(text=info)
        return []

class ActionHELBFlow(Action):
    def name(self) -> Text:
        return "action_helb_flow"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher): return []
        lang = get_user_lang(tracker)
        is_ussd = tracker.get_slot("is_ussd")
        
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        if is_negation(text):
            return [FollowupAction("utter_deny_service")]
            
        # Check for ambiguity (short keyword check)
        text = str(tracker.latest_message.get("text", "")).lower().strip()
        meaningful_words = [w for w in text.split() if len(w) > 1]
        current_service = tracker.get_slot("current_service")
        
        if len(meaningful_words) <= 2 and current_service != "helb":
            return [SlotSet("current_service", "helb"), FollowupAction("action_confirm_service")]
            
        info = query_service("general_services", "helb", lang, is_ussd)
        if "Service database unavailable" in info or "Hifadhi ya huduma haipatikani" in info:
            if lang == "sw":
                info = "**HELB (Higher Education Loans Board)**\nMikopo ya elimu ya juu. Omba kupitia HELB App au eCitizen."
            else:
                info = "**HELB (Higher Education Loans Board)**\nHigher education loans. Apply via HELB App or eCitizen."
        dispatcher.utter_message(text=info)
        return []

class ActionEcitizenGeneral(Action):
    def name(self) -> Text:
        return "action_ecitizen_general"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        if not check_lang_or_ask(tracker, dispatcher): return []
        lang = get_user_lang(tracker)
        is_ussd = tracker.get_slot("is_ussd")
        
        if is_ussd:
            msg = "Search all govt services at ecitizen.go.ke. Use the search bar for rare services." if lang == "en" else "Tafuta huduma zote za serikali kupitia ecitizen.go.ke."
            dispatcher.utter_message(text=msg)
        else:
            msg = "You can find all Kenyan government services on the **eCitizen Portal**. Simply visit `https://ecitizen.go.ke` and use the search bar for any specific service you need." if lang == "en" else "Unaweza kupata huduma zote za serikali ya Kenya kwenye **eCitizen Portal**. Tembelea `https://ecitizen.go.ke` na utumie sehemu ya kutafuta kupata huduma yoyote unayohitaji."
            dispatcher.utter_message(text=msg)
            
        return []

class ActionForceLanguagePersistence(Action):
    def name(self) -> Text:
        return "action_force_language_persistence"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Extract language from metadata if provided by frontend
        metadata = tracker.get_slot("session_started_metadata") or {}
        if not metadata:
            # Fallback to latest message metadata
            metadata = tracker.latest_message.get("metadata", {})
            
        frontend_lang = metadata.get("language")
        current_slot_lang = tracker.get_slot("language")
        
        if frontend_lang and frontend_lang != current_slot_lang:
            print(f"DEBUG: Syncing backend slot '{current_slot_lang}' to frontend lang '{frontend_lang}'")
            return [SlotSet("language", frontend_lang)]
            
        return []

class ActionDefaultFallback(Action):
    def name(self) -> Text:
        return "action_default_fallback"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        lang = get_user_lang(tracker) or "en"
        
        if lang == "sw":
            msg = "Samahani, sijafahamu vizuri unachohitaji. Unaweza kujaribu kuuliza kuhusu:\n- KRA PIN\n- Pasipoti\n- SHIF\n- Huduma za NTSA\n- Hospitali karibu nawe"
        else:
            msg = "I'm sorry, I didn't quite catch that. You can try asking about:\n- KRA PIN\n- Passport application\n- SHIF registration\n- NTSA services\n- Hospitals near you"
            
        dispatcher.utter_message(text=msg)
        return [UserUtteranceReverted()]

def log_analytics(tracker: Tracker) -> None:
    try:
        latest = tracker.latest_message
        intent_info = latest.get("intent", {})
        intent_name = intent_info.get("name")
        confidence = intent_info.get("confidence", 0.0)
        message_text = latest.get("text", "")
        
        # Scrub PII (phone numbers, emails) from message text
        message_text = re.sub(r'\+?\d{10,13}', '[PHONE]', message_text)
        message_text = re.sub(r'\S+@\S+\.\S+', '[EMAIL]', message_text)
        
        # Anonymize User ID
        sender_id = tracker.sender_id
        hashed_id = get_anon_id(sender_id)
        session_id = tracker.sender_id # Using sender_id as session_id for simplicity
        
        # Check for fallback
        is_fallback = intent_name == "nlu_fallback" or confidence < 0.75
        
        # Get metadata and slots
        metadata = tracker.get_slot("session_started_metadata") or latest.get("metadata", {})
        platform = metadata.get("platform", "app")
        lang = tracker.get_slot("language") or metadata.get("language", "en")
        county = tracker.get_slot("county")
        service_name = tracker.get_slot("current_service")
        
        conn = sqlite3.connect(SERVICES_DB)
        cur = conn.cursor()
        
        # 1. Update/Insert User
        cur.execute("""
            INSERT INTO users (user_id, language, platform, county, last_seen)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET 
                language = EXCLUDED.language,
                platform = EXCLUDED.platform,
                county = COALESCE(EXCLUDED.county, users.county),
                last_seen = CURRENT_TIMESTAMP
        """, (hashed_id, lang, platform, county))

        # 2. Update/Insert Conversation
        cur.execute("""
            INSERT INTO conversations (session_id, user_id, start_time, platform)
            VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(session_id) DO NOTHING
        """, (session_id, hashed_id, platform))

        # 3. Log Message
        cur.execute("""
            INSERT INTO messages (session_id, user_id, message_text, intent, confidence, is_fallback, language, platform)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, hashed_id, message_text, intent_name, confidence, is_fallback, lang, platform))
        
        # 4. Update Intent Analytics
        if intent_name:
            cur.execute("""
                INSERT INTO intent_analytics (intent_name, usage_count, avg_confidence, last_used)
                VALUES (?, 1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(intent_name) DO UPDATE SET 
                    avg_confidence = (avg_confidence * usage_count + ?) / (usage_count + 1),
                    usage_count = usage_count + 1,
                    last_used = CURRENT_TIMESTAMP
            """, (intent_name, confidence, confidence))

        # 5. Log Service Usage if applicable
        if service_name and intent_name not in ["greet", "goodbye", "choose_language", "nlu_fallback"]:
            cur.execute("""
                INSERT INTO service_usage (service_name, county, platform, user_id)
                VALUES (?, ?, ?, ?)
            """, (service_name, county, platform, hashed_id))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DEBUG: Action analytics logging error: {e}")

class ActionServiceMenu(Action):
    def name(self) -> Text:
        return "action_service_menu"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        log_analytics(tracker)
        lang = get_user_lang(tracker)
        if lang == "sw":
            msg = "Chagua huduma:\n1. Hospitali\n2. KRA\n3. SHIF\n4. Huduma Centre\n5. NTSA\n6. Cheti cha Tabia Njema\n7. HELB\n8. Usajili wa Biashara"
        else:
            msg = "Choose a service:\n1. Hospitals\n2. KRA\n3. SHIF\n4. Huduma Centre\n5. NTSA\n6. Good Conduct\n7. HELB\n8. Business Registration"
        dispatcher.utter_message(text=msg)
        return []
