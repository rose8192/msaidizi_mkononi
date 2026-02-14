import sqlite3

conn = sqlite3.connect("data/services.db")
c = conn.cursor()

# Drop old kra table
c.execute("DROP TABLE IF EXISTS kra")

# Create new kra table
c.execute('''CREATE TABLE kra (
             id INTEGER PRIMARY KEY,
             service TEXT,
             steps_sw TEXT,
             link TEXT)''')

# Expanded KRA data
kra_data = [
    ("KRA PIN Registration", 
     "1. Ingia https://itax.kra.go.ke\n2. Bonyeza 'New PIN Registration'\n3. Chagua 'Individual'\n4. Jaza ID number, email, phone\n5. Thibitisha na code ya SMS\n6. PIN itatumwa kwa SMS na email",
     "https://www.kra.go.ke/individual/individual-pin-registration"),
    
    ("KRA PIN Requirements", 
     "Mahitaji:\n• National ID au Passport (asili)\n• Email address inayotumika\n• Namba ya simu inayotumika\n• Uwe na umri wa miaka 18+\nHakuna malipo ya kupata PIN",
     "https://www.kra.go.ke"),
    
    ("File Income Tax Return", 
     "1. Ingia iTax na PIN yako\n2. Bonyeza 'File Return'\n3. Chagua 'Income Tax - Resident Individual'\n4. Jaza mapato yako (mshahara, biashara, etc)\n5. Submit na lipa kodi kupitia M-Pesa au Bank",
     "https://itax.kra.go.ke"),
    
    ("Pay Tax", 
     "Lipa kupitia:\n• M-Pesa PayBill 222222 (tumia PIN kama account number)\n• Bank transfer\n• iTax portal direct payment",
     "https://www.kra.go.ke/paying-tax")
]

c.executemany("INSERT INTO kra (service, steps_sw, link) VALUES (?, ?, ?)", kra_data)

conn.commit()
conn.close()
print("KRA data updated with requirements and more details!")