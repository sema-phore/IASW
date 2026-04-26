import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from iasw.backend.agents import pipeline
from iasw.backend.db.models import AuditLog, Customer, PendingRequest
from iasw.backend.db.session import SessionLocal, get_chroma_collection, init_db
from iasw.backend.services import filenet, rps, otp

load_dotenv()

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


class OTPSendRequest(BaseModel):
    contact_value: str  # phone number or email address
    contact_type: str   # "PHONE" or "EMAIL"


class ContactChangeRequest(BaseModel):
    customer_id: str
    contact_type: str   # "PHONE" or "EMAIL"
    new_value: str      # new phone number or email address
    otp_code: str       # user-entered OTP


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
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


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
        file_path=local_path,
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
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "request_id": request_id,
        "status": result["status"],
        "overall_confidence": scoring.get("overall_confidence"),
        "recommended_action": scoring.get("recommended_action"),
        "summary": scoring.get("summary"),
    }


@app.post("/requests/address-change")
async def submit_address_change(
    customer_id: str = Form(...),
    new_address: str = Form(...),
    new_city: str = Form(...),
    new_state: str = Form(...),
    new_pincode: str = Form(...),
    document: UploadFile = Form(...),
    db: Session = Depends(get_db),
    chroma=Depends(get_chroma),
):
    # 1. Look up customer to get current (old) address and name
    customer = db.query(Customer).filter_by(customer_id=customer_id).first()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    old_address_dict = {
        "address": customer.address or "",
        "city": customer.city or "",
        "state": customer.state or "",
        "pincode": customer.pincode or "",
    }
    new_address_dict = {
        "address": new_address,
        "city": new_city,
        "state": new_state,
        "pincode": new_pincode,
    }

    # 2. Save to mock FileNet store
    file_bytes = await document.read()
    filenet_ref = filenet.save_document(file_bytes, document.filename)

    # 3. Save locally so OCR can read the file
    _LOCAL_FILENET_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _LOCAL_FILENET_DIR / f"{filenet_ref}_{document.filename}"
    local_path.write_bytes(file_bytes)

    # 4. Run AI address pipeline
    request_id = str(uuid.uuid4())
    result = pipeline.run_address_pipeline(
        file_path=local_path,
        customer_name=customer.current_name,
        old_address=old_address_dict,
        new_address=new_address_dict,
        db_session=db,
        chroma_collection=chroma,
        request_id=request_id,
    )

    scoring = result["scoring"]

    # 5. Persist PendingRequest — old_value and new_value stored as JSON strings
    pending = PendingRequest(
        request_id=request_id,
        customer_id=customer_id,
        change_type="ADDRESS_CHANGE",
        old_value=json.dumps(old_address_dict),
        new_value=json.dumps(new_address_dict),
        extracted_json=json.dumps(result["extracted"]),
        confidence_json=json.dumps(scoring),
        overall_status=result["status"],
        filenet_ref=filenet_ref,
        ai_summary=scoring.get("summary"),
        recommended_action=scoring.get("recommended_action"),
    )
    db.add(pending)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "request_id": request_id,
        "status": result["status"],
        "overall_confidence": scoring.get("overall_confidence"),
        "recommended_action": scoring.get("recommended_action"),
        "summary": scoring.get("summary"),
    }


@app.post("/otp/send")
def send_otp_endpoint(body: OTPSendRequest):
    """Send a mock OTP to the given contact value.

    No DB interaction needed — the OTP store is held in-process by otp.py.
    """
    result = otp.send_otp(body.contact_value, body.contact_type)
    return result


@app.post("/requests/contact-change")
def submit_contact_change(
    body: ContactChangeRequest,
    db: Session = Depends(get_db),
    chroma=Depends(get_chroma),
):
    """Submit a phone or email change request.

    This endpoint intentionally skips OCR and document upload.
    Contact changes are verified via OTP — this is correct design, not a shortcut.
    """
    # 1. Look up customer — 404 if not found
    customer = db.query(Customer).filter_by(customer_id=body.customer_id).first()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    # 2. Determine current value from the customer record
    old_value = customer.phone if body.contact_type == "PHONE" else customer.email

    # 3. No FileNet save — contact changes have no document upload.
    #    filenet_ref is intentionally None (Per Rule 12).
    filenet_ref = None

    # 4. Run contact pipeline (OTP-only, no OCR or LLM extraction)
    request_id = str(uuid.uuid4())
    result = pipeline.run_contact_pipeline(
        contact_type=body.contact_type,
        customer_name=customer.current_name,
        old_value=old_value or "",
        new_value=body.new_value,
        otp_code=body.otp_code,
        db_session=db,
        chroma_collection=chroma,
        request_id=request_id,
    )

    scoring = result["scoring"]

    # 5. Persist PendingRequest — old/new stored as JSON for consistent parsing
    pending = PendingRequest(
        request_id=request_id,
        customer_id=body.customer_id,
        change_type="CONTACT_CHANGE",
        old_value=json.dumps({"contact_type": body.contact_type, "value": old_value or ""}),
        new_value=json.dumps({"contact_type": body.contact_type, "value": body.new_value}),
        extracted_json=json.dumps(result["extracted"]),
        confidence_json=json.dumps(scoring),
        overall_status=result["status"],
        filenet_ref=filenet_ref,  # None — no document for contact changes
        ai_summary=scoring.get("ai_summary"),
        recommended_action=scoring.get("recommended_action"),
    )
    db.add(pending)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "request_id": request_id,
        "status": result["status"],
        "overall_confidence": scoring.get("overall_confidence"),
        "recommended_action": scoring.get("recommended_action"),
        "summary": scoring.get("ai_summary"),
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
            "change_type": r.change_type,
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
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        if row.change_type == "NAME_CHANGE":
            rps.write_name_update(
                customer_id=row.customer_id,
                new_name=row.new_value,
                request_id=request_id,
                db_session=db,
            )
            return {"success": True, "message": f"RPS updated. Name changed to {row.new_value}."}

        elif row.change_type == "ADDRESS_CHANGE":
            new_addr = json.loads(row.new_value)
            rps.write_address_update(
                customer_id=row.customer_id,
                new_address=new_addr["address"],
                new_city=new_addr["city"],
                new_state=new_addr["state"],
                new_pincode=new_addr["pincode"],
                request_id=request_id,
                db_session=db,
            )
            return {"success": True, "message": f"RPS updated. Address changed to {new_addr['address']}, {new_addr['city']}."}

        elif row.change_type == "CONTACT_CHANGE":
            new_contact = json.loads(row.new_value)
            if new_contact["contact_type"] == "PHONE":
                rps.write_phone_update(
                    customer_id=row.customer_id,
                    new_phone=new_contact["value"],
                    request_id=request_id,
                    db_session=db,
                )
            elif new_contact["contact_type"] == "EMAIL":
                rps.write_email_update(
                    customer_id=row.customer_id,
                    new_email=new_contact["value"],
                    request_id=request_id,
                    db_session=db,
                )
            return {
                "success": True,
                "message": f"RPS updated. {new_contact['contact_type']} changed to {new_contact['value']}.",
            }

        else:
            return {"success": True, "message": f"Request approved (no RPS write for change_type={row.change_type})."}

    # REJECT
    row.overall_status = "REJECTED"
    row.checker_id = body.checker_id
    row.checker_decision = "REJECTED"
    row.checker_comment = body.comment
    row.updated_at = datetime.utcnow()
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

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
