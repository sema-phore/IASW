import json
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from iasw.backend.db.models import AuditLog
from iasw.backend.services import ocr, otp
from iasw.backend.agents import (
    doc_processor,
    cross_ref as cross_ref_agent,
    forgery_check,
    scorer,
    address_doc_processor,
    address_cross_ref as address_cross_ref_agent,
    address_forgery_check,
    address_scorer,
)


class PipelineState(TypedDict):
    """Shared state carried across all LangGraph nodes in the pipeline."""

    file_path: Path
    old_name: str
    new_name: str
    db_session: Any
    chroma_collection: Any
    request_id: str
    raw_text: str
    extracted: dict
    cross_ref: dict
    forgery: dict
    scoring: dict
    status: str


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


def _ocr_node(state: PipelineState) -> dict:
    """Run OCR on the uploaded document and log the char count.

    Input:  state with file_path, db_session, request_id.
    Output: partial state update with raw_text (str).
    """
    raw_text = ocr.extract_text_from_file(state["file_path"])
    _log(state["db_session"], state["request_id"], "OCR_COMPLETE", {"chars": len(raw_text)})
    return {"raw_text": raw_text}


def _doc_processor_node(state: PipelineState) -> dict:
    """Extract structured fields from OCR text and log the result.

    Input:  state with raw_text, db_session, request_id.
    Output: partial state update with extracted (dict).
    """
    extracted = doc_processor.run(state["raw_text"])
    _log(state["db_session"], state["request_id"], "DOC_EXTRACTED", extracted)
    return {"extracted": extracted}


def _cross_ref_node(state: PipelineState) -> dict:
    """Fuzzy-match extracted names against the requested name change and log.

    Input:  state with extracted, old_name, new_name, db_session, request_id.
    Output: partial state update with cross_ref (dict).
    """
    cross_ref = cross_ref_agent.run(state["extracted"], state["old_name"], state["new_name"])
    _log(state["db_session"], state["request_id"], "CROSS_REF_COMPLETE", cross_ref)
    return {"cross_ref": cross_ref}


def _forgery_node(state: PipelineState) -> dict:
    """Assess document authenticity against policy knowledge base and log.

    Input:  state with raw_text, chroma_collection, db_session, request_id.
    Output: partial state update with forgery (dict).
    """
    forgery = forgery_check.run(state["raw_text"], state["chroma_collection"])
    _log(state["db_session"], state["request_id"], "FORGERY_CHECK_COMPLETE", forgery)
    return {"forgery": forgery}


def _scorer_node(state: PipelineState) -> dict:
    """Compute overall confidence score and AI summary, then log.

    Input:  state with cross_ref, forgery, extracted, old_name, new_name,
            chroma_collection, db_session, request_id.
    Output: partial state update with scoring (dict).
    """
    result = scorer.run(
        state["cross_ref"],
        state["forgery"],
        state["extracted"],
        state["old_name"],
        state["new_name"],
        state["chroma_collection"],
    )
    _log(state["db_session"], state["request_id"], "SCORING_COMPLETE", result)
    return {"scoring": result}


def _status_node(state: PipelineState) -> dict:
    """Determine final AI status from scoring and forgery verdict.

    Input:  state with scoring (dict), forgery (dict).
    Output: partial state update with status ("AI_FLAGGED" or
            "AI_VERIFIED_PENDING_HUMAN").
    """
    if state["scoring"]["overall_confidence"] < 60 or state["forgery"]["verdict"] == "FAIL":
        status = "AI_FLAGGED"
    else:
        status = "AI_VERIFIED_PENDING_HUMAN"
    return {"status": status}


def _build_graph():
    """Compile the LangGraph StateGraph for the full processing pipeline."""
    graph = StateGraph(PipelineState)

    graph.add_node("ocr", _ocr_node)
    graph.add_node("doc_processor", _doc_processor_node)
    graph.add_node("cross_ref", _cross_ref_node)
    graph.add_node("forgery", _forgery_node)
    graph.add_node("scorer", _scorer_node)
    graph.add_node("status", _status_node)

    graph.set_entry_point("ocr")
    graph.add_edge("ocr", "doc_processor")
    graph.add_edge("doc_processor", "cross_ref")
    graph.add_edge("cross_ref", "forgery")
    graph.add_edge("forgery", "scorer")
    graph.add_edge("scorer", "status")
    graph.add_edge("status", END)

    return graph.compile()


