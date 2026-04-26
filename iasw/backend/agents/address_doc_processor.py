import json
import re
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "address_extraction.txt"


def run(ocr_text: str) -> dict:
    """Extract structured fields from raw OCR text of an address proof document.

    Input:  ocr_text (str) — raw text extracted from the uploaded address proof
            (utility bill, bank statement, rental agreement, Aadhaar, or passport).
    Output: dict with keys document_type, full_name, address_line, city, state,
            pincode, issue_date, provider_name, has_official_seal,
            or {"error": <message>, "raw": <response>} on JSON parse failure.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    template = _PROMPT_PATH.read_text()
    prompt = PromptTemplate(template=template, input_variables=["ocr_text"])
    chain = prompt | llm | StrOutputParser()

    response_text = chain.invoke({"ocr_text": ocr_text})

    # Strip markdown fences before parsing
    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        return {"error": str(e), "raw": response_text}
