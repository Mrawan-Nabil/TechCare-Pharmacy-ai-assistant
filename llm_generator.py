"""
llm_generator.py — TechCare Senior Clinical Auditor
=====================================================
Refactored to accept the three-artefact output of live_checkout.run_full_pipeline():

    extracted_json      — structured prescription dict (patient + medications)
    safety_alerts       — deterministic Python dosing alerts from SQLite math checks
    combined_context    — raw FDA literature retrieved from ChromaDB (pure RAG)

The LLM acts as a Senior Auditor: it explains the WHY behind system alerts,
spots risks the rule engine may have missed, and stays strictly grounded in the
provided literature.
"""

import json
import ollama


def generate_pharmacist_warning(
    extracted_json: dict,
    safety_alerts: list[str],
    combined_context: str,
) -> str:
    """
    Uses BioMistral as a Senior Clinical Auditor to generate a final safety report.

    Args:
        extracted_json:   Structured prescription data from extractor.py
        safety_alerts:    Deterministic dosing alerts from live_checkout.run_dosing_checks()
        combined_context: Raw FDA literature from live_checkout.build_context_payload()

    Returns:
        A formatted markdown string with CRITICAL and ADVISORY bullet points.
    """
    print("\n[AI Module] Senior Clinical Auditor (BioMistral) initialising...")

    # ── System Prompt: Interaction-First Senior Auditor ──────────────────────
    system_prompt = (
        "You are the TechCare Senior Clinical Auditor. "
        "Your HIGHEST PRIORITY is identifying life-threatening interactions BETWEEN "
        "the medications listed.\n\n"
        "MANDATORY AUDIT PROCEDURE — follow this order exactly:\n"
        "1. Cross-reference every drug against every other drug in the 'PATIENT DATA' "
        "medications list using the provided FDA Reference Literature.\n"
        "2. If you find a drug-to-drug interaction (e.g., MAOI + Opioid, Warfarin + NSAID), "
        "place it at the VERY TOP of your report in **bold** using the prefix '**CRITICAL INTERACTION:**'.\n"
        "3. Only mention general precautions (e.g., renal impairment, hepatic dose adjustment) "
        "AFTER you have fully addressed all drug-to-drug interactions.\n"
        "4. Do NOT copy the first warning you encounter and stop. "
        "You MUST scan the ENTIRE FDA Reference Literature section for the keyword 'interaction' "
        "and evaluate every occurrence before writing your report.\n\n"
        "OUTPUT FORMAT:\n"
        "- Start with drug-to-drug interactions (if any) in **bold**.\n"
        "- MANDATORY: For EVERY interaction or alert listed, you MUST include at least one "
        "full sentence that explains the clinical mechanism or reason WHY it is dangerous. "
        "Do NOT simply state that an interaction exists. "
        "Use the 'Known Mechanism' and 'Note' fields from the System Alerts, "
        "and the FDA Reference Literature, to explain the pharmacological risk in plain clinical language.\n"
        "- Follow with CRITICAL: prefix for life-threatening risks.\n"
        "- Use ADVISORY: prefix for general precautions and monitoring recommendations.\n"
        "- No introductions. No conclusions. Bullet points only.\n\n"
        "CRITICAL NOISE FILTER: The FDA REFERENCE LITERATURE may contain generic research "
        "statistics, study percentages (e.g., 'the number of patients referred', 'incidence "
        "rate in clinical trials'), or meta-data unrelated to drug safety. "
        "DISREGARD all such content entirely. "
        "PRIORITY: Focus exclusively on sections labelled 'Drug Interactions', "
        "'Contraindications', or 'Warnings and Precautions'.\n\n"
        "FALLBACK: If NO '[SQL INTERACTION]' alerts are provided AND the FDA Reference "
        "Literature does not contain clear safety data regarding the drugs or their interactions, "
        "output exactly this statement for each affected drug:\n"
        "'WARNING: Detailed interaction data for [Drug Name] not found in current local "
        "knowledge base. Manual pharmacist review required.'\n\n"
        "CRITICAL RULE — SQL ALERTS TAKE PRECEDENCE: If a '[SQL INTERACTION]' alert is "
        "present in the System Alerts, you MUST report it as a CRITICAL or ADVISORY warning "
        "at the top of your report. You MAY use the 'Known Mechanism' field provided in the "
        "SQL alert to explain the pharmacological risk, even if the attached FDA Reference "
        "Literature does not contain specific details about that pair. "
        "A SQL alert is a database-confirmed interaction — never ignore it.\n\n"
        "STRICT GROUNDING RULE: If a risk is not supported by the provided Literature "
        "or System Alerts, do not invent facts. Stay strictly grounded in the provided context."
    )

    # ── Format safety alerts for the prompt ──────────────────────────────────
    if safety_alerts:
        alerts_text = "\n".join(f"  • {a}" for a in safety_alerts)
    else:
        alerts_text = "  [None — all doses within known limits or rules not found]"

    # ── Serialize extracted_json cleanly for the prompt ───────────────────────
    try:
        patient_block = json.dumps(extracted_json, indent=2)
    except Exception:
        patient_block = str(extracted_json)

    # ── User Prompt: Three-section grounded audit request ─────────────────────
    user_prompt = (
        "--- PATIENT DATA ---\n"
        f"{patient_block}\n\n"
        "--- SYSTEM DOSING ALERTS ---\n"
        f"{alerts_text}\n\n"
        "--- FDA REFERENCE LITERATURE ---\n"
        f"{combined_context}\n\n"
        "Perform the clinical audit now. Output ONLY the bullet-point report. "
        "Use 'CRITICAL:' or 'ADVISORY:' prefixes. No introductions, no conclusions."
    )

    # ── Zero-shot stateless call ──────────────────────────────────────────────
    # IMPORTANT — context bleed prevention:
    # Ollama runs as a local server and caches the KV-context of the last
    # loaded model in VRAM between API calls.  Two defences are applied:
    #
    #   keep_alive=0   — instructs Ollama to unload the model from memory
    #                    immediately after responding, destroying the cached
    #                    context so the next call starts from a clean state.
    #
    #   num_ctx=2048   — caps the context window.  Even if a stale cache
    #                    exists, it cannot exceed this token budget, which is
    #                    consumed entirely by the fresh prompt below.
    #
    # The messages list is a brand-new literal built inside this function on
    # every call — it is never appended to and never references a global list.
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        response = ollama.chat(
            model="biomistral",
            messages=messages,
            options={
                "temperature": 0.1,   # Near-deterministic for clinical accuracy
                "num_predict": 1200,  # Enough for multi-drug prescriptions
                "num_ctx":     2048,  # Hard context window cap — no stale token bleed
            },
            keep_alive=0,             # Flush Ollama's KV-cache after every response
        )
        return response["message"]["content"]

    except Exception as e:
        return f"❌ Error communicating with local LLM: {e}"



