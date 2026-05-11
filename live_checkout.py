"""
live_checkout.py — TechCare Clinical Data Aggregator (Pure RAG Architecture)
=============================================================================
Refactored from similarity-math model to Pure RAG approach.

Pipeline:
  Phase 1  │ Autonomous Knowledge Retrieval
            │   → Ensures every drug exists in SQLite + ChromaDB.
            │   → Calls auto_learner if any data is missing (BLOCKS).

  Phase 2  │ Numerical Dosing Safety  (SQLite math check)
            │   → Strict Python comparison of extracted dose vs max_daily_dose_mg.
            │   → No LLM involved — deterministic rule enforcement.

  Phase 3  │ RAG Context Aggregation  (ChromaDB retrieval)
            │   → Retrieves raw FDA literature for every drug by direct ID lookup.
            │   → Concatenates all text into a single context_payload string.

  Returns  │ (extracted_json, python_dosing_alerts, context_payload)
            │   → These three artefacts are passed to llm_generator for auditing.
"""

import itertools
import json
import sqlite3

import chromadb

import auto_learner
import extractor
import llm_generator
import ocr_reader

# ─── Constants ────────────────────────────────────────────────────────────────

CHROMA_PATH = "./chroma_data"
CHROMA_COLLECTION = "drug_interactions"


# ─── Internal helpers ──────────────────────────────────────────────────────────

