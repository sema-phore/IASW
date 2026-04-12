import json
import re
from pathlib import Path

from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "doc_extraction.txt"


def run(ocr_text: str) -> dict:
    """Extract structured fields from raw OCR text using an LLM.

    Input:  ocr_text (str) — raw text extracted from the uploaded document.
    Output: dict with keys bride_name, married_name, marriage_date, etc.,
            or {"error": <message>, "raw": <response>} on JSON parse failure.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    template = _PROMPT_PATH.read_text()
    prompt = PromptTemplate(template=template, input_variables=["ocr_text"])
    chain = prompt | llm | StrOutputParser()

    response_text = chain.invoke({"ocr_text": ocr_text})

    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        return {"error": str(e), "raw": response_text}
