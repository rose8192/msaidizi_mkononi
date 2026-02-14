from flask import Flask, request

app = Flask(__name__)

def get_response(text=""):
    if not text:
        return "CON Karibu Msaidizi Mkononi!\n1. Hospitali\n2. KRA\n3. SHIF\n4. Huduma\n0. Toka"
    if "1" in text:
        return "CON Hospitali:\n1. Nairobi Level 5\n2. Kisumu Level 5\n0. Rudi"
    if "1.1" in text:
        return "END Mama Lucy Kibaki Hospital\nPhone: 0733333333"
    if "0" in text:
        return "END Asante! Karibu tena."
    return "CON Samahani, sielewi. Jaribu tena."

@app.route('/ussd', methods=['POST'])
def ussd():
    text = request.values.get('text', '')
    response = get_response(text)
    return response

if __name__ == '__main__':
    app.run(port=5000, debug=True)