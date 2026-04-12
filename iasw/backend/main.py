import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

from fastapi import Depends, FastAPI, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from iasw.backend.agents import pipeline
from iasw.backend.db.models import AuditLog, PendingRequest
from iasw.backend.db.session import SessionLocal, get_chroma_collection, init_db
from iasw.backend.services import filenet, rps

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # IASW/
_LOCAL_FILENET_DIR = _PROJECT_ROOT / "data" / "filenet"

# ---------------------------------------------------------------------------
# Chroma singleton
# ---------------------------------------------------------------------------
_chroma_collection = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _chroma_collection
    init_db()
    _chroma_collection = get_chroma_collection()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="IASW API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_chroma():
    return _chroma_collection


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class DecisionRequest(BaseModel):
    decision: str  # "APPROVE" | "REJECT"
    checker_id: str
    comment: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _log_audit(db: Session, request_id: str, agent_step: str, payload: dict) -> None:
    db.add(
        AuditLog(
            request_id=request_id,
            agent_step=agent_step,
            payload=json.dumps(payload),
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/requests/name-change")
async def submit_name_change(
    customer_id: str = Form(...),
    old_name: str = Form(...),
    new_name: str = Form(...),
    document: UploadFile = Form(...),
    db: Session = Depends(get_db),
    chroma=Depends(get_chroma),
):
    file_bytes = await document.read()

    # 1. Save to mock FileNet store
    filenet_ref = filenet.save_document(file_bytes, document.filename)

    # 2. Save locally so OCR can read the file
    _LOCAL_FILENET_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _LOCAL_FILENET_DIR / f"{filenet_ref}_{document.filename}"
    local_path.write_bytes(file_bytes)

    # 3. Run AI pipeline
    request_id = str(uuid.uuid4())
    result = pipeline.run_pipeline(
        file_path=str(local_path),
        old_name=old_name,
        new_name=new_name,
        db_session=db,
        chroma_collection=chroma,
        request_id=request_id,
    )

    scoring = result["scoring"]

    # 4. Persist PendingRequest
    pending = PendingRequest(
        request_id=request_id,
        customer_id=customer_id,
        change_type="NAME_CHANGE",
        old_value=old_name,
        new_value=new_name,
        extracted_json=json.dumps(result["extracted"]),
        confidence_json=json.dumps(scoring),
        overall_status=result["status"],
        filenet_ref=filenet_ref,
        ai_summary=scoring.get("summary"),
        recommended_action=scoring.get("recommended_action"),
    )
    db.add(pending)
    db.commit()

    return {
        "request_id": request_id,
        "status": result["status"],
        "overall_confidence": scoring.get("overall_confidence"),
        "recommended_action": scoring.get("recommended_action"),
        "summary": scoring.get("summary"),
    }


@app.get("/requests/pending")
def list_pending_requests(db: Session = Depends(get_db)):
    rows = (
        db.query(PendingRequest)
        .filter(
            PendingRequest.overall_status.in_(
                ["AI_VERIFIED_PENDING_HUMAN", "AI_FLAGGED"]
            )
        )
        .all()
    )
    return [
        {
            "request_id": r.request_id,
            "customer_id": r.customer_id,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "overall_status": r.overall_status,
            "recommended_action": r.recommended_action,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@app.get("/requests/{request_id}")
def get_request(request_id: str, db: Session = Depends(get_db)):
    row = db.query(PendingRequest).filter_by(request_id=request_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")

    return {
        "request_id": row.request_id,
        "customer_id": row.customer_id,
        "change_type": row.change_type,
        "old_value": row.old_value,
        "new_value": row.new_value,
        "overall_status": row.overall_status,
        "recommended_action": row.recommended_action,
        "ai_summary": row.ai_summary,
        "filenet_ref": row.filenet_ref,
        "checker_id": row.checker_id,
        "checker_decision": row.checker_decision,
        "checker_comment": row.checker_comment,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "extracted_json": json.loads(row.extracted_json) if row.extracted_json else None,
        "confidence_json": json.loads(row.confidence_json) if row.confidence_json else None,
    }


@app.post("/requests/{request_id}/decision")
def submit_decision(
    request_id: str,
    body: DecisionRequest,
    db: Session = Depends(get_db),
):
    if body.decision not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    row = db.query(PendingRequest).filter_by(request_id=request_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")

    if row.overall_status not in ("AI_VERIFIED_PENDING_HUMAN", "AI_FLAGGED"):
        raise HTTPException(
            status_code=400,
            detail=f"Request is in status '{row.overall_status}' and cannot be actioned",
        )

    _log_audit(
        db,
        request_id,
        "CHECKER_DECISION",
        {
            "decision": body.decision,
            "checker_id": body.checker_id,
            "comment": body.comment,
        },
    )

    if body.decision == "APPROVE":
        row.overall_status = "APPROVED"
        row.checker_id = body.checker_id
        row.checker_decision = "APPROVED"
        row.checker_comment = body.comment
        row.updated_at = datetime.utcnow()
        db.commit()

        rps.write_name_update(
            customer_id=row.customer_id,
            new_name=row.new_value,
            request_id=request_id,
            db_session=db,
        )

        return {"success": True, "message": f"RPS updated. Name changed to {row.new_value}."}

    # REJECT
    row.overall_status = "REJECTED"
    row.checker_id = body.checker_id
    row.checker_decision = "REJECTED"
    row.checker_comment = body.comment
    row.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": "Request rejected."}


@app.get("/audit/{request_id}")
def get_audit_log(request_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(AuditLog)
        .filter_by(request_id=request_id)
        .order_by(AuditLog.timestamp)
        .all()
    )
    return [
        {
            "id": r.id,
            "request_id": r.request_id,
            "agent_step": r.agent_step,
            "payload": json.loads(r.payload) if r.payload else None,
            "timestamp": r.timestamp,
        }
        for r in rows
    ]
