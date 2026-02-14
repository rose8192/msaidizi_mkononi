import sqlite3

conn = sqlite3.connect("data/services.db")
c = conn.cursor()

# Drop old huduma table if exists
c.execute("DROP TABLE IF EXISTS huduma")

# Create new huduma table
c.execute('''CREATE TABLE huduma (
             id INTEGER PRIMARY KEY,
             service TEXT,
             info_sw TEXT,
             link TEXT)''')

# Huduma services
huduma_data = [
    ("National ID Application", 
     "Mahitaji:\n• Birth Certificate (asili au nakala)\n• Parent's ID (if under 18)\n• Form filled at Huduma Centre\n\nHuduma Centres Nairobi: GPO, City Hall, Makadara, Eastleigh",
     "https://www.hudumakenya.go.ke"),
    ("Passport Application", 
     "Mahitaji:\n• National ID\n• Birth Certificate\n• 2 passport photos\n• Form B1 filled online\n• Pay KES 4,500 (32 pages)\n\nApply at Huduma Centre or online",
     "https://immigration.ecitizen.go.ke"),
    ("Birth Certificate Application", 
     "Mahitaji:\n• Hospital notification\n• Parent's ID\n• Form filled at Huduma Centre\n• Fee KES 50-200\n\nProcessing time: 10 days",
     "https://www.hudumakenya.go.ke"),
    ("Huduma Centres Nairobi", 
     "• GPO (Posta House)\n• City Hall\n• Makadara\n• Eastleigh\n• Teleposta Towers\n\nHours: Monday-Friday 8AM-5PM",
     "https://www.hudumakenya.go.ke")
]

c.executemany("INSERT INTO huduma (service, info_sw, link) VALUES (?, ?, ?)", huduma_data)

conn.commit()
conn.close()
print("Huduma data added successfully!")