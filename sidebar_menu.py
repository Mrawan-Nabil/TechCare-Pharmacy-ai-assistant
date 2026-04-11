import streamlit as st
import os
import sqlite3
import requests

# --- TELEMETRY FUNCTIONS (Cached for 60 seconds for speed) ---
@st.cache_data(ttl=60, show_spinner=False)
def ping_biomistral():
    """Pings the local Ollama API to ensure it is running and has biomistral."""
    try:
        # A 1-second timeout ensures the app doesn't freeze if Ollama is turned off!
        response = requests.get("http://localhost:11434/api/tags", timeout=1)
        if response.status_code == 200:
            models = response.json().get("models", [])
            # Check if biomistral is actively installed in the engine
            for m in models:
                if "biomistral" in m.get("name", "").lower():
                    return True
        return False
    except Exception:
        # If the connection is refused, Ollama is completely off
        return False

@st.cache_data(ttl=60, show_spinner=False)
def ping_database():
    """Pings the SQLite database to ensure it isn't locked or missing."""
    try:
        conn = sqlite3.connect('pharmacy.db')
        conn.cursor().execute("SELECT 1") # A lightweight test query
        conn.close()
        return True
    except Exception:
        return False


# --- MAIN SIDEBAR BUILDER ---
def draw_sidebar():
    logo3_path = "assets/logo3_v2.jpg" if os.path.exists("assets/logo3_v2.jpg") else "logo3_v2.jpg"

    # 1. HIDE THE DEFAULT MENU & FIX TOP SPACING
    st.markdown(
        """
        <style>
            [data-testid="stSidebarNav"] { display: none !important; }
            [data-testid="stSidebar"] > div:first-child { padding-top: 2rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        # 2. THE BIG LOGO
        if os.path.exists(logo3_path):
            st.image(logo3_path, use_container_width=True)
        else:
            st.title("TechCare")

        # 3. THE CAPTION
        st.caption("Autonomous AI Safety Controller")
        st.divider()

        # 4. THE CUSTOM NAVIGATION
        st.page_link("app.py", label="Home", icon="🏠")
        st.page_link("pages/1_🔬_Live_Scanner.py", label="Live Scanner", icon="🔬")
        st.page_link("pages/2_💬_Clinical_Chatbot.py", label="Clinical Chatbot", icon="💬")
        st.page_link("pages/3_📊_Admin_Dashboard.py", label="Admin Dashboard", icon="📊")

        # 5. THE LIVE STATUS BOXES
        st.divider()
        
        # Run the live checks
        is_ai_up = ping_biomistral()
        is_db_up = ping_database()
        
        if is_ai_up:
            st.success("● BioMistral Online")
        else:
            st.error("● BioMistral Offline")
            
        if is_db_up:
            st.success("● Database Connected")
        else:
            st.error("● Database Offline")