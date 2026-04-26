import json
import re
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "address_summary.txt"


def run(
    cross_ref: dict,
    forgery: dict,
    extracted: dict,
    old_address: dict,
    new_address: dict,
    customer_name: str,
    chroma_collection,
) -> dict:
    """Compute an overall confidence score and generate an AI summary for an address-change request.

    Input:
        cross_ref        - output of address_cross_ref.run()
        forgery          - output of address_forgery_check.run()
        extracted        - output of address_doc_processor.run()
        old_address      - dict with keys address, city, state, pincode (current on-record address)
        new_address      - dict with keys address, city, state, pincode (requested new address)
        customer_name    - account holder name on record
        chroma_collection - ChromaDB collection for policy context retrieval

    Output:
        dict with overall_confidence (float), summary (str), recommended_action (str),
        reasoning (str), and all component scores for the checker UI.
    """
    # Retrieve address-specific policy context from ChromaDB
    results = chroma_collection.query(
        query_texts=["address change proof validation policy"],
        n_results=3,
    )
    docs = results.get("documents", [[]])[0]
    policy_context = "\n".join(docs)

    # --- Deterministic confidence formula ---
    # Weights: name 20%, address line 30%, pincode 20%, authenticity 15%, recency 15%
    name_score = cross_ref.get("name_match_score", 0)
    address_score = cross_ref.get("address_match_score", 0)
    pincode_score = 100 if cross_ref.get("pincode_match", False) else 0
    auth_score = forgery.get("authenticity_score", 0)
    recency_score = 100 if cross_ref.get("doc_recency_valid", False) else 0

    overall_confidence = round(
        name_score * 0.20
        + address_score * 0.30
        + pincode_score * 0.20
        + auth_score * 0.15
        + recency_score * 0.15,
        1,
    )

    # --- Recommendation rules (deterministic, applied before LLM summary) ---
    pincode_match = cross_ref.get("pincode_match", False)
    doc_recency_valid = cross_ref.get("doc_recency_valid", False)
    forgery_verdict = forgery.get("verdict", "FLAG")
    doc_age_days = cross_ref.get("doc_age_days", -1)

    if not pincode_match:
        # Pincode mismatch is an automatic reject per KYC policy
        deterministic_action = "REJECT"
    elif doc_age_days > 90:
        # Document older than 90 days requires human review per banking policy
        deterministic_action = "MANUAL_REVIEW"
    elif (
        overall_confidence >= 85
        and pincode_match
        and doc_recency_valid
        and forgery_verdict == "PASS"
    ):
        deterministic_action = "APPROVE"
    elif overall_confidence >= 60:
        deterministic_action = "MANUAL_REVIEW"
    else:
        deterministic_action = "REJECT"

    # --- LLM generates human-readable summary and reasoning ---
    old_address_str = (
        f"{old_address.get('address', '')}, {old_address.get('city', '')}, "
        f"{old_address.get('state', '')} - {old_address.get('pincode', '')}"
    )
    new_address_str = (
        f"{new_address.get('address', '')}, {new_address.get('city', '')}, "
        f"{new_address.get('state', '')} - {new_address.get('pincode', '')}"
    )

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    template = _PROMPT_PATH.read_text()
    prompt = PromptTemplate(
        template=template,
        input_variables=[
            "old_address",
            "new_address",
            "extracted_name",
            "customer_name",
            "name_match_score",
            "address_match_score",
            "pincode_match",
            "doc_age_days",
            "authenticity_score",
            "forgery_verdict",
            "forgery_flags",
            "policy_context",
        ],
    )
    chain = prompt | llm | StrOutputParser()

    inputs = {
        "old_address": old_address_str,
        "new_address": new_address_str,
        "extracted_name": extracted.get("full_name", ""),
        "customer_name": customer_name,
        "name_match_score": name_score,
        "address_match_score": address_score,
        "pincode_match": pincode_match,
        "doc_age_days": doc_age_days,
        "authenticity_score": auth_score,
        "forgery_verdict": forgery_verdict,
        "forgery_flags": forgery.get("forgery_flags", []),
        "policy_context": policy_context,
    }

    response_text = chain.invoke(inputs)

    # Strip markdown fences before parsing
    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        llm_output = json.loads(cleaned)
    except json.JSONDecodeError as e:
        llm_output = {
            "error": str(e),
            "summary": "Parse error during summary generation.",
            "recommended_action": "MANUAL_REVIEW",
            "reasoning": "",
        }

    return {
        "name_match_score": name_score,
        "address_match_score": address_score,
        "city_match_score": cross_ref.get("city_match_score", 0),
        "state_match_score": cross_ref.get("state_match_score", 0),
        "pincode_match": pincode_match,
        "doc_age_days": doc_age_days,
        "doc_recency_valid": doc_recency_valid,
        "authenticity_score": auth_score,
        "forgery_verdict": forgery_verdict,
        "forgery_flags": forgery.get("forgery_flags", []),
        "overall_confidence": overall_confidence,
        "summary": llm_output.get("summary", ""),
        "recommended_action": deterministic_action,  # deterministic rules take precedence
        "reasoning": llm_output.get("reasoning", ""),
    }
