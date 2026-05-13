# Admin Dashboard — Architectural Documentation

> **Module:** `pages/3_📊_Admin_Dashboard.py`
> **Role:** Human-in-the-Loop Knowledge Management Interface
> **Last Updated:** May 2026

---

## 1. Component Tree

The diagram below shows how the Admin Dashboard sits within the full TechCare project and which external stores it directly reads from and writes to.

```
TechCare-Pharmacy-ai-assistant/
│
├── app.py                          ← Streamlit entry point (multi-page router)
│
├── pages/
│   ├── 1_🔬_Live_Scanner.py        ← CONSUMER of pharmacy.db (reads SQLite tripwires)
│   ├── 2_💬_Clinical_Chatbot.py    ← CONSUMER of ChromaDB
│   └── 3_📊_Admin_Dashboard.py     ◄─── THIS FILE (PRODUCER / knowledge manager)
│
├── auto_learner.py                 ◄─── Primary backend called by Admin Dashboard
│   ├── _ensure_schema()            │    Guarantees both tables exist before any read/write
│   ├── check_if_exists()           │    SQLite existence check (pre-conflict gate)
│   ├── get_existing_rules()        │    Reads current advanced_dosing_rules for diff view
│   ├── fetch_new_rules_dry_run()   │    Full FDA fetch + BioMistral extraction (no DB write)
│   ├── save_rules_to_db()          │    Overwrites advanced_dosing_rules for a drug
│   ├── save_interactions_to_db()   │    Appends to interactions (with dedup logic)
│   └── learn_and_save_drug()       │    Full pipeline: fetch → ChromaDB → SQLite (both tables)
│
├── sidebar_menu.py                 ← Shared navigation component
│
├── pharmacy.db  (SQLite)
│   ├── advanced_dosing_rules       ◄─── READ (diff display) + WRITTEN (on Approve)
│   └── interactions                ◄─── READ (tab view)    + WRITTEN (on Approve)
│
└── chroma_data/  (ChromaDB)
    └── drug_interactions           ← WRITTEN indirectly via auto_learner.learn_and_save_drug()
                                      (raw FDA label text stored here for Live Scanner RAG)
```

### Key Architectural Distinction

| Page | Role w.r.t. pharmacy.db |
|---|---|
| `Admin_Dashboard.py` | **PRODUCER** — creates and updates rules |
| `Live_Scanner.py` | **CONSUMER** — reads rules as deterministic safety tripwires |
| `Clinical_Chatbot.py` | **CONSUMER** — reads ChromaDB vector store only |

---

## 2. Module & Dependency Breakdown

| Import | Source | Why Used in This Page |
|---|---|---|
| `streamlit` | External (pip) | Full UI rendering — widgets, state, tabs, data editors, dialogs |
| `pandas` | External (pip) | DataFrame wrapping for `st.dataframe()` and `st.data_editor()`; `pd.read_sql_query()` for live table display; `.to_dict(orient="records")` to convert edited grids back to Python lists |
| `sqlite3` | Python stdlib | Direct SQLite connection for the two `@st.cache_data` read functions (`load_dosing_rules`, `load_interactions`) |
| `os` | Python stdlib | `os.path.exists("failed_queue.txt")` check for the Quarantine Queue section |
| `time` | Python stdlib | `time.sleep()` pauses after batch ingestion success/conflict messages to give the pharmacist time to read them before `st.rerun()` fires |
| `auto_learner` | Internal module | All database read/write operations — the dashboard has **no direct SQLite writes of its own**; every mutation is delegated to `auto_learner` functions |
| `sidebar_menu` | Internal module | Shared `draw_sidebar()` call for consistent navigation across all pages |

> **Note:** The Admin Dashboard intentionally does **not** import `chromadb` directly. ChromaDB writes happen inside `auto_learner.learn_and_save_drug()`, keeping the dashboard decoupled from the vector store layer.

---

## 3. The Granular Merge Workflow — Step-by-Step

### Trigger Condition

