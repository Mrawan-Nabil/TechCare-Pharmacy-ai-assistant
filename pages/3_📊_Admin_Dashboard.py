import streamlit as st
import pandas as pd
import sqlite3
import os
import time

import auto_learner
from sidebar_menu import draw_sidebar

# --- SHARED SIDEBAR ---
draw_sidebar()

# ==========================================
# PAGE: ADMIN DASHBOARD & DATABASE INTEGRITY
# ==========================================
st.markdown("### Admin Dashboard & Database Integrity")
st.caption("Manage your clinical database and autonomous learning pipeline.")

# Initialise the Conflict Resolution Queue in session state
if "conflict_queue" not in st.session_state:
    st.session_state.conflict_queue = []


# ─── Helper: unpack new_rules safely ──────────────────────────────────────────
# auto_learner.fetch_new_rules_dry_run() now returns:
#   { "dosing_rules": [...], "known_interactions": [...] }
# This helper defensively extracts both lists regardless of whether the caller
# stored the new schema dict or the legacy plain list.

def _unpack_new_rules(new_rules_data) -> tuple[list, list]:
    """
    Returns (dosing_rules, known_interactions) from the new_rules payload.
    Handles both the new dict schema and the legacy plain list gracefully.
    """
    if isinstance(new_rules_data, dict):
        dosing      = new_rules_data.get("dosing_rules", []) or []
        interactions = new_rules_data.get("known_interactions", []) or []
    elif isinstance(new_rules_data, list):
        # Legacy format — plain list of dosing rules, no interactions
        dosing      = new_rules_data
        interactions = []
    else:
        dosing      = []
        interactions = []
    return dosing, interactions


# --- 1. Manual & Excel Upload Boxes ---
st.markdown("#### Teach TechCare New Medications")
col_manual, col_excel = st.columns(2)

with col_manual:
    with st.container(border=True):
        st.markdown("**Single Drug Ingestion**")
        manual_drug = st.text_input(
            "Enter generic drug name",
            label_visibility="collapsed",
            placeholder="e.g. 'Metformin'",
        )

        if st.button("Fetch & Learn", type="primary", use_container_width=True):
            if manual_drug:
                drug_clean = manual_drug.strip().lower()

                if auto_learner.check_if_exists(drug_clean):
                    with st.spinner(
                        f"⚠️ {drug_clean.upper()} exists. Fetching new AI rules for comparison..."
                    ):
                        old_r = auto_learner.get_existing_rules(drug_clean)
                        # fetch_new_rules_dry_run returns the new dual-schema dict
                        new_r = auto_learner.fetch_new_rules_dry_run(drug_clean)
                        st.session_state.conflict_queue.append(
                            {"drug": drug_clean, "old_rules": old_r, "new_rules": new_r}
                        )
                    st.rerun()
                else:
                    with st.spinner(
                        f"Fetching {drug_clean.upper()} from FDA & extracting rules..."
                    ):
                        success = auto_learner.learn_and_save_drug(
                            drug_clean, interactive=False
                        )
                    if success:
                        st.success(f"✅ {drug_clean.upper()} integrated successfully!")
                    else:
                        st.error(
                            f"❌ Failed to process {drug_clean.upper()}. Check Quarantine Queue."
                        )
            else:
                st.warning("Please enter a drug name.")

