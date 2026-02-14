# voice_input.py - Standalone Voice Mode for Msaidizi Mkononi
import speech_recognition as sr
import requests
import time
import pyttsx3  # For TTS (speak replies)

# Configuration
RASA_URL = "http://localhost:5005/webhooks/rest/webhook"
SENDER_ID = "voice_user"  # Fixed sender ID for session persistence

def get_swahili_voice(engine):
    voices = engine.getProperty('voices')
    # Try to find a Swahili-sounding voice or just a good female voice
    for voice in voices:
        if "swahili" in voice.name.lower() or "sw-ke" in voice.languages:
            return voice.id
    # Fallback to Zira or any female voice often used for assistants
    for voice in voices:
        if "zira" in voice.name.lower() or "female" in voice.name.lower():
            return voice.id
    return None

# TTS engine setup
engine = pyttsx3.init()
engine.setProperty('rate', 160)    # Slightly faster for natural flow
engine.setProperty('volume', 1.0)

sw_voice = get_swahili_voice(engine)
if sw_voice:
    engine.setProperty('voice', sw_voice)

def speech_to_text():
    r = sr.Recognizer()
    # Adjust recognition sensitivity
    r.energy_threshold = 4000  # Standard threshold for voice
    r.dynamic_energy_threshold = True
    
    with sr.Microphone() as source:
        print("\n[LISTENING] Speak now (Swahili or English)...")
        # Reduce ambient noise impact
        r.adjust_for_ambient_noise(source, duration=0.8)
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=12)
        except sr.WaitTimeoutError:
            print("[IDLE] No speech detected.")
            return None

    print("[PROCESSING] Recognizing...")
    try:
        # Try Swahili first (KE region)
        text = r.recognize_google(audio, language="sw-KE")
        print(f"You said: {text}")
        return text
    except sr.UnknownValueError:
        # Fallback to English (KE region)
        try:
            text = r.recognize_google(audio, language="en-KE")
            print(f"You said: {text}")
            return text
        except sr.UnknownValueError:
            print("[ERROR] Could not understand audio.")
            return None
    except sr.RequestError as e:
        print(f"[ERROR] Google Speech API Error: {e}")
        return None

def send_to_rasa(message):
    if not message:
        return

    payload = {
        "sender": SENDER_ID,
        "message": message
    }

    try:
        response = requests.post(RASA_URL, json=payload, timeout=10)
        response.raise_for_status()
        rasa_replies = response.json()

        if rasa_replies and rasa_replies[0].get("text"):
            reply_text = rasa_replies[0]["text"]
            print(f"Bot: {reply_text}")
            
            # Speak the reply (TTS uncommented)
            engine.say(reply_text)
            engine.runAndWait()
        else:
            print("Bot: Hakuna jibu (no reply from Rasa)")
            engine.say("Samahani, sielewi.")
            engine.runAndWait()
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Rasa: {e}")
        engine.say("Tatizo la kiufundi. Jaribu tena.")
        engine.runAndWait()

def main():
    print("=== MSAIDIZI MKONONI - VOICE MODE ===")
    print("Speak in Swahili or English. Say 'toka', 'exit' or 'bye' to quit.")
    print("Make sure Rasa core & actions are running!\n")

    while True:
        user_text = speech_to_text()
        if user_text:
            lower_text = user_text.lower()
            if any(word in lower_text for word in ["toka", "exit", "bye"]):
                print("Asante kwa kutumia Msaidizi Mkononi! Karibu tena.")
                engine.say("Asante kwa kutumia Msaidizi Mkononi! Karibu tena.")
                engine.runAndWait()
                break
            send_to_rasa(user_text)
        time.sleep(0.5)  # small pause to avoid rapid re-listening

if __name__ == "__main__":
    main()