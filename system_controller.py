import sqlite3
import chromadb
import extractor
import llm_generator
import ocr_reader

def process_prescription(extracted_drug, extracted_dose, patient_current_meds, patient_age, patient_gender):
    """
    The Advanced Hybrid RAG Controller.
    Routes data through demographic-aware SQLite (Math) and ChromaDB (Semantic).
    """
    print(f"\n{'='*50}")
    print(f"🏥 PHARMACY AI: SAFETY CONTROLLER")
    print(f"{'='*50}")
    print(f"Scanned Drug: {extracted_drug}")
    print(f"Scanned Dose: {extracted_dose}mg")
    print(f"Patient Demographics: Age {patient_age}, Gender {patient_gender}")
    print(f"Patient File: Currently taking {patient_current_meds}\n")

    if not extracted_drug or extracted_dose is None:
        return None

    safety_report = {
        "drug": extracted_drug,
        "dose_mg": extracted_dose,
        "dose_flag": False,
        "interaction_flag": False,
        "alerts": [],
        "context_for_llm": ""
    }

    # ==========================================
    # BRANCH 1: SQLite (Demographic Math Check)
    # ==========================================
    print("[System] Checking SQLite for age/gender dosing rules...")
    
    # 1. Safe Float Conversion (Handles decimals like 0.29mg for Linaclotide!)
    try:
        clean_dose_str = ''.join(filter(lambda x: x.isdigit() or x == '.', str(extracted_dose)))
        if not clean_dose_str:
            raise ValueError("No numeric values found.")
        dose_float = float(clean_dose_str)
    except ValueError:
        safety_report["dose_flag"] = True
        safety_report["alerts"].append(f"SYSTEM ERROR: Unparseable dose format '{extracted_dose}'.")
        print(f"❌ Unparseable dose format.")
        dose_float = None

    if dose_float is not None and patient_age is not None:
        try:
            conn = sqlite3.connect('pharmacy.db')
            cursor = conn.cursor()
            
            # 2. The Advanced Demographic Query
            # We look for the specific drug where the patient's age falls between the min/max 
            # and the gender matches (or applies to 'ALL').
            cursor.execute("""
                SELECT max_daily_dose_mg 
                FROM advanced_dosing_rules 
                WHERE drug_name = ? COLLATE NOCASE 
                  AND ? >= min_age_yrs 
                  AND ? <= max_age_yrs 
                  AND (gender = ? OR gender = 'ALL')
            """, (extracted_drug, patient_age, patient_age, patient_gender))
            
            result = cursor.fetchone()
            
            if result:
                max_dose = result[0]
                
                # 3. Handle Strict Contraindications (Black Box Pediatric Bans = 0mg)
                if max_dose == 0:
                    safety_report["dose_flag"] = True
                    alert_msg = f"CRITICAL: {extracted_drug} is STRICTLY CONTRAINDICATED (banned) for Age {patient_age}."
                    safety_report["alerts"].append(alert_msg)
                    print(f"❌ {alert_msg}")
                    
                # 4. Handle Standard Overdose
                elif dose_float > max_dose:
                    safety_report["dose_flag"] = True
                    alert_msg = f"CRITICAL DOSING ERROR: {dose_float}mg exceeds max safe limit of {max_dose}mg for Age {patient_age}."
                    safety_report["alerts"].append(alert_msg)
                    print(f"❌ {alert_msg}")
                    
                else:
                    print(f"✅ Dose is safe for Age {patient_age} (Max: {max_dose}mg).")
            else:
                warning_msg = f"DATABASE WARNING: No demographic rules found for '{extracted_drug}' at Age {patient_age}."
                safety_report["alerts"].append(warning_msg) 
                print(f"⚠️ {warning_msg}")
                
            conn.close()
        except sqlite3.OperationalError as e:
             print(f"⚠️ Database error: {e}")

    # ==========================================
    # BRANCH 2: ChromaDB (Semantic Interaction Check)
    # ==========================================
    print("\n[System] Checking ChromaDB for interaction risks...")
    
    if patient_current_meds and str(patient_current_meds).strip().lower() not in ["none", "null", ""]:
        try:
            chroma_client = chromadb.PersistentClient(path="./chroma_data")
            collection = chroma_client.get_collection(name="drug_interactions")
            
            query = f"What is the risk or interaction between {extracted_drug} and {patient_current_meds}?"
            results = collection.query(query_texts=[query], n_results=1)
            
            if results['documents'] and results['documents'][0]:
                retrieved_warning = results['documents'][0][0]
                safety_report["interaction_flag"] = True
                safety_report["context_for_llm"] = retrieved_warning
                alert_msg = f"INTERACTION RISK FOUND with {patient_current_meds}."
                safety_report["alerts"].append(alert_msg)
                
                print(f"❌ {alert_msg}")
                print(f"📄 Retrieved Medical Context:\n   \"{retrieved_warning}\"")
                
        except Exception as e:
            print(f"⚠️ Error accessing vector database: {e}")
    else:
        print("✅ No concurrent medications to check against.")

    print(f"\n{'='*50}")
    return safety_report

if __name__ == "__main__":
    
    raw_ocr_text = ocr_reader.extract_and_sanitize_text("prescription.png")
    
    if not raw_ocr_text:
        print("❌ OCR Failed to extract any text. Aborting Pipeline.")
    else:
        structured_data = extractor.parse_prescription_text(raw_ocr_text)
        
        if not structured_data or "medications" not in structured_data:
            print("❌ Smart Extractor failed to parse JSON or find medications. Aborting Pipeline.")
        else:
            patient_history = structured_data.get("medical_history")
            
            # Extract the new demographic data! Defaults added just in case OCR misses it.
            p_age = structured_data.get("patient_age", 30) 
            p_gender = structured_data.get("patient_gender", "ALL")
            
            all_drug_reports = []
            
            for med in structured_data["medications"]:
                test_drug = med.get("drug_name")
                test_dose = med.get("dose_mg")
                
                # Pass age and gender into the controller
                report_dict = process_prescription(test_drug, test_dose, patient_history, p_age, p_gender)
                
                if report_dict:
                    all_drug_reports.append(report_dict)
            
            print("\n[AI Module] Generating Final Summarized Report...")
            final_summary = llm_generator.generate_pharmacist_warning(all_drug_reports)
            print("\n==========================================")
            print("🤖 FINAL AI PHARMACIST WARNING:")
            print("==========================================")
            print(final_summary)