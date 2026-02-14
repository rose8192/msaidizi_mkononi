# actions/actions.py
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)

CURRENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(CURRENT_DIR, "data", "services.db")

def get_language(tracker: Tracker) -> str:
    return tracker.get_slot("language") or "sw"

def is_swahili(lang: str) -> bool:
    return lang == "sw"

class ActionHospitalSearch(Action):
    def name(self) -> Text:
        return "action_hospital_search"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        text = tracker.latest_message.get("text", "").lower().strip()

        # Log incoming message
        logging.info(f"Hospital search - user message: '{text}' | lang: {lang}")

        # Get current slots
        county = tracker.get_slot("county")
        level = tracker.get_slot("level")

        # Parse from text if missing
        if not county:
            counties = ["nairobi", "kisumu", "mombasa", "nakuru", "nyeri", "eldoret", "kiambu", "machakos"]
            for c in counties:
                if c in text:
                    county = c.title()
                    break

        if not level:
            level_map = {
                "1": "1", "level 1": "1", "i": "1",
                "2": "2", "level 2": "2", "ii": "2",
                "3": "3", "level 3": "3", "iii": "3",
                "4": "4", "level 4": "4", "iv": "4",
                "5": "5", "level 5": "5", "v": "5",
                "6": "6", "level 6": "6", "vi": "6"
            }
            for kw, lvl in level_map.items():
                if kw in text:
                    level = lvl
                    break

        # Ask for missing info
        if not county:
            msg = "Please type the county name (e.g. Nyeri, Nairobi, Kisumu):" if not is_sw else "Tafadhali andika jina la kaunti (mfano: Nyeri, Nairobi, Kisumu):"
            dispatcher.utter_message(text=msg)
            return [SlotSet("requested_slot", "county")]

        if not level:
            msg = "Please type the hospital level (e.g. Level 5 or 5):" if not is_sw else "Tafadhali andika level ya hospitali (mfano: Level 5 au 5):"
            dispatcher.utter_message(text=msg)
            return [SlotSet("requested_slot", "level")]

        # Set memory
        events = [SlotSet("current_service", "hospital")]

        # Query DB
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "SELECT name, ownership, level FROM hospitals WHERE LOWER(county) LIKE ? AND LOWER(level) LIKE ? LIMIT 10",
                (f"%{county.lower()}%", f"%{level}%")
            )
            results = c.fetchall()
            conn.close()

            if results:
                msg = f"Level {level} hospitals in {county.capitalize()}:\n" if not is_sw else f"Hospitali za Level {level} katika {county.capitalize()}:\n"
                for name, ownership, db_level in results:
                    msg += f"- {name} (Level {db_level}, {ownership or 'N/A'})\n"
                msg += "\nYou can visit any of these directly or search Google Maps for directions." if not is_sw else "\nUnaweza kutembelea moja yoyote moja kwa moja au tumia Google Maps kupata mwelekeo."
            else:
                msg = f"No Level {level} hospitals found in {county.capitalize()}. Try another level or county." if not is_sw else f"Hakuna hospitali za Level {level} katika {county.capitalize()}. Jaribu level au kaunti nyingine."
        except Exception as e:
            logging.error(f"Hospital search error: {str(e)}")
            msg = "Technical issue while searching hospitals. Please try again later." if not is_sw else "Tatizo la kiufundi wakati wa kutafuta hospitali. Tafadhali jaribu tena baadaye."

        dispatcher.utter_message(text=msg)
        return events + [SlotSet("county", None), SlotSet("level", None), SlotSet("requested_slot", None)]

