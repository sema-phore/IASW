import json
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from iasw.backend.db.models import AuditLog
from iasw.backend.services import ocr
from iasw.backend.agents import (
    doc_processor,
    cross_ref as cross_ref_agent,
    forgery_check,
    scorer,
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
