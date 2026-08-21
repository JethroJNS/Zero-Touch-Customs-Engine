"""
Shipment SQLAlchemy model.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum
from .database import Base


def get_local_time():
    """Get current time in Asia/Jakarta timezone (WIB, UTC+7)."""
    from zoneinfo import ZoneInfo
    jakarta_tz = ZoneInfo("Asia/Jakarta")
    return datetime.now(jakarta_tz).replace(tzinfo=None)


class ShipmentStatus(str, enum.Enum):
    DRAFT_VALID = "Draft Valid"
    DRAFT_INVALID = "Draft Invalid"
    SENT = "Sent"
    FAILED = "Failed"
    APPROVED = "Approved"


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    aju_number = Column(String(50), unique=True, index=True, nullable=True)
    reference_code = Column(String(30), unique=True, index=True)
    filename = Column(String(255))
    excel_filename = Column(String(255))
    documents_processed = Column(String(100))
    total_amount = Column(String(50), nullable=True)
    extraction_confidence = Column(Float, default=0.0)
    quality_score = Column(String(20))
    status = Column(
        Enum(ShipmentStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=ShipmentStatus.DRAFT_VALID,
    )
    header_fields = Column(Text, nullable=True)
    line_items = Column(Text, nullable=True)
    quality_report = Column(Text, nullable=True)
    excel_data = Column(Text, nullable=True)
    file_size_kb = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_local_time)
    updated_at = Column(DateTime, default=get_local_time, onupdate=get_local_time)
