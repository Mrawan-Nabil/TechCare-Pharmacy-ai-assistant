import sqlite3
import chromadb
import streamlit as st
import ollama
from sidebar_menu import draw_sidebar

# ── Database initialisation (mirrors live_checkout.py) ───────────────────────
_CHROMA_PATH = "./chroma_data"
_CHROMA_COLLECTION = "drug_interactions"

try:
    _chroma_client = chromadb.PersistentClient(path=_CHROMA_PATH)
    _collection = _chroma_client.get_or_create_collection(name=_CHROMA_COLLECTION)
except Exception as _e:
    _collection = None
    # Non-fatal: chatbot degrades gracefully to LLM-only if ChromaDB is unavailable
    print(f"[Chatbot] ChromaDB init warning: {_e}")

# --- SHARED SIDEBAR ---
draw_sidebar()

# ==========================================
# PAGE: CLINICAL CHATBOT
# ==========================================
st.markdown("### Clinical Chatbot Assistant")
st.caption("Ask BioMistral questions about pharmacology or specific drug interactions.")

# --- AVATAR CONFIG ---
ASSISTANT_AVATAR = "assets/logo2.png"   # TechCare branded logo
USER_AVATAR = None                       # No avatar for the user side

# --- CSS: Hide the user avatar container as a hard fallback ---
st.markdown(
    """
    <style>
    /* Hide the avatar image/icon for user chat messages */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) img,
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="chatAvatarIcon-user"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Strict enterprise system prompt ─────────────────────────────────────────
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are TechCare, an enterprise-grade Clinical AI Assistant designed exclusively "
        "to support licensed pharmacists. Your primary function is to provide pharmacological "
        "data, analyze drug interactions, and assist with medication safety checks.\n\n"
        "CRITICAL RULES:\n"
        "1. You are advising a pharmacist, NOT a patient. Use professional, clinical terminology.\n"
        "2. NEVER provide definitive medical diagnoses.\n"
        "3. If asked about a severe drug interaction, always highlight the clinical risks and "
        "suggest the pharmacist consult official FDA documentation or the prescribing doctor.\n"
        "4. If a user asks non-medical questions (e.g., coding, creative writing, general trivia), "
        "politely decline and state that you are a dedicated clinical safety tool.\n"
        "5. Keep your answers concise, structured, and strictly evidence-based."
    ),
}

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
    role = message["role"]
    avatar = ASSISTANT_AVATAR if role == "assistant" else USER_AVATAR
    with st.chat_message(role, avatar=avatar):
        st.markdown(message["content"])

# Handle new user input
if prompt := st.chat_input("Ask about an alternative antibiotic for Atorvastatin..."):

    # ── Step 1: UI State — store and render the raw prompt as-is ─────────────
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    # ── Step 2: RAG Retrieval — query ChromaDB before calling the LLM ────────
    retrieved_context = ""
    if _collection is not None:
        try:
            rag_results = _collection.query(
                query_texts=[prompt],
                n_results=3,                    # top-3 most relevant literature chunks
                include=["documents"],
            )
            docs = rag_results.get("documents", [[]])[0]
            if docs:
                retrieved_context = "\n\n---\n\n".join(docs)
        except Exception as _rag_err:
            print(f"[Chatbot RAG] Retrieval error: {_rag_err}")
            # Graceful degradation: if retrieval fails, proceed with LLM-only answer

    # ── Step 3: Build the LLM payload (separate from UI session_state) ───────
    #
    # We deep-copy the history to build a temporary list so the UI-facing
    # session_state always contains only the user's clean, raw prompt.
    # The augmented context is injected only into the copy that goes to Ollama.
    #
    llm_messages = [SYSTEM_PROMPT] + [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]

    # Overwrite the last entry (which is the user's raw prompt) with the
    # context-augmented version that grounds the LLM in our local knowledge base.
    if retrieved_context:
        llm_messages[-1]["content"] = (
            "Using the following medical literature, answer the question. "
            "Always answer the question directly and briefly using the literature provided. "
            "Avoid unnecessary disclaimers or hedging language. "
            "If the answer is not in the literature, answer with the knowledge you have or state that you do not have the answer.\n\n"
            f"LITERATURE:\n{retrieved_context}\n\n"
            f"QUESTION: {prompt}"
        )

    # ── Step 4: Stream the RAG-augmented response ─────────────────────────────
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        # Show a subtle badge if the answer is grounded in local data
        if retrieved_context:
            st.caption("📚 Answering from local clinical knowledge base")

        try:
            stream = ollama.chat(
                model="biomistral",
                messages=llm_messages,          # ← augmented payload, not session_state
                stream=True,
                options={
                    "temperature": 0.2,
                    "num_predict": 800,
                },
            )

            full_response = st.write_stream(
                chunk["message"]["content"] for chunk in stream
            )

            # Persist the clean response to UI memory for the next turn
            st.session_state.messages.append(
                {"role": "assistant", "content": full_response}
            )

        except Exception as e:
            st.error(
                f"⚠️ Failed to connect to BioMistral. "
                f"Ensure Ollama is running and the model is loaded.\n\n`{e}`"
            )
