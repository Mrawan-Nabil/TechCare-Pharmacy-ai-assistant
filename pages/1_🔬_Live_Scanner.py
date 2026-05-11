import streamlit as st
import pandas as pd

import ocr_reader
import extractor
import llm_generator
from live_checkout import run_full_pipeline
from sidebar_menu import draw_sidebar

# --- SHARED SIDEBAR ---
draw_sidebar()

# ==========================================
# PAGE: LIVE SCANNER (CHECKOUT COUNTER)
# ==========================================
st.markdown("### Live Scanner — Checkout Counter")
st.caption("Upload or capture a prescription to run full OCR → AI extraction → pharmacological safety analysis.")

# ── Session-state initialisation (isolated per scan) ─────────────────────────
# Every variable that carries results between Streamlit re-runs is explicitly
# declared here so there is a guaranteed empty default. This prevents context
# bleed from a previous scan appearing in a new one.
_STATE_DEFAULTS = {
    "scan_results":          None,   # dict returned by run_full_pipeline
    "final_summary":         None,   # string report from llm_generator
    "python_dosing_alerts":  [],     # list[str] — dosing alerts
    "context_payload":       "",     # str — RAG context
    "raw_ocr_text":          None,   # str — raw OCR output
    "structured_data":       None,   # dict — BioMistral extraction
    "scan_complete":         False,  # flag: True only after a full successful run
}
for _k, _v in _STATE_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _clear_scan_state():
    """Wipes every scan-result key back to its empty default. Call before a new scan."""
    for k, v in _STATE_DEFAULTS.items():
        st.session_state[k] = v


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

    # ── New Scan / Clear button ───────────────────────────────────────────────
    # Shown whenever a previous result is in state, so the pharmacist can
    # explicitly wipe the previous patient's data before scanning a new one.
    if st.session_state.scan_complete:
        if st.button(
            "🧹 Clear Previous Results & Start New Scan",
            type="secondary",
            use_container_width=True,
        ):
            _clear_scan_state()
            st.rerun()

    # ── Run button (disabled while processing) ────────────────────────────────
    btn_placeholder = st.empty()

    if btn_placeholder.button(
        "🚀 Run Clinical Safety Check", type="primary", use_container_width=True,
        disabled=st.session_state.scan_complete,   # locked once a result exists
    ):
        # Immediately wipe any previous scan state before building fresh results.
        # This is the primary defence against context bleed.
        _clear_scan_state()

        # Swap button to a disabled/processing state
        btn_placeholder.button(
            "⏳ Processing Prescription... Please Wait.",
            disabled=True,
            use_container_width=True,
        )

        with st.status(
            "Running Autonomous Processing Pipeline...", expanded=True
        ) as status:

            # ── STEP 1: OCR ────────────────────────────────────────────────────
            st.write("1️⃣ Extracting raw text via Tesseract OCR...")
            # Build a completely fresh local — never read from session_state here
            raw_ocr_text = ocr_reader.extract_text(temp_path)
            st.session_state.raw_ocr_text = raw_ocr_text  # persist for display only

            if not raw_ocr_text:
                status.update(label="OCR Failed.", state="error", expanded=True)
                st.error(
                    "Could not read text from the image. Please try a clearer picture."
                )

            else:
                # ── STEP 2: BioMistral Extraction ─────────────────────────────
                st.write("2️⃣ BioMistral parsing demographics and medications...")
                # Fresh variable — not loaded from session_state
                structured_data = extractor.parse_prescription_text(raw_ocr_text)
                st.session_state.structured_data = structured_data

                if not structured_data:
                    status.update(label="AI Extraction Failed.", state="error", expanded=True)
                    st.error(
                        "⚠️ BioMistral could not extract structured data from the prescription text. "
                        "Please ensure **Ollama is running** and the **biomistral** model is loaded, "
                        "then try again."
                    )

                else:
                    # ── STEP 3: Hybrid Rules Engine pipeline ──────────────────
                    # run_full_pipeline() is a pure function — it builds all its
                    # variables from scratch on every call. No global state.
                    st.write("3️⃣ Running clinical data aggregation pipeline...")
                    extracted_json, python_dosing_alerts, context_payload = run_full_pipeline(
                        structured_data
                    )
                    # Write results to session state
                    st.session_state.scan_results         = extracted_json
                    st.session_state.python_dosing_alerts = python_dosing_alerts
                    st.session_state.context_payload      = context_payload

                    # ── STEP 4: LLM Audit ─────────────────────────────────────
                    # generate_pharmacist_warning() constructs its messages list
                    # from scratch — it does not maintain chat history.
                    st.write("🧐 Senior Clinical Auditor synthesising safety report...")
                    final_summary = llm_generator.generate_pharmacist_warning(
                        extracted_json,
                        python_dosing_alerts,
                        context_payload,
                    )
                    st.session_state.final_summary = final_summary
                    st.session_state.scan_complete = True

                    status.update(
                        label="Analysis Complete!", state="complete", expanded=False
                    )

        # Restore run button after processing
        btn_placeholder.empty()

    # ── Display Results (read from session_state, not local vars) ────────────
    # Reading from session_state means results survive Streamlit re-runs caused
    # by widget interactions (e.g., expanding the OCR expander) without
    # re-triggering the expensive pipeline.
    if st.session_state.scan_complete and st.session_state.structured_data:

        structured_data = st.session_state.structured_data
        final_summary   = st.session_state.final_summary
        p_age           = structured_data.get("patient_age", 30)
        p_gender        = structured_data.get("patient_gender", "ALL")
        p_history       = structured_data.get("medical_history", "None")

        st.markdown("### Clinical Analysis Results")

        with st.container(border=True):
            st.markdown("#### Patient Information")
            col1, col2, col3 = st.columns(3)
            col1.metric(label="AGE",    value=f"{p_age} yrs")
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
        if st.button(
            "🔄 Retry Extraction (Rescan Same Image)",
            type="secondary",
            use_container_width=True,
        ):
            _clear_scan_state()   # wipe state before retry
            st.rerun()

    # ── Human-in-the-Loop: Raw OCR Verification ──────────────────────────────
    if st.session_state.raw_ocr_text:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🔍 Double-Check Raw OCR Extraction", expanded=False):
            st.warning(
                "⚕️ **Clinical Safety Check:** If the text below looks like random symbols "
                "or is missing key drug names, please adjust the lighting and rescan the image.",
                icon="⚠️",
            )
            st.text_area(
                label="Raw Tesseract Output (read-only)",
                value=st.session_state.raw_ocr_text,
                height=250,
                disabled=True,
                help="This is the unprocessed text extracted directly from your prescription image "
                     "before any AI parsing. Use it to verify OCR quality.",
            )
