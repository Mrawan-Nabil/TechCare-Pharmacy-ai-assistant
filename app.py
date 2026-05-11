import streamlit as st
from sidebar_menu import draw_sidebar

# --- PAGE CONFIG (must be the first Streamlit call in the entire app) ---
st.set_page_config(
    page_title="TechCare",
    layout="wide",
    page_icon="assets/logo2.png",
)

# --- SHARED SIDEBAR ---
draw_sidebar()

# --- SIDEBAR TOGGLE: Replace tiny arrow with a visible hamburger icon ---
st.markdown(
    """
    <style>
    /* ── Sidebar collapse/expand control button ── */
    [data-testid="collapsedControl"] {
        /* Make the button larger and pill-shaped */
        width: 48px !important;
        height: 48px !important;
        border-radius: 12px !important;
        background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%) !important;
        border: 2px solid rgba(96, 165, 250, 0.6) !important;
        box-shadow: 0 4px 18px rgba(37, 99, 235, 0.45) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: box-shadow 0.25s ease, transform 0.2s ease !important;
        cursor: pointer !important;
        position: relative !important;
    }

    [data-testid="collapsedControl"]:hover {
        box-shadow: 0 6px 28px rgba(37, 99, 235, 0.70) !important;
        transform: scale(1.08) !important;
    }

    /* Hide the default SVG arrow Streamlit renders */
    [data-testid="collapsedControl"] svg {
        display: none !important;
    }

    /* Inject a ☰ hamburger character as the visible icon */
    [data-testid="collapsedControl"]::after {
        content: "☰" !important;
        font-size: 22px !important;
        color: #e0f2fe !important;
        line-height: 1 !important;
        font-weight: 700 !important;
        letter-spacing: -1px !important;
        pointer-events: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- HOME PAGE CONTENT ---
st.image("assets/logo2.png", width=170)
st.title(" Welcome to TechCare")
st.markdown(
    """
    **TechCare** is an Autonomous AI-Powered Clinical Safety Controller built for modern pharmacy workflows.

    Use the **sidebar** on the left to navigate between the available system modules:

    | Module | Description |
    |---|---|
    | 🔬 **Live Scanner** | Upload a handwritten or printed prescription and run full OCR → AI extraction → pharmacological safety analysis. |
    | 💬 **Clinical Chatbot** | Ask BioMistral clinical pharmacy questions or query drug interaction information in plain language. |
    | 📊 **Admin Dashboard** | Manage your clinical knowledge base, teach the AI new medications, and review the dosing rules database. |
    """
)

st.info("👈 Select a module from the sidebar to get started.", icon="ℹ️")