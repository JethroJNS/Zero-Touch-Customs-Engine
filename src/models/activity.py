"""
Activity / Audit Log SQLAlchemy model.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from .shipment import Base


def get_local_time():
    """Get current time in Asia/Jakarta timezone (WIB, UTC+7)."""
    from zoneinfo import ZoneInfo
    jakarta_tz = ZoneInfo("Asia/Jakarta")
    return datetime.now(jakarta_tz).replace(tzinfo=None)


class ActivityAction(str, enum.Enum):
    OCR_PROCESS = "OCR Process"
    DECLARATION_CREATE = "Declaration Create"
    DECLARATION_UPDATE = "Declaration Update"
    DECLARATION_DELETE = "Declaration Delete"
    DECLARATION_SEND = "Declaration Send"
    DECLARATION_APPROVE = "Declaration Approve"
    DECLARATION_REJECT = "Declaration Reject"


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    entity_type = Column(String(30), nullable=True)  # "shipment"
    entity_id = Column(Integer, nullable=True, index=True)
    reference_code = Column(String(30), nullable=True, index=True)
    event_data = Column(Text, nullable=True)  # JSON string
    status = Column(String(30), nullable=True)  # "success", "failed", "approved", etc.
    created_at = Column(DateTime, default=get_local_time)
