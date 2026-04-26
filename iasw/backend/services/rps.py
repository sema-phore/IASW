import json
from datetime import datetime

from iasw.backend.db.models import AuditLog, PendingRequest, RPSRecord


def write_name_update(
    customer_id: str,
    new_name: str,
    request_id: str,
    db_session,
) -> dict:
    """Write an approved name change to the mock RPS core-banking record.

    Raises ValueError if the request has not reached APPROVED status —
    enforcing the HITL constraint before any write occurs.
    """
    pending = db_session.query(PendingRequest).filter_by(request_id=request_id).first()
    if pending is None or pending.overall_status != "APPROVED":
        raise ValueError(
            "RPS write blocked: HITL constraint not met. "
            "Request must be in APPROVED status before writing to RPS."
        )

    rps_record = db_session.query(RPSRecord).filter_by(customer_id=customer_id).first()
    if rps_record:
        rps_record.name = new_name
        rps_record.last_updated = datetime.utcnow()

    audit = AuditLog(
        request_id=request_id,
        agent_step="RPS_WRITE",
        payload=json.dumps(
            {"customer_id": customer_id, "new_name": new_name, "request_id": request_id}
        ),
    )
    db_session.add(audit)
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise

    return {"success": True, "customer_id": customer_id, "new_name": new_name}


def write_address_update(
    customer_id: str,
    new_address: str,
    new_city: str,
    new_state: str,
    new_pincode: str,
    request_id: str,
    db_session,
) -> dict:
    """Write an approved address change to the mock RPS core-banking record.

    Input:
        customer_id  - the customer whose record is being updated
        new_address  - new street address line
        new_city     - new city
        new_state    - new state
        new_pincode  - new pincode (must match document exactly per policy)
        request_id   - UUID of the PendingRequest authorising this write
        db_session   - active SQLAlchemy session

    Output:
        dict with keys: success, customer_id, new_address, new_city,
                        new_state, new_pincode

    Raises ValueError if the HITL constraint is not met (request not APPROVED).
    Never call this function directly from an agent — only from the decision endpoint.
    """
    # HITL guard — identical pattern to write_name_update
    pending = db_session.query(PendingRequest).filter_by(request_id=request_id).first()
    if pending is None or pending.overall_status != "APPROVED":
        raise ValueError(
            "RPS write blocked: HITL constraint not met. "
            "Request must be in APPROVED status before writing to RPS."
        )

    rps_record = db_session.query(RPSRecord).filter_by(customer_id=customer_id).first()
    if rps_record:
        rps_record.address = new_address
        rps_record.city = new_city
        rps_record.state = new_state
        rps_record.pincode = new_pincode
        rps_record.last_updated = datetime.utcnow()

    audit = AuditLog(
        request_id=request_id,
        agent_step="RPS_WRITE_ADDRESS",
        payload=json.dumps({
            "customer_id": customer_id,
            "new_address": new_address,
            "new_city": new_city,
            "new_state": new_state,
            "new_pincode": new_pincode,
            "request_id": request_id,
        }),
    )
    db_session.add(audit)
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise

    return {
        "success": True,
        "customer_id": customer_id,
        "new_address": new_address,
        "new_city": new_city,
        "new_state": new_state,
        "new_pincode": new_pincode,
    }