with col_excel:
    with st.container(border=True):
        st.markdown("**Batch Excel/CSV Ingestion**")
        batch_file = st.file_uploader(
            "Upload a list of drugs",
            type=["csv", "xlsx", "xls"],
            label_visibility="collapsed",
        )

        if batch_file and st.button(
            "Run Bulk Ingestion", type="primary", use_container_width=True
        ):
            with st.spinner("Processing batch file..."):
                try:
                    if batch_file.name.endswith(".csv"):
                        df_batch = pd.read_csv(batch_file)
                    else:
                        df_batch = pd.read_excel(batch_file)

                    drugs_to_process = (
                        df_batch.iloc[:, 0].dropna().astype(str).tolist()
                    )
                    progress_bar = st.progress(0)

                    success_count  = 0
                    conflict_count = 0

                    for idx, drug in enumerate(drugs_to_process):
                        drug_clean  = drug.strip().lower()
                        status_text = st.empty()
                        status_text.text(
                            f"Processing ({idx + 1}/{len(drugs_to_process)}): {drug_clean.upper()}"
                        )

                        if auto_learner.check_if_exists(drug_clean):
                            old_r = auto_learner.get_existing_rules(drug_clean)
                            new_r = auto_learner.fetch_new_rules_dry_run(drug_clean)
                            st.session_state.conflict_queue.append(
                                {
                                    "drug":      drug_clean,
                                    "old_rules": old_r,
                                    "new_rules": new_r,
                                }
                            )
                            conflict_count += 1
                        else:
                            is_success = auto_learner.learn_and_save_drug(
                                drug_clean, interactive=False
                            )
                            if is_success:
                                success_count += 1

                        progress_bar.progress((idx + 1) / len(drugs_to_process))
                        status_text.empty()
                        time.sleep(1)  # API breathing room

                    st.success(
                        f"✅ Batch Complete! "
                        f"Added New: {success_count} | Conflicts Queued: {conflict_count}"
                    )
                    time.sleep(2.5)

                    if conflict_count > 0:
                        st.rerun()

                except Exception as e:
                    st.error(f"Failed to read file: {e}")