def _drug_in_sqlite(drug_name: str) -> bool:
    """Returns True if at least one dosing rule exists for this drug."""
    try:
        conn = sqlite3.connect("pharmacy.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM advanced_dosing_rules WHERE drug_name = ? COLLATE NOCASE",
            (drug_name,),
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        print(f"[SQLite] Existence check failed for '{drug_name}': {e}")
        return False


def _drug_in_chroma(drug_name: str) -> bool:
    """Returns True if FDA literature for this drug exists in ChromaDB."""
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_or_create_collection(name=CHROMA_COLLECTION)
        result = collection.get(ids=[drug_name.lower()])
        return bool(result["ids"])
    except Exception as e:
        print(f"[ChromaDB] Existence check failed for '{drug_name}': {e}")
        return False


# ─── Phase 1: Autonomous Knowledge Retrieval ──────────────────────────────────

def ensure_drug_knowledge(drug_name: str) -> None:
    """
    Guarantees that dosing rules and FDA literature exist locally before the
    safety checks run.  If either store is missing the drug, auto_learner is
    called synchronously — the call BLOCKS until the write completes.
    """
    sqlite_ok = _drug_in_sqlite(drug_name)
    chroma_ok = _drug_in_chroma(drug_name)

    if sqlite_ok and chroma_ok:
        return  # Already fully populated — nothing to do.

    print(f"⚠️  [{drug_name.upper()}] not fully known — triggering FDA auto-learn...")
    success = auto_learner.learn_and_save_drug(drug_name, interactive=False)

    if success:
        print(f"✅  [{drug_name.upper()}] knowledge written to SQLite + ChromaDB.")
    else:
        print(
            f"⚠️  [{drug_name.upper()}] auto-learn returned no rules "
            "(drug may not be in FDA database). Proceeding with limited data."
        )


# ─── Phase 2: Numerical Dosing Safety Check ───────────────────────────────────

def run_dosing_checks(
    medications: list[dict],
    patient_age,
    patient_gender: str,
) -> list[str]:
    """
    Strict Python math check — no LLM, no similarity scores.
    Compares each drug's extracted total_daily_dose_mg against the SQLite
    max_daily_dose_mg limit for the patient's age and gender.

    Returns a flat list of alert strings (empty if all doses are within limits).
    """
    dosing_alerts: list[str] = []

    try:
        conn = sqlite3.connect("pharmacy.db")
        cursor = conn.cursor()

        for med in medications:
            drug = med.get("drug_name", "Unknown")
            concentration = med.get("concentration", "UNKNOWN")
            raw_dose = med.get("total_daily_dose_mg") or med.get("dose_mg", 0)

            try:
                dose_float = float(
                    "".join(filter(lambda x: x.isdigit() or x == ".", str(raw_dose)))
                )
            except (ValueError, TypeError):
                dosing_alerts.append(
                    f"WARNING: Could not parse dose value '{raw_dose}' for {drug}."
                )
                continue

            cursor.execute(
                """
                SELECT max_daily_dose_mg FROM advanced_dosing_rules
                WHERE drug_name = ? COLLATE NOCASE
                  AND (concentration = ? OR concentration = 'UNKNOWN')
                  AND ? >= min_age_yrs AND ? <= max_age_yrs
                  AND (gender = ? OR gender = 'ALL')
                """,
                (drug, concentration, patient_age, patient_age, patient_gender),
            )

            result = cursor.fetchone()

            if result:
                max_dose = result[0]
                if max_dose is None or max_dose == 0:
                    # Zero or missing max dose means the auto-learner found a rule
                    # but couldn't determine a numeric limit — NOT the same as banned.
                    dosing_alerts.append(
                        f"ADVISORY: No strict maximum daily dose found in local database "
                        f"for {drug} ({concentration}). Verify standard dosing guidelines."
                    )
                elif dose_float > max_dose:
                    dosing_alerts.append(
                        f"DOSING ERROR: {drug} — {dose_float}mg exceeds the maximum "
                        f"safe limit of {max_dose}mg/day for Age {patient_age} "
                        f"({concentration})."
                    )
            else:
                dosing_alerts.append(
                    f"WARNING: No local dosing rules found for '{drug}' "
                    f"at concentration '{concentration}'. Manual verification required."
                )

        conn.close()

    except Exception as e:
        print(f"[Dosing Check] SQLite error: {e}")

    return dosing_alerts


# ─── Safety keyword filter ─────────────────────────────────────────────────────
# Only chunks containing at least one of these terms pass through to the LLM.
# This strips out pharmacokinetic tables, indication summaries, and trial stats.
SAFETY_KEYWORDS = [
    "interaction",
    "contraindicat",
    "warning",
    "fatal",
    "concomitant",
    "maoi",
    "contraindication",
    "boxed warning",
    "black box",
    "do not use",
    "avoid",
    "prohibited",
    "severe",
    "life-threatening",
    "serotonin syndrome",
    "overdose",
]


def _chunk_is_safety_relevant(doc: str) -> bool:
    """
    Returns True if the document chunk contains at least one safety keyword.
    Case-insensitive. Drops 'Indications for Use', pharmacokinetic tables,
    trial statistics, and other non-safety content.
    """
    doc_lower = doc.lower()
    return any(keyword in doc_lower for keyword in SAFETY_KEYWORDS)


# ─── Hybrid Rules Engine — Step 1: SQL Interaction Trigger ───────────────────

def _check_sql_interactions(drug_names: list[str]) -> list[tuple[str, str, str]]:
    """
    Uses itertools.combinations to generate every drug pair and queries the
    SQLite 'interactions' table for known pairs.

    Returns a list of (drug_a, drug_b, severity) tuples for confirmed interactions.
    Returns an empty list if the table doesn't exist yet (future-proof).
    """
    confirmed_pairs: list[tuple[str, str, str]] = []

    if len(drug_names) < 2:
        return confirmed_pairs

    try:
        conn = sqlite3.connect("pharmacy.db")
        cursor = conn.cursor()

        # Verify the interactions table exists before querying it
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='interactions'"
        )
        if not cursor.fetchone():
            print(
                "[Hybrid] 'interactions' table not found in SQLite — "
                "skipping SQL trigger. Add the table via auto_learner to enable this step."
            )
            conn.close()
            return confirmed_pairs

        for raw_a, raw_b in itertools.combinations(drug_names, 2):
            # ── Aggressive first-word extraction ──────────────────────────────
            # Step 1: Replace hyphens and slashes with spaces so compound names
            #         become word sequences: 'Oxycodone-Acetaminophen' → 'Oxycodone Acetaminophen'
            # Step 2: Split on whitespace and take the first token only.
            # Step 3: Strip and lowercase to match SQLite COLLATE NOCASE rows.
            # Results: 'Warfarin Sodium' → 'warfarin'
            #          'Oxycodone-Acetaminophen' → 'oxycodone'
            #          'Amoxicillin/Clavulanate' → 'amoxicillin'
            drug_a = raw_a.replace("-", " ").replace("/", " ").split()[0].strip().lower()
            drug_b = raw_b.replace("-", " ").replace("/", " ").split()[0].strip().lower()

            # Pull severity + explanation columns in one query
            cursor.execute(
                """
                SELECT severity, mechanism, clinical_note FROM interactions
                WHERE (drug_a = ? COLLATE NOCASE AND drug_b = ? COLLATE NOCASE)
                   OR (drug_a = ? COLLATE NOCASE AND drug_b = ? COLLATE NOCASE)
                LIMIT 1
                """,
                (drug_a, drug_b, drug_b, drug_a),
            )
            row = cursor.fetchone()
            if row:
                severity    = row[0] if row[0] else "Unknown"
                mechanism   = row[1] if row[1] else "Mechanism not recorded."
                clinical_note = row[2] if row[2] else "No clinical note available."
                # Store the cleaned names so the Sniper Search query is also clean
                confirmed_pairs.append((drug_a, drug_b, severity, mechanism, clinical_note))
                print(
                    f"[SQL Trigger] Interaction confirmed: "
                    f"{drug_a.upper()} <-> {drug_b.upper()} ({severity})"
                )

        conn.close()

    except Exception as e:
        print(f"[SQL Trigger] Error: {e}")

    return confirmed_pairs