class ActionKRAInfo(Action):
    def name(self) -> Text:
        return "action_kra_info"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        text = tracker.latest_message.get("text", "").lower()

        events = [SlotSet("current_service", "kra")]

        current_topic = None
        if any(x in text for x in ["file return", "return", "file", "kurudisha", "submit return"]):
            current_topic = "file_return"
            msg = (
                "Filing Income Tax Return (KRA):\n"
                "1. Log in to iTax portal: https://itax.kra.go.ke\n"
                "2. Go to 'Returns' → 'File Return'\n"
                "3. Select the correct return type (individual, business, etc.)\n"
                "4. Fill in income, deductions, and taxes\n"
                "5. Submit and pay any balance due\n"
                "Deadline: Usually 30th June each year for individuals.\n"
                "Need help with a specific step or type of return?"
            ) if not is_sw else (
                "Kusajili Kurudi kwa Mapato (KRA):\n"
                "1. Ingia kwenye iTax portal: https://itax.kra.go.ke\n"
                "2. Nenda 'Returns' → 'File Return'\n"
                "3. Chagua aina ya kurudi (binafsi, biashara, n.k.)\n"
                "4. Jaza mapato, makato, na kodi\n"
                "5. Wasilisha na ulipe salio lolote\n"
                "Muda: Kwa kawaida 30 Juni kila mwaka kwa binafsi.\n"
                "Unahitaji msaada katika hatua gani?"
            )

        elif any(x in text for x in ["lost pin", "potea", "kupoteza", "reset pin"]):
            current_topic = "lost_pin"
            msg = (
                "Recovering Lost KRA PIN:\n"
                "1. Visit https://itax.kra.go.ke\n"
                "2. Click 'Forgot PIN'\n"
                "3. Enter your National ID number\n"
                "4. Verify with email/phone\n"
                "5. Reset and receive new PIN\n"
                "You can also visit any Huduma Centre with your ID.\n"
                "Need help with the online process?"
            ) if not is_sw else (
                "Kupata PIN ya KRA Iliyopotea:\n"
                "1. Tembelea https://itax.kra.go.ke\n"
                "2. Bonyeza 'Forgot PIN'\n"
                "3. Weka namba yako ya Kitambulisho\n"
                "4. Thibitisha kwa barua pepe au simu\n"
                "5. Weka upya na upokee PIN mpya\n"
                "Unaweza pia kwenda Huduma Centre yoyote na ID yako.\n"
                "Unahitaji msaada katika hatua za mtandaoni?"
            )

        else:
            # General KRA overview
            msg = (
                "Kenya Revenue Authority (KRA) handles taxes and revenue collection in Kenya.\n"
                "Main services:\n"
                "• KRA PIN registration & recovery\n"
                "• Filing annual income tax returns\n"
                "• Paying taxes (VAT, PAYE, corporate tax)\n"
                "• Managing obligations and compliance\n\n"
                "What do you need help with today: PIN, lost PIN, filing returns, payments, or something else?"
            ) if not is_sw else (
                "Kenya Revenue Authority (KRA) inashughulikia ushuru na ukusanyaji wa mapato nchini Kenya.\n"
                "Huduma kuu:\n"
                "• Usajili na upatikanaji wa KRA PIN\n"
                "• Kusajili kurudi kwa mapato kila mwaka\n"
                "• Kulipa kodi (VAT, PAYE, kodi ya kampuni)\n"
                "• Kusimamia wajibu na uzingatiaji\n\n"
                "Unahitaji msaada leo na nini: PIN, PIN iliyopotea, kurudi kwa mapato, malipo, au nini kingine?"
            )

        if current_topic:
            events.append(SlotSet("current_topic", current_topic))

        dispatcher.utter_message(text=msg)
        return events

