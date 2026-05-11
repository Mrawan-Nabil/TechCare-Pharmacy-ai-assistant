"""
auto_learner.py — TechCare Autonomous Knowledge Engine
=======================================================
Fetches drug data from the OpenFDA API, runs BioMistral to extract
structured clinical rules, and persists them to two stores:

  SQLite  (pharmacy.db)
    - advanced_dosing_rules : max daily dose per age/gender/concentration
    - interactions           : confirmed drug-to-drug interaction pairs

  ChromaDB (./chroma_data)
    - drug_interactions collection : raw FDA label text for Sniper Search
"""

import json
import sqlite3

import chromadb
import ollama
import requests

# ─── Database bootstrap ───────────────────────────────────────────────────────

def _ensure_schema():
    """
    Creates all required tables if they do not already exist.
    Called at the start of every public function to guarantee schema integrity.
    """
    conn = sqlite3.connect("pharmacy.db")
    cursor = conn.cursor()

    # Dosing rules table (pre-existing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS advanced_dosing_rules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name       TEXT NOT NULL COLLATE NOCASE,
            concentration   TEXT DEFAULT 'UNKNOWN',
            indication      TEXT DEFAULT 'General',
            min_age_yrs     INTEGER DEFAULT 0,
            max_age_yrs     INTEGER DEFAULT 120,
            gender          TEXT DEFAULT 'ALL',
            max_daily_dose_mg REAL DEFAULT 0.0
        )
    """)

    # Interactions table (new — supports Hybrid Rules Engine)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_a        TEXT NOT NULL COLLATE NOCASE,
            drug_b        TEXT NOT NULL COLLATE NOCASE,
            severity      TEXT NOT NULL,
            mechanism     TEXT,
            clinical_note TEXT
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_interactions_pair
        ON interactions (drug_a, drug_b)
    """)

    conn.commit()
    conn.close()


# ─── Existence checks ─────────────────────────────────────────────────────────