The Merge Conflict UI activates only when `st.session_state.conflict_queue` is non-empty. Items are enqueued when the dashboard detects that a drug being ingested **already exists** in `advanced_dosing_rules`.

```
pharmacist types drug name → "Fetch & Learn" clicked
         │
         ▼
auto_learner.check_if_exists(drug_name)
         │
    ┌────┴────┐
   YES        NO
    │          └─► auto_learner.learn_and_save_drug() → writes directly → done
    ▼
auto_learner.get_existing_rules()     ← reads current DB state for diff display
auto_learner.fetch_new_rules_dry_run() ← hits OpenFDA + BioMistral (DRY RUN — no DB write)
         │
         ▼
st.session_state.conflict_queue.append({
    "drug":      drug_name,
    "old_rules": [list of current SQLite rows],
    "new_rules": { "dosing_rules": [...], "known_interactions": [...] }
})
         │
         ▼
st.rerun()  → Merge Conflict UI renders
```

### Step 1 — FDA Fetch (`auto_learner.fetch_new_rules_dry_run`)

```
OpenFDA API → drug label JSON
    │
    ├── dosage_and_administration
    ├── indications_and_usage
    ├── drug_interactions          ← primary interaction text
    ├── boxed_warning              ← highest-severity warnings
    └── contraindications
         │
         ▼
    ChromaDB upsert (raw label text stored for Live Scanner RAG)
         │
         ▼
    BioMistral (biomistral model, temp=0.1, format="json")
```

### Step 2 — BioMistral Dual Extraction

BioMistral is prompted to return a **single JSON object with two keys**:

```json
{
  "dosing_rules": [
    {
      "concentration":     "500 mg",
      "indication":        "General",
      "min_age_yrs":       18,
      "max_age_yrs":       120,
      "gender":            "ALL",
      "max_daily_dose_mg": 4000.0
    }
  ],
  "known_interactions": [
    {
      "interacting_drug": "warfarin",
      "severity":         "MAJOR",
      "reason":           "NSAIDs displace warfarin from albumin binding, raising free warfarin levels."
    }
  ]
}
```

The system prompt includes:
- A **strict severity enum**: `CONTRAINDICATED | MAJOR | MODERATE | MINOR`
- A rule that **only named drugs** (not drug classes) may appear in `interacting_drug`
- Dose unit normalisation instructions (mcg → mg conversion)

### Step 3 — Payload Unpacking (`_unpack_new_rules`)

```python
def _unpack_new_rules(new_rules_data) -> tuple[list, list]:
```

This helper runs **before** any UI rendering and defensively handles three schema types:

| Input type | `dosing_rules` | `known_interactions` |
|---|---|---|
| New dict `{"dosing_rules": [...], "known_interactions": [...]}` | Extracted | Extracted |
| Legacy plain `list` (old schema) | Used as-is | `[]` empty |
| `None` / unexpected | `[]` | `[]` |

### Step 4 — Editable Grid Rendering

Both lists are passed to `st.data_editor()`:

```python
edited_dosing_df = st.data_editor(
    pd.DataFrame(new_dosing_rules),
    num_rows="dynamic",                    # "+" to add rows, row selection to delete
    key=f"editor_dosing_{drug_name}",      # unique key prevents state bleed across queue items
)
```

**Why unique keys?** Streamlit identifies widgets by key. If two consecutive conflict items in the queue both rendered a data_editor with the same key, the second would silently inherit the edited state of the first, potentially saving row data for the wrong drug.

The **left column** renders the existing DB rules as a read-only `st.dataframe()` for comparison. The pharmacist sees old vs. new side-by-side and can delete hallucinated rows or fix typos directly in the right-column grids before proceeding.

### Step 5 — Granular Checkbox Gate

```
┌─────────────────────────────────────────────────────┐
│  #### Select Categories to Save                      │
│                                                      │
│  [✓] Overwrite Dosing Rules   [✓] Append Interactions│
│   ↑ defaults True if table     ↑ defaults True if    │
│     has data, False if empty     table has data       │
└─────────────────────────────────────────────────────┘
```

