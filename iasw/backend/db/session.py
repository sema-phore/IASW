import os
from pathlib import Path

import chromadb
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from iasw.backend.db.models import Base, Customer, RPSRecord

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # IASW/
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "iasw.db"
CHROMA_PATH = DATA_DIR / "chroma"

# ---------------------------------------------------------------------------
# SQLAlchemy
# ---------------------------------------------------------------------------
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables and seed initial data if not already present."""
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        # Seed Customer
        if not session.get(Customer, "C001"):
            session.add(Customer(customer_id="C001", current_name="Priya Sharma", dob="1990-01-01"))

        # Seed RPSRecord
        if not session.get(RPSRecord, "C001"):
            session.add(RPSRecord(customer_id="C001", name="Priya Sharma"))

        session.commit()


# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------
_POLICY_DOCS = [
    "A marriage certificate is valid proof for a legal name change request.",
    (
        "Required fields in a marriage certificate: bride name, groom name, "
        "married name, marriage date, issuing authority signature."
    ),
    (
        "Forgery red flags: inconsistent fonts, missing official seal, altered "
        "dates, mismatched ink color, pixelation around text fields."
    ),
    "Name match is considered valid if fuzzy similarity score exceeds 85%.",
    "Any confidence score below 60% must be flagged for mandatory human review.",
]


def get_chroma_collection() -> chromadb.Collection:
    """Return the policy_kb collection, seeding documents on first run."""
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_or_create_collection("policy_kb")

    if collection.count() == 0:
        collection.add(
            documents=_POLICY_DOCS,
            ids=[f"doc_{i}" for i in range(len(_POLICY_DOCS))],
        )

    return collection
