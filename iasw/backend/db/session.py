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
            session.add(Customer(
                customer_id="C001",
                current_name="Priya Sharma",
                dob="1990-01-01",
                address="42 MG Road",
                city="Delhi",
                state="Delhi",
                pincode="110001",
                phone="9876543210",
                email="priya.sharma@email.com",
            ))

        # Seed RPSRecord
        if not session.get(RPSRecord, "C001"):
            session.add(RPSRecord(
                customer_id="C001",
                name="Priya Sharma",
                address="42 MG Road",
                city="Delhi",
                state="Delhi",
                pincode="110001",
                phone="9876543210",
                email="priya.sharma@email.com",
            ))

        try:
            session.commit()
        except Exception:
            session.rollback()
            raise


# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------
_POLICY_DOCS = [
    # --- Name-change policies ---
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
    # --- Address-change policies ---
    (
        "Acceptable address proofs: utility bill, bank statement, rental agreement, "
        "Aadhaar card, passport."
    ),
    (
        "Address proof documents must be issued within the last 3 months "
        "to be considered valid."
    ),
    (
        "Pincode must match exactly between the submitted address and the "
        "supporting document."
    ),
    (
        "If the customer name on the address proof does not match the account name, "
        "the request must be flagged for manual review."
    ),
    # --- Contact-change (phone/email) policies ---
    "Phone number changes require OTP verification sent to the new phone number.",
    "Email address changes require OTP verification sent to the new email address.",
    "Contact changes verified via OTP do not require document upload or forgery checks.",
    "OTP verification codes expire after 10 minutes. A maximum of 3 attempts are allowed.",
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