# ─── Hybrid Rules Engine — Step 2: Sniper ChromaDB Search (pair-level) ────────

def _sniper_search_pair(
    drug_a: str,
    drug_b: str,
    collection,
) -> str:
    """
    Fires a highly targeted ChromaDB query ONLY for a confirmed interacting pair.
    Each retrieved chunk is hard-sliced to 1500 chars to prevent context overflow.
    Returns a formatted string or empty string.
    """
    query = (
        f"Detailed clinical interaction, mechanism of action, and severe warnings "
        f"between {drug_a} and {drug_b}"
    )
    try:
        result = collection.query(
            query_texts=[query],
            n_results=2,
            include=["documents"],
        )
        docs = result.get("documents", [[]])[0]
        filtered = [d for d in docs if _chunk_is_safety_relevant(d)]

        if filtered:
            # Hard Slice: cap every chunk at 1500 chars before concatenating
            sliced = [
                (doc[:1500] + "..." if len(doc) > 1500 else doc)
                for doc in filtered
            ]
            return (
                f"=== INTERACTION: {drug_a.upper()} <-> {drug_b.upper()} ===\n"
                + "\n\n---\n\n".join(sliced)
            )
    except Exception as e:
        print(f"[Sniper Search] Error for pair ({drug_a}, {drug_b}): {e}")

    return ""


# ─── Hybrid Rules Engine — Step 3: Diagnosis Contraindication Check ───────────

def _diagnosis_contraindication_search(
    drug_names: list[str],
    diagnosis_summary: str,
    collection,
) -> str:
    """
    Optional — only runs if a diagnosis_summary exists.
    Queries ChromaDB for each drug's contraindications against the patient's diagnosis.
    Returns top-1 result per drug, filtered by safety keywords.
    """
    if not diagnosis_summary or str(diagnosis_summary).strip().lower() in (
        "none", "null", "",
    ):
        return ""

    sections: list[str] = []

    for drug in drug_names:
        try:
            query = (
                f"Contraindications for {drug} in patients with {diagnosis_summary}"
            )
            result = collection.query(
                query_texts=[query],
                n_results=1,
                include=["documents"],
            )
            docs = result.get("documents", [[]])[0]
            filtered = [d for d in docs if _chunk_is_safety_relevant(d)]

            if filtered:
                # Hard Slice: cap the diagnosis chunk at 1500 chars
                doc = filtered[0]
                truncated = doc[:1500] + "..." if len(doc) > 1500 else doc
                sections.append(
                    f"=== DIAGNOSIS RISK: {drug.upper()} in [{diagnosis_summary}] ===\n"
                    f"{truncated}"
                )
        except Exception as e:
            print(f"[Diagnosis Check] Error for '{drug}': {e}")

    return "\n\n".join(sections)


# ─── Hybrid Rules Engine — Context Builder ────────────────────────────────────

