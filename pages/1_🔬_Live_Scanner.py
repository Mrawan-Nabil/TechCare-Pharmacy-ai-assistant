import streamlit as st
import pandas as pd

import ocr_reader
import extractor
import llm_generator
from live_checkout import check_local_databases
from sidebar_menu import draw_sidebar

# --- SHARED SIDEBAR ---
draw_sidebar()

# ==========================================
# PAGE: LIVE SCANNER (CHECKOUT COUNTER)
# ==========================================
st.markdown("### 🔬 Live Scanner — Checkout Counter")
st.caption("Upload or capture a prescription to run full OCR → AI extraction → pharmacological safety analysis.")

# 1. Input Section
with st.container(border=True):
    st.markdown("#### Prescription Input")

    input_method = st.radio(
        "Select Input Method:",
        ["File Upload", "Live Camera"],
        horizontal=True,
        label_visibility="collapsed",
    )

    uploaded_file = None
    if input_method == "File Upload":
        uploaded_file = st.file_uploader(
            "Drop a scanned prescription here", type=["png", "jpg", "jpeg"]
        )
    else:
        uploaded_file = st.camera_input("Take a picture of the prescription")

# 2. Processing & Results Section
if uploaded_file is not None:

    # Image Preview
    with st.expander("👁️ Preview Scanned Prescription", expanded=True):
        st.image(uploaded_file, use_container_width=True)

    temp_path = "temp_prescription.png"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.markdown("---")

    # Unpressable Button Trick:
    # Create an empty placeholder; once clicked, instantly swap to a disabled button
    # so the user cannot trigger a second run while processing is underway.
    btn_placeholder = st.empty()

    if btn_placeholder.button(
        "🚀 Run Clinical Safety Check", type="primary", use_container_width=True
    ):
        # Instantly swap the button to a disabled state
        btn_placeholder.button(
            "⏳ Processing Prescription... Please Wait.",
            disabled=True,
            use_container_width=True,
        )

        with st.status(
            "Running Autonomous Processing Pipeline...", expanded=True
        ) as status:

            # STEP 1: OCR
            st.write("1️⃣ Extracting raw text via Tesseract OCR...")
            raw_ocr_text = ocr_reader.extract_and_sanitize_text(temp_path)

            if not raw_ocr_text:
                status.update(label="OCR Failed.", state="error", expanded=True)
                st.error(
                    "Could not read text from the image. Please try a clearer picture."
                )
            else:
                # STEP 2: BioMistral Extraction
                st.write("2️⃣ BioMistral parsing demographics and medications...")
                structured_data = extractor.parse_prescription_text(raw_ocr_text)

                p_age = structured_data.get("patient_age", 30)
                p_gender = structured_data.get("patient_gender", "ALL")
                p_history = structured_data.get("medical_history", "None")

                # STEP 3: Database Safety Checks
                st.write("3️⃣ Querying SQLite and ChromaDB for safety limits...")
                all_drug_reports = []

                for med in structured_data.get("medications", []):
                    test_drug = med.get("drug_name")
                    test_dose = med.get("dose_mg")
                    test_concentration = med.get("concentration", "UNKNOWN")

                    report_dict = check_local_databases(
                        test_drug,
                        test_dose,
                        test_concentration,
                        p_history,
                        p_age,
                        p_gender,
                    )
                    all_drug_reports.append(report_dict)

                # STEP 4: Final AI Summary
                st.write("4️⃣ Synthesizing final Pharmacist Alerts...")
                final_summary = llm_generator.generate_pharmacist_warning(
                    all_drug_reports
                )

                status.update(
                    label="Analysis Complete!", state="complete", expanded=False
                )

        # Restore the original button after processing is done
        btn_placeholder.empty()

        # --- DISPLAY THE RESULTS ---
        st.markdown("### Clinical Analysis Results")

        with st.container(border=True):
            st.markdown("#### Patient Information")
            col1, col2, col3 = st.columns(3)
            col1.metric(label="AGE", value=f"{p_age} yrs")
            col2.metric(label="GENDER", value=p_gender.upper())
            col3.metric(
                label="HISTORY",
                value=str(p_history).title()[:20]
                + ("..." if len(str(p_history)) > 20 else ""),
            )

        with st.container(border=True):
            st.markdown("#### ⚠️ AI Safety Report")
            st.markdown(final_summary)

            st.markdown("#### Detected Medications")
            if structured_data.get("medications"):
                df = pd.DataFrame(structured_data["medications"])
                st.dataframe(df, use_container_width=True, hide_index=True)

        # Rescan / Retry Button
        st.markdown("<br>", unsafe_allow_html=True)

        # Clicking this resets the page state, clearing results and restoring
        # the original "Run" button — without losing the uploaded image.
        if st.button(
            "🔄 Retry Extraction (Rescan Image)",
            type="secondary",
            use_container_width=True,
        ):
            st.rerun()
