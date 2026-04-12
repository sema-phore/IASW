import json
import re
from pathlib import Path

from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "forgery_check.txt"


def run(ocr_text: str, chroma_collection) -> dict:
    """Assess document authenticity by checking OCR text against policy knowledge base.

    Input:  ocr_text (str) — raw text from the document;
            chroma_collection — ChromaDB collection containing forgery-detection policies.
    Output: dict with authenticity_score (int 0-100), forgery_flags (list[str]),
            verdict ("PASS" | "FAIL" | "FLAG"), or error fallback dict on failure.
    """
    try:
        results = chroma_collection.query(query_texts=[ocr_text], n_results=2)
        docs = results.get("documents", [[]])[0]
        policy_context = "\n".join(docs)

        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        template = _PROMPT_PATH.read_text()
        prompt = PromptTemplate(
            template=template,
            input_variables=["ocr_text", "policy_context"],
        )
        chain = prompt | llm | StrOutputParser()

        response_text = chain.invoke({"ocr_text": ocr_text, "policy_context": policy_context})

        cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)

        return json.loads(cleaned)
    except Exception as e:
        return {
            "error": str(e),
            "authenticity_score": 50,
            "forgery_flags": ["processing_error"],
            "verdict": "FLAG",
        }
