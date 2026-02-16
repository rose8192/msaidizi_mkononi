import requests
import json

FLASK_URL = "http://localhost:10000/chat"

def test_chat(sender, text):
    print(f"\n--- Testing Chat for '{sender}' -> '{text}' ---")
    try:
        payload = {"sender": sender, "message": text}
        r = requests.post(FLASK_URL, json=payload, timeout=30)
        print(f"Status Code: {r.status_code}")
        print(f"Response Text: {r.text}")
        try:
            print(f"Response JSON: {json.dumps(r.json(), indent=2)}")
        except:
            print("Could not parse JSON")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    # Test 'hi' with flutter_user
    test_chat("flutter_user", "hi")
