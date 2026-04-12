from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String, primary_key=True)
    current_name = Column(String)
    dob = Column(String)


class PendingRequest(Base):
    __tablename__ = "pending_requests"

    request_id = Column(String, primary_key=True)
    customer_id = Column(String)
    change_type = Column(String, default="NAME_CHANGE")
    old_value = Column(String)
    new_value = Column(String)
    extracted_json = Column(Text)
    confidence_json = Column(Text)
    overall_status = Column(String)  # AI_VERIFIED_PENDING_HUMAN | APPROVED | REJECTED | AI_FLAGGED
    filenet_ref = Column(String)
    ai_summary = Column(Text)
    recommended_action = Column(String)  # APPROVE | REJECT | MANUAL_REVIEW
    checker_id = Column(String, nullable=True)
    checker_decision = Column(String, nullable=True)
    checker_comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String)
    agent_step = Column(String)
    payload = Column(Text)  # JSON string
    timestamp = Column(DateTime, default=datetime.utcnow)


class RPSRecord(Base):
    """Mock core banking record."""

    __tablename__ = "rps_records"

    customer_id = Column(String, primary_key=True)
    name = Column(String)
    last_updated = Column(DateTime, nullable=True)
