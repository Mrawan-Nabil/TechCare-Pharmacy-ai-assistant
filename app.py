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