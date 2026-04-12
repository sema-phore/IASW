import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def _vision_fallback(file_path: Path) -> str:
    """Use OpenAI GPT-4o vision to extract text when Tesseract is unavailable."""
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage

    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if len(text.strip()) >= 20:
                return text
        except Exception:
            pass
        # Convert first PDF page to image for vision
        from pdf2image import convert_from_path
        pages = convert_from_path(str(file_path), first_page=1, last_page=1)
        if not pages:
            return ""
        import io
        buf = io.BytesIO()
        pages[0].save(buf, format="PNG")
        image_bytes = buf.getvalue()
        mime = "image/png"
    else:
        image_bytes = file_path.read_bytes()
        mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"

    encoded = base64.b64encode(image_bytes).decode("utf-8")

    llm = ChatOpenAI(model="gpt-4o", temperature=0, max_tokens=1024)
    msg = HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "Extract and return ALL visible text from this document image exactly as it appears. "
                    "Do not interpret or summarize — return only the raw text."
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            },
        ]
    )
    response = llm.invoke([msg])
    return response.content


def extract_text_from_file(file_path: Path) -> str:
    """Extract text from a PDF or image file using OCR.

    Tries Tesseract first; falls back to OpenAI GPT-4o vision when Tesseract
    is not installed. Returns an empty string on unexpected failure.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    # --- Tesseract path ---
    try:
        import pytesseract
        from PIL import Image

        if suffix == ".pdf":
            from pdf2image import convert_from_path
            pages = convert_from_path(str(path), first_page=1, last_page=1)
            if not pages:
                return ""
            image = pages[0]
        elif suffix in IMAGE_SUFFIXES:
            image = Image.open(path)
        else:
            logger.warning("Unsupported file type for OCR: %s", suffix)
            return ""

        text: str = pytesseract.image_to_string(image)

        if len(text.strip()) >= 20:
            return text

    except Exception:
        logger.info("Tesseract unavailable for %s — switching to vision fallback", file_path)

    # --- Vision fallback ---
    try:
        text = _vision_fallback(path)
        if len(text.strip()) < 20:
            return f"OCR_INSUFFICIENT: file saved at {path}"
        return text
    except Exception:
        logger.exception("Vision fallback OCR failed for file: %s", file_path)
        return ""
