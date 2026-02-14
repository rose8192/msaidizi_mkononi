from flask import Flask, request
import africastalking

app = Flask(__name__)

# Initialize Africa's Talking
username = "sandbox"  # or your live username
api_key = "your_api_key_here"  # from https://account.africastalking.com/
africastalking.initialize(username, api_key)

# Your shortcode (e.g., 12345 for sandbox, or your live shortcode)
SHORTCODE = "12345"

@app.route('/ussd', methods=['POST'])
def ussd():
    session_id = request.values.get('sessionId')
    phone_number = request.values.get('phoneNumber')
    service_code = request.values.get('serviceCode')
    text = request.values.get('text', '')  # the input the user has entered

    # Clean the text (split into levels)
    levels = text.split('*') if text else []

    # Start the response
    response = ""

    # Level 1: Welcome screen
    if len(levels) == 0:
        response = "CON Karibu Msaidizi Mkononi\n"
        response += "1. Ingia\n"
        response += "2. Sajili\n"
        response += "3. Angalia Salio\n"
        response += "4. Huduma\n"
        response += "5. Nisaidie\n"

    # Level 2: User chose an option
    elif len(levels) == 1:
        if levels[0] == '1':  # Login
            response = "CON Weka namba ya simu au PIN:\n"
        elif levels[0] == '2':  # Register
            response = "CON Sajili\n"
            response += "Weka jina lako kamili:\n"
        elif levels[0] == '3':  # Check balance
            response = "END Salio lako ni KES 1,234.56\nAsante kwa kutumia Msaidizi Mkononi!"
        elif levels[0] == '4':  # Services
            response = "CON Chagua huduma:\n"
            response += "1. Duka\n"
            response += "2. Mikopo\n"
            response += "3. Uhamisho\n"
        elif levels[0] == '5':  # Help
            response = "END Nisaidie:\nPiga 0712345678 au tuma SMS kwa 0712345678"

    # Level 3: Collect full name for registration
    elif len(levels) == 2 and levels[0] == '2':
        full_name = levels[1]
        response = f"CON Salamu {full_name}!\n"
        response += "Weka namba ya simu (bila +254):\n"

    # Level 4: Collect phone number
    elif len(levels) == 3 and levels[0] == '2':
        phone = levels[2]
        # Here you would save to DB, send OTP, etc.
        response = f"CON Umefanikiwa kusajiliwa!\n"
        response += f"Jina: {levels[1]}\nNamba: {phone}\n"
        response += "END Asante kwa kusajiliwa na Msaidizi Mkononi!"

    # Default fallback
    else:
        response = "END Tafadhali jaribu tena baadaye. Tatizo la kiufundi."

    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)