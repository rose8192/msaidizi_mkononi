import requests

def test_rasa():
    try:
        r = requests.get("http://localhost:5005/version", timeout=5)
        print(f"Rasa Version Status: {r.status_code}")
        print(r.text)
    except Exception as e:
        print(f"Rasa not reachable: {e}")

if __name__ == "__main__":
    test_rasa()
