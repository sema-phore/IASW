import logging
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def extract_text_from_file(file_path: str) -> str:
    """Extract text from a PDF or image file using OCR.

    Returns an empty string on unexpected failure, or a sentinel string when
    the extracted text is too short for the LLM to act on (so the caller can
    fall back to vision-based processing).
    """
    try:
        import pytesseract
        from PIL import Image

        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            from pdf2image import convert_from_path

            pages = convert_from_path(str(path), first_page=1, last_page=1)
            if not pages:
                return ""
            image = pages[0]
        elif suffix in IMAGE_SUFFIXES:
            image = Image.open(str(path))
        else:
            logger.warning("Unsupported file type for OCR: %s", suffix)
            return ""

        text: str = pytesseract.image_to_string(image)

        if len(text.strip()) < 20:
            return f"OCR_INSUFFICIENT: file saved at {file_path}"

        return text

    except Exception:
        logger.exception("OCR failed for file: %s", file_path)
        return ""