The `value=not edited_dosing_df.empty` default means:
- If BioMistral returned dosing rules → checkbox pre-ticked
- If BioMistral returned nothing for that category → checkbox pre-unticked

This prevents accidental writes of empty data while removing the need for the pharmacist to think about toggling in the common case.

### Step 6 — Conditional Save Logic (Approve Button)

```
"✅ Approve & Save Selected" clicked
           │
    ┌──────┴──────────────────────────────┐
    │                                     │
    ▼                                     ▼
do_save_dosing == True              do_save_interactions == True
AND edited_dosing_df not empty      AND edited_interactions_df not empty
    │                                     │
    ▼                                     ▼
edited_dosing_df                    edited_interactions_df
  .to_dict(orient="records")          .to_dict(orient="records")
           │                                     │
           ▼                                     ▼
auto_learner.save_rules_to_db()    auto_learner.save_interactions_to_db()
  DELETE FROM advanced_dosing_rules    SELECT count(*) → skip if pair exists
  WHERE drug_name = ?                  INSERT INTO interactions (drug_a, drug_b,
  INSERT INTO advanced_dosing_rules      severity, mechanism, clinical_note)
  (drug_name, concentration, ...)
```

Four terminal states handled after Approve:

| Checkbox | Table | Outcome |
|---|---|---|
| ✓ checked | Has data | Written + success message |
| ✓ checked | Empty | Warning: "table is empty — nothing written" |
| ✗ unchecked | (any) | Silently skipped |
| Both unchecked | (any) | Warning: "No categories selected" |

After all routes execute:
```python
time.sleep(1.5)
st.session_state.conflict_queue.pop(0)   # Remove resolved conflict
st.rerun()                                # Advance to next conflict (or clear queue)
```

---

## 4. System-Wide Reactivity — How Admin Changes Propagate

### The SQLite Tripwire Model

`pharmacy.db` is the **shared state layer** of the entire TechCare application. Both the Admin Dashboard (producer) and the Live Scanner (consumer) connect to the **same file** on disk. There is no API layer, no cache invalidation step, and no message queue — changes are immediately visible to any subsequent reader.

```
Admin Dashboard                     pharmacy.db                 Live Scanner
     │                                   │                           │
     │  "Approve & Save Selected"         │                           │
     ├──────────────────────────────────►│                           │
     │  save_rules_to_db()               │  advanced_dosing_rules    │
     │  → DELETE old rows                │  ┌────────────────────┐  │
     │  → INSERT new rows                │  │ drug_name          │  │
     │                                   │  │ max_daily_dose_mg  │◄─┤ run_dosing_checks()
     │  save_interactions_to_db()        │  │ min_age_yrs        │  │ compares extracted
     │  → INSERT new pairs (dedup)       │  │ max_age_yrs        │  │ dose vs. this value
     │                                   │  └────────────────────┘  │
     │                                   │                           │
     │                                   │  interactions             │
     │                                   │  ┌────────────────────┐  │
     │                                   │  │ drug_a             │  │
     │                                   │  │ drug_b             │◄─┤ _check_sql_interactions()
     │                                   │  │ severity           │  │ itertools pairs loop
     │                                   │  │ mechanism          │  │ triggers Sniper Search
     │                                   │  │ clinical_note      │  │
     │                                   │  └────────────────────┘  │
```

### Concrete Effect on Live Scanner Safety Checks

When the pharmacist approves a drug update on the Admin Dashboard, **two deterministic safety checks in the Live Scanner are immediately updated** for the next scan:

#### Tripwire 1 — Dosing Check (`run_dosing_checks`)

```python
# live_checkout.py — Phase 2
cursor.execute("""
    SELECT max_daily_dose_mg FROM advanced_dosing_rules
    WHERE drug_name = ? COLLATE NOCASE
      AND ? >= min_age_yrs AND ? <= max_age_yrs
      AND (gender = ? OR gender = 'ALL')
""", (drug, patient_age, patient_age, patient_gender))
```