def build_hybrid_context_payload(
    drug_names: list[str],
    diagnosis_summary: str = "",
) -> tuple[str, list[str]]:
    """
    Orchestrates the Hybrid Rules Engine to produce a minimised, targeted
    context_payload and a list of SQL interaction alerts.

    Step 1 — SQL Trigger: find confirmed interactions via itertools pairs
    Step 2 — Sniper Search: ChromaDB query ONLY for confirmed pairs (n_results=2)
    Step 3 — Diagnosis Check: ChromaDB query for diagnosis vs each drug (n_results=1)

    Returns:
        (context_payload: str, sql_interaction_alerts: list[str])
    """
    context_sections: list[str] = []
    sql_interaction_alerts: list[str] = []

    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_or_create_collection(name=CHROMA_COLLECTION)
    except Exception as e:
        print(f"[Hybrid Engine] ChromaDB connection failed: {e}")
        return "", []

    # ── Step 1: SQL Interaction Trigger ───────────────────────────────────────
    confirmed_pairs = _check_sql_interactions(drug_names)

    for drug_a, drug_b, severity, mechanism, clinical_note in confirmed_pairs:
        # Rich alert — includes mechanism + clinical note so the LLM
        # has the pharmacological explanation directly in the alert payload.
        sql_interaction_alerts.append(
            f"[SQL INTERACTION]: {severity} risk between {drug_a.upper()} and "
            f"{drug_b.upper()}. "
            f"Known Mechanism: {mechanism}. "
            f"Note: {clinical_note}"
        )

        # ── Step 2: Sniper ChromaDB Search (only for confirmed pairs) ─────────
        snippet = _sniper_search_pair(drug_a, drug_b, collection)
        if snippet:
            context_sections.append(snippet)
        else:
            print(
                f"[Sniper Search] No safety-relevant chunks found for "
                f"{drug_a.upper()} <-> {drug_b.upper()} — pair alert retained from SQL."
            )


    # ── Step 3: Diagnosis Contraindication Check ──────────────────────────────
    diagnosis_context = _diagnosis_contraindication_search(
        drug_names, diagnosis_summary, collection
    )
    if diagnosis_context:
        context_sections.append(diagnosis_context)

    # ── Assemble context payload: SQL alerts pinned FIRST ─────────────────────
    # SQL alerts are prepended as a dedicated header so they always appear at
    # the top of the payload and are NEVER truncated by the 4000-char cap.
    pinned_sql_header = ""
    if sql_interaction_alerts:
        pinned_sql_header = (
            "=== CONFIRMED SQL INTERACTION ALERTS ===\n"
            + "\n".join(f"  * {a}" for a in sql_interaction_alerts)
        )

    # ChromaDB sniper snippets (subject to the hard cap below)
    chroma_body = "\n\n".join(context_sections)

    # Join: pinned header always comes first
    if pinned_sql_header and chroma_body:
        context_payload = pinned_sql_header + "\n\n" + chroma_body
    elif pinned_sql_header:
        context_payload = pinned_sql_header
    else:
        context_payload = chroma_body

    # ── Final safety cap: hard-limit the entire payload to 4000 chars ──────────
    # Prevents BioMistral's context window from being overwhelmed even when
    # multiple interaction snippets are combined.
    raw_len = len(context_payload)
    if raw_len > 4000:
        context_payload = context_payload[:4000]
        print(
            f"[Hybrid Engine] Context payload hard-capped: "
            f"{raw_len} -> 4000 chars."
        )

    print(
        f"[Hybrid Engine] Final context payload: {len(context_sections)} section(s), "
        f"{len(context_payload)} chars — "
        f"{len(sql_interaction_alerts)} SQL interaction alert(s)."
    )

    return context_payload, sql_interaction_alerts


# ─── Main Aggregator (called by Streamlit Live Scanner) ───────────────────────

def run_full_pipeline(
    structured_data: dict,
) -> tuple[dict, list[str], str]:
    """
    Orchestrates the full Hybrid Rules Engine pipeline.

    Args:
        structured_data: The JSON dict returned by extractor.parse_prescription_text()

    Returns:
        (extracted_json, all_safety_alerts, context_payload)
        Passed directly to llm_generator.generate_pharmacist_warning()
    """
    medications = structured_data.get("medications", [])
    p_age = structured_data.get("patient_age", 30)
    p_gender = structured_data.get("patient_gender", "ALL")
    diagnosis = structured_data.get("diagnosis", "")
    drug_names = [m.get("drug_name", "") for m in medications if m.get("drug_name")]

    # Phase 1 — Ensure all drugs are known locally (blocks until complete)
    for drug in drug_names:
        ensure_drug_knowledge(drug)

    # Phase 2 — Numerical dosing alerts (pure Python, no LLM)
    dosing_alerts = run_dosing_checks(medications, p_age, p_gender)

    # Phase 3 — Hybrid Rules Engine: SQL trigger → Sniper search → Diagnosis check
    context_payload, sql_interaction_alerts = build_hybrid_context_payload(
        drug_names, diagnosis
    )

    # Merge dosing alerts + SQL interaction alerts for the LLM auditor
    all_safety_alerts = dosing_alerts + sql_interaction_alerts

    return structured_data, all_safety_alerts, context_payload


