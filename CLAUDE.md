# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**IASW (Intelligent Account Servicing Workflow)** is a Human-in-the-Loop (HITL) AI system that automates bank account change requests — legal name changes (marriage certificate), address changes (address proof document), and contact changes (phone/email via OTP). A LangGraph AI pipeline extracts and verifies information from documents before a human checker approves changes to the core banking system (RPS).

## Commands

**Install dependencies (using UV):**
```bash
uv add -r iasw/requirements.txt
```

**Run the backend API:**
```bash
uvicorn iasw.backend.main:app --reload
# Swagger UI: http://localhost:8000/docs
```

**Run the frontend:**
```bash
cd iasw
streamlit run frontend/app.py
# UI: http://localhost:8501
```

Both services must run simultaneously. The frontend calls `BACKEND_URL` (default `http://localhost:8000`) from `.env`.

**No automated test suite** — validation is done manually via the Streamlit UI or the FastAPI Swagger UI (`/docs`). The pre-seeded demo customer is `C001 (Priya Sharma)`. The mock OTP code is always `123456`.

**Sample documents** for demos are in `iasw/samples/`:
- `marriage_cert.png` — name change
- `electricity_bill.png` — address change

## Architecture

### Layer Breakdown

| Layer | Tech | Entry Point |
|-------|------|-------------|
| Frontend | Streamlit multipage | `iasw/frontend/app.py` |
| Backend API | FastAPI (8 endpoints) | `iasw/backend/main.py` |
| AI Orchestration | LangGraph pipelines | `iasw/backend/agents/pipeline.py` |
| LLM | OpenAI GPT-4o | used in `doc_processor.py`, `forgery_check.py`, `scorer.py` |
| Vector DB | ChromaDB (13 KYC policy docs) | seeded in `iasw/backend/db/session.py` |
| Relational DB | SQLite | `data/iasw.db` via `iasw/backend/db/models.py` |
| Document OCR | Tesseract + GPT-4o vision fallback | `iasw/backend/services/ocr.py` |
| Tracing | LangSmith | configured via `.env` |

### Request Flow

1. **Maker (staff)** submits a change via `staff_intake.py` form (with uploaded document or OTP entry).
2. **FastAPI** receives the request, stores the document in the mock FileNet store, and invokes the appropriate LangGraph pipeline.
3. **LangGraph pipeline** runs:
   - *Document changes* (name/address) — 6 nodes: OCR → Field Extraction → Cross-Reference → Forgery Check → Scoring → Status Write
   - *Contact changes* (phone/email) — 3 nodes: OTP Verify → Scoring → Status Write
4. Each node logs to both **AuditLog** (SQLite) and **LangSmith**.
5. **Checker** reviews pending requests in `checker_ui.py`, sees AI confidence scores and summary, then approves or rejects.
6. **HITL gate** — The `/requests/{id}/decision` endpoint is the only path to RPS writes. All four RPS write functions (`iasw/backend/services/rps.py`) enforce `overall_status == "APPROVED"` and raise `ValueError` otherwise.

### Scoring is Deterministic, Not LLM-driven

The recommended action (APPROVE / REJECT / MANUAL\_REVIEW) is computed by a deterministic formula in `scorer.py`. GPT-4o only generates the human-readable summary. This is intentional to prevent hallucination-induced banking mutations.

### Database Schema (SQLite, 4 tables)