class ActionSHIFInfo(Action):
    def name(self) -> Text:
        return "action_shif_info"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        text = tracker.latest_message.get("text", "").lower().strip()

        events = [SlotSet("current_service", "shif")]

        current_topic = tracker.get_slot("current_topic")

        if not current_topic:
            # First time → show general + menu
            msg = (
                "SHIF (Social Health Insurance Fund) ni mpango wa bima ya afya ya kitaifa unaochukua nafasi ya NHIF.\n"
                "• Mchango: KSh 500 kwa mtu au familia (hadi wanachama 6)\n"
                "• Faida: Huduma za hospitali kwa gharama ndogo au bure\n"
                "Sajili kwenye https://shif.go.ke au Huduma Centre.\n\n"
                "Chagua nini unahitaji:\n"
                "1. Jinsi ya kujiunga\n2. Michango na malipo\n3. Faida na hospitali\n4. Nyingine"
            ) if not is_sw else (
                "SHIF ni bima ya afya ya kitaifa inayochukua nafasi ya NHIF.\n"
                "• Mchango: KSh 500 kwa mtu/familia (hadi 6)\n"
                "• Faida: Huduma za hospitali kwa gharama nafuu\n"
                "Sajili https://shif.go.ke au Huduma Centre.\n\n"
                "Chagua:\n1. Kujiunga\n2. Michango na malipo\n3. Faida na hospitali\n4. Nyingine"
            )
        elif "kujiunga" in text or "join" in text or "sajili" in text or current_topic == "kujiunga":
            msg = (
                "Jinsi ya kujiunga na SHIF:\n"
                "1. Tembelea https://shif.go.ke au pakua app\n"
                "2. Sajili kwa Kitambulisho cha Taifa\n"
                "3. Chagua mpango (binafsi au familia)\n"
                "4. Lipa KSh 500 ya kwanza\n"
                "Au nenda Huduma Centre au ofisi za zamani za NHIF.\n"
                "Hitaji: ID halali."
            ) if not is_sw else msg  # add Swahili version similarly

        elif "michango" in text or "contribution" in text or "lipa" in text or "malipo" in text or current_topic == "michango":
            msg = (
                "Michango ya SHIF:\n"
                "• Binafsi au familia (hadi 6): KSh 500/mwezi\n"
                "• Zaidi ya 6: KSh 500 + KSh 100 kwa kila mtu wa ziada\n"
                "Lipa kupitia:\n"
                "• M-PESA Paybill 222222\n"
                "• eCitizen\n"
                "• Huduma Centre au benki"
            ) if not is_sw else msg

        elif "faida" in text or "benefits" in text or "hospitali" in text or current_topic == "faida":
            msg = (
                "Faida za SHIF:\n"
                "• Huduma za hospitali (outpatient, inpatient, uzazi, dialysis, chemotherapy, upasuaji)\n"
                "• Gharama ndogo au bure kwa huduma zilizoidhinishwa\n"
                "• Inakubaliwa katika hospitali nyingi za umma na binafsi"
            ) if not is_sw else msg

        else:
            # Fallback to general + menu
            msg = (
                "SHIF ni bima ya afya inayochukua nafasi ya NHIF.\n"
                "Chagua:\n1. Kujiunga\n2. Michango\n3. Faida\n4. Nyingine"
            ) if not is_sw else msg

        dispatcher.utter_message(text=msg)
        return events

