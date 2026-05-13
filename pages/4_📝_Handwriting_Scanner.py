"""
2_📝_Handwriting_Scanner.py — TechCare Handwriting OCR
========================================================
A dedicated page for reading messy, handwritten doctor prescriptions
using EasyOCR's deep-learning-based character recognition.

Why EasyOCR instead of Tesseract for this page?
  • Tesseract is optimised for clean, printed/typed text.
  • EasyOCR uses a CRNN neural network that handles cursive handwriting,
    irregular spacing, and mixed fonts far more accurately.

Pipeline (this page only — no drug safety checks yet):
  Upload image → display preview → EasyOCR readtext → display raw text
"""

import numpy as np
import streamlit as st
from PIL import Image

import easyocr

from sidebar_menu import draw_sidebar

# --- SHARED SIDEBAR ---
draw_sidebar()

# ─── Page header ──────────────────────────────────────────────────────────────
st.markdown("### 📝 Handwriting Scanner")
st.caption(
    "Upload a photo of a handwritten prescription. "
    "EasyOCR's neural network will decode the text for you."
)


# ─── Model initialisation (cached — loads the neural net ONCE per session) ────
@st.cache_resource(show_spinner="🧠 Loading EasyOCR neural network (first run only)...")
def load_reader() -> easyocr.Reader:
    """
    Initialises the EasyOCR Reader for English text.

    Decorated with @st.cache_resource so Streamlit keeps this object alive
    in memory across all re-runs. Without this, the ~200 MB CRNN model would
    reload from disk every time the user clicks a button — adding 10–30 seconds
    of delay on every single interaction.

    Returns:
        easyocr.Reader: A ready-to-use reader instance.
    """
    return easyocr.Reader(["en"], gpu=False)


reader = load_reader()


# ─── Section 1: Image Upload ──────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("#### 📤 Upload Handwritten Prescription")
    uploaded_file = st.file_uploader(
        "Drop a photo of the handwritten prescription here",
        type=["png", "jpg", "jpeg"],
        label_visibility="collapsed",
    )

# ─── Section 2: Preview + Decode ─────────────────────────────────────────────
if uploaded_file is not None:

    # Open as PIL Image — this is what we'll convert for EasyOCR
    image = Image.open(uploaded_file).convert("RGB")

    with st.expander("👁️ Preview Uploaded Image", expanded=True):
        st.image(image, use_container_width=True)

    st.markdown("---")

    # ── Decode button ─────────────────────────────────────────────────────────
    if st.button(
        "🔍 Decode Handwriting",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("🔍 EasyOCR is reading the handwriting..."):
            # EasyOCR expects a NumPy array (H × W × 3 uint8), not a PIL Image.
            # np.array() converts in-place — no file I/O needed.
            image_np = np.array(image)

            # detail=0  →  returns only the text strings, not bounding boxes
            #              or confidence scores. Keeps the output simple.
            results: list[str] = reader.readtext(image_np, detail=0)

        if results:
            extracted_text = "\n".join(results)

            st.success(f"✅ Extracted {len(results)} line(s) of text.")

            with st.container(border=True):
                st.markdown("#### 📋 Extracted Handwritten Text")
                st.text_area(
                    label="Raw EasyOCR Output (read-only)",
                    value=extracted_text,
                    height=300,
                    disabled=True,
                    help=(
                        "This is the raw text decoded from the handwritten image. "
                        "Review it for accuracy before using it in the safety pipeline."
                    ),
                )

            # Hint for next steps
            st.info(
                "⚕️ **Next step:** Copy this text into the **Live Scanner** page "
                "to run it through the full drug interaction safety analysis.",
                icon="ℹ️",
            )

        else:
            st.warning(
                "⚠️ EasyOCR could not detect any readable text in this image. "
                "Try a clearer photo with better lighting and less shadow."
            )
