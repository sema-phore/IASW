import json
from pathlib import Path

from iasw.backend.db.models import AuditLog
from iasw.backend.services import ocr
from iasw.backend.agents import doc_processor, cross_ref as cross_ref_agent, forgery_check, scorer


def _log(db_session, request_id: str, agent_step: str, payload: dict) -> None:
    entry = AuditLog(
        request_id=request_id,
        agent_step=agent_step,
        payload=json.dumps(payload),
    )
    db_session.add(entry)
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise


def run_pipeline(
    file_path: Path,
    old_name: str,
    new_name: str,
    db_session,
    chroma_collection,
    request_id: str,
) -> dict:
    """Orchestrate the full AI processing pipeline for a name-change request.

    Input:  file_path (Path) — local path to the uploaded document;
            old_name / new_name (str) — requested name change values;
            db_session — SQLAlchemy session for audit logging;
            chroma_collection — ChromaDB collection for policy context;
            request_id (str) — UUID for this request.
    Output: dict with keys extracted, cross_ref, forgery, scoring, status.
    """
    # 1. OCR
    raw_text = ocr.extract_text_from_file(file_path)

    # 2. Log OCR complete
    _log(db_session, request_id, "OCR_COMPLETE", {"chars": len(raw_text)})

    # 3. Doc Processor
    extracted = doc_processor.run(raw_text)

    # 4. Log extraction
    _log(db_session, request_id, "DOC_EXTRACTED", extracted)

    # 5. Cross Ref
    cross_ref = cross_ref_agent.run(extracted, old_name, new_name)

    # 6. Log cross ref
    _log(db_session, request_id, "CROSS_REF_COMPLETE", cross_ref)

    # 7. Forgery Check
    forgery = forgery_check.run(raw_text, chroma_collection)

    # 8. Log forgery check
    _log(db_session, request_id, "FORGERY_CHECK_COMPLETE", forgery)

    # 9. Scorer
    result = scorer.run(cross_ref, forgery, extracted, old_name, new_name, chroma_collection)

    # 10. Log scoring
    _log(db_session, request_id, "SCORING_COMPLETE", result)

    # 11. Determine status
    if result["overall_confidence"] < 60 or forgery["verdict"] == "FAIL":
        status = "AI_FLAGGED"
    else:
        status = "AI_VERIFIED_PENDING_HUMAN"

    # 12. Return
    return {
        "extracted": extracted,
        "cross_ref": cross_ref,
        "forgery": forgery,
        "scoring": result,
        "status": status,
    }
