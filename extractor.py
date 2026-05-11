import ollama
import json
import re
import ocr_reader

def parse_prescription_text(raw_ocr_text):
    """
    Uses the local LLM to extract structured variables from messy OCR text.
    """
    print("🧠 [Smart Extractor] Analyzing raw OCR text...")

    # 1. The System Prompt: We force the AI to act as a strict JSON converter and medical calculator.
    system_prompt = (
        "You are an expert clinical data extractor. Your ONLY job is to extract medical data "
        "from the provided text into a strict JSON format.\n"
        "CRITICAL INSTRUCTION: You MUST extract EVERY SINGLE MEDICATION found in the text. "
        "Do not stop after the first one. Output the medications as a JSON array.\n\n"
        "CRITICAL INSTRUCTION FOR DOSAGE:\n"
        "You must calculate the TOTAL DAILY DOSE in milligrams for each medication based on the frequency provided.\n"
        "Use these standard medical abbreviations to do the math:\n"
        "- Daily / OD = 1 time per day (Multiply pill dose by 1)\n"
        "- BID = 2 times per day (Multiply pill dose by 2)\n"
        "- TID = 3 times per day (Multiply pill dose by 3)\n"
        "- QID = 4 times per day (Multiply pill dose by 4)\n"
        "- q4h = Every 4 hours (Multiply pill dose by 6)\n"
        "- q4-6h = Every 4 to 6 hours (Use the maximum frequency: 6x per day)\n\n"
        "Example: If the text says 'Ibuprofen 600 mg TID', the total_daily_dose_mg should be 1800 (600 x 3).\n"
        "Example: If the text says 'Cephalexin 500 mg QID', the total_daily_dose_mg should be 2000 (500 x 4).\n"
        "For combo drugs like 'Percocet 5/325 mg', use the higher number (325) as the base pill dose.\n\n"
        "CRITICAL SCHEMA RULES — field isolation is MANDATORY:\n"
        "1. 'drug_name' MUST contain ONLY the alphabetical name of the medication. "
        "Do NOT include any numbers, dosages, strengths, or frequency abbreviations in this field. "
        "WRONG: 'Ibuprofen 600 mg TID'  |  CORRECT: 'Ibuprofen'\n"
        "WRONG: 'Cephalexin 500mg QID'  |  CORRECT: 'Cephalexin'\n"
        "WRONG: 'Percocet 5/325'        |  CORRECT: 'Percocet'\n"
        "2. 'concentration' MUST contain ONLY the strength per pill or unit (e.g., '600 mg', '500 mg', '5/325 mg'). "
        "Do NOT include the drug name or frequency here.\n"
        "3. 'frequency' MUST contain ONLY the timing or administration instruction "
        "(e.g., 'TID', 'BID', 'q4-6h', 'once daily'). "
        "Do NOT include the drug name, dose, or strength here.\n\n"
        "Use this exact JSON schema — output ONLY raw JSON, no markdown, no backticks, no explanations:\n"
        '{\n'
        '  "patient_age": "integer or null",\n'
        '  "patient_gender": "M, F, or ALL — default ALL if unknown",\n'
        '  "diagnosis": "string or null",\n'
        '  "medical_history": "string or null",\n'
        '  "medications": [\n'
        '    {\n'
        '      "drug_name": "alphabetical name only — NO numbers or frequencies",\n'
        '      "concentration": "strength per unit only — e.g. 600 mg",\n'
        '      "frequency": "timing only — e.g. TID, BID, q4-6h",\n'
        '      "total_daily_dose_mg": "integer"\n'
        '    }\n'
        '  ]\n'
        '}'
    )

    user_prompt = f"Raw OCR Text:\n{raw_ocr_text}"

    try:
        response = ollama.chat(
            model='biomistral',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            format='json',          # Force structured JSON output
            options={
                'num_predict': 1000, # Allow enough tokens for all medications
                'temperature': 0.1,  # Near-deterministic — reduces hallucinations
            },
        )

        # 2. Extract and clean the AI's text response
        ai_output = response['message']['content'].strip()
        
        # 3. Convert the string back into a real Python dictionary
        extracted_data = json.loads(ai_output)
        
        return extracted_data

    except json.JSONDecodeError:
        print("❌ Error: The AI did not return valid JSON.")
        print(f"Raw output was: {ai_output}")
        return None
    except Exception as e:
        print(f"❌ Error communicating with LLM: {e}")
        return None

if __name__ == "__main__":
    # Let's simulate a really messy, realistic OCR scan result
    simulated_messy_ocr = ocr_reader.extract_and_sanitize_text("prescription_sample.jpg")
    print("--- Simulating Messy OCR Input ---")
    print(simulated_messy_ocr)
    print("----------------------------------\n")

    structured_data = parse_prescription_text(simulated_messy_ocr)
    
    if structured_data:
        print("✅ Success! Extracted Structured Data:")
        # We print it nicely formatted with an indent
        print(json.dumps(structured_data, indent=4))