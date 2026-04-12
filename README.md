# Intelligent Account Servicing Workflow (IASW)

IASW is a Human-in-the-Loop (HITL) AI system that automates bank account name-change requests triggered by life events such as marriage or divorce. A LangChain AI agent extracts and verifies information from uploaded documents, while a human checker retains final approval authority before any account update is committed.

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd IASW
```

### 2. Install Python dependencies

```bash
pip install -r iasw/requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required keys:

```
ANTHROPIC_API_KEY=your_anthropic_key
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=iasw
```

### 4. Install Tesseract OCR

Tesseract is required for OCR on scanned documents.

**Linux:**
```bash
sudo apt install tesseract-ocr
```

**macOS:**
```bash
brew install tesseract
```

**Windows:** Download the installer from https://github.com/UB-Mannheim/tesseract/wiki and add it to your PATH.

---

## Running the Application

Open two terminals and run each command from the project root.

**Terminal 1 — FastAPI backend:**
```bash
cd iasw
uvicorn backend.main:app --reload
```

**Terminal 2 — Streamlit frontend:**
```bash
cd iasw
streamlit run frontend/app.py
```

The frontend will be available at `http://localhost:8501`.  
The backend API docs are at `http://localhost:8000/docs`.

---

## Demo — Golden Path

1. Open the app and navigate to **Staff Intake** in the sidebar.
2. Enter the following details:
   - **Customer ID:** `C001`
   - **Current Name:** `Priya Sharma`
   - **Requested Name:** `Priya Mehta`
3. Upload `iasw/samples/marriage_cert.png` as the supporting document.
4. Click **Submit**. Note the **Request ID** returned on screen.
5. Switch to **Checker Review** in the sidebar.
6. Select the pending request with the noted Request ID.
7. Review the AI agent's extraction summary.
8. Click **Approve** to finalize the name change.

---

## Key Design Decisions

- **Human-in-the-Loop (HITL):** The AI agent extracts and validates document data but never writes to the account directly. Every request requires explicit checker approval via a dedicated `/requests/{id}/decision` endpoint, ensuring a human remains accountable for all account mutations.

- **ChromaDB for semantic policy retrieval:** Bank compliance policies are stored as vector embeddings in ChromaDB. The agent retrieves the most relevant policy chunks at runtime using semantic search, avoiding brittle keyword matching and keeping policy logic decoupled from the agent code.

- **LangSmith tracing:** All agent runs are traced end-to-end in LangSmith, capturing inputs, tool calls, LLM outputs, and latency at each step. This makes it straightforward to audit decisions, debug failures, and evaluate agent quality over time without instrumenting the code manually.
