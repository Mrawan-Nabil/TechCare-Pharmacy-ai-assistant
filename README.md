# TechCare: Autonomous AI Safety Controller

TechCare is an enterprise-grade, AI-powered pharmacy safety and data governance platform. It is designed to act as a clinical safety net, utilizing OCR and advanced Large Language Models (LLMs) to digitize prescriptions, extract clinical data, and run real-time pharmacological safety checks against local, secure databases.

### 🌟 Core Features
* **Live Scanner (OCR + AI):** Extracts raw text from prescription images using Tesseract, then parses the data into structured JSON (Patient Demographics, Medications, Dosages) using BioMistral.
* **Pharmacological Safety Checks:** Automatically cross-references extracted medications against a local SQLite database and ChromaDB vector store to flag contraindications and dosing errors.
* **Clinical Chatbot:** An offline, secure assistant powered by BioMistral to help pharmacists query drug interactions and alternative treatments.
* **Admin Data Governance:** A batch-ingestion pipeline (CSV/Excel) and manual API fetcher that pulls FDA data to teach the system new drugs. Features a GitHub-style "Merge Conflict" UI requiring pharmacist approval before overwriting existing clinical rules.

---

## 🛠️ Tech Stack
* **Frontend:** [Streamlit](https://streamlit.io/) (Multi-Page Application Architecture)
* **AI/LLM Engine:** [Ollama](https://ollama.com/) running `biomistral`
* **Computer Vision:** [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
* **Databases:** SQLite (Structured Rules), ChromaDB (Vector Embeddings)
* **Data Processing:** Pandas, Openpyxl

---

## ⚠️ System Requirements (Prerequisites)

Because TechCare processes sensitive clinical data offline, it relies on local system engines. **You must install these on your machine before running the Python app.**

### 1. Tesseract OCR
TechCare uses Tesseract to read prescription images.
* **Windows:** Download the installer from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki). 
  * *Crucial:* Ensure Tesseract is added to your System PATH, or update the `tesseract_cmd` path in `ocr_reader.py`.
* **Mac (Homebrew):** `brew install tesseract`
* **Linux (Ubuntu):** `sudo apt-get install tesseract-ocr`

### 2. Ollama & BioMistral
TechCare uses Ollama to run the medical AI locally without sending patient data to the cloud.
* Download and install **Ollama** from [ollama.com](https://ollama.com/).
* Open your terminal and pull the BioMistral model by running:
  
  ```bash
  ollama run biomistral
  ```
  *(Note: Keep Ollama running in the background while using the app).*

---

## 🚀 Installation & Setup

**1. Clone the repository**
```bash
git clone [https://github.com/YOUR-USERNAME/techcare.git](https://github.com/YOUR-USERNAME/techcare.git)
cd techcare
```

**2. Create and activate a virtual environment (Recommended)**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

**3. Install Python Dependencies**
```bash
pip install -r requirements.txt
```

---

## 💻 Running the Application

Once your dependencies are installed and Ollama is running in the background, launch the application using Streamlit:

```bash
streamlit run app.py
```
The app will automatically open in your default web browser at `http://localhost:8501`.

---

## 📁 Project Structure

```text
techcare/
│
├── app.py                         # Home Page & Global Config
├── sidebar_menu.py                # Shared UI Component (Navigation & Telemetry)
├── requirements.txt               # Python Dependencies
├── pharmacy.db                    # SQLite Database (Auto-generated if missing)
│
├── pages/                         # Streamlit MPA Pages
│   ├── 1_🔬_Live_Scanner.py       
│   ├── 2_💬_Clinical_Chatbot.py   
│   └── 3_📊_Admin_Dashboard.py    
│
├── assets/                        # Brand Assets (Logos, Icons)
│   ├── logo1_v2.jpg               # Stacked Main Logo
│   ├── logo2_v2.jpg               # App Icon
│   └── logo3_v2.jpg               # Sidebar Logo
│
└── backend_modules/               # (Conceptual - Your modular python scripts)
    ├── ocr_reader.py              # Tesseract integration
    ├── extractor.py               # JSON structuring via BioMistral
    ├── auto_learner.py            # FDA API fetching & Conflict logic
    ├── llm_generator.py           # Final pharmacist warning synthesis
    └── live_checkout.py           # Database querying logic
```
---
*Developed for modern pharmacy data governance.*