# ─── Legacy per-drug helper (retained for backward compatibility) ──────────────
# check_local_databases() is kept so existing imports in the Live Scanner page
# do not break. The Live Scanner page will be updated to use run_full_pipeline().

def check_local_databases(
    extracted_drug: str,
    extracted_dose,
    extracted_concentration: str,
    patient_current_meds: str,
    patient_age,
    patient_gender: str,
) -> dict:
    """
    Legacy single-drug helper — retained for backward compatibility.
    New code should use run_full_pipeline() instead.
    """
    safety_report = {
        "drug": extracted_drug,
        "dose_mg": extracted_dose,
        "concentration": extracted_concentration,
        "dose_flag": False,
        "interaction_flag": False,
        "alerts": [],
        "context_for_llm": "",
    }

    try:
        dose_float = float(
            "".join(filter(lambda x: x.isdigit() or x == ".", str(extracted_dose)))
        )
        conn = sqlite3.connect("pharmacy.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT max_daily_dose_mg FROM advanced_dosing_rules
            WHERE drug_name = ? COLLATE NOCASE
              AND (concentration = ? OR concentration = 'UNKNOWN')
              AND ? >= min_age_yrs AND ? <= max_age_yrs
              AND (gender = ? OR gender = 'ALL')
            """,
            (extracted_drug, extracted_concentration, patient_age, patient_age, patient_gender),
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            max_dose = result[0]
            if max_dose == 0:
                safety_report["dose_flag"] = True
                safety_report["alerts"].append(
                    f"CRITICAL: {extracted_drug} is STRICTLY BANNED for Age {patient_age}."
                )
            elif dose_float > max_dose:
                safety_report["dose_flag"] = True
                safety_report["alerts"].append(
                    f"DOSING ERROR: {dose_float}mg exceeds max limit of {max_dose}mg "
                    f"for Age {patient_age} using {extracted_concentration}."
                )
        else:
            safety_report["alerts"].append(
                f"WARNING: No local dosing rules found for '{extracted_drug}' "
                f"at concentration '{extracted_concentration}'."
            )
    except Exception as e:
        print(f"[Math Check] Error: {e}")

    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = chroma_client.get_or_create_collection(name=CHROMA_COLLECTION)
        results = collection.get(ids=[extracted_drug.lower()])
        if results["documents"]:
            safety_report["context_for_llm"] = results["documents"][0]
            safety_report["interaction_flag"] = True
    except Exception as e:
        print(f"[Vector DB] Error: {e}")

    return safety_report


# ─── CLI entry point (standalone testing) ─────────────────────────────────────

if __name__ == "__main__":
    print("\n📷 [1] Scanning Prescription...")
    raw_ocr_text = ocr_reader.extract_text("prescription.png")

    if raw_ocr_text:
        print("🧠 [2] AI extracting demographics and meds...")
        structured_data = extractor.parse_prescription_text(raw_ocr_text)

        if structured_data and "medications" in structured_data:
            print("\n⚡ [3] Running full RAG pipeline...")
            extracted_json, dosing_alerts, context_payload = run_full_pipeline(structured_data)

            print(f"\n🚨 Dosing Alerts ({len(dosing_alerts)}):")
            for alert in dosing_alerts:
                print(f"   • {alert}")

            print("\n📚 Context payload preview (first 500 chars):")
            print(context_payload[:500])

            print("\n🤖 [4] BioMistral Senior Clinical Auditor generating report...")
            final_summary = llm_generator.generate_pharmacist_warning(
                extracted_json, dosing_alerts, context_payload
            )

            print("\n==========================================")
            print("⚕️  FINAL PHARMACIST DASHBOARD:")
            print("==========================================")
            print(final_summary)
            print("==========================================")