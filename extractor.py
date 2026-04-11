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
    system_prompt = """
    You are an expert medical data extraction API. 
    Read the provided raw OCR text from a prescription and extract the patient's details and medications.
    
    CRITICAL INSTRUCTION FOR DOSAGE:
    You must calculate the TOTAL DAILY DOSE in milligrams for each medication based on the frequency provided. 
    Use these standard medical abbreviations to do the math:
    - Daily / OD = 1 time per day (Multiply pill dose by 1)
    - BID = 2 times per day (Multiply pill dose by 2)
    - TID = 3 times per day (Multiply pill dose by 3)
    - QID = 4 times per day (Multiply pill dose by 4)
    - q4h = Every 4 hours (Multiply pill dose by 6)
    - q4-6h = Every 4 to 6 hours (Use the maximum frequency, which is 6 times per day. Multiply pill dose by 6)
    
    Example: If the text says "Ibuprofen 600 mg TID", the dose_mg should be 1800 (600 x 3).
    Example: If the text says "Cephalexin 500 mg QID", the dose_mg should be 2000 (500 x 4).
    For combo drugs like "Percocet 5/325 mg", use the higher number (325) as the base pill dose.

    You MUST output ONLY a raw JSON object with these exact keys. Do not include markdown, explanations, or backticks:
    {
        "patient_age": (integer or null),
        "patient_gender": (string: "M", "F", or "ALL" - default to "ALL" if unknown),
        "diagnosis": (string or null),
        "medical_history": (string or null),
        "medications": [{
            "drug_name": "Amoxicillin",
            "concentration": "500mg", 
            "frequency": "BID",
            "total_daily_dose_mg": 1000
        }]
    }
    """

    user_prompt = f"Raw OCR Text:\n{raw_ocr_text}"

    try:
        response = ollama.chat(model='biomistral', messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ], format='json') # Forcing JSON format output is a great feature in Ollama

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