- **customers** — seed data for demo accounts
- **pending\_requests** — central tracking table; `overall_status` is the HITL gate field
- **audit\_logs** — per-step JSON payloads for every pipeline node
- **rps\_records** — mirrors the core banking system (write-protected by HITL guard)

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/otp/send` | Send mock OTP |
| POST | `/requests/name-change` | Submit name change + document |
| POST | `/requests/address-change` | Submit address change + document |
| POST | `/requests/contact-change` | Submit phone/email change (OTP) |
| GET | `/requests/pending` | List requests awaiting checker |
| GET | `/requests/{id}` | Get full request details |
| POST | `/requests/{id}/decision` | Checker approve/reject |
| GET | `/audit/{id}` | Retrieve full audit trail |

### Prompt Templates

LLM prompts are stored as `.txt` files in `iasw/backend/prompts/` and loaded at runtime — policy logic lives there, not in Python code. Changing LLM behavior means editing these files, not the agent modules.

### RAG Policy Store

13 KYC policy documents are hardcoded in `iasw/backend/db/session.py` and loaded into ChromaDB at startup. The forgery check node retrieves relevant policies at runtime. Adding or changing policies requires updating `session.py`.

## Environment Variables (`.env`)

```
OPENAI_API_KEY=
LANGSMITH_API_KEY=
LANGSMITH_ENDPOINT=
LANGSMITH_PROJECT=
BACKEND_URL=http://localhost:8000
DATABASE_URL=sqlite:///./iasw.db
FILENET_STORE_PATH=./data/filenet
CHROMA_PERSIST_PATH=./data/chroma
```

Both `data/iasw.db` and `data/chroma/` are auto-created on first startup.

## Key Design Constraints

- **FileNet and OTP are mocks** — no real integrations; `filenet.py` writes to local disk, OTP is always `123456`.
- **Contact changes skip RAG** — the 3-node OTP pipeline does not use ChromaDB (binary pass/fail needs no policy retrieval).
- **Frontend timeout is 120 s** — document pipelines (OCR + multiple GPT-4o calls) can be slow; avoid adding unnecessary LLM calls.
- **ChromaDB is seeded once** — if `data/chroma/` already exists, seeding is skipped; delete the directory to re-seed.


## Code Conventions

- **Rule: Never rewrite existing agents.** Add new `run_*()` functions alongside existing ones. Every agent file has a working `run()` — don't touch it.
- **HITL guard is mandatory** in every new `rps.write_*` function. Pattern: check `pending.overall_status == "APPROVED"` before any mutation.
- **No `st.form()` in Streamlit.** Use `st.button()` with `st.session_state` for multi-step flows.
- **All `db.commit()` calls** must be wrapped in `try/except` with `db.rollback()` on failure.
- **JSON from LLM responses** must be parsed with `try/except`, strip markdown fences (````json`), and return a safe fallback dict on failure.
- **Date parsing** uses `dateutil.parser` as primary, with plain string fallback in a `try/except`.
- **Prompt templates** live in `prompts/*.txt`, not inline in Python. New agent = new prompt file.


## Common Tasks

**Adding a new change type (e.g., DOB change):**
1. Add columns to `Customer` and `RPSRecord` in `models.py` (then delete `data/iasw.db` to re-create).
2. Create new prompt templates in `prompts/`.
3. Create new agent files (`dob_doc_processor.py`, `dob_cross_ref.py`, etc.).
4. Add a new `StateGraph` + `run_dob_pipeline()` in `pipeline.py`.
5. Add a new `write_dob_update()` in `rps.py` with HITL guard.
6. Add `POST /requests/dob-change` endpoint in `main.py`.
7. Extend the `submit_decision` dispatcher in `main.py`.
8. Add the form in `staff_intake.py` and metrics in `checker_ui.py`.
9. Add policy docs to `_POLICY_DOCS` in `session.py` (then delete `data/chroma/`).

**Resetting demo state:**
```bash
rm data/iasw.db data/chroma/ -rf
# Restart backend — both are auto-recreated with seed data.
```

## File Dependency Map

- Changing `models.py` → delete `data/iasw.db` → restart backend
- Changing `session.py` policy docs → delete `data/chroma/` → restart backend
- Changing `pipeline.py` → restart backend (graphs compile at import time)
- Changing `prompts/*.txt` → restart backend (loaded at import time)
- Changing `staff_intake.py` or `checker_ui.py` → Streamlit hot-reloads automatically