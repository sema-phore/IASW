# Intelligent Account Servicing Workflow (IASW)

IASW is a Human-in-the-Loop (HITL) AI system that automates bank account change requests — including name changes, address updates, and contact (phone/email) changes. A LangGraph AI pipeline extracts and verifies information from uploaded documents (or validates OTPs for contact changes), while a human checker retains final approval authority before any account update is committed to the core banking system.

---

## Supported Change Types

| Change Type | Verification Method | Document Required |
|-------------|--------------------|--------------------|
| Name Change | AI document extraction + fuzzy match + forgery check | Marriage certificate |
| Address Change | AI document extraction + field validation + forgery check | Utility bill, bank statement, Aadhaar, etc. |
| Contact Change (Phone/Email) | OTP verification sent to new contact value | None |

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd IASW
```

### 2. Install Python dependencies

```bash
uv add -r iasw/requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required keys:

```
OPENAI_API_KEY = "your_openai_key"
LANGCHAIN_API_KEY = "your_langsmith_key"
LANGCHAIN_TRACING_V2 = "true"
LANGCHAIN_PROJECT = "iasw"
```

### 4. Install Tesseract OCR

Tesseract is required for OCR on scanned documents (name and address changes only).

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

Open two terminals and run each command from the **project root** (`IASW/`).

**Terminal 1 — FastAPI backend:**
```bash
uvicorn iasw.backend.main:app --reload
```

**Terminal 2 — Streamlit frontend:**
```bash
cd iasw
streamlit run frontend/app.py
```

The frontend will be available at `http://localhost:8501`.  
The backend API docs are at `http://localhost:8000/docs`.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/otp/send` | Send (mock) OTP to a phone number or email address |
| `POST` | `/requests/name-change` | Submit a name change request with document upload |
| `POST` | `/requests/address-change` | Submit an address change request with document upload |
| `POST` | `/requests/contact-change` | Submit a phone or email change request (OTP-verified, no document) |
| `GET` | `/requests/pending` | List all requests awaiting human review |
| `GET` | `/requests/{id}` | Get full details of a specific request |
| `POST` | `/requests/{id}/decision` | Approve or reject a request (checker action) |
| `GET` | `/audit/{id}` | Get the full audit trail for a request |

---

## Demo — Golden Paths

### Name Change

1. Open the app and navigate to **Staff Intake**.
2. Select **Name Change** from the Change Type dropdown.
3. Enter:
   - **Customer ID:** `C001`
   - **Current Name:** `Priya Sharma`
   - **Requested Name:** `Priya Mehta`
4. Upload `iasw/samples/marriage_cert.png` as the supporting document.
5. Click **Submit**. Note the **Request ID** returned on screen.
6. Switch to **Checker Review** and select the pending request.
7. Review the AI extraction, confidence scores, and forgery check.
8. Click **Approve** to finalise the name change.

### Address Change

1. Select **Address Change** from the Change Type dropdown.
2. Enter Customer ID `C001` and the new address fields.
3. Upload `iasw/samples/electricity_bill.png` as address proof.
4. Click **Submit**, then approve in Checker Review.

### Contact Change (Phone or Email)

1. Select **Contact Change (Phone/Email)** from the Change Type dropdown.
2. Enter Customer ID `C001`, select **PHONE** or **EMAIL**, and enter the new value.
3. Click **Send OTP**. The demo OTP is always `123456`.
4. Enter the OTP and click **Verify & Submit**.
5. Switch to **Checker Review** — the request shows OTP Verified status and 100% confidence.
6. Click **Approve** to finalise the contact change.

**OTP failure path:** Enter any wrong OTP (e.g. `000000`) — the request will be submitted as `AI_FLAGGED` with 0% confidence and a `REJECT` recommendation. The checker can still override and approve (HITL), or reject.

---

## AI Pipeline Architecture

```
Name / Address Change:
  Upload → OCR → Field Extraction (GPT-4o) → Cross-Reference → Forgery Check → Score → HITL Decision → RPS Write

Contact Change (Phone / Email):
  OTP Send → OTP Verify → Score (deterministic) → HITL Decision → RPS Write
```

Contact changes intentionally skip OCR, document extraction, and forgery checks. OTP verification is the correct verification method for contact ownership — AI document analysis adds no value here.

---

## Key Design Decisions

- **Human-in-the-Loop (HITL):** The AI pipeline extracts and validates data but never writes to the account directly. Every request requires explicit checker approval via `/requests/{id}/decision`. The RPS write functions enforce this with a hard guard that raises an error if the request is not in `APPROVED` status.

- **OTP-only contact pipeline:** Phone and email changes use a 3-node LangGraph pipeline (OTP verify → score → status) with no LLM calls. This is intentional: OTP is a binary pass/fail — AI scoring adds no value and would only introduce latency and cost.

- **Deterministic demo OTP:** The mock OTP service always uses `123456` for demo reproducibility. This is not a shortcut — it is an explicit design choice to make the demo reliable and predictable.

- **ChromaDB for semantic policy retrieval:** Bank compliance policies (including contact-change OTP policies) are stored as vector embeddings in ChromaDB. The agent retrieves the most relevant policy chunks at runtime using semantic search, keeping policy logic decoupled from agent code.

- **LangSmith tracing:** All agent runs are traced end-to-end in LangSmith, capturing inputs, LLM outputs, and latency at each step. The OTP pipeline is also logged to the `AuditLog` table (steps: `OTP_VERIFIED` / `OTP_FAILED`, `CONTACT_SCORING_COMPLETE`) so checkers can see the full verification history even though no LLM was involved.

- **Null-safe `filenet_ref`:** Contact changes have no document upload, so `filenet_ref` is stored as `None`. All UI code that renders this field uses a `'N/A'` fallback to handle this safely.
