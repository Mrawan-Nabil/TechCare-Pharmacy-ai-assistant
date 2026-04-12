import sqlite3
import chromadb
import requests
import json
import ollama

def check_if_exists(drug_name):
    """Checks if the drug is already in the database."""
    conn = sqlite3.connect('pharmacy.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM advanced_dosing_rules WHERE drug_name = ?", (drug_name.lower(),))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

def get_existing_rules(drug_name):
    """Fetches current DB rules as a list of dictionaries for clean Streamlit rendering."""
    conn = sqlite3.connect('pharmacy.db')
    conn.row_factory = sqlite3.Row # This forces SQLite to return dictionary-like rows
    cursor = conn.cursor()
    cursor.execute("""
        SELECT concentration, indication, min_age_yrs, max_age_yrs, gender, max_daily_dose_mg 
        FROM advanced_dosing_rules WHERE drug_name = ?
    """, (drug_name.lower(),))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def verify_rule_integrity(rule, drug_name):
    """The Safety Net: Runs mathematical bounds-checking on the LLM's output."""
    try:
        min_age = int(rule.get('min_age_yrs', 0))
        max_age = int(rule.get('max_age_yrs', 120))
        max_dose = float(rule.get('max_daily_dose_mg', 0.0))
        
        if min_age > max_age: return False
        if max_dose > 10000: return False
        if max_dose < 0 or min_age < 0: return False

        return True
    except Exception as e:
        return False

def extract_dosing_rules_with_llm(drug_name, fda_dosage_text, fda_indications_text):
    print(f"🧠 [BioMistral] Analyzing FDA dosage data for {drug_name}...")
    system_prompt = """
    You are an expert clinical data extraction API. 
    Read the provided FDA Dosage and Administration text and Indications text.
    Extract the maximum daily safe dosages based on patient age, gender, concentration, and indication.
    
    CRITICAL RULES:
    1. Convert ALL units to milligrams (mg). If it says 290 mcg, output 0.29.
    2. Extract the specific 'concentration'. If not specified, output 'UNKNOWN'.
    3. Extract the specific 'indication'. If general, output 'General'.
    4. If a rule applies to adults, set min_age_yrs to 18 and max_age_yrs to 120.
    
    You MUST output ONLY a JSON array of objects:
    [
        {
            "concentration": (string),
            "indication": (string),
            "min_age_yrs": (integer),
            "max_age_yrs": (integer),
            "gender": (string: "M", "F", or "ALL"),
            "max_daily_dose_mg": (float)
        }
    ]
    """
    user_prompt = f"DRUG: {drug_name}\nINDICATIONS:\n{fda_indications_text}\nDOSAGE TEXT:\n{fda_dosage_text}"

    try:
        response = ollama.chat(model='biomistral', messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ], format='json')
        
        raw_data = json.loads(response['message']['content'])
        if isinstance(raw_data, dict):
            for key, value in raw_data.items():
                if isinstance(value, list): return value
            return [raw_data]
        return raw_data
    except Exception as e:
        return []

def fetch_new_rules_dry_run(drug_name):
    """Hits the FDA, runs the LLM, and returns valid rules WITHOUT saving to SQLite."""
    url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{drug_name}\"&limit=1"
    try:
        response = requests.get(url)
        if response.status_code != 200: return []

        drug_data = response.json()['results'][0]
        fda_warnings = drug_data.get('warnings', ['No warnings listed.'])[0]
        fda_dosage_text = drug_data.get('dosage_and_administration', ['No dosage listed.'])[0]
        fda_interactions = drug_data.get('drug_interactions', ['No interactions listed.'])[0]
        fda_indications_text = drug_data.get('indications_and_usage', ['No indications listed.'])[0]
        
        chroma_text = f"DRUG: {drug_name}\nINDICATIONS: {fda_indications_text}\nWARNINGS: {fda_warnings}\nINTERACTIONS: {fda_interactions}\nDOSAGE: {fda_dosage_text}"
        
        if len(chroma_text.strip()) > 100:
            chroma_client = chromadb.PersistentClient(path="./chroma_data")
            collection = chroma_client.get_or_create_collection(name="drug_interactions")
            collection.upsert(
                documents=[chroma_text],
                ids=[drug_name.lower()],
                metadatas=[{"source": "OpenFDA API"}]
            )

        structured_rules = extract_dosing_rules_with_llm(drug_name, fda_dosage_text, fda_indications_text)
        
        valid_rules = []
        if structured_rules:
            for rule in structured_rules:
                if isinstance(rule, dict) and verify_rule_integrity(rule, drug_name):
                    # Clean the dict to match DB columns exactly
                    clean_rule = {
                        "concentration": str(rule.get('concentration', 'UNKNOWN')),
                        "indication": str(rule.get('indication', 'General')),
                        "min_age_yrs": int(rule.get('min_age_yrs', 0)),
                        "max_age_yrs": int(rule.get('max_age_yrs', 120)),
                        "gender": str(rule.get('gender', 'ALL')),
                        "max_daily_dose_mg": float(rule.get('max_daily_dose_mg', 0.0))
                    }
                    valid_rules.append(clean_rule)
        return valid_rules
    except Exception as e:
        return []

def save_rules_to_db(drug_name, valid_rules):
    """Executes the SQLite Overwrite."""
    if not valid_rules: return False
    conn = sqlite3.connect('pharmacy.db')
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM advanced_dosing_rules WHERE drug_name = ?", (drug_name.lower(),))
        for rule in valid_rules:
            cursor.execute("""
                INSERT INTO advanced_dosing_rules 
                (drug_name, concentration, indication, min_age_yrs, max_age_yrs, gender, max_daily_dose_mg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                drug_name.lower(), rule['concentration'], rule['indication'], 
                rule['min_age_yrs'], rule['max_age_yrs'], rule['gender'], rule['max_daily_dose_mg']
            ))
        conn.commit()
        return True
    except Exception as e:
        return False
    finally:
        conn.close()

def learn_and_save_drug(drug_name, interactive=False):
    """The automated batch version. Skips if exists unless approved."""
    if check_if_exists(drug_name):
        if not interactive:
            print(f"⏭️ {drug_name.upper()} exists. Skipping in batch mode.")
            return True
            
    print(f"🌐 Fetching {drug_name.upper()}...")
    rules = fetch_new_rules_dry_run(drug_name)
    if rules:
        return save_rules_to_db(drug_name, rules)
    return False

if __name__ == "__main__":
    learn_and_save_drug("linaclotide", interactive=True)