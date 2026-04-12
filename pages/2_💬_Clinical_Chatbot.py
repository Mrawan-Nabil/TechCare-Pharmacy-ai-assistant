import streamlit as st
import ollama
from sidebar_menu import draw_sidebar

# --- SHARED SIDEBAR ---
draw_sidebar()

# ==========================================
# PAGE: CLINICAL CHATBOT
# ==========================================
st.markdown("### 💬 Clinical Chatbot Assistant")
st.caption("Ask BioMistral questions about pharmacology or specific drug interactions.")

# Initialize chat history in session state on first load
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "I am TechCare's Clinical Assistant. How can I help?",
        }
    ]

# Render full chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle new user input
if prompt := st.chat_input("Ask about an alternative antibiotic for Atorvastatin..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = ollama.chat(
                    model="biomistral",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful clinical pharmacy assistant.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
                msg = response["message"]["content"]
                st.markdown(msg)
                st.session_state.messages.append(
                    {"role": "assistant", "content": msg}
                )
            except Exception as e:
                st.error(f"Failed to connect to BioMistral: {e}")
