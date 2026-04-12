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
    db_session.commit()

    return {"success": True, "customer_id": customer_id, "new_name": new_name}
