import json
import re
from pathlib import Path

from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "summary.txt"


def run(
    cross_ref: dict,
    forgery: dict,
    extracted: dict,
    old_name: str,
    new_name: str,
    chroma_collection,
) -> dict:
    results = chroma_collection.query(
        query_texts=["name change confidence scoring policy"],
        n_results=2,
    )
    docs = results.get("documents", [[]])[0]
    policy_context = "\n".join(docs)

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    template = _PROMPT_PATH.read_text()
    prompt = PromptTemplate(
        template=template,
        input_variables=[
            "old_name",
            "new_name",
            "bride_name",
            "married_name",
            "name_match_score",
            "authenticity_score",
            "forgery_verdict",
            "forgery_flags",
            "policy_context",
        ],
    )
    chain = prompt | llm | StrOutputParser()

    inputs = {
        "old_name": old_name,
        "new_name": new_name,
        "bride_name": extracted.get("bride_name", ""),
        "married_name": extracted.get("married_name", ""),
        "name_match_score": cross_ref["old_name_score"],
        "authenticity_score": forgery["authenticity_score"],
        "forgery_verdict": forgery["verdict"],
        "forgery_flags": forgery["forgery_flags"],
        "policy_context": policy_context,
    }

    response_text = chain.invoke(inputs)

    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    llm_output = json.loads(cleaned)

    overall_confidence = round(
        cross_ref["old_name_score"] * 0.4
        + cross_ref["new_name_score"] * 0.4
        + forgery["authenticity_score"] * 0.2,
        1,
    )

    return {
        "name_match_score": cross_ref["old_name_score"],
        "new_name_match_score": cross_ref["new_name_score"],
        "authenticity_score": forgery["authenticity_score"],
        "forgery_verdict": forgery["verdict"],
        "forgery_flags": forgery["forgery_flags"],
        "overall_confidence": overall_confidence,
        "summary": llm_output["summary"],
        "recommended_action": llm_output["recommended_action"],
        "reasoning": llm_output["reasoning"],
    }