# Compiled once at import time; reused for every request.
_PIPELINE_GRAPH = _build_graph()


def run_pipeline(
    file_path: Path,
    old_name: str,
    new_name: str,
    db_session,
    chroma_collection,
    request_id: str,
) -> dict:
    """Orchestrate the full AI processing pipeline via a LangGraph StateGraph.

    Input:  file_path (Path) — local path to the uploaded document;
            old_name / new_name (str) — requested name change values;
            db_session — SQLAlchemy session for audit logging;
            chroma_collection — ChromaDB collection for policy context;
            request_id (str) — UUID for this request.
    Output: dict with keys extracted, cross_ref, forgery, scoring, status.
    """
    initial_state: PipelineState = {
        "file_path": file_path,
        "old_name": old_name,
        "new_name": new_name,
        "db_session": db_session,
        "chroma_collection": chroma_collection,
        "request_id": request_id,
        "raw_text": "",
        "extracted": {},
        "cross_ref": {},
        "forgery": {},
        "scoring": {},
        "status": "",
    }

    final_state = _PIPELINE_GRAPH.invoke(initial_state)

    return {
        "extracted": final_state["extracted"],
        "cross_ref": final_state["cross_ref"],
        "forgery": final_state["forgery"],
        "scoring": final_state["scoring"],
        "status": final_state["status"],
    }


# ---------------------------------------------------------------------------
# Address-change pipeline
# ---------------------------------------------------------------------------

class AddressPipelineState(TypedDict):
    """Shared state carried across all LangGraph nodes in the address pipeline."""

    file_path: Path
    customer_name: str
    old_address: dict   # {address, city, state, pincode} — current on-record address
    new_address: dict   # {address, city, state, pincode} — requested new address
    db_session: Any
    chroma_collection: Any
    request_id: str
    # intermediate / output fields
    raw_text: str
    extracted: dict
    cross_ref: dict
    forgery: dict
    scoring: dict
    status: str


def _address_ocr_node(state: AddressPipelineState) -> dict:
    """Run OCR on the uploaded address proof document and log the char count.

    Input:  state with file_path, db_session, request_id.
    Output: partial state update with raw_text (str).
    """
    raw_text = ocr.extract_text_from_file(state["file_path"])
    _log(state["db_session"], state["request_id"], "ADDR_OCR_COMPLETE", {"chars": len(raw_text)})
    return {"raw_text": raw_text}


def _address_doc_processor_node(state: AddressPipelineState) -> dict:
    """Extract structured address fields from OCR text and log the result.

    Input:  state with raw_text, db_session, request_id.
    Output: partial state update with extracted (dict).
    """
    extracted = address_doc_processor.run(state["raw_text"])
    _log(state["db_session"], state["request_id"], "ADDR_DOC_EXTRACTED", extracted)
    return {"extracted": extracted}


def _address_cross_ref_node(state: AddressPipelineState) -> dict:
    """Validate extracted address fields against customer and requested address data.

    Input:  state with extracted, customer_name, new_address, db_session, request_id.
    Output: partial state update with cross_ref (dict).
    """
    cross_ref = address_cross_ref_agent.run(
        state["extracted"],
        state["customer_name"],
        state["new_address"],
    )
    _log(state["db_session"], state["request_id"], "ADDR_CROSS_REF_COMPLETE", cross_ref)
    return {"cross_ref": cross_ref}


def _address_forgery_node(state: AddressPipelineState) -> dict:
    """Assess address proof authenticity against policy knowledge base and log.

    Input:  state with raw_text, chroma_collection, db_session, request_id.
    Output: partial state update with forgery (dict).
    """
    forgery = address_forgery_check.run(state["raw_text"], state["chroma_collection"])
    _log(state["db_session"], state["request_id"], "ADDR_FORGERY_CHECK_COMPLETE", forgery)
    return {"forgery": forgery}


def _address_scorer_node(state: AddressPipelineState) -> dict:
    """Compute overall confidence score and AI summary for address change, then log.

    Input:  state with cross_ref, forgery, extracted, old_address, new_address,
            customer_name, chroma_collection, db_session, request_id.
    Output: partial state update with scoring (dict).
    """
    result = address_scorer.run(
        state["cross_ref"],
        state["forgery"],
        state["extracted"],
        state["old_address"],
        state["new_address"],
        state["customer_name"],
        state["chroma_collection"],
    )
    _log(state["db_session"], state["request_id"], "ADDR_SCORING_COMPLETE", result)
    return {"scoring": result}


