import uuid
from pathlib import Path

FILENET_DIR = Path(__file__).resolve().parents[4] / "data" / "filenet"


def save_document(file_bytes: bytes, filename: str) -> str:
    """Save file bytes to the mock FileNet store and return a reference ID."""
    FILENET_DIR.mkdir(parents=True, exist_ok=True)
    filenet_ref_id = str(uuid.uuid4())
    dest = FILENET_DIR / f"{filenet_ref_id}_{filename}"
    dest.write_bytes(file_bytes)
    return filenet_ref_id
