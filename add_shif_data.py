import sqlite3

conn = sqlite3.connect("data/services.db")
c = conn.cursor()

# Drop old shif table if exists
c.execute("DROP TABLE IF EXISTS shif")

# Create new shif table
c.execute('''CREATE TABLE shif (
             id INTEGER PRIMARY KEY,
             topic TEXT,
             info_sw TEXT,
             info_en TEXT,
             link TEXT)''')

# SHIF data - Kiswahili and English versions
shif_data = [
    ("SHIF Contributions", 
     "Michango: 2.75% ya mshahara (mwajiri na mfanyakazi wanalipa nusu nusu) au min KES 300 kwa mwezi.\nWajibu kwa wafanyakazi na wafanyabiashara binafsi.",
     "Contributions: 2.75% of salary (employer and employee each pay half) or minimum KES 300 per month.\nMandatory for employees and self-employed.",
     "https://sha.go.ke"),
    
    ("How to Join SHIF", 
     "1. Piga *147# au ingia sha.go.ke\n2. Chagua 'Register'\n3. Jaza ID number, jina, email, phone\n4. Thibitisha na OTP iliyotumwa kwa SMS",
     "1. Dial *147# or visit sha.go.ke\n2. Select 'Register'\n3. Fill ID number, name, email, phone\n4. Confirm with OTP sent via SMS",
     "https://sha.go.ke"),
    
    ("Pay SHIF", 
     "Lipa kupitia:\n• *147#\n• M-Pesa PayBill 200022 (tumia ID number kama account)\n• Bank transfer",
     "Pay via:\n• *147#\n• M-Pesa PayBill 200022 (use ID number as account)\n• Bank transfer",
     "https://sha.go.ke"),
    
    ("SHIF Benefits", 
     "Faida za SHIF:\n• Huduma hospitali za umma na binafsi\n• Maternity cover (kuzaliwa)\n• Dental na optical\n• Family cover (mke/mume na watoto)\n• Hakuna waiting period",
     "SHIF Benefits:\n• Public and private hospital care\n• Maternity cover\n• Dental and optical\n• Family cover (spouse + children)\n• No waiting period",
     "https://sha.go.ke"),
    
    ("SHIF Hospital List", 
     "Orodha ya hospitali zinazokubali SHIF inapatikana kwenye app ya SHA au website.\nMifano: Kenyatta National Hospital, Aga Khan, Nairobi Hospital, Mater, Consolata, etc.",
     "List of SHIF hospitals available on SHA app or website.\nExamples: Kenyatta National Hospital, Aga Khan, Nairobi Hospital, Mater, Consolata, etc.",
     "https://sha.go.ke"),
    
    ("SHIF Hospital Coverage Check", 
     "Kujua hospitali inayokubali SHIF:\n• Hospitali zote za umma (Level 2-6) zinakubali SHIF moja kwa moja.\n• Hospitali nyingi za dini (kama Consolata, PCEA Tumutumu) na binafsi zinakubali SHIF.\n• Baadhi ya kliniki binafsi zinaweza kuwa na huduma chache tu.\n\nIli kuthibitisha hospitali maalum:\n1. Piga *147# → Chagua huduma za SHIF → Tafuta hospitali\n2. Piga hotline ya SHA 0800 720 601 (bure)\n3. Tembelea https://portal.sha.go.ke",
     "To check if a hospital accepts SHIF:\n• All public hospitals (Level 2-6) accept SHIF automatically.\n• Many faith-based (e.g. Consolata, PCEA Tumutumu) and private hospitals are empanelled.\n• Some private clinics may have limited services.\n\nTo verify a specific hospital:\n1. Dial *147# → Select SHIF services → Search facility\n2. Call SHA hotline 0800 720 601 (free)\n3. Visit https://portal.sha.go.ke",
     "https://sha.go.ke")
]

# Insert data (topic is unique, so one row per topic with both languages)
c.executemany("INSERT INTO shif (topic, info_sw, info_en, link) VALUES (?, ?, ?, ?)", shif_data)

conn.commit()
conn.close()
print("SHIF data updated successfully with Hospital Coverage Check feature!")