import time
from auto_learner import learn_and_save_drug

def run_overnight_ingestion(inventory_list):
    print("\n🌙 Starting NetHealth Overnight Batch Processing...")
    print(f"📦 Total Drugs in Queue: {len(inventory_list)}")
    print("==================================================\n")

    successful_drugs = []
    failed_drugs = []

    for index, drug in enumerate(inventory_list):
        print(f"[{index + 1}/{len(inventory_list)}] Processing: {drug.upper()}")
        
        # We set interactive=False so it skips existing drugs automatically 
        # instead of pausing the script to ask you.
        success = learn_and_save_drug(drug, interactive=False)
        
        if success:
            successful_drugs.append(drug)
        else:
            failed_drugs.append(drug)
            
        time.sleep(2) # Give the FDA API and your computer a 2-second breathing room

    print("\n==================================================")
    print("🌅 OVERNIGHT BATCH COMPLETE")
    print(f"✅ Successfully Processed/Skipped: {len(successful_drugs)}")
    print(f"❌ Failed: {len(failed_drugs)}")
    print("==================================================")

    # --- WRITE THE QUARANTINE QUEUE ---
    if failed_drugs:
        print("\n⚠️ Writing failed drugs to 'failed_queue.txt' for manual review...")
        with open("failed_queue.txt", "w") as f:
            f.write("--- NETHEALTH FAILED DRUGS QUEUE ---\n")
            f.write("These drugs failed LLM extraction, Integrity Checks, or API limits.\n\n")
            for fd in failed_drugs:
                f.write(f"{fd}\n")
        print("Done. Check failed_queue.txt to see which drugs need attention.")

if __name__ == "__main__":
    # In the real world, this would be a CSV file export from the pharmacy's cash register.
    # For now, we simulate a small inventory list.
    sample_inventory = [
        "amoxicillin",
        "ibuprofen",
        "cephalexin",
        "oxycodone",
        "acetaminophen",
        "linaclotide",
        "warfarin",
        "lisinopril",
        "atorvastatin",   # Cholesterol (Statins - has strict liver warnings)
        "metformin",      # Diabetes (Has a famous Black Box warning for lactic acidosis)
        "omeprazole",     # Acid reflux (Proton-pump inhibitor)
        "sertraline",     # Antidepressant (SSRI - lots of interaction data)
        "albuterol",      # Asthma (Inhaler - tests how the AI handles non-pill doses)
        "amlodipine",     # Blood pressure (Calcium channel blocker)
        "gabapentin",     # Nerve pain / Seizures
        "levothyroxine",  # Thyroid hormone (Dosed in very specific micrograms)
        "azithromycin",   # Antibiotic (Z-Pak)
        "prednisone"      # Steroid (Has highly variable, tapering dose rules)
    ]
    
    run_overnight_ingestion(sample_inventory)