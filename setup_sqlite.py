import sqlite3

def setup_database():
    print("⚙️ Setting up TechCare SQLite Database...")
    conn = sqlite3.connect('pharmacy.db')
    cursor = conn.cursor()
    
    # 1. Destroy any old tables so we don't have schema conflicts
    cursor.execute('DROP TABLE IF EXISTS drugs')
    cursor.execute('DROP TABLE IF EXISTS advanced_dosing_rules')

    # 2. Create the new, advanced indication-based table
    cursor.execute('''
        CREATE TABLE advanced_dosing_rules (
            rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name TEXT NOT NULL,
            concentration TEXT NOT NULL, -- e.g., '400mg/5mL' or '875mg'
            indication TEXT DEFAULT 'General', -- e.g., 'Pneumonia' or 'Otitis Media'
            min_age_yrs INTEGER NOT NULL,
            max_age_yrs INTEGER NOT NULL,
            gender TEXT NOT NULL DEFAULT 'ALL',
            max_daily_dose_mg REAL NOT NULL
        );
    ''')

    conn.commit()
    conn.close()

    print("✅ Database setup complete! Schema is ready for Indication-Based Prescribing.")
    print("⚠️ NOTE: The database is now empty. Run your overnight batch script to populate it!")

if __name__ == "__main__":
    setup_database()