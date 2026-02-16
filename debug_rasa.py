import requests
import json

RASA_URL = "http://localhost:5005"

def test_nlu(text):
    print(f"\n--- Testing NLU for '{text}' ---")
    try:
        url = f"{RASA_URL}/model/parse"
        payload = {"text": text}
        r = requests.post(url, json=payload)
        if r.status_code == 200:
            data = r.json()
            intent = data.get("intent", {})
            print(f"Intent: {intent.get('name')} (confidence: {intent.get('confidence')})")
            print("Entities:", data.get("entities"))
        else:
            print(f"Error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_chat(text):
    print(f"\n--- Testing Chat for '{text}' ---")
    try:
        url = f"{RASA_URL}/webhooks/rest/webhook"
        payload = {"sender": "debug_user", "message": text}
        r = requests.post(url, json=payload)
        if r.status_code == 200:
            responses = r.json()
            print(f"Responses: {json.dumps(responses, indent=2)}")
        else:
            print(f"Error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_nlu("hi")
    test_chat("hi")
