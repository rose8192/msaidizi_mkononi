# ussd_simulator.py - BILINGUAL + CONTINUOUS SESSION
import sqlite3

DB_PATH = "data/services.db"

current_lang = "sw"  # Default

def set_language(choice):
    global current_lang
    if choice == "1":
        current_lang = "sw"
        return "Kiswahili imechaguliwa"
    elif choice == "2":
        current_lang = "en"
        return "English selected"
    return "Invalid"

def get_text(key):
    texts = {
        "welcome": {"sw": "Karibu Msaidizi Mkononi!\nChagua lugha:\n1. Kiswahili\n2. English", "en": "Welcome!\nChoose language:\n1. Swahili\n2. English"},
        "main_menu": {"sw": "1. Hospitali\n2. KRA\n3. SHIF\n4. Huduma\n0. Toka", "en": "1. Hospitals\n2. KRA\n3. SHIF\n4. Huduma\n0. Exit"},
        "hospital_county": {"sw": "Chagua kaunti:\n1. Nairobi\n2. Kisumu\n0. Rudi", "en": "Choose county:\n1. Nairobi\n2. Kisumu\n0. Back"},
        "hospital_level": {"sw": "Chagua level:\n1. Level 5\n2. Level 6\n0. Rudi", "en": "Choose level:\n1. Level 5\n2. Level 6\n0. Back"},
        "kra_pin": {"sw": "Hatua za KRA PIN:\n1. Ingia itax.kra.go.ke\n2. Bonyeza 'Register'\nLink: https://www.kra.go.ke", "en": "KRA PIN Steps:\n1. Go to itax.kra.go.ke\n2. Click 'Register'\nLink: https://www.kra.go.ke"},
        "invalid": {"sw": "Samahani, sielewi. Jaribu tena.", "en": "Sorry, I don't understand. Try again."},
        "thanks": {"sw": "Asante! Karibu tena.", "en": "Thank you! Welcome again."}
    }
    return texts.get(key, {"sw": "", "en": ""})[current_lang]

def ussd_menu(text=""):
    global current_lang
    parts = text.split(".")
    
    if not text:
        return "CON " + get_text("welcome")
    
    if len(parts) == 1 and parts[0] in ["1", "2"]:
        lang_msg = set_language(parts[0])
        return "CON " + lang_msg + "\n\n" + get_text("main_menu")
    
    if len(parts) == 1 and parts[0] == "1":
        return "CON " + get_text("hospital_county")
    
    if parts[-1] == "1" and len(parts) == 2:
        return "CON " + get_text("hospital_level")
    
    if parts[-1] == "1" and len(parts) == 3:
        return "END Nairobi Level 5 Hospitals:\n• Mama Lucy Kibaki - 0733333333\n• Pumwani Maternity - 0725890123"
    
    if "2" in parts:
        return "END " + get_text("kra_pin")
    
    if "0" in parts:
        return "END " + get_text("thanks")
    
    return "CON " + get_text("invalid") + "\n\n" + get_text("main_menu")

print("=== MSAIDIZI MKONONI BILINGUAL SIMULATOR ===")
text = ""
while True:
    menu = ussd_menu(text)
    print("\n" + menu)
    if "END" in menu:
        break
    user_input = input("\nYour choice → ").strip()
    if user_input == "0":
        print("\nEND " + get_text("thanks"))
        break
    if not text:
        text = user_input
    else:
        text += "." + user_input