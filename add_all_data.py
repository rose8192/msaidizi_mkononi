import sqlite3

conn = sqlite3.connect("data/services.db")
c = conn.cursor()

# === KRA - Expanded ===
c.execute("DROP TABLE IF EXISTS kra")
c.execute('''CREATE TABLE kra (
             id INTEGER PRIMARY KEY,
             service TEXT,
             steps_sw TEXT,
             link TEXT)''')

kra_data = [
    ("KRA PIN Registration", 
     "1. Ingia https://itax.kra.go.ke\n2. Bonyeza 'New PIN Registration'\n3. Chagua 'Individual'\n4. Jaza ID number, email, phone\n5. Thibitisha na code ya SMS\n6. PIN itatumwa kwa SMS na email",
     "https://www.kra.go.ke/individual/individual-pin-registration"),
    
    ("KRA PIN Requirements", 
     "Mahitaji:\n• National ID au Passport (asili)\n• Email address inayotumika\n• Namba ya simu inayotumika\n• Uwe na umri wa miaka 18+\nHakuna malipo ya kupata PIN",
     "https://www.kra.go.ke"),
    
    ("Lost KRA PIN", 
     "Ili kupata PIN iliyopotea:\n1. Ingia https://itax.kra.go.ke\n2. Bonyeza 'Forgot PIN'\n3. Jaza ID number na email/phone iliyosajiliwa\n4. PIN mpya itatumwa kwa SMS/email",
     "https://itax.kra.go.ke"),
    
    ("Change KRA Email or Phone", 
     "1. Ingia iTax na PIN yako\n2. Bonyeza 'Registration' → 'Amend PIN'\n3. Badilisha email au phone\n4. Thibitisha na OTP",
     "https://itax.kra.go.ke"),
    
    ("KRA Obligations", 
     "Wajibu wa KRA:\n• Wafanyakazi: Lipa PAYE kila mwezi\n• Wafanyabiashara: File returns na lipa kodi\n• Wenye mapato ya ziada: Declare kila mwaka\n• Adhabu kwa kutoa return: KES 2,000+",
     "https://www.kra.go.ke"),
    
    ("File Income Tax Return", 
     "1. Ingia iTax na PIN yako\n2. Bonyeza 'File Return'\n3. Chagua 'Income Tax - Resident Individual'\n4. Jaza mapato yako\n5. Submit na lipa kupitia M-Pesa/Bank",
     "https://itax.kra.go.ke"),
    
    ("Pay Tax", 
     "Lipa kupitia:\n• M-Pesa PayBill 222222 (tumia PIN kama account)\n• Bank transfer\n• iTax portal direct",
     "https://www.kra.go.ke/paying-tax")
]

c.executemany("INSERT INTO kra (service, steps_sw, link) VALUES (?, ?, ?)", kra_data)

# === SHIF - Expanded ===
c.execute("DROP TABLE IF EXISTS shif")
c.execute('''CREATE TABLE shif (
             id INTEGER PRIMARY KEY,
             topic TEXT,
             info_sw TEXT,
             link TEXT)''')

shif_data = [
    ("SHIF Contributions", 
     "Michango: 2.75% ya mshahara (mwajiri 1.375%, mfanyakazi 1.375%) au min KES 300 kwa mwezi.\nWajibu kwa wafanyakazi na wafanyabiashara.",
     "https://sha.go.ke"),
    
    ("How to Join SHIF", 
     "1. Piga *147# au ingia sha.go.ke\n2. Chagua 'Register'\n3. Jaza ID, jina, email, phone\n4. Thibitisha na OTP",
     "https://sha.go.ke"),
    
    ("Pay SHIF", 
     "Lipa via:\n• *147#\n• M-Pesa PayBill 200022 (tumia ID number kama account)\n• Bank",
     "https://sha.go.ke"),
    
    ("SHIF Benefits", 
     "Faida:\n• Huduma hospitali za umma na binafsi\n• Maternity cover\n• Dental na optical\n• Family cover (mke/mume na watoto)\n• No waiting period",
     "https://sha.go.ke"),
    
    ("SHIF Hospital List", 
     "Orodha ya hospitali zinazokubali SHIF inapatikana kwenye app ya SHA au website.\nMifano: Kenyatta, Aga Khan, Nairobi Hospital, Mater, etc.",
     "https://sha.go.ke")
]

c.executemany("INSERT INTO shif (topic, info_sw, link) VALUES (?, ?, ?)", shif_data)

# === Huduma - Expanded ===
c.execute("DROP TABLE IF EXISTS huduma")
c.execute('''CREATE TABLE huduma (
             id INTEGER PRIMARY KEY,
             service TEXT,
             info_sw TEXT,
             link TEXT)''')

huduma_data = [
    ("National ID Application", 
     "Mahitaji:\n• Birth Certificate (asili au nakala)\n• Parent's ID (kwa chini ya 18)\n• Form filled at Huduma Centre\n• Fee: Free for first time",
     "https://www.hudumakenya.go.ke"),
    
    ("Passport Application", 
     "Mahitaji:\n• National ID\n• Birth Certificate\n• 2 passport photos\n• Form B1 filled online\n• Fee: KES 4,500 (32 pages), KES 6,000 (50 pages)\n• Processing: 10 days",
     "https://immigration.ecitizen.go.ke"),
    
    ("Birth Certificate Application", 
     "Mahitaji:\n• Hospital notification\n• Parent's ID\n• Form filled at Huduma Centre\n• Fee KES 50-200\n• Processing time: 10 days",
     "https://www.hudumakenya.go.ke"),
    
    ("Huduma Centres Nairobi", 
     "• GPO (Posta House)\n• City Hall\n• Makadara\n• Eastleigh\n• Teleposta Towers\n• Westlands\nHours: Monday-Friday 8AM-5PM",
     "https://www.hudumakenya.go.ke")
]

c.executemany("INSERT INTO huduma (service, info_sw, link) VALUES (?, ?, ?)", huduma_data)

conn.commit()
conn.close()
print("All services updated with more topics!")