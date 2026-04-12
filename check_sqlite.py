import sqlite3

def check_sqlite():
    print("🔍 Checking SQLite Database (pharmacy.db)...")
    try:
        conn = sqlite3.connect('pharmacy.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT rule_id, drug_name, min_age_yrs, max_age_yrs, gender, max_daily_dose_mg FROM advanced_dosing_rules")
        rows = cursor.fetchall()
        
        if not rows:
            print("⚠️ The 'advanced_dosing_rules' table is currently EMPTY.")
        else:
            print(f"\n✅ Found {len(rows)} dosing rules:\n")
            # Format a nice table header
            print(f"{'ID':<5} | {'Drug Name':<15} | {'Age Range':<10} | {'Gender':<6} | {'Max Dose (mg)':<10}")
            print("-" * 65)
            
            # Print each row dynamically
            for row in rows:
                print(f"{row[0]:<5} | {row[1].upper():<15} | {row[2]}-{row[3]:<7} | {row[4]:<6} | {row[5]:<10}")
                
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"❌ Database Error: {e}\n(Did you run the auto_learner or overnight batch yet?)")

if __name__ == "__main__":
    check_sqlite()