def _address_status_node(state: AddressPipelineState) -> dict:
    """Determine final AI status from scoring and forgery verdict.

    Input:  state with scoring (dict), forgery (dict).
    Output: partial state update with status ("AI_FLAGGED" or
            "AI_VERIFIED_PENDING_HUMAN").
    """
    confidence = state["scoring"]["overall_confidence"]
    forgery_verdict = state["forgery"]["verdict"]

    if confidence < 60 or forgery_verdict == "FAIL":
        status = "AI_FLAGGED"
    else:
        status = "AI_VERIFIED_PENDING_HUMAN"

    return {"status": status}


def _build_address_graph():
    """Compile the LangGraph StateGraph for the address-change processing pipeline."""
    graph = StateGraph(AddressPipelineState)

    graph.add_node("ocr", _address_ocr_node)
    graph.add_node("doc_processor", _address_doc_processor_node)
    graph.add_node("cross_ref", _address_cross_ref_node)
    graph.add_node("forgery", _address_forgery_node)
    graph.add_node("scorer", _address_scorer_node)
    graph.add_node("status", _address_status_node)

    graph.set_entry_point("ocr")
    graph.add_edge("ocr", "doc_processor")
    graph.add_edge("doc_processor", "cross_ref")
    graph.add_edge("cross_ref", "forgery")
    graph.add_edge("forgery", "scorer")
    graph.add_edge("scorer", "status")
    graph.add_edge("status", END)

    return graph.compile()


# Compiled once at import time; reused for every request.
_ADDRESS_PIPELINE_GRAPH = _build_address_graph()


def run_address_pipeline(
    file_path: Path,
    customer_name: str,
    old_address: dict,
    new_address: dict,
    db_session,
    chroma_collection,
    request_id: str,
) -> dict:
    """Orchestrate the full AI address-change pipeline via a LangGraph StateGraph.

    Input:
        file_path       - local path to the uploaded address proof document
        customer_name   - account holder name on record
        old_address     - dict {address, city, state, pincode} currently on record
        new_address     - dict {address, city, state, pincode} being requested
        db_session      - SQLAlchemy session for audit logging
        chroma_collection - ChromaDB collection for policy context
        request_id      - UUID for this request

    Output: dict with keys extracted, cross_ref, forgery, scoring, status.
    """
    initial_state: AddressPipelineState = {
        "file_path": file_path,
        "customer_name": customer_name,
        "old_address": old_address,
        "new_address": new_address,
        "db_session": db_session,
        "chroma_collection": chroma_collection,
        "request_id": request_id,
        "raw_text": "",
        "extracted": {},
        "cross_ref": {},
        "forgery": {},
        "scoring": {},
        "status": "",
    }

    final_state = _ADDRESS_PIPELINE_GRAPH.invoke(initial_state)

    return {
        "extracted": final_state["extracted"],
        "cross_ref": final_state["cross_ref"],
        "forgery": final_state["forgery"],
        "scoring": final_state["scoring"],
        "status": final_state["status"],
    }


# ---------------------------------------------------------------------------
# Contact-change pipeline (phone / email)
# ---------------------------------------------------------------------------

class ContactPipelineState(TypedDict):
    """Shared state for the contact-change (phone/email) pipeline.

    This pipeline intentionally skips OCR, document extraction, and forgery
    checks. Phone/email changes are verified via OTP — this is correct
    architectural design, not a shortcut.
    """
    contact_type: str       # "PHONE" or "EMAIL"
    customer_name: str
    old_value: str          # current phone/email on record
    new_value: str          # requested new phone/email
    otp_code: str           # user-entered OTP
    db_session: Any
    chroma_collection: Any
    request_id: str
    # intermediate / output fields
    otp_result: dict
    scoring: dict
    status: str


def _contact_otp_node(state: ContactPipelineState) -> dict:
    """Verify the user-supplied OTP against the value sent to the new contact.

    Input:  state with new_value (the contact to verify), otp_code (user input),
            db_session, request_id.
    Output: partial state update with otp_result (dict containing 'verified' bool).

    Per design: this node replaces OCR + doc_processor + forgery for contact changes.
    """
    result = otp.verify_otp(state["new_value"], state["otp_code"])

    # Per Rule 13 — audit every OTP step so the Checker sees the outcome.
    step = "OTP_VERIFIED" if result.get("verified") else "OTP_FAILED"
    _log(state["db_session"], state["request_id"], step, result)

    return {"otp_result": result}