# ─── Legacy wrapper (backward compatibility) ──────────────────────────────────
# Older callers that pass a reports_list dict are handled here so no call sites
# outside live_checkout break silently.

def generate_pharmacist_warning_legacy(reports_list: list[dict]) -> str:
    """
    Converts the old reports_list format into the new three-artefact signature
    and delegates to generate_pharmacist_warning().  Keeps old callers working.
    """
    all_alerts: list[str] = []
    all_context_parts: list[str] = []
    all_meds: list[dict] = []

    for report in reports_list:
        drug = report.get("drug", "Unknown")
        dose = report.get("dose_mg", "?")
        all_meds.append({"drug_name": drug, "dose_mg": dose})

        for alert in report.get("alerts", []):
            all_alerts.append(f"[{drug}]: {alert}")

        ctx = report.get("context_for_llm", "")
        if ctx:
            all_context_parts.append(f"=== FDA LITERATURE: {drug.upper()} ===\n{ctx}")

    pseudo_json = {"medications": all_meds}
    combined = "\n\n".join(all_context_parts) if all_context_parts else "[No literature retrieved]"

    return generate_pharmacist_warning(pseudo_json, all_alerts, combined)


# ─── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mock_json = {
        "patient_age": 72,
        "patient_gender": "M",
        "diagnosis": "atrial fibrillation, hypertension",
        "medical_history": "chronic kidney disease stage 3",
        "medications": [
            {"drug_name": "Aspirin", "concentration": "325mg", "frequency": "OD", "total_daily_dose_mg": 325},
            {"drug_name": "Warfarin", "concentration": "5mg", "frequency": "OD", "total_daily_dose_mg": 5},
        ],
    }

    mock_alerts = [
        "DOSING ERROR: Aspirin — 325mg exceeds max limit of 100mg/day for Age 72 (325mg).",
    ]

    mock_context = (
        "=== FDA LITERATURE: ASPIRIN ===\n"
        "Aspirin combined with anticoagulants such as Warfarin significantly increases "
        "the risk of major gastrointestinal and intracranial bleeding. Concomitant use "
        "requires strong clinical justification. INR must be monitored closely.\n\n"
        "=== FDA LITERATURE: WARFARIN ===\n"
        "Warfarin is contraindicated in patients at high bleeding risk. Dose adjustments "
        "are required in renal impairment. NSAIDs and antiplatelet agents potentiate effect."
    )

    print("Generating Senior Clinical Audit Report...\n")
    result = generate_pharmacist_warning(mock_json, mock_alerts, mock_context)

    print("==========================================")
    print("⚕️  SENIOR CLINICAL AUDITOR REPORT:")
    print("==========================================")
    print(result)
    print("==========================================")