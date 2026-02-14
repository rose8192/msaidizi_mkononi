import sqlite3

conn = sqlite3.connect("data/services.db")
c = conn.cursor()

# Add english columns
c.execute("ALTER TABLE kra ADD COLUMN steps_en TEXT")
c.execute("ALTER TABLE kra ADD COLUMN link_en TEXT")  # same as sw, but optional

c.execute("ALTER TABLE shif ADD COLUMN info_en TEXT")
c.execute("ALTER TABLE huduma ADD COLUMN info_en TEXT")

# Update KRA with English
kra_en = [
    ("KRA PIN Registration", "1. Go to https://itax.kra.go.ke\n2. Click 'New PIN Registration'\n3. Select 'Individual'\n4. Fill ID, email, phone\n5. PIN sent via SMS", "https://www.kra.go.ke/individual/individual-pin-registration"),
    ("KRA PIN Requirements", "Requirements:\n• National ID or Passport\n• Active email\n• Active phone number\n• Age 18+\nNo fee for PIN", "https://www.kra.go.ke"),
    ("Lost KRA PIN", "To recover lost PIN:\n1. Go to itax.kra.go.ke\n2. Click 'Forgot PIN'\n3. Enter ID and registered email/phone\n4. New PIN sent via SMS/email", "https://itax.kra.go.ke"),
    ("Change KRA Email or Phone", "1. Log in to iTax\n2. Go to 'Registration' → 'Amend PIN'\n3. Update email or phone\n4. Verify with OTP", "https://itax.kra.go.ke"),
    ("KRA Obligations", "KRA duties:\n• Employees: PAYE monthly\n• Businesses: File returns and pay tax\n• Additional income: Declare annually\n• Penalty for late return: KES 2,000+", "https://www.kra.go.ke"),
    ("File Income Tax Return", "1. Log in to iTax\n2. Click 'File Return'\n3. Select 'Income Tax - Resident Individual'\n4. Fill income\n5. Submit and pay via M-Pesa/Bank", "https://itax.kra.go.ke"),
    ("Pay Tax", "Pay via:\n• M-Pesa PayBill 222222 (use PIN as account)\n• Bank transfer\n• iTax portal", "https://www.kra.go.ke/paying-tax")
]

for service, steps_en, link in kra_en:
    c.execute("UPDATE kra SET steps_en = ? WHERE service = ?", (steps_en, service))

# SHIF English
shif_en = [
    ("SHIF Contributions", "Contributions: 2.75% of salary (employer 1.375%, employee 1.375%) or min KES 300/month.\nMandatory for employees and self-employed.", "https://sha.go.ke"),
    ("How to Join SHIF", "1. Dial *147# or visit sha.go.ke\n2. Select 'Register'\n3. Fill ID, name, email, phone\n4. Confirm with OTP", "https://sha.go.ke"),
    ("Pay SHIF", "Pay via:\n• *147#\n• M-Pesa PayBill 200022 (use ID as account)\n• Bank", "https://sha.go.ke"),
    ("SHIF Benefits", "Benefits:\n• Public and private hospital care\n• Maternity cover\n• Dental and optical\n• Family cover (spouse + children)\n• No waiting period", "https://sha.go.ke"),
    ("SHIF Hospital List", "List of SHIF hospitals available on SHA app or website.\nExamples: Kenyatta, Aga Khan, Nairobi Hospital, Mater, etc.", "https://sha.go.ke")
]

for topic, info_en, link in shif_en:
    c.execute("UPDATE shif SET info_en = ? WHERE topic = ?", (info_en, topic))

# Huduma English
huduma_en = [
    ("National ID Application", "Requirements:\n• Birth Certificate (original or copy)\n• Parent's ID (if under 18)\n• Form filled at Huduma Centre\n• Fee: Free for first time", "https://www.hudumakenya.go.ke"),
    ("Passport Application", "Requirements:\n• National ID\n• Birth Certificate\n• 2 passport photos\n• Form B1 filled online\n• Fee: KES 4,500 (32 pages)\n• Processing: 10 days", "https://immigration.ecitizen.go.ke"),
    ("Birth Certificate Application", "Requirements:\n• Hospital notification\n• Parent's ID\n• Form filled at Huduma Centre\n• Fee KES 50-200\n• Processing: 10 days", "https://www.hudumakenya.go.ke"),
    ("Huduma Centres Nairobi", "• GPO (Posta House)\n• City Hall\n• Makadara\n• Eastleigh\n• Teleposta Towers\n• Westlands\nHours: Monday-Friday 8AM-5PM", "https://www.hudumakenya.go.ke")
]

for service, info_en, link in huduma_en:
    c.execute("UPDATE huduma SET info_en = ? WHERE service = ?", (info_en, service))

conn.commit()
conn.close()
print("Bilingual data added — English + Kiswahili!")