class ActionKRAInfo(Action):
    def name(self) -> Text:
        return "action_kra_info"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        text = tracker.latest_message.get("text", "").lower().strip()

        # FIX: Handle menu number "2"
        if text == "2":
            events = [SlotSet("current_service", "kra")]
            msg = (
                "Kenya Revenue Authority (KRA) handles taxes and revenue collection in Kenya.\n"
                "Main services:\n"
                "• KRA PIN registration & recovery\n"
                "• Filing annual income tax returns\n"
                "• Paying taxes (VAT, PAYE, corporate tax)\n"
                "• Managing obligations and compliance\n\n"
                "What do you need help with today: PIN registration, lost PIN, filing returns, payments, or something else?"
            ) if not is_sw else (
                "Kenya Revenue Authority (KRA) inashughulikia ushuru na ukusanyaji wa mapato nchini Kenya.\n"
                "Huduma kuu:\n"
                "• Usajili na upatikanaji wa KRA PIN\n"
                "• Kusajili kurudi kwa mapato kila mwaka\n"
                "• Kulipa kodi (VAT, PAYE, kodi ya kampuni)\n"
                "• Kusimamia wajibu na uzingatiaji\n\n"
                "Unahitaji msaada leo na nini: usajili wa PIN, PIN iliyopotea, kurudi kwa mapato, malipo, au nini kingine?"
            )
            dispatcher.utter_message(text=msg)
            return events

        events = [SlotSet("current_service", "kra")]

        current_topic = None
        
        # FIXED: Added PIN registration keywords
        if any(x in text for x in ["file return", "return", "file", "kurudisha", "submit return", "kurudi", "mapato"]):
            current_topic = "file_return"
            msg = (
                "Filing Income Tax Return (KRA):\n"
                "1. Log in to iTax portal: https://itax.kra.go.ke\n"
                "2. Go to 'Returns' → 'File Return'\n"
                "3. Select the correct return type (individual, business, etc.)\n"
                "4. Fill in income, deductions, and taxes\n"
                "5. Submit and pay any balance due\n"
                "Deadline: Usually 30th June each year for individuals.\n"
                "Need help with a specific step or type of return?"
            ) if not is_sw else (
                "Kusajili Kurudi kwa Mapato (KRA):\n"
                "1. Ingia kwenye iTax portal: https://itax.kra.go.ke\n"
                "2. Nenda 'Returns' → 'File Return'\n"
                "3. Chagua aina ya kurudi (binafsi, biashara, n.k.)\n"
                "4. Jaza mapato, makato, na kodi\n"
                "5. Wasilisha na ulipe salio lolote\n"
                "Muda: Kwa kawaida 30 Juni kila mwaka kwa binafsi.\n"
                "Unahitaji msaada katika hatua gani?"
            )

        elif any(x in text for x in ["lost pin", "potea", "kupoteza", "reset pin", "pin ipotea", "pin nimepoteza"]):
            current_topic = "lost_pin"
            msg = (
                "Recovering Lost KRA PIN:\n"
                "1. Visit https://itax.kra.go.ke\n"
                "2. Click 'Forgot PIN'\n"
                "3. Enter your National ID number\n"
                "4. Verify with email/phone\n"
                "5. Reset and receive new PIN\n"
                "You can also visit any Huduma Centre with your ID.\n"
                "Need help with the online process?"
            ) if not is_sw else (
                "Kupata PIN ya KRA Iliyopotea:\n"
                "1. Tembelea https://itax.kra.go.ke\n"
                "2. Bonyeza 'Forgot PIN'\n"
                "3. Weka namba yako ya Kitambulisho\n"
                "4. Thibitisha kwa barua pepe au simu\n"
                "5. Weka upya na upokee PIN mpya\n"
                "Unaweza pia kwenda Huduma Centre yoyote na ID yako.\n"
                "Unahitaji msaada katika hatua za mtandaoni?"
            )
        
        # FIXED: Added PIN registration response
        elif any(x in text for x in ["pin registration", "usajili", "sajili pin", "register pin", "get pin", "new pin", 
                                     "usajili pin", "usajili wa pin", "pata pin", "tafuta pin", "sajili kra pin"]):
            current_topic = "pin_registration"
            msg = (
                "KRA PIN Registration:\n"
                "1. Visit https://itax.kra.go.ke\n"
                "2. Click 'Register' or 'Get PIN'\n"
                "3. Enter your National ID and personal details\n"
                "4. Verify via email/phone\n"
                "5. Receive PIN instantly\n"
                "Requirements: National ID, email address, phone number.\n"
                "Fee: Free for first registration."
            ) if not is_sw else (
                "Usajili wa KRA PIN:\n"
                "1. Tembelea https://itax.kra.go.ke\n"
                "2. Bonyeza 'Register' au 'Pata PIN'\n"
                "3. Weka Kitambulisho cha Taifa na maelezo ya kibinafsi\n"
                "4. Thibitisha kwa barua pepe au simu\n"
                "5. Pokee PIN mara moja\n"
                "Mahitaji: Kitambulisho cha Taifa, anwani ya barua pepe, namba ya simu.\n"
                "Gharama: Bure kwa usajili wa kwanza."
            )

        else:
            # General KRA overview
            msg = (
                "Kenya Revenue Authority (KRA) handles taxes and revenue collection in Kenya.\n"
                "Main services:\n"
                "• KRA PIN registration & recovery\n"
                "• Filing annual income tax returns\n"
                "• Paying taxes (VAT, PAYE, corporate tax)\n"
                "• Managing obligations and compliance\n\n"
                "What do you need help with today: PIN registration, lost PIN, filing returns, payments, or something else?"
            ) if not is_sw else (
                "Kenya Revenue Authority (KRA) inashughulikia ushuru na ukusanyaji wa mapato nchini Kenya.\n"
                "Huduma kuu:\n"
                "• Usajili na upatikanaji wa KRA PIN\n"
                "• Kusajili kurudi kwa mapato kila mwaka\n"
                "• Kulipa kodi (VAT, PAYE, kodi ya kampuni)\n"
                "• Kusimamia wajibu na uzingatiaji\n\n"
                "Unahitaji msaada leo na nini: usajili wa PIN, PIN iliyopotea, kurudi kwa mapato, malipo, au nini kingine?"
            )

        if current_topic:
            events.append(SlotSet("current_topic", current_topic))

        dispatcher.utter_message(text=msg)
        return events