If the Admin Dashboard just approved a rule setting `max_daily_dose_mg = 4000` for Acetaminophen, **the very next prescription scan** will compare the extracted dose against `4000`. No restart required.

#### Tripwire 2 — Interaction SQL Trigger (`_check_sql_interactions`)

```python
# live_checkout.py — Hybrid Engine Phase 1
for raw_a, raw_b in itertools.combinations(drug_names, 2):
    drug_a = raw_a.replace("-", " ").replace("/", " ").split()[0].lower()
    drug_b = raw_b.replace("-", " ").replace("/", " ").split()[0].lower()

    cursor.execute("""
        SELECT severity, mechanism, clinical_note FROM interactions
        WHERE (drug_a = ? AND drug_b = ?) OR (drug_a = ? AND drug_b = ?)
        LIMIT 1
    """, (drug_a, drug_b, drug_b, drug_a))
```

If the Admin Dashboard approved a new `CONTRAINDICATED` pair (e.g., `phenelzine` ↔ `tramadol`), the next scan containing both drugs will:

1. **Find the row** in `interactions` → append a rich alert to `sql_interaction_alerts`
2. **Trigger the Sniper Search** → query ChromaDB specifically for that pair
3. **Pass the combined payload** to `llm_generator` → the Senior Clinical Auditor reports it as `CRITICAL INTERACTION` at the top of the report

### ChromaDB — Indirect Propagation

When a **new** drug is added (not a conflict — the `else` branch), `learn_and_save_drug()` also writes the raw FDA label text to the `drug_interactions` ChromaDB collection. This feeds the Live Scanner's Sniper Search for any future interaction involving that drug, even if it is not yet in the `interactions` SQL table.

```
Admin: "Fetch & Learn" for new drug
    └─► auto_learner.learn_and_save_drug()
              ├─► ChromaDB.upsert(drug_name, raw_fda_text)
              │        └─► Live Scanner ChromaDB Sniper Search can now retrieve this text
              └─► SQLite: advanced_dosing_rules + interactions updated
```

---

## 5. UI State Machine

The Admin Dashboard has two mutually exclusive render modes:

```
                    ┌─────────────────────────────────┐
                    │  conflict_queue is EMPTY         │
                    │                                  │
                    │  Show:                           │
                    │  • Section 1 (ingestion inputs)  │
                    │  • Section 3 (tabbed DB tables)  │
                    │  • Section 4 (quarantine queue)  │
                    └──────────┬──────────────────────┘
                               │
             conflict_queue.append(item)
                               │
                               ▼
                    ┌─────────────────────────────────┐
                    │  conflict_queue has items        │
                    │                                  │
                    │  Show:                           │
                    │  • Section 1 (ingestion inputs)  │
                    │  • Section 2 (Merge Conflict UI) │
                    │    [hides Section 3 tables]      │
                    └──────────┬──────────────────────┘
                               │
              Approve or Reject → pop(0) → st.rerun()
                               │
             ┌─────────────────┴───────────────────┐
             │ queue empty?                          │ queue not empty?
             ▼                                       ▼
         Return to                         Next conflict
         idle state                        renders (FIFO)
```

> **Design rationale:** The live database tables (Section 3) are hidden during conflict resolution to prevent the pharmacist from being distracted by the current DB state while reviewing a proposed change. They reappear only after the queue is fully resolved.

---

## 6. Cache & Performance Notes

```python
@st.cache_data(ttl=60)
def load_dosing_rules(): ...

@st.cache_data(ttl=60)
def load_interactions(): ...
```

Both read functions are decorated with `@st.cache_data(ttl=60)`. This means:
- Streamlit caches the returned DataFrame in memory
- Any widget interaction (clicking a tab, expanding a section) that triggers a re-render does **not** re-query SQLite
- The cache expires after **60 seconds**, ensuring the tables shown are at most 1 minute stale after an Approve action

If you need to see changes immediately after an Approve, trigger `st.cache_data.clear()` or wait for the TTL to expire.