# --- 2. THE MERGE CONFLICT UI (QUEUE PROCESSOR) ---
if len(st.session_state.conflict_queue) > 0:

    current_conflict = st.session_state.conflict_queue[0]
    drug_name        = current_conflict["drug"]
    queue_length     = len(st.session_state.conflict_queue)

    # ── Unpack the new dual-schema from new_rules ──────────────────────────────
    new_dosing_rules, new_interactions = _unpack_new_rules(current_conflict["new_rules"])
    old_rules = current_conflict["old_rules"]   # Always a plain list (dosing only)

    st.markdown("---")
    st.markdown(f"### ⚠️ Merge Conflict: `{drug_name.upper()}`")
    st.info(
        f"**Conflict 1 of {queue_length}.** "
        f"You can **edit or delete rows** in the AI proposals before approving. "
        f"Use the checkboxes below to select which categories to save."
    )

    # ── Side-by-side: OLD (dosing only) vs NEW (dosing + interactions) ─────────
    col_old, col_new = st.columns(2)

    with col_old:
        st.markdown("#### 🟥 Current Database Rules (Dosing)")
        if old_rules:
            st.dataframe(
                pd.DataFrame(old_rules),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No existing dosing rules found in the database.")

    with col_new:
        st.markdown("#### 🟩 Newly Fetched AI Data — Edit Before Saving")

        # ── Editable: Proposed Dosing Rules ──────────────────────────────────
        st.subheader("Proposed Dosing Rules")
        if new_dosing_rules:
            edited_dosing_df = st.data_editor(
                pd.DataFrame(new_dosing_rules),
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                key=f"editor_dosing_{drug_name}",
            )
        else:
            st.info("No new dosing rules found for this drug.")
            edited_dosing_df = pd.DataFrame()

        # ── Editable: Proposed Interactions ──────────────────────────────
        st.subheader("Proposed Interactions")
        if new_interactions:
            edited_interactions_df = st.data_editor(
                pd.DataFrame(new_interactions),
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                key=f"editor_interactions_{drug_name}",
            )
        else:
            st.info("No new drug-drug interactions identified by the AI.")
            edited_interactions_df = pd.DataFrame()

    # ── Guard: warn if AI returned nothing at all ──────────────────────────────
    if not new_dosing_rules and not new_interactions:
        st.error(
            "⚠️ The LLM failed to extract any valid rules or interactions. "
            "It is recommended to **Reject** this update."
        )

    # ── Granular Save Checkboxes ───────────────────────────────────────────────
    st.markdown("#### Select Categories to Save")
    chk_col1, chk_col2 = st.columns(2)

    do_save_dosing = chk_col1.checkbox(
        "Overwrite Dosing Rules",
        value=not edited_dosing_df.empty,
        key=f"chk_dosing_{drug_name}",
        help="Replaces the current dosing rules with the edited proposals above.",
    )
    do_save_interactions = chk_col2.checkbox(
        "Append New Interactions",
        value=not edited_interactions_df.empty,
        key=f"chk_interactions_{drug_name}",
        help="Appends the edited interaction rows to the interactions table (duplicates are skipped).",
    )

    # ── Action Buttons ─────────────────────────────────────────────────────────
    st.markdown("")
    c1, c2 = st.columns(2)

    # REJECT — keeps existing DB entries, removes from queue
    if c1.button("❌ Reject Changes (Keep Existing)", use_container_width=True):
        st.session_state.conflict_queue.pop(0)
        st.rerun()

    # APPROVE — saves only the checked categories using the EDITED dataframes
    if c2.button(
        "✅ Approve & Save Selected", type="primary", use_container_width=True
    ):
        wrote_something = False

        # Route 1: Dosing rules → advanced_dosing_rules (overwrite)
        if do_save_dosing and not edited_dosing_df.empty:
            final_dosing = edited_dosing_df.to_dict(orient="records")
            auto_learner.save_rules_to_db(drug_name, final_dosing)
            st.success(
                f"✅ Dosing rules overwritten for **{drug_name.upper()}** "
                f"({len(final_dosing)} rule(s) from edited table)."
            )
            wrote_something = True
        elif do_save_dosing and edited_dosing_df.empty:
            st.warning("Dosing Rules checkbox is checked but the table is empty — nothing written.")

        # Route 2: Interactions → interactions table (append, dedup by auto_learner)
        if do_save_interactions and not edited_interactions_df.empty:
            final_interactions = edited_interactions_df.to_dict(orient="records")
            auto_learner.save_interactions_to_db(drug_name, final_interactions)
            st.success(
                f"✅ Interactions saved for **{drug_name.upper()}** "
                f"({len(final_interactions)} row(s) from edited table)."
            )
            wrote_something = True
        elif do_save_interactions and edited_interactions_df.empty:
            st.warning("Interactions checkbox is checked but the table is empty — nothing written.")

        if not wrote_something and not do_save_dosing and not do_save_interactions:
            st.warning("No categories were selected. Nothing was written to the database.")

        time.sleep(1.5)
        st.session_state.conflict_queue.pop(0)
        st.rerun()

    st.markdown("---")




# --- 3. Active Database Tables (cached — does not re-query on every frame) ---
@st.cache_data(ttl=60)
def load_dosing_rules():
    """Queries the SQLite database for the full dosing rules table."""
    conn = sqlite3.connect("pharmacy.db")
    try:
        df = pd.read_sql_query("SELECT * FROM advanced_dosing_rules", conn)
    finally:
        conn.close()
    return df


@st.cache_data(ttl=60)
def load_interactions():
    """Queries the SQLite database for the full interactions table."""
    conn = sqlite3.connect("pharmacy.db")
    try:
        df = pd.read_sql_query("SELECT * FROM interactions", conn)
    finally:
        conn.close()
    return df


# Show both tables only when there are no pending conflicts
if len(st.session_state.conflict_queue) == 0:

    tab_dosing, tab_interactions = st.tabs(["💊 Dosing Rules", "⚠️ Drug Interactions"])

    with tab_dosing:
        st.markdown("#### 📋 Active Dosing Rules (SQLite)")
        try:
            df_rules = load_dosing_rules()
            if not df_rules.empty:
                st.dataframe(df_rules, use_container_width=True, hide_index=True)
            else:
                st.info("Dosing rules table is empty. Add drugs above to populate.")
        except Exception as e:
            st.error(f"Could not load dosing rules: {e}")

    with tab_interactions:
        st.markdown("#### ⚡ Active Drug Interactions (SQLite)")
        try:
            df_interactions = load_interactions()
            if not df_interactions.empty:
                st.dataframe(df_interactions, use_container_width=True, hide_index=True)
            else:
                st.info(
                    "Interactions table is empty. "
                    "Run migrate_interactions.py or fetch drugs to populate."
                )
        except Exception as e:
            st.error(f"Could not load interactions table: {e}")



# --- 4. Quarantine Queue ---
if os.path.exists("failed_queue.txt"):
    with st.container(border=True):
        st.markdown("#### ⚠️ Quarantine Queue")
        with open("failed_queue.txt", "r") as f:
            st.text(f.read())
