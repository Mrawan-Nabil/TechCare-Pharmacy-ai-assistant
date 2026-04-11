import ollama

def generate_pharmacist_warning(reports_list):
    """
    Takes a LIST of safety_report dictionaries from system_controller.py 
    and uses a local LLM to generate ONE summarized professional clinical warning.
    """
    print("\n[AI Module] Connecting to local LLM (BioMistral)...")
    
    all_drugs = []
    all_alerts = []
    all_context = ""
    
    # We will specifically count how many drugs triggered a warning
    flagged_drugs_count = 0

    for report in reports_list:
        drug_name = report.get('drug')
        all_drugs.append(f"{drug_name} ({report.get('dose_mg', 'Unknown')}mg)")
        
        if report.get("dose_flag") or report.get("interaction_flag"):
            flagged_drugs_count += 1
            
            # Tag the alerts with the specific drug name
            for alert in report.get("alerts", []):
                all_alerts.append(f"[{drug_name}]: {alert}")
                
            # Tag the ChromaDB context with the specific drug name
            all_context += f"\n--- Literature for {drug_name} ---\n{report.get('context_for_llm', '')}\n"

    if flagged_drugs_count == 0:
        return "✅ Prescription is safe. No dosing errors or interactions found for any medications."

    # 1. System Prompt (Few-Shot Example Technique)
    system_prompt = (
        "You are a strict, expert clinical pharmacy AI assistant. Your job is to read the provided "
        "safety flags and medical context, and extract ALL distinct clinical warnings to write a "
        "highly condensed, urgent, and professional report for the human pharmacist.\n\n"
        "CRITICAL RULES AND FORMATTING:\n"
        "1. You MUST generate a separate bullet point for EVERY specific medication risk, allergy warning, or interaction mentioned in the Retrieved Medical Literature.\n"
        "2. If the literature mentions multiple distinct issues or flagged drugs, you must output a corresponding number of bullet points. Do not group them together.\n"
        "3. STRICT GROUNDING, Focus only on the severe risks mentioned in the Provided Medical Literature without new medical facts or hallucinate.\n"
        "4. NO FILLER: Do NOT write introductory or concluding paragraphs. Output ONLY the bulleted list. Do NOT repeat phrases.\n"
        "5. EXACT TEMPLATE: Format your output EXACTLY matching this structural template:\n"
        "- **WARNING: [Drug Name(s) - Short Risk]** - PURPOSE: [Specific clinical reason, severe risk, or required action]\n"
        "- **WARNING: [Drug Name(s) - Short Risk]** - PURPOSE: [Specific clinical reason, severe risk, or required action]\n"
    )
    
    # 2. User Prompt (Explicit Counting Technique)
    # We dynamically inject 'flagged_drugs_count' to force the AI to reach that quota!
    user_prompt = f"""
    TASK: You must write EXACTLY {flagged_drugs_count} bullet points for the following {flagged_drugs_count} flagged medications.

    Triggered System Alerts:
    {chr(10).join(all_alerts)}
    
    Retrieved Medical Literature:
    {all_context}
    
    Generate the {flagged_drugs_count} bullet points now:
    """

    try:
        response = ollama.chat(model='biomistral', messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ])
        
        return response['message']['content']
        
    except Exception as e:
        return f"❌ Error communicating with local LLM: {e}"

# --- Let's test the AI Generation ---
if __name__ == "__main__":
    # Simulating a LIST of dictionary outputs we would get from Phase 1
    mock_reports_list = [
        {
            "drug": "Aspirin",
            "dose_mg": 5000,
            "dose_flag": True,
            "interaction_flag": True,
            "alerts": [
                "CRITICAL DOSING ERROR: 5000mg exceeds max safe daily dose of 4000mg!",
                "INTERACTION RISK FOUND with Warfarin."
            ],
            "context_for_llm": "Aspirin combined with blood thinners like Warfarin significantly increases the risk of major gastrointestinal bleeding. Concurrent use requires strict medical justification and close INR monitoring."
        },
        {
            "drug": "Lisinopril",
            "dose_mg": 20,
            "dose_flag": False,
            "interaction_flag": False,
            "alerts": [],
            "context_for_llm": ""
        }
    ]

    print("Generating AI Warning... (This may take 5-15 seconds depending on your CPU/GPU)\n")
    
    final_warning = generate_pharmacist_warning(mock_reports_list)
    
    print("==========================================")
    print("🤖 AI PHARMACIST WARNING:")
    print("==========================================")
    print(final_warning)
    print("==========================================")