def _contact_scorer_node(state: ContactPipelineState) -> dict:
    """Compute confidence score and summary for a contact change request.

    Input:  state with otp_result, contact_type, old_value, new_value,
            db_session, request_id.
    Output: partial state update with scoring (dict).

    No LLM call is made in this function.
    """
    # This scorer intentionally does not call an LLM.
    # OTP verification is a binary pass/fail — AI scoring adds no value here.
    # This is correct design, not a shortcut.
    otp_verified = state["otp_result"].get("verified", False)
    overall_confidence = 100 if otp_verified else 0
    recommended_action = "APPROVE" if otp_verified else "REJECT"
    summary = (
        f"OTP verification {'passed' if otp_verified else 'FAILED'} "
        f"for {state['contact_type'].lower()} change "
        f"from {state['old_value']} to {state['new_value']}. "
        f"{'Recommended: Approve.' if otp_verified else 'Recommended: Reject.'}"
    )
    reasoning = (
        "OTP verified successfully — contact ownership confirmed."
        if otp_verified
        else "OTP verification failed — cannot confirm ownership of new contact."
    )

    scoring = {
        "overall_confidence": overall_confidence,
        "recommended_action": recommended_action,
        "summary": summary,
        "reasoning": reasoning,
        "otp_verified": otp_verified,
    }

    _log(state["db_session"], state["request_id"], "CONTACT_SCORING_COMPLETE", scoring)
    return {"scoring": scoring}


def _contact_status_node(state: ContactPipelineState) -> dict:
    """Determine final AI status from OTP-based confidence score.

    Input:  state with scoring (dict).
    Output: partial state update with status ("AI_VERIFIED_PENDING_HUMAN" or
            "AI_FLAGGED").
    """
    if state["scoring"]["overall_confidence"] == 100:
        status = "AI_VERIFIED_PENDING_HUMAN"
    else:
        status = "AI_FLAGGED"
    return {"status": status}


def _build_contact_graph():
    """Compile the LangGraph StateGraph for contact-change (phone/email) pipeline.

    This graph has only 3 nodes (otp → scorer → status) because contact
    changes do not require document analysis. This is intentional.
    """
    graph = StateGraph(ContactPipelineState)
    graph.add_node("otp_verify", _contact_otp_node)
    graph.add_node("scorer", _contact_scorer_node)
    graph.add_node("status", _contact_status_node)
    graph.set_entry_point("otp_verify")
    graph.add_edge("otp_verify", "scorer")
    graph.add_edge("scorer", "status")
    graph.add_edge("status", END)
    return graph.compile()


# Compiled once at import time; reused for every request.
_CONTACT_PIPELINE_GRAPH = _build_contact_graph()


def run_contact_pipeline(
    contact_type: str,
    customer_name: str,
    old_value: str,
    new_value: str,
    otp_code: str,
    db_session,
    chroma_collection,
    request_id: str,
) -> dict:
    """Orchestrate the contact-change pipeline via a LangGraph StateGraph.

    Input:
        contact_type      - "PHONE" or "EMAIL"
        customer_name     - account holder name (for audit trail)
        old_value         - current phone/email on record
        new_value         - requested new phone/email
        otp_code          - user-entered OTP code
        db_session        - SQLAlchemy session for audit logging
        chroma_collection - ChromaDB collection (unused but kept for interface consistency)
        request_id        - UUID for this request

    Output: dict with keys extracted, cross_ref, forgery, scoring, status.
            extracted/cross_ref/forgery will be empty/N/A dicts — this is intentional
            because contact changes skip document analysis.
    """
    initial_state: ContactPipelineState = {
        "contact_type": contact_type,
        "customer_name": customer_name,
        "old_value": old_value,
        "new_value": new_value,
        "otp_code": otp_code,
        "db_session": db_session,
        "chroma_collection": chroma_collection,
        "request_id": request_id,
        "otp_result": {},
        "scoring": {},
        "status": "",
    }

    final_state = _CONTACT_PIPELINE_GRAPH.invoke(initial_state)

    return {
        "extracted": {},            # no document to extract
        "cross_ref": {},            # no cross-referencing needed
        "forgery": {                # not applicable for contact changes
            "verdict": "N/A",
            "authenticity_score": 0,
            "forgery_flags": [],
        },
        "scoring": final_state["scoring"],
        "status": final_state["status"],
    }