class ActionHudumaServiceInfo(Action):
    def name(self) -> Text:
        return "action_huduma_service_info"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)
        text = tracker.latest_message.get("text", "").lower()

        events = [SlotSet("current_service", "huduma")]

        current_topic = None
        if any(x in text for x in ["huduma centres", "centres", "6"]):
            current_topic = "huduma_centres"
            msg = "Please type the county name to show Huduma Centres there (e.g. Nyeri, Nairobi, Kisumu):" if not is_sw else "Tafadhali andika jina la kaunti ili nikuonyeshe Huduma Centres zilizopo hapo (mfano: Nyeri, Nairobi, Kisumu):"
            events.append(SlotSet("requested_slot", "county"))
        elif any(x in text for x in ["cheti cha kuzaliwa", "birth certificate", "3"]):
            current_topic = "cheti_cha_kuzaliwa"
            msg = (
                "Birth Certificate Application:\n"
                "• Required: CR12 form, child's birth notification, parents' ID\n"
                "• Fee: KSh 50–200 depending on urgency\n"
                "• Process time: 1–14 days\n"
                "• Where: Nearest Huduma Centre\n\n"
                "Need help with required documents or process steps?"
            ) if not is_sw else (
                "Maombi ya Cheti cha Kuzaliwa:\n"
                "• Inahitajika: Fomu CR12, taarifa ya kuzaliwa ya mtoto, ID za wazazi\n"
                "• Gharama: KSh 50–200 kulingana na haraka\n"
                "• Muda: siku 1–14\n"
                "• Wapi: Huduma Centre ya karibu\n\n"
                "Unahitaji msaada na hati zinazohitajika au hatua za mchakato?"
            )
        elif any(x in text for x in ["kitambulisho", "national id", "1"]):
            current_topic = "kitambulisho"
            msg = (
                "National ID Application:\n"
                "• Required: 2 passport photos, birth certificate, parent's/guardian's ID\n"
                "• Fee: KSh 1,000 (first time)\n"
                "• Age requirement: 18 years and above\n"
                "• Where: Huduma Centre or registration office\n\n"
                "Need help with the full list of documents or appointment booking?"
            ) if not is_sw else (
                "Maombi ya Kitambulisho cha Taifa:\n"
                "• Inahitajika: Picha 2 za pasipoti, cheti cha kuzaliwa, ID ya mzazi/mlezi\n"
                "• Gharama: KSh 1,000 (mara ya kwanza)\n"
                "• Umri: miaka 18 na zaidi\n"
                "• Wapi: Huduma Centre au ofisi ya usajili\n\n"
                "Unahitaji msaada na orodha kamili ya hati au kuweka miadi?"
            )
        else:
            msg = (
                "Huduma Centres provide government services in one location.\n"
                "Common services:\n"
                "• National ID application\n"
                "• Passport application\n"
                "• Birth/death/marriage certificates\n"
                "• Business registration\n\n"
                "What service do you need help with today?"
            ) if not is_sw else (
                "Huduma Centres hutoa huduma za serikali mahali pamoja.\n"
                "Huduma za kawaida:\n"
                "• Maombi ya Kitambulisho cha Taifa\n"
                "• Maombi ya Pasipoti\n"
                "• Cheti cha kuzaliwa/kifo/ndoa\n"
                "• Usajili wa biashara\n\n"
                "Unahitaji msaada na huduma gani leo?"
            )

        if current_topic:
            events.append(SlotSet("current_topic", current_topic))

        dispatcher.utter_message(text=msg)
        return events

class ActionListHudumaCentres(Action):
    def name(self) -> Text:
        return "action_list_huduma_centres"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)
        county = tracker.get_slot("county")

        events = [SlotSet("current_service", "huduma_centres")]

        if not county:
            msg = "Please type the county name." if not is_sw else "Tafadhali andika jina la kaunti."
            dispatcher.utter_message(text=msg)
            return events + [SlotSet("requested_slot", "county")]

        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "SELECT name, location FROM huduma_centres WHERE LOWER(county) LIKE ? LIMIT 5",
                (f"%{county.lower()}%",)
            )
            results = c.fetchall()
            conn.close()

            if results:
                msg = f"Huduma Centres in {county.capitalize()}:\n" if not is_sw else f"Huduma Centres katika {county.capitalize()}:\n"
                for name, location in results:
                    msg += f"- {name} ({location or 'N/A'})\n"
            else:
                msg = f"No Huduma Centres found in {county.capitalize()}. Try another county." if not is_sw else f"Hakuna Huduma Centres zilizopatikana katika {county.capitalize()}. Jaribu kaunti nyingine."
        except Exception as e:
            logging.error(f"Huduma centres error: {str(e)}")
            msg = "Technical issue while searching Huduma Centres." if not is_sw else "Tatizo la kiufundi wakati wa kutafuta Huduma Centres."

        dispatcher.utter_message(text=msg)
        return events + [SlotSet("county", None), SlotSet("requested_slot", None)]

