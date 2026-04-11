import sqlite3
import chromadb
import extractor
import llm_generator
import ocr_reader
from auto_learner import learn_and_save_drug

def check_local_databases(extracted_drug, extracted_dose, extracted_concentration, patient_current_meds, patient_age, patient_gender):
    """
    Queries the local SQLite and ChromaDB. Runs instantly.
    """
    safety_report = {
        "drug": extracted_drug,
        "dose_mg": extracted_dose,
        "concentration": extracted_concentration,
        "dose_flag": False,
        "interaction_flag": False,
        "alerts": [],
        "context_for_llm": ""
    }

    # 1. SQLite Math Check
    try:
        dose_float = float(''.join(filter(lambda x: x.isdigit() or x == '.', str(extracted_dose))))
        conn = sqlite3.connect('pharmacy.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT max_daily_dose_mg FROM advanced_dosing_rules 
            WHERE drug_name = ? COLLATE NOCASE 
              AND (concentration = ? OR concentration = 'UNKNOWN')
              AND ? >= min_age_yrs AND ? <= max_age_yrs 
              AND (gender = ? OR gender = 'ALL')
        """, (extracted_drug, extracted_concentration, patient_age, patient_age, patient_gender))
        
        result = cursor.fetchone()
        
        if result:
            max_dose = result[0]
            if max_dose == 0:
                safety_report["dose_flag"] = True
                safety_report["alerts"].append(f"CRITICAL: {extracted_drug} is STRICTLY BANNED for Age {patient_age}.")
            elif dose_float > max_dose:
                safety_report["dose_flag"] = True
                safety_report["alerts"].append(f"DOSING ERROR: {dose_float}mg exceeds max limit of {max_dose}mg for Age {patient_age} using {extracted_concentration}.")
        else:
            safety_report["alerts"].append(f"WARNING: No local dosing rules found for '{extracted_drug}' at concentration '{extracted_concentration}'.")
            
        conn.close()
    except Exception as e:
        print(f"Math Check Error: {e}")

    # 2. ChromaDB Semantic Check
    if patient_current_meds and str(patient_current_meds).strip().lower() not in ["none", "null", ""]:
        try:
            chroma_client = chromadb.PersistentClient(path="./chroma_data")
            collection = chroma_client.get_collection(name="drug_interactions")
            
            # Fetch context specific to the drug being scanned
            results = collection.get(ids=[extracted_drug.lower()])
            
            if results['documents']:
                safety_report["context_for_llm"] = results['documents'][0]
                safety_report["interaction_flag"] = True # We flag it so the LLM knows to read the context
        except Exception as e:
             print(f"Vector DB Error: {e}")

    return safety_report


if __name__ == "__main__":
    print("\n📷 [1] Scanning Prescription...")
    raw_ocr_text = ocr_reader.extract_and_sanitize_text("prescription.png")
    
    if raw_ocr_text:
        print("🧠 [2] AI extracting demographics and meds...")
        structured_data = extractor.parse_prescription_text(raw_ocr_text)
        
        if structured_data and "medications" in structured_data:
            p_age = structured_data.get("patient_age", 30) 
            p_gender = structured_data.get("patient_gender", "ALL")
            p_history = structured_data.get("medical_history", "None")
            
            all_drug_reports = []
            
            print(f"⚡ [3] Checking Local Databases for Age {p_age} ({p_gender})...")
            
            for med in structured_data["medications"]:
                test_drug = med.get("drug_name")
                test_dose = med.get("dose_mg")
                test_concentration = med.get("concentration", "UNKNOWN") # EXTRACTING NEW VAR
                
                # --- THE LAZY LOADING FALLBACK ---
                chroma_client = chromadb.PersistentClient(path="./chroma_data")
                collection = chroma_client.get_or_create_collection(name="drug_interactions")
                if not collection.get(ids=[test_drug.lower()])['ids']:
                    print(f"⚠️ {test_drug.upper()} not found in local DB. Fetching from FDA...")
                    learn_and_save_drug(test_drug)
                
                # Run the fast local check with concentration
                report_dict = check_local_databases(test_drug, test_dose, test_concentration, p_history, p_age, p_gender)
                all_drug_reports.append(report_dict)
            
            print("🤖 [4] BioMistral Generating Final Summary...")
            final_summary = llm_generator.generate_pharmacist_warning(all_drug_reports)
            
            print("\n==========================================")
            print("⚕️ FINAL PHARMACIST DASHBOARD:")
            print("==========================================")
            print(final_summary)
            print("==========================================")