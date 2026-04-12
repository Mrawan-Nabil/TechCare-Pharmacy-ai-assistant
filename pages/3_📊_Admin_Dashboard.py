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
st.markdown("### 📊 Admin Dashboard & Database Integrity")
st.caption("Manage your clinical database and autonomous learning pipeline.")

# Initialize the Conflict Resolution Queue in session state
if "conflict_queue" not in st.session_state:
    st.session_state.conflict_queue = []

# --- 1. Manual & Excel Upload Boxes ---
st.markdown("#### 🧠 Teach TechCare New Medications")
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
                        new_r = auto_learner.fetch_new_rules_dry_run(drug_clean)
                        # Push to the conflict resolution queue
                        st.session_state.conflict_queue.append(
                            {"drug": drug_clean, "old_rules": old_r, "new_rules": new_r}
                        )
                    st.rerun()
                else:
                    with st.spinner(
                        f"Fetching {drug_clean.upper()} from FDA & extracting math..."
                    ):
                        success = auto_learner.learn_and_save_drug(
                            drug_clean, interactive=False
                        )
                    if success:
                        st.success(f"✅ {drug_clean.upper()} integrated successfully!")
                    else:
                        st.error(
                            f"❌ Failed to process {drug_clean.upper()}. Check failed queue."
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

                    success_count = 0
                    conflict_count = 0

                    for idx, drug in enumerate(drugs_to_process):
                        drug_clean = drug.strip().lower()
                        status_text = st.empty()
                        status_text.text(
                            f"Processing ({idx + 1}/{len(drugs_to_process)}): {drug_clean.upper()}"
                        )

                        # Queue conflicts instead of silently overwriting
                        if auto_learner.check_if_exists(drug_clean):
                            old_r = auto_learner.get_existing_rules(drug_clean)
                            new_r = auto_learner.fetch_new_rules_dry_run(drug_clean)
                            st.session_state.conflict_queue.append(
                                {
                                    "drug": drug_clean,
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

                    # Summary after batch completes
                    st.success(
                        f"✅ Batch Complete! Added New: {success_count} | Conflicts Queued: {conflict_count}"
                    )
                    time.sleep(2.5)  # Give the user time to read the summary

                    if conflict_count > 0:
                        st.rerun()  # Refresh to pop open the Conflict UI below

                except Exception as e:
                    st.error(f"Failed to read file: {e}")

# --- 2. THE MERGE CONFLICT UI (QUEUE PROCESSOR) ---
if len(st.session_state.conflict_queue) > 0:

    # Grab the FIRST item in the queue
    current_conflict = st.session_state.conflict_queue[0]
    drug_name = current_conflict["drug"]
    queue_length = len(st.session_state.conflict_queue)

    st.markdown("---")
    st.markdown(f"### ⚠️ Merge Conflict: `{drug_name.upper()}`")
    st.info(
        f"**Conflict {1} of {queue_length}**. Please review the old vs. new dosing rules before overwriting."
    )

    col_old, col_new = st.columns(2)

    with col_old:
        st.markdown("#### 🟥 Current Database Rules")
        if current_conflict["old_rules"]:
            st.dataframe(
                pd.DataFrame(current_conflict["old_rules"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.write("No existing rules found.")

    with col_new:
        st.markdown("#### 🟩 Newly Fetched AI Rules")
        if current_conflict["new_rules"]:
            st.dataframe(
                pd.DataFrame(current_conflict["new_rules"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.error(
                "The LLM failed to extract valid new rules. You must reject this update."
            )

    c1, c2 = st.columns(2)

    # REJECT BUTTON — keeps existing DB entry, removes from queue
    if c1.button("❌ Reject Changes (Keep Existing)", use_container_width=True):
        st.session_state.conflict_queue.pop(0)
        st.rerun()

    # APPROVE BUTTON — overwrites DB entry, removes from queue
    if c2.button(
        "✅ Approve & Overwrite Database", type="primary", use_container_width=True
    ):
        if current_conflict["new_rules"]:
            auto_learner.save_rules_to_db(drug_name, current_conflict["new_rules"])
            st.success(f"Database successfully overwritten for {drug_name.upper()}!")
            time.sleep(1)
        st.session_state.conflict_queue.pop(0)
        st.rerun()

    st.markdown("---")


# --- 3. Active Database Table (cached so it doesn't query on every frame) ---
@st.cache_data(ttl=60)
def load_dosing_rules():
    """Queries the SQLite database for the full dosing rules table.
    Result is cached for 60 seconds to prevent redundant DB reads on every render.
    """
    conn = sqlite3.connect("pharmacy.db")
    try:
        df = pd.read_sql_query("SELECT * FROM advanced_dosing_rules", conn)
    finally:
        conn.close()
    return df


# Hide the main table while resolving conflicts to keep the UI clean
if len(st.session_state.conflict_queue) == 0:
    with st.container(border=True):
        st.markdown("#### 📁 Active Dosing Rules (SQLite)")
        try:
            df_rules = load_dosing_rules()
            if not df_rules.empty:
                st.dataframe(df_rules, use_container_width=True, hide_index=True)
            else:
                st.info(
                    "Database is currently empty. Add drugs above to populate data."
                )
        except Exception as e:
            st.error(f"Could not load database: {e}")

# --- 4. Quarantine Queue ---
if os.path.exists("failed_queue.txt"):
    with st.container(border=True):
        st.markdown("#### ⚠️ Quarantine Queue")
        with open("failed_queue.txt", "r") as f:
            st.text(f.read())