def check_if_exists(drug_name):
    """Checks if the drug already has dosing rules in SQLite."""
    _ensure_schema()
    conn = sqlite3.connect("pharmacy.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM advanced_dosing_rules WHERE drug_name = ?",
        (drug_name.lower(),),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0


def get_existing_rules(drug_name):
    """Returns current DB rules as a list of dicts for Streamlit rendering."""
    conn = sqlite3.connect("pharmacy.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT concentration, indication, min_age_yrs, max_age_yrs, gender, max_daily_dose_mg
        FROM advanced_dosing_rules WHERE drug_name = ?
        """,
        (drug_name.lower(),),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# ─── Rule validation ──────────────────────────────────────────────────────────

def verify_rule_integrity(rule, drug_name):
    """Safety net: runs mathematical bounds-checking on the LLM's dosing output."""
    try:
        min_age = int(rule.get("min_age_yrs", 0))
        max_age = int(rule.get("max_age_yrs", 120))
        max_dose = float(rule.get("max_daily_dose_mg", 0.0))

        if min_age > max_age:
            return False
        if max_dose > 10000 or max_dose < 0 or min_age < 0:
            return False
        return True
    except Exception:
        return False


# ─── BioMistral extraction (upgraded dual-output schema) ──────────────────────

def extract_rules_and_interactions_with_llm(drug_name, fda_dosage_text,
                                             fda_indications_text, fda_interactions_text):
    """
    Sends FDA label sections to BioMistral and requests BOTH:
      1. Dosing rules (max_daily_dose_mg per population segment)
      2. Known interactions (interacting_drug, severity, reason)

    Returns a dict with keys 'dosing_rules' (list) and 'known_interactions' (list).
    """
    print(f"[BioMistral] Analysing FDA data for {drug_name}...")

    system_prompt = """
You are a clinical data extraction API. You will be given FDA drug label sections.
Your job is to extract TWO things and return them as a single JSON object:

1. dosing_rules: A list of maximum safe daily doses per patient population.
   Each rule must have:
   {
     "concentration": string (e.g. "500mg", "UNKNOWN"),
     "indication":    string (e.g. "General", "Pain"),
     "min_age_yrs":   integer,
     "max_age_yrs":   integer,
     "gender":        string ("M", "F", or "ALL"),
     "max_daily_dose_mg": float
   }

2. known_interactions: A list of specific drugs that interact with this drug.
   Extract ONLY named drugs (not drug classes). Each interaction must have:
   {
     "interacting_drug": string (generic drug name, lowercase),
     "severity":         string — MUST be one of: "CONTRAINDICATED", "MAJOR", "MODERATE", "MINOR",
     "reason":           string (one concise clinical sentence)
   }

CRITICAL RULES:
- Convert ALL dose units to milligrams (mg). 290 mcg = 0.29 mg.
- If no specific concentration is mentioned, use "UNKNOWN".
- If a dosing rule applies to adults, set min_age_yrs=18, max_age_yrs=120.
- For interactions: only include drugs explicitly named in the text. Do NOT invent drugs.
- Severity must be exactly one of the four allowed values.

Return ONLY this JSON structure, nothing else:
{
  "dosing_rules": [ { ... } ],
  "known_interactions": [ { "interacting_drug": "...", "severity": "...", "reason": "..." } ]
}
"""

    user_prompt = (
        f"DRUG: {drug_name}\n\n"
        f"INDICATIONS:\n{fda_indications_text}\n\n"
        f"DOSAGE AND ADMINISTRATION:\n{fda_dosage_text}\n\n"
        f"DRUG INTERACTIONS:\n{fda_interactions_text}"
    )

    try:
        response = ollama.chat(
            model="biomistral",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            format="json",
            options={"temperature": 0.1, "num_predict": 1500},
        )
        raw = json.loads(response["message"]["content"])

        # Normalise — BioMistral sometimes wraps the array in an outer key
        if isinstance(raw, dict):
            dosing = raw.get("dosing_rules", [])
            if not dosing:
                # Fallback: check if it returned the old flat array format
                for key, val in raw.items():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        if "max_daily_dose_mg" in val[0]:
                            dosing = val
                            break
            interactions = raw.get("known_interactions", [])
        else:
            dosing = raw if isinstance(raw, list) else []
            interactions = []

        return {"dosing_rules": dosing, "known_interactions": interactions}

    except Exception as e:
        print(f"[BioMistral] Extraction error for {drug_name}: {e}")
        return {"dosing_rules": [], "known_interactions": []}


# ─── Legacy extraction wrapper (for backward compatibility) ───────────────────

def extract_dosing_rules_with_llm(drug_name, fda_dosage_text, fda_indications_text):
    """
    Retained for any existing callers. Delegates to the upgraded dual-output
    extractor and returns only the dosing_rules list.
    """
    result = extract_rules_and_interactions_with_llm(
        drug_name, fda_dosage_text, fda_indications_text,
        fda_interactions_text="No interaction data provided."
    )
    return result["dosing_rules"]


# ─── SQLite write logic ───────────────────────────────────────────────────────

def save_rules_to_db(drug_name, valid_rules):
    """Overwrites the dosing rules for this drug in SQLite."""
    if not valid_rules:
        return False
    _ensure_schema()
    conn = sqlite3.connect("pharmacy.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM advanced_dosing_rules WHERE drug_name = ?",
            (drug_name.lower(),),
        )
        for rule in valid_rules:
            cursor.execute(
                """
                INSERT INTO advanced_dosing_rules
                (drug_name, concentration, indication, min_age_yrs, max_age_yrs, gender, max_daily_dose_mg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    drug_name.lower(),
                    rule["concentration"],
                    rule["indication"],
                    rule["min_age_yrs"],
                    rule["max_age_yrs"],
                    rule["gender"],
                    rule["max_daily_dose_mg"],
                ),
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"[SQLite] Dosing rule save error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def save_interactions_to_db(drug_name, known_interactions):
    """
    Inserts interaction pairs for the newly learned drug into the interactions table.
    drug_name = drug_a (the drug being learned)
    known_interactions = list of {interacting_drug, severity, reason} dicts from the LLM

    Uses INSERT OR IGNORE semantics to avoid duplicating pairs that the
    migrate_interactions.py seed already added.
    """
    if not known_interactions:
        return

    _ensure_schema()

    VALID_SEVERITIES = {"CONTRAINDICATED", "MAJOR", "MODERATE", "MINOR"}

    conn = sqlite3.connect("pharmacy.db")
    cursor = conn.cursor()

    inserted = 0
    skipped = 0

    for item in known_interactions:
        if not isinstance(item, dict):
            continue

        drug_b = str(item.get("interacting_drug", "")).strip().lower()
        severity = str(item.get("severity", "MODERATE")).strip().upper()
        reason = str(item.get("reason", "")).strip()

        if not drug_b:
            continue

        # Normalise severity to one of the four allowed values
        if severity not in VALID_SEVERITIES:
            severity = "MODERATE"

        # Check if either direction of the pair already exists
        cursor.execute(
            """
            SELECT COUNT(*) FROM interactions
            WHERE (drug_a = ? AND drug_b = ?)
               OR (drug_a = ? AND drug_b = ?)
            """,
            (drug_name.lower(), drug_b, drug_b, drug_name.lower()),
        )
        if cursor.fetchone()[0] > 0:
            skipped += 1
            continue

        cursor.execute(
            """
            INSERT INTO interactions (drug_a, drug_b, severity, mechanism, clinical_note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (drug_name.lower(), drug_b, severity, reason, reason),
        )
        inserted += 1
        print(
            f"  [Interactions] {drug_name.upper()} <-> {drug_b.upper()} "
            f"[{severity}]"
        )

    conn.commit()
    conn.close()

    print(
        f"  [Interactions] {inserted} new pair(s) inserted, "
        f"{skipped} duplicate(s) skipped for {drug_name.upper()}."
    )


# ─── Main fetch pipeline ──────────────────────────────────────────────────────

def fetch_new_rules_dry_run(drug_name):
    """
    Hits the OpenFDA API, extracts all relevant label sections,
    saves the raw text to ChromaDB, and runs BioMistral extraction.

    Returns a dict: {'dosing_rules': [...], 'known_interactions': [...]}
    Returns empty dict on failure.
    """
    url = (
        f"https://api.fda.gov/drug/label.json"
        f"?search=openfda.generic_name:\"{drug_name}\"&limit=1"
    )
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            print(f"[FDA] No data found for '{drug_name}' (HTTP {response.status_code})")
            return {}

        drug_data = response.json()["results"][0]

        # Extract all relevant FDA label sections
        fda_warnings       = drug_data.get("warnings",                ["No warnings listed."])[0]
        fda_boxed_warning  = drug_data.get("boxed_warning",           ["No boxed warning."])[0]
        fda_dosage_text    = drug_data.get("dosage_and_administration",["No dosage listed."])[0]
        fda_interactions   = drug_data.get("drug_interactions",        ["No interactions listed."])[0]
        fda_indications    = drug_data.get("indications_and_usage",   ["No indications listed."])[0]
        fda_contraindic    = drug_data.get("contraindications",        ["No contraindications listed."])[0]

        # ── ChromaDB: save raw FDA label text (DO NOT MODIFY THIS BLOCK) ─────
        # This raw text feeds the Live Scanner's Sniper Search via ChromaDB.
        chroma_text = (
            f"DRUG: {drug_name}\n"
            f"INDICATIONS: {fda_indications}\n"
            f"BOXED WARNING: {fda_boxed_warning}\n"
            f"WARNINGS: {fda_warnings}\n"
            f"CONTRAINDICATIONS: {fda_contraindic}\n"
            f"INTERACTIONS: {fda_interactions}\n"
            f"DOSAGE: {fda_dosage_text}"
        )

        if len(chroma_text.strip()) > 100:
            chroma_client = chromadb.PersistentClient(path="./chroma_data")
            collection = chroma_client.get_or_create_collection(name="drug_interactions")
            collection.upsert(
                documents=[chroma_text],
                ids=[drug_name.lower()],
                metadatas=[{"source": "OpenFDA API", "drug": drug_name.lower()}],
            )
            print(f"  [ChromaDB] Raw FDA label saved for {drug_name.upper()}.")
        # ─────────────────────────────────────────────────────────────────────

        # ── BioMistral: extract dosing rules + interactions ───────────────────
        extracted = extract_rules_and_interactions_with_llm(
            drug_name, fda_dosage_text, fda_indications, fda_interactions
        )

        # Validate dosing rules
        valid_rules = []
        for rule in extracted.get("dosing_rules", []):
            if isinstance(rule, dict) and verify_rule_integrity(rule, drug_name):
                valid_rules.append({
                    "concentration":    str(rule.get("concentration", "UNKNOWN")),
                    "indication":       str(rule.get("indication", "General")),
                    "min_age_yrs":      int(rule.get("min_age_yrs", 0)),
                    "max_age_yrs":      int(rule.get("max_age_yrs", 120)),
                    "gender":           str(rule.get("gender", "ALL")),
                    "max_daily_dose_mg": float(rule.get("max_daily_dose_mg", 0.0)),
                })

        return {
            "dosing_rules":       valid_rules,
            "known_interactions": extracted.get("known_interactions", []),
        }

    except Exception as e:
        print(f"[FDA Fetch] Error for '{drug_name}': {e}")
        return {}


# ─── Public entry point ───────────────────────────────────────────────────────

def learn_and_save_drug(drug_name, interactive=False):
    """
    Full pipeline: FDA fetch → ChromaDB save → BioMistral extract →
    SQLite dosing rules write → SQLite interactions write.

    In batch/auto mode (interactive=False): skips if dosing rules already exist.
    Returns True on success, False on failure.
    """
    _ensure_schema()

    if check_if_exists(drug_name):
        if not interactive:
            print(f"[AutoLearn] {drug_name.upper()} exists in dosing rules. Skipping.")
            return True

    print(f"[AutoLearn] Fetching {drug_name.upper()} from OpenFDA...")
    result = fetch_new_rules_dry_run(drug_name)

    if not result:
        print(f"[AutoLearn] No data returned for {drug_name.upper()}.")
        return False

    # Write dosing rules to SQLite
    dosing_ok = save_rules_to_db(drug_name, result.get("dosing_rules", []))

    # Write interaction pairs to SQLite (new step)
    save_interactions_to_db(drug_name, result.get("known_interactions", []))

    return dosing_ok


if __name__ == "__main__":
    learn_and_save_drug("tramadol", interactive=True)