class ActionListHudumaServices(Action):
    def name(self) -> Text:
        return "action_list_huduma_services"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        events = [SlotSet("current_service", "huduma")]

        msg = (
            "Huduma Centre can help with:\n"
            "1. National ID Application\n"
            "2. Passport Application\n"
            "3. Birth Certificate\n"
            "4. Death Certificate\n"
            "5. Marriage Certificate\n"
            "6. Huduma Centres locator\n"
            "7. Other government services\n\n"
            "Type number or name (e.g. 3 or Birth Certificate or Huduma Centres)."
        ) if not is_sw else (
            "Huduma Centre inaweza kukusaidia na:\n"
            "1. Maombi ya Kitambulisho cha Taifa\n"
            "2. Maombi ya Pasipoti\n"
            "3. Maombi ya Cheti cha Kuzaliwa\n"
            "4. Maombi ya Cheti cha Kifo\n"
            "5. Maombi ya Cheti cha Ndoa\n"
            "6. Huduma Centres locator\n"
            "7. Huduma zingine za serikali\n\n"
            "Andika namba au jina (mfano: 3 au Cheti cha Kuzaliwa au Huduma Centres)."
        )

        dispatcher.utter_message(text=msg)
        return events
    
# ────────────────────────────────────────────────
# UTTERANCE ACTIONS (language aware)
# ────────────────────────────────────────────────

class ActionUtterGreet(Action):
    def name(self) -> Text:
        return "action_utter_greet"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        msg = (
            "Welcome to Msaidizi Mkononi! How can I assist you today?"
            if not is_sw else
            "Karibu Msaidizi Mkononi! Unataka msaada na nini?"
        )
        dispatcher.utter_message(text=msg)
        return [SlotSet("language", lang)]

class ActionUtterMenu(Action):
    def name(self) -> Text:
        return "action_utter_menu"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        msg = (
            "Choose a service:\n1. Hospitals\n2. KRA\n3. SHIF\n4. Huduma Centre\n0. Exit"
            if not is_sw else
            "Chagua huduma:\n1. Hospitali\n2. KRA\n3. SHIF\n4. Huduma Centre\n0. Toka"
        )
        dispatcher.utter_message(text=msg)
        return [SlotSet("language", lang)]

class ActionUtterAskCounty(Action):
    def name(self) -> Text:
        return "action_utter_ask_county"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        msg = (
            "Please type the county name (e.g. Nyeri, Nairobi, Kisumu):"
            if not is_sw else
            "Tafadhali andika jina la kaunti (mfano: Nyeri, Nairobi, Kisumu):"
        )
        dispatcher.utter_message(text=msg)
        return [SlotSet("language", lang)]

class ActionUtterAskLevel(Action):
    def name(self) -> Text:
        return "action_utter_ask_level"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        msg = (
            "Please type the hospital level (e.g. Level 5 or 5):"
            if not is_sw else
            "Tafadhali andika level ya hospitali (mfano: Level 5 au 5):"
        )
        dispatcher.utter_message(text=msg)
        return [SlotSet("language", lang)]

class ActionUtterHudumaMenu(Action):
    def name(self) -> Text:
        return "action_utter_huduma_menu"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        lang = get_language(tracker)
        is_sw = is_swahili(lang)

        msg = (
            "Huduma Centre can help with these services:\n"
            "1. National ID\n2. Passport\n3. Birth Certificate\n4. Death Certificate\n5. Marriage Certificate\n"
            "6. Huduma Centres locator\n7. Other services\n\n"
            "Type number or name (e.g. 3 or Birth Certificate or Huduma Centres)."
            if not is_sw else
            "Huduma Centre inaweza kukusaidia na huduma zifuatazo:\n"
            "1. Kitambulisho cha Taifa\n2. Pasipoti\n3. Cheti cha Kuzaliwa\n4. Cheti cha Kifo\n5. Cheti cha Ndoa\n"
            "6. Huduma Centres locator\n7. Huduma zingine\n\n"
            "Andika namba au jina (mfano: 3 au Cheti cha Kuzaliwa au Huduma Centres)."
        )
        dispatcher.utter_message(text=msg)
        return [SlotSet("language", lang)]