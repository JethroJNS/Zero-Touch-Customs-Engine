"""
FastAPI web application for the Document OCR Extraction Engine.

Provides:
  - POST /api/extract: Run OCR + extraction pipeline
  - GET /api/shipments: List all shipments (Declarations page)
  - CRUD operations for shipments
"""

import sys
import os
import uuid
import shutil
import tempfile
import logging
import base64
import json
import enum
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Depends, Query, BackgroundTasks, APIRouter
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Enum as SQLEnum, select, delete, func, or_
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

# ── Setup logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ocr_web")

# ── Database configuration ────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/ocr_engine"
)

async_database_url = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(async_database_url, poolclass=NullPool, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

sync_engine = create_engine(DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=sync_engine)
Base = declarative_base()


# ── Enums ─────────────────────────────────────────────────────────────────────
# Status System:
# - Draft Valid: OCR result with confidence > 50%
# - Draft Invalid: OCR result with confidence < 50% (cannot be sent)
# - Sent: Shipment sent to CEISA system
# - Failed: Shipment rejected by CEISA system
# - Approved: Draft Valid that was accepted by CEISA system
class ShipmentStatus(str, enum.Enum):
    DRAFT_VALID = "Draft Valid"
    DRAFT_INVALID = "Draft Invalid"
    SENT = "Sent"
    FAILED = "Failed"
    APPROVED = "Approved"


def get_local_time():
    """Get current time in Asia/Jakarta timezone (WIB, UTC+7).
    This matches the local time of the application's users in Indonesia.
    """
    jakarta_tz = ZoneInfo("Asia/Jakarta")
    return datetime.now(jakarta_tz).replace(tzinfo=None)


# ── SQLAlchemy Model ──────────────────────────────────────────────────────────
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
        SQLEnum(ShipmentStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=ShipmentStatus.DRAFT_VALID,
    )
    header_fields = Column(Text, nullable=True)
    line_items = Column(Text, nullable=True)
    quality_report = Column(Text, nullable=True)
    excel_data = Column(Text, nullable=True)
    file_size_kb = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_local_time)
    updated_at = Column(DateTime, default=get_local_time, onupdate=get_local_time)


# ── Activity / Audit Log Enums & Model ─────────────────────────────────────────
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


async def create_activity(
    db: AsyncSession,
    action: ActivityAction,
    description: str,
    entity_type: str = "shipment",
    entity_id: int = None,
    reference_code: str = None,
    metadata: dict = None,
    status: str = "success",
):
    """Insert an activity log entry."""
    act = Activity(
        action=action.value,
        description=description,
        entity_type=entity_type,
        entity_id=entity_id,
        reference_code=reference_code,
        event_data=json.dumps(metadata) if metadata else None,
        status=status,
    )
    db.add(act)
    await db.commit()
    return act


# ── Database dependency ────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


def generate_reference_code() -> str:
    return f"CD-{uuid.uuid4().hex[:8].upper()}"


# ── ML Engine paths (conditional import) ──────────────────────────────────────
# Structure: /app/main.py, /app/ml/
# - ml/ is a top-level package containing OCR and extraction modules
# - ml/src/ contains extraction/, excel/, ocr/ submodules

ENGINE_DIR = Path(__file__).parent.parent / "ml"  # = /app/ml/
sys.path.insert(0, str(ENGINE_DIR))

HybridExtractor = None
ExcelExporter = None
ENGINE_AVAILABLE = False

try:
    from ml.src.extraction.hybrid_engine import HybridExtractor as _HE
    from ml.src.excel.exporter import ExcelExporter as _EE
    HybridExtractor = _HE
    ExcelExporter = _EE
    ENGINE_AVAILABLE = True
    logger.info("OCR Engine modules loaded successfully.")
except ImportError as e:
    logger.warning(f"OCR Engine not available: {e}")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Document OCR Extraction Engine",
    description="Upload CI, PL, and BL documents to run CEISA 4.0 extraction pipeline.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Database startup ───────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _create_tables)
    await loop.run_in_executor(None, _seed_data)


def _create_tables():
    try:
        Base.metadata.create_all(bind=sync_engine)
        logger.info("Database tables created / verified.")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")


def _seed_data():
    """Auto-seed sample data on first startup."""
    try:
        db = SessionLocal()
        try:
            if db.query(Shipment).count() > 0:
                return

            now = get_local_time()

            # Create a mix of shipments with different statuses for dashboard testing
            samples = [
                # Draft Valid (high confidence - needs review before submission)
                {"aju_number": "AJU-2025-1201", "reference_code": "CD-UCCCDEP1", "filename": "INV-2025-1201.pdf", "excel_filename": "AJU-2025-1201_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 175,000,000.00", "extraction_confidence": 0.92, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 256, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2025-1002", "reference_code": "CD-GT8GJ4H1", "filename": "INV-2025-1002.pdf", "excel_filename": "AJU-2025-1002_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 154,250,000.00", "extraction_confidence": 0.88, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 198, "created_at": now, "updated_at": now},

                # Approved (accepted by CEISA)
                {"aju_number": "AJU-2026-0901", "reference_code": "CD-TBNZQK7Y", "filename": "INV-2026-0901.pdf", "excel_filename": "AJU-2026-0901_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 190,500,000.00", "extraction_confidence": 0.98, "quality_score": "high", "status": ShipmentStatus.APPROVED, "file_size_kb": 312, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0315", "reference_code": "CD-QAWBPENN", "filename": "INV-2026-0315.pdf", "excel_filename": "AJU-2026-0315_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 59,680.00", "extraction_confidence": 0.85, "quality_score": "medium", "status": ShipmentStatus.APPROVED, "file_size_kb": 89, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0425", "reference_code": "CD-PRTVWXYZ", "filename": "INV-2026-0425.pdf", "excel_filename": "AJU-2026-0425_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 234,500,000.00", "extraction_confidence": 0.95, "quality_score": "high", "status": ShipmentStatus.APPROVED, "file_size_kb": 178, "created_at": now, "updated_at": now},

                # Sent (submitted to CEISA)
                {"aju_number": "AJU-2026-0618", "reference_code": "CD-SENT001", "filename": "INV-2026-0618.pdf", "excel_filename": "AJU-2026-0618_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 456,000,000.00", "extraction_confidence": 0.99, "quality_score": "high", "status": ShipmentStatus.SENT, "file_size_kb": 245, "created_at": now, "updated_at": now},

                # Draft Invalid (Needs Review)
                {"aju_number": "AJU-2026-0018", "reference_code": "CD-JQVSDCE", "filename": "INV-2026-0018.pdf", "excel_filename": "AJU-2026-0018_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 518,500.00", "extraction_confidence": 0.45, "quality_score": "low", "status": ShipmentStatus.DRAFT_INVALID, "file_size_kb": 156, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0319", "reference_code": "CD-KLSMNRTO", "filename": "INV-2026-0319.pdf", "excel_filename": "AJU-2026-0319_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 89,200,000.00", "extraction_confidence": 0.40, "quality_score": "low", "status": ShipmentStatus.DRAFT_INVALID, "file_size_kb": 201, "created_at": now, "updated_at": now},

                # Failed
                {"aju_number": "AJU-2026-0510", "reference_code": "CD-ABCFGH12", "filename": "INV-2026-0510.pdf", "excel_filename": "AJU-2026-0510_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 12,340,000.00", "extraction_confidence": 0.0, "quality_score": "low", "status": ShipmentStatus.FAILED, "file_size_kb": 45, "created_at": now, "updated_at": now},

                # More diverse entries
                {"aju_number": "AJU-2026-0701", "reference_code": "CD-DIVERSE1", "filename": "INV-2026-0701.pdf", "excel_filename": "AJU-2026-0701_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 78,500,000.00", "extraction_confidence": 0.78, "quality_score": "medium", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 112, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0702", "reference_code": "CD-DIVERSE2", "filename": "INV-2026-0702.pdf", "excel_filename": "AJU-2026-0702_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 320,000,000.00", "extraction_confidence": 0.91, "quality_score": "high", "status": ShipmentStatus.APPROVED, "file_size_kb": 189, "created_at": now, "updated_at": now},
            ]

            for data in samples:
                db.add(Shipment(**data))
            db.commit()
            logger.info(f"Auto-seeded {len(samples)} sample shipments.")

            # Seed activity log entries
            from datetime import timedelta

            activity_samples = [
                {"action": "OCR Process", "description": "Processed upload(s) with OCR and intelligent extraction.", "reference_code": None, "event_data": json.dumps({"engine": "HybridExtractor", "documents": ["CI", "PL", "BL"], "confidence": 98, "items_extracted": 12, "processing_time_seconds": 3.2, "quality_score": "high"}), "status": "success", "created_at": now},
                {"action": "OCR Process", "description": "Processed upload(s) with OCR and intelligent extraction.", "reference_code": None, "event_data": json.dumps({"engine": "HybridExtractor", "documents": ["CI", "PL"], "confidence": 92, "items_extracted": 8, "processing_time_seconds": 2.8, "quality_score": "high"}), "status": "success", "created_at": now - timedelta(minutes=5)},
                {"action": "Declaration Create", "description": "Created declaration CD-UCCCDEP1.", "entity_type": "shipment", "entity_id": 1, "reference_code": "CD-UCCCDEP1", "event_data": json.dumps({"aju_number": "AJU-2025-1201", "confidence": 92, "quality_score": "high", "documents": ["CI", "PL", "BL"]}), "status": "success", "created_at": now - timedelta(minutes=10)},
                {"action": "Declaration Create", "description": "Created declaration CD-GT8GJ4H1.", "entity_type": "shipment", "entity_id": 2, "reference_code": "CD-GT8GJ4H1", "event_data": json.dumps({"aju_number": "AJU-2025-1002", "confidence": 88, "quality_score": "high", "documents": ["CI", "PL"]}), "status": "success", "created_at": now - timedelta(minutes=15)},
                {"action": "Declaration Create", "description": "Created declaration CD-TBNZQK7Y.", "entity_type": "shipment", "entity_id": 3, "reference_code": "CD-TBNZQK7Y", "event_data": json.dumps({"aju_number": "AJU-2026-0901", "confidence": 98, "quality_score": "high", "documents": ["CI", "PL", "BL"]}), "status": "success", "created_at": now - timedelta(minutes=25)},
                {"action": "Declaration Send", "description": "Submitted declaration CD-TBNZQK7Y to CEISA simulation.", "entity_type": "shipment", "entity_id": 3, "reference_code": "CD-TBNZQK7Y", "event_data": json.dumps({"aju_number": "AJU-2026-0901", "confidence": 98}), "status": "sent", "created_at": now - timedelta(minutes=30)},
                {"action": "Declaration Approve", "description": "Declaration CD-TBNZQK7Y approved by CEISA.", "entity_type": "shipment", "entity_id": 3, "reference_code": "CD-TBNZQK7Y", "event_data": json.dumps({"aju_number": "AJU-2026-0901", "confidence": 98, "cesa_ref": "CESA-CCEPI"}), "status": "approved", "created_at": now - timedelta(minutes=31)},
                {"action": "Declaration Create", "description": "Created declaration CD-QAWBPENN.", "entity_type": "shipment", "entity_id": 4, "reference_code": "CD-QAWBPENN", "event_data": json.dumps({"aju_number": "AJU-2026-0315", "confidence": 85, "quality_score": "medium", "documents": ["CI"]}), "status": "success", "created_at": now - timedelta(hours=1)},
                {"action": "Declaration Create", "description": "Created declaration CD-PRTVWXYZ.", "entity_type": "shipment", "entity_id": 5, "reference_code": "CD-PRTVWXYZ", "event_data": json.dumps({"aju_number": "AJU-2026-0425", "confidence": 95, "quality_score": "high", "documents": ["CI", "PL"]}), "status": "success", "created_at": now - timedelta(hours=1, minutes=10)},
                {"action": "Declaration Send", "description": "Submitted declaration CD-PRTVWXYZ to CEISA simulation.", "entity_type": "shipment", "entity_id": 5, "reference_code": "CD-PRTVWXYZ", "event_data": json.dumps({"aju_number": "AJU-2026-0425", "confidence": 95}), "status": "sent", "created_at": now - timedelta(hours=1, minutes=15)},
                {"action": "Declaration Approve", "description": "Declaration CD-PRTVWXYZ approved by CEISA.", "entity_type": "shipment", "entity_id": 5, "reference_code": "CD-PRTVWXYZ", "event_data": json.dumps({"aju_number": "AJU-2026-0425", "confidence": 95}), "status": "approved", "created_at": now - timedelta(hours=1, minutes=16)},
                {"action": "OCR Process", "description": "Processed upload(s) with OCR and intelligent extraction.", "reference_code": None, "event_data": json.dumps({"engine": "HybridExtractor", "documents": ["CI", "PL", "BL"], "confidence": 45, "items_extracted": 5, "processing_time_seconds": 4.1, "quality_score": "low"}), "status": "failed", "created_at": now - timedelta(hours=2)},
                {"action": "Declaration Create", "description": "Created declaration CD-JQVSDCE.", "entity_type": "shipment", "entity_id": 7, "reference_code": "CD-JQVSDCE", "event_data": json.dumps({"aju_number": "AJU-2026-0018", "confidence": 45, "quality_score": "low", "documents": ["CI", "PL"]}), "status": "success", "created_at": now - timedelta(hours=2, minutes=5)},
                {"action": "Declaration Create", "description": "Created declaration CD-SENT001.", "entity_type": "shipment", "entity_id": 6, "reference_code": "CD-SENT001", "event_data": json.dumps({"aju_number": "AJU-2026-0618", "confidence": 99, "quality_score": "high", "documents": ["CI", "PL", "BL"]}), "status": "success", "created_at": now - timedelta(hours=3)},
                {"action": "Declaration Send", "description": "Submitted declaration CD-SENT001 to CEISA simulation.", "entity_type": "shipment", "entity_id": 6, "reference_code": "CD-SENT001", "event_data": json.dumps({"aju_number": "AJU-2026-0618", "confidence": 99}), "status": "sent", "created_at": now - timedelta(hours=3, minutes=5)},
                {"action": "Declaration Create", "description": "Created declaration CD-DIVERSE1.", "entity_type": "shipment", "entity_id": 10, "reference_code": "CD-DIVERSE1", "event_data": json.dumps({"aju_number": "AJU-2026-0701", "confidence": 78, "quality_score": "medium", "documents": ["CI"]}), "status": "success", "created_at": now - timedelta(hours=4)},
                {"action": "OCR Process", "description": "Processed upload(s) with OCR and intelligent extraction.", "reference_code": None, "event_data": json.dumps({"engine": "HybridExtractor", "documents": ["CI"], "confidence": 91, "items_extracted": 10, "processing_time_seconds": 2.1, "quality_score": "high"}), "status": "success", "created_at": now - timedelta(hours=5)},
                {"action": "Declaration Create", "description": "Created declaration CD-DIVERSE2.", "entity_type": "shipment", "entity_id": 11, "reference_code": "CD-DIVERSE2", "event_data": json.dumps({"aju_number": "AJU-2026-0702", "confidence": 91, "quality_score": "high", "documents": ["CI", "PL"]}), "status": "success", "created_at": now - timedelta(hours=5, minutes=10)},
                {"action": "Declaration Create", "description": "Created declaration CD-ABCFGH12.", "entity_type": "shipment", "entity_id": 9, "reference_code": "CD-ABCFGH12", "event_data": json.dumps({"aju_number": "AJU-2026-0510", "confidence": 0, "quality_score": "low", "documents": ["CI"]}), "status": "success", "created_at": now - timedelta(days=1)},
                {"action": "Declaration Reject", "description": "Declaration CD-ABCFGH12 rejected by CEISA.", "entity_type": "shipment", "entity_id": 9, "reference_code": "CD-ABCFGH12", "event_data": json.dumps({"aju_number": "AJU-2026-0510", "confidence": 0, "error": "Invalid HS Code"}), "status": "failed", "created_at": now - timedelta(days=1, hours=1)},
            ]

            for act_data in activity_samples:
                db.add(Activity(**act_data))
            db.commit()
            logger.info(f"Auto-seeded {len(activity_samples)} activity records.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to seed data: {e}")


# ── Supported file extensions ────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
MAX_FILE_SIZE_MB = 20


# ═══════════════════════════════════════════════════════════════════════════════
# API: Seed Database
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/seed", tags=["dev"])
async def seed_database():
    """Seed the database with sample shipment records."""
    db = SessionLocal()
    try:
        if db.query(Shipment).count() > 0:
            return {"message": "Database already has records, skipping seed."}

        samples = [
            # Draft Valid (high confidence)
            {"aju_number": "AJU-2025-1201", "reference_code": "CD-UCCCDEP1", "filename": "INV-2025-1201.pdf", "excel_filename": "AJU-2025-1201_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 175,000,000.00", "extraction_confidence": 0.92, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 256},
            {"aju_number": "AJU-2025-1002", "reference_code": "CD-GT8GJ4H1", "filename": "INV-2025-1002.pdf", "excel_filename": "AJU-2025-1002_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 154,250,000.00", "extraction_confidence": 0.88, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 198},
            # Approved (accepted by CEISA)
            {"aju_number": "AJU-2026-0901", "reference_code": "CD-TBNZQK7Y", "filename": "INV-2026-0901.pdf", "excel_filename": "AJU-2026-0901_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 190,500,000.00", "extraction_confidence": 0.98, "quality_score": "high", "status": ShipmentStatus.APPROVED, "file_size_kb": 312},
            {"aju_number": "AJU-2026-0315", "reference_code": "CD-QAWBPENN", "filename": "INV-2026-0315.pdf", "excel_filename": "AJU-2026-0315_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 59,680.00", "extraction_confidence": 0.85, "quality_score": "medium", "status": ShipmentStatus.APPROVED, "file_size_kb": 89},
            {"aju_number": "AJU-2026-0425", "reference_code": "CD-PRTVWXYZ", "filename": "INV-2026-0425.pdf", "excel_filename": "AJU-2026-0425_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 234,500,000.00", "extraction_confidence": 0.95, "quality_score": "high", "status": ShipmentStatus.APPROVED, "file_size_kb": 178},
            # Sent (submitted to CEISA)
            {"aju_number": "AJU-2026-0618", "reference_code": "CD-SENT001", "filename": "INV-2026-0618.pdf", "excel_filename": "AJU-2026-0618_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 456,000,000.00", "extraction_confidence": 0.99, "quality_score": "high", "status": ShipmentStatus.SENT, "file_size_kb": 245},
            # Draft Invalid (Needs Review)
            {"aju_number": "AJU-2026-0018", "reference_code": "CD-JQVSDCE", "filename": "INV-2026-0018.pdf", "excel_filename": "AJU-2026-0018_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 518,500.00", "extraction_confidence": 0.45, "quality_score": "low", "status": ShipmentStatus.DRAFT_INVALID, "file_size_kb": 156},
            {"aju_number": "AJU-2026-0319", "reference_code": "CD-KLSMNRTO", "filename": "INV-2026-0319.pdf", "excel_filename": "AJU-2026-0319_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 89,200,000.00", "extraction_confidence": 0.40, "quality_score": "low", "status": ShipmentStatus.DRAFT_INVALID, "file_size_kb": 201},
            # Failed
            {"aju_number": "AJU-2026-0510", "reference_code": "CD-ABCFGH12", "filename": "INV-2026-0510.pdf", "excel_filename": "AJU-2026-0510_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 12,340,000.00", "extraction_confidence": 0.0, "quality_score": "low", "status": ShipmentStatus.FAILED, "file_size_kb": 45},
            # More diverse
            {"aju_number": "AJU-2026-0701", "reference_code": "CD-DIVERSE1", "filename": "INV-2026-0701.pdf", "excel_filename": "AJU-2026-0701_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 78,500,000.00", "extraction_confidence": 0.78, "quality_score": "medium", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 112},
            {"aju_number": "AJU-2026-0702", "reference_code": "CD-DIVERSE2", "filename": "INV-2026-0702.pdf", "excel_filename": "AJU-2026-0702_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 320,000,000.00", "extraction_confidence": 0.91, "quality_score": "high", "status": ShipmentStatus.APPROVED, "file_size_kb": 189},
        ]

        for data in samples:
            db.add(Shipment(**data))
        db.commit()
        logger.info(f"Seeded {len(samples)} sample shipments.")
        return {"message": f"Seeded {len(samples)} sample shipments."}
    finally:
        db.close()


@app.post("/api/seed/activities", tags=["dev"])
async def seed_activities():
    """Seed the activities table with sample audit log records.
    Safe to call multiple times — always replaces existing activity records.
    """
    from datetime import timedelta
    db = SessionLocal()
    try:
        # Clear existing activities first so it's always fresh
        db.query(Activity).delete()
        db.commit()

        now = get_local_time()
        samples = [
            {"action": "OCR Process", "description": "Processed upload(s) with OCR and intelligent extraction.", "reference_code": None, "event_data": json.dumps({"engine": "HybridExtractor", "documents": ["CI", "PL", "BL"], "confidence": 98, "items_extracted": 12, "processing_time_seconds": 3.2, "quality_score": "high"}), "status": "success", "created_at": now},
            {"action": "OCR Process", "description": "Processed upload(s) with OCR and intelligent extraction.", "reference_code": None, "event_data": json.dumps({"engine": "HybridExtractor", "documents": ["CI", "PL"], "confidence": 92, "items_extracted": 8, "processing_time_seconds": 2.8, "quality_score": "high"}), "status": "success", "created_at": now - timedelta(minutes=5)},
            {"action": "Declaration Create", "description": "Created declaration CD-UCCCDEP1.", "entity_type": "shipment", "entity_id": 1, "reference_code": "CD-UCCCDEP1", "event_data": json.dumps({"aju_number": "AJU-2025-1201", "confidence": 92, "quality_score": "high", "documents": ["CI", "PL", "BL"]}), "status": "success", "created_at": now - timedelta(minutes=10)},
            {"action": "Declaration Create", "description": "Created declaration CD-GT8GJ4H1.", "entity_type": "shipment", "entity_id": 2, "reference_code": "CD-GT8GJ4H1", "event_data": json.dumps({"aju_number": "AJU-2025-1002", "confidence": 88, "quality_score": "high", "documents": ["CI", "PL"]}), "status": "success", "created_at": now - timedelta(minutes=15)},
            {"action": "Declaration Create", "description": "Created declaration CD-TBNZQK7Y.", "entity_type": "shipment", "entity_id": 3, "reference_code": "CD-TBNZQK7Y", "event_data": json.dumps({"aju_number": "AJU-2026-0901", "confidence": 98, "quality_score": "high", "documents": ["CI", "PL", "BL"]}), "status": "success", "created_at": now - timedelta(minutes=25)},
            {"action": "Declaration Send", "description": "Submitted declaration CD-TBNZQK7Y to CEISA simulation.", "entity_type": "shipment", "entity_id": 3, "reference_code": "CD-TBNZQK7Y", "event_data": json.dumps({"aju_number": "AJU-2026-0901", "confidence": 98}), "status": "sent", "created_at": now - timedelta(minutes=30)},
            {"action": "Declaration Approve", "description": "Declaration CD-TBNZQK7Y approved by CEISA.", "entity_type": "shipment", "entity_id": 3, "reference_code": "CD-TBNZQK7Y", "event_data": json.dumps({"aju_number": "AJU-2026-0901", "confidence": 98, "cesa_ref": "CESA-CCEPI"}), "status": "approved", "created_at": now - timedelta(minutes=31)},
            {"action": "Declaration Create", "description": "Created declaration CD-QAWBPENN.", "entity_type": "shipment", "entity_id": 4, "reference_code": "CD-QAWBPENN", "event_data": json.dumps({"aju_number": "AJU-2026-0315", "confidence": 85, "quality_score": "medium", "documents": ["CI"]}), "status": "success", "created_at": now - timedelta(hours=1)},
            {"action": "Declaration Create", "description": "Created declaration CD-PRTVWXYZ.", "entity_type": "shipment", "entity_id": 5, "reference_code": "CD-PRTVWXYZ", "event_data": json.dumps({"aju_number": "AJU-2026-0425", "confidence": 95, "quality_score": "high", "documents": ["CI", "PL"]}), "status": "success", "created_at": now - timedelta(hours=1, minutes=10)},
            {"action": "Declaration Send", "description": "Submitted declaration CD-PRTVWXYZ to CEISA simulation.", "entity_type": "shipment", "entity_id": 5, "reference_code": "CD-PRTVWXYZ", "event_data": json.dumps({"aju_number": "AJU-2026-0425", "confidence": 95}), "status": "sent", "created_at": now - timedelta(hours=1, minutes=15)},
            {"action": "Declaration Approve", "description": "Declaration CD-PRTVWXYZ approved by CEISA.", "entity_type": "shipment", "entity_id": 5, "reference_code": "CD-PRTVWXYZ", "event_data": json.dumps({"aju_number": "AJU-2026-0425", "confidence": 95}), "status": "approved", "created_at": now - timedelta(hours=1, minutes=16)},
            {"action": "OCR Process", "description": "Processed upload(s) with OCR and intelligent extraction.", "reference_code": None, "event_data": json.dumps({"engine": "HybridExtractor", "documents": ["CI", "PL", "BL"], "confidence": 45, "items_extracted": 5, "processing_time_seconds": 4.1, "quality_score": "low"}), "status": "failed", "created_at": now - timedelta(hours=2)},
            {"action": "Declaration Create", "description": "Created declaration CD-JQVSDCE.", "entity_type": "shipment", "entity_id": 7, "reference_code": "CD-JQVSDCE", "event_data": json.dumps({"aju_number": "AJU-2026-0018", "confidence": 45, "quality_score": "low", "documents": ["CI", "PL"]}), "status": "success", "created_at": now - timedelta(hours=2, minutes=5)},
            {"action": "Declaration Create", "description": "Created declaration CD-SENT001.", "entity_type": "shipment", "entity_id": 6, "reference_code": "CD-SENT001", "event_data": json.dumps({"aju_number": "AJU-2026-0618", "confidence": 99, "quality_score": "high", "documents": ["CI", "PL", "BL"]}), "status": "success", "created_at": now - timedelta(hours=3)},
            {"action": "Declaration Send", "description": "Submitted declaration CD-SENT001 to CEISA simulation.", "entity_type": "shipment", "entity_id": 6, "reference_code": "CD-SENT001", "event_data": json.dumps({"aju_number": "AJU-2026-0618", "confidence": 99}), "status": "sent", "created_at": now - timedelta(hours=3, minutes=5)},
            {"action": "Declaration Create", "description": "Created declaration CD-DIVERSE1.", "entity_type": "shipment", "entity_id": 10, "reference_code": "CD-DIVERSE1", "event_data": json.dumps({"aju_number": "AJU-2026-0701", "confidence": 78, "quality_score": "medium", "documents": ["CI"]}), "status": "success", "created_at": now - timedelta(hours=4)},
            {"action": "OCR Process", "description": "Processed upload(s) with OCR and intelligent extraction.", "reference_code": None, "event_data": json.dumps({"engine": "HybridExtractor", "documents": ["CI"], "confidence": 91, "items_extracted": 10, "processing_time_seconds": 2.1, "quality_score": "high"}), "status": "success", "created_at": now - timedelta(hours=5)},
            {"action": "Declaration Create", "description": "Created declaration CD-DIVERSE2.", "entity_type": "shipment", "entity_id": 11, "reference_code": "CD-DIVERSE2", "event_data": json.dumps({"aju_number": "AJU-2026-0702", "confidence": 91, "quality_score": "high", "documents": ["CI", "PL"]}), "status": "success", "created_at": now - timedelta(hours=5, minutes=10)},
            {"action": "Declaration Create", "description": "Created declaration CD-ABCFGH12.", "entity_type": "shipment", "entity_id": 9, "reference_code": "CD-ABCFGH12", "event_data": json.dumps({"aju_number": "AJU-2026-0510", "confidence": 0, "quality_score": "low", "documents": ["CI"]}), "status": "success", "created_at": now - timedelta(days=1)},
            {"action": "Declaration Reject", "description": "Declaration CD-ABCFGH12 rejected by CEISA.", "entity_type": "shipment", "entity_id": 9, "reference_code": "CD-ABCFGH12", "event_data": json.dumps({"aju_number": "AJU-2026-0510", "confidence": 0, "error": "Invalid HS Code"}), "status": "failed", "created_at": now - timedelta(days=1, hours=1)},
        ]

        for data in samples:
            db.add(Activity(**data))
        db.commit()
        logger.info(f"Seeded {len(samples)} activity records.")
        return {"message": f"Seeded {len(samples)} activity records."}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# API: Shipments CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/shipments", tags=["shipments"])
async def list_shipments(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all shipments with optional filtering and pagination."""
    query = select(Shipment)
    count_query = select(func.count(Shipment.id))

    if status:
        # Filter by category: Draft, Approved, or Failed
        query = query.where(Shipment.status.like(f"{status}%"))
        count_query = count_query.where(Shipment.status.like(f"{status}%"))

    if search:
        search_filter = or_(
            Shipment.reference_code.ilike(f"%{search}%"),
            Shipment.aju_number.ilike(f"%{search}%"),
            Shipment.filename.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Shipment.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    shipments = result.scalars().all()

    items = []
    for s in shipments:
        items.append({
            "id": s.id,
            "aju_number": s.aju_number,
            "reference_code": s.reference_code,
            "filename": s.filename,
            "excel_filename": s.excel_filename,
            "documents_processed": json.loads(s.documents_processed) if s.documents_processed else [],
            "total_amount": s.total_amount,
            "extraction_confidence": round(s.extraction_confidence * 100) if s.extraction_confidence else 0,
            "quality_score": s.quality_score,
            "status": s.status.value if s.status else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })

    return {"total": total, "items": items}


@app.get("/api/shipments/{shipment_id}", tags=["shipments"])
async def get_shipment(shipment_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single shipment by ID."""
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    return {
        "id": s.id,
        "aju_number": s.aju_number,
        "reference_code": s.reference_code,
        "filename": s.filename,
        "excel_filename": s.excel_filename,
        "documents_processed": json.loads(s.documents_processed) if s.documents_processed else [],
        "total_amount": s.total_amount,
        "extraction_confidence": round(s.extraction_confidence * 100) if s.extraction_confidence else 0,
        "quality_score": s.quality_score,
        "status": s.status.value if s.status else None,
        "header_fields": json.loads(s.header_fields) if s.header_fields else {},
        "line_items": json.loads(s.line_items) if s.line_items else [],
        "quality_report": json.loads(s.quality_report) if s.quality_report else {},
        "excel_base64": s.excel_data,
        "file_size_kb": s.file_size_kb,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@app.get("/api/shipments/{shipment_id}/download", tags=["shipments"])
async def download_shipment_excel(shipment_id: int, db: AsyncSession = Depends(get_db)):
    """Download the Excel file for a shipment."""
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    if not s.excel_data:
        raise HTTPException(status_code=404, detail="Excel file not found")

    excel_bytes = base64.b64decode(s.excel_data)
    temp_path = Path(tempfile.gettempdir()) / f"download_{uuid.uuid4().hex}.xlsx"
    with open(temp_path, "wb") as f:
        f.write(excel_bytes)

    def cleanup():
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass

    background_tasks = BackgroundTasks()
    background_tasks.add_task(cleanup)

    return FileResponse(
        path=str(temp_path),
        filename=s.excel_filename or "extracted.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=background_tasks,
    )


@app.delete("/api/shipments/{shipment_id}", tags=["shipments"])
async def delete_shipment(shipment_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a shipment by ID."""
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    ref_code = s.reference_code
    await db.execute(delete(Shipment).where(Shipment.id == shipment_id))
    await db.commit()
    logger.info(f"Deleted shipment {shipment_id}: {ref_code}")

    await create_activity(
        db=db,
        action=ActivityAction.DECLARATION_DELETE,
        description=f"Deleted declaration {ref_code}.",
        entity_type="shipment",
        entity_id=shipment_id,
        reference_code=ref_code,
        metadata={"shipment_id": shipment_id},
        status="success",
    )

    return {"message": f"Shipment {shipment_id} deleted", "reference_code": ref_code}


@app.post("/api/shipments/{shipment_id}/send", tags=["shipments"])
async def send_shipment(shipment_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a shipment as sent."""
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    s.status = ShipmentStatus.SENT
    s.updated_at = get_local_time()
    await db.commit()
    await db.refresh(s)
    logger.info(f"Shipment {shipment_id} marked as SENT")

    await create_activity(
        db=db,
        action=ActivityAction.DECLARATION_SEND,
        description=f"Submitted declaration {s.reference_code} to CEISA simulation.",
        entity_type="shipment",
        entity_id=s.id,
        reference_code=s.reference_code,
        metadata={
            "aju_number": s.aju_number,
            "confidence": round(s.extraction_confidence * 100) if s.extraction_confidence else 0,
        },
        status="sent",
    )

    return {"message": "Shipment marked as sent", "id": s.id, "status": s.status.value}


@app.patch("/api/shipments/{shipment_id}/status", tags=["shipments"])
async def update_shipment_status(
    shipment_id: int,
    status: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Update the status of a shipment."""
    try:
        new_status = ShipmentStatus(status)
    except ValueError:
        valid = [e.value for e in ShipmentStatus]
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {valid}")

    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    s.status = new_status
    s.updated_at = get_local_time()
    await db.commit()
    await db.refresh(s)

    act_action = ActivityAction.DECLARATION_UPDATE
    act_status = "success"
    if new_status == ShipmentStatus.APPROVED:
        act_action = ActivityAction.DECLARATION_APPROVE
        act_status = "approved"
        act_desc = f"Declaration {s.reference_code} approved by CEISA."
    elif new_status == ShipmentStatus.FAILED:
        act_action = ActivityAction.DECLARATION_REJECT
        act_status = "failed"
        act_desc = f"Declaration {s.reference_code} rejected by CEISA."
    else:
        act_desc = f"Updated declaration {s.reference_code} status to {new_status.value}."

    await create_activity(
        db=db,
        action=act_action,
        description=act_desc,
        entity_type="shipment",
        entity_id=s.id,
        reference_code=s.reference_code,
        metadata={"old_status": None, "new_status": new_status.value},
        status=act_status,
    )

    return {"message": "Status updated", "id": s.id, "status": s.status.value}


# ═══════════════════════════════════════════════════════════════════════════════
# API: Save Extraction Result to Database
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/shipments", tags=["shipments"])
async def create_shipment(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Save an extraction result to the database.
    Called when user clicks 'Save to Declarations'.
    """
    try:
        body = await request.json()

        # Generate unique reference code
        reference_code = generate_reference_code()
        attempts = 0
        while attempts < 5:
            existing_check = await db.execute(
                select(Shipment).where(Shipment.reference_code == reference_code)
            )
            if not existing_check.scalar_one_or_none():
                break
            reference_code = generate_reference_code()
            attempts += 1

        # Calculate status based on confidence (server-side validation)
        # Draft Valid: confidence > 50%, Draft Invalid: confidence <= 50%
        extraction_confidence = body.get("extraction_confidence", 0) / 100
        if extraction_confidence > 0.50:
            status = ShipmentStatus.DRAFT_VALID
        else:
            status = ShipmentStatus.DRAFT_INVALID

        shipment = Shipment(
            aju_number=body.get("aju_number"),
            reference_code=reference_code,
            filename=body.get("filename", ""),
            excel_filename=body.get("excel_filename"),
            documents_processed=json.dumps(body.get("documents_processed", [])),
            total_amount=body.get("total_amount"),
            extraction_confidence=extraction_confidence,
            quality_score=body.get("quality_score", "medium"),
            status=status,
            header_fields=json.dumps(body.get("header_fields", {})),
            line_items=json.dumps(body.get("line_items", [])),
            quality_report=json.dumps(body.get("quality_report", {})),
            excel_data=body.get("excel_base64"),
            file_size_kb=body.get("file_size_kb", 0),
            created_at=get_local_time(),
            updated_at=get_local_time(),
        )

        db.add(shipment)
        await db.commit()
        await db.refresh(shipment)

        logger.info(
            f"Shipment saved: id={shipment.id}, ref={shipment.reference_code}, "
            f"status={shipment.status.value}"
        )

        await create_activity(
            db=db,
            action=ActivityAction.DECLARATION_CREATE,
            description=f"Created declaration {shipment.reference_code}.",
            entity_type="shipment",
            entity_id=shipment.id,
            reference_code=shipment.reference_code,
            metadata={
                "aju_number": body.get("aju_number"),
                "confidence": body.get("extraction_confidence"),
                "quality_score": body.get("quality_score"),
                "documents": body.get("documents_processed", []),
            },
            status="success",
        )

        return JSONResponse(content={
            "success": True,
            "shipment_id": shipment.id,
            "reference_code": shipment.reference_code,
        })

    except Exception as e:
        logger.error(f"Failed to save shipment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# API: OCR Extraction (extract only, no save)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/extract")
async def extract_documents(request: Request):
    """
    Run the OCR + extraction pipeline on uploaded CI, PL, and BL documents.
    Returns extraction results and Excel file WITHOUT saving to database.
    Use /api/shipments to save the result separately.
    """
    if not ENGINE_AVAILABLE or HybridExtractor is None:
        raise HTTPException(
            status_code=503,
            detail="OCR extraction engine not available.",
        )

    form = await request.form()

    def get_file(key: str) -> tuple[str, Optional[UploadFile]]:
        for k in [key.upper(), key.lower()]:
            val = form.get(k)
            if val and hasattr(val, "filename") and val.filename:
                return k, val
        return None, None

    ci_key, ci_file = get_file("CI")
    pl_key, pl_file = get_file("PL")
    bl_key, bl_file = get_file("BL")

    uploaded = {}
    for doc_type, file in [("CI", ci_file), ("PL", pl_file), ("BL", bl_file)]:
        if file and file.filename:
            uploaded[doc_type] = file

    shipment_id_raw = form.get("shipment_id")
    shipment_id = shipment_id_raw if shipment_id_raw else None

    if not uploaded:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least one document (CI, PL, or BL).",
        )

    for doc_type, file in uploaded.items():
        suffix = Path(file.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{suffix}' for {doc_type}.",
            )

    logger.info(f"Received extraction request: {list(uploaded.keys())}")

    work_id = uuid.uuid4().hex[:12]
    work_dir = Path(tempfile.gettempdir()) / f"ocr_web_{work_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    excel_path: Optional[Path] = None

    def _cleanup():
        if work_dir.exists():
            try:
                shutil.rmtree(work_dir)
                logger.info(f"Cleaned up working directory: {work_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up {work_dir}: {e}")

    try:
        file_paths: dict[str, str] = {}

        for doc_type, upload_file in uploaded.items():
            filename = upload_file.filename
            file_path = work_dir / filename
            content = await upload_file.read()
            size_mb = len(content) / (1024 * 1024)
            if size_mb > MAX_FILE_SIZE_MB:
                raise HTTPException(
                    status_code=413,
                    detail=f"File '{filename}' is too large ({size_mb:.1f} MB). Max: {MAX_FILE_SIZE_MB} MB.",
                )
            with open(file_path, "wb") as f:
                f.write(content)
            file_paths[doc_type] = str(file_path)
            logger.info(f"Saved {doc_type}: {filename} ({size_mb:.1f} MB)")

        logger.info("Starting extraction pipeline...")
        t0 = __import__("time").time()

        extractor = HybridExtractor(
            use_gpu=False,
            layout_confidence_threshold=0.05,
            use_vision_fallback=False,
        )

        result = extractor.extract_from_files(
            file_paths=file_paths,
            shipment_id=shipment_id if shipment_id else f"WEB_{work_id}",
        )

        elapsed = __import__("time").time() - t0
        conf = result.entities.extraction_confidence
        logger.info(
            f"Extraction complete in {elapsed:.1f}s - items={len(result.entities.items)}, confidence={conf:.2f}"
        )

        final_shipment_id = shipment_id if shipment_id else f"WEB_{work_id}"
        excel_filename = f"{final_shipment_id}_ceisa.xlsx"
        excel_path = work_dir / excel_filename

        exporter = ExcelExporter()
        exporter.export(
            entities=result.entities,
            shipment_id=final_shipment_id,
            output_path=excel_path,
        )

        if not excel_path.exists():
            raise HTTPException(
                status_code=500,
                detail="Engine did not produce an output Excel file.",
            )

        with open(excel_path, "rb") as f:
            excel_bytes = f.read()
        excel_base64 = base64.b64encode(excel_bytes).decode("utf-8")
        file_size_kb = len(excel_bytes) // 1024

        if conf >= 0.80:
            quality_score = "high"
        elif conf >= 0.60:
            quality_score = "medium"
        else:
            quality_score = "low"

        # Status based on confidence:
        # - Draft Valid: OCR confidence > 50%
        # - Draft Invalid: OCR confidence < 50%
        # (Sent, Failed, Approved are set manually after CEISA interaction)
        if conf >= 0.50:
            status = ShipmentStatus.DRAFT_VALID
        else:
            status = ShipmentStatus.DRAFT_INVALID

        header_fields = {}
        header_field_names = {
            'invoice_number': 'Invoice Number',
            'invoice_date': 'Invoice Date',
            'buyer_name': 'Buyer Name',
            'seller_name': 'Seller Name',
            'port_of_loading': 'Port of Loading',
            'port_of_discharge': 'Port of Discharge',
            'country_of_origin': 'Country of Origin',
            'currency': 'Currency',
            'total_amount': 'Total Amount',
            'total_quantity': 'Total Quantity',
            'total_gross_weight': 'Total Gross Weight',
            'total_net_weight': 'Total Net Weight',
        }

        for field_key, field_label in header_field_names.items():
            value = getattr(result.entities, field_key, None)
            if value and value != '':
                header_fields[field_label] = {
                    'value': str(value)[:80],
                    'confidence': round(conf * 100),
                }

        line_items = []
        for item in result.entities.items[:20]:
            item_data = {
                'description': getattr(item, 'description', None),
                'hs_code': getattr(item, 'hs_code', None),
                'quantity': getattr(item, 'quantity', None),
                'unit': getattr(item, 'unit', None),
                'unit_price': getattr(item, 'unit_price', None),
                'amount': getattr(item, 'amount', None),
                'confidence': round(getattr(item, 'confidence', 0) * 100),
            }
            if item_data['description']:
                line_items.append(item_data)

        quality_report = {}
        if hasattr(result.entities, 'get_quality_report'):
            quality_report = result.entities.get_quality_report()

        total_amount = getattr(result.entities, 'total_amount', None)

        # Return extraction results without saving to database
        # User must click "Save to Declarations" to persist

        _status = "success" if conf >= 0.50 else "failed"
        _log_meta = {
            "engine": "HybridExtractor",
            "documents": list(file_paths.keys()),
            "confidence": round(conf * 100),
            "items_extracted": len(result.entities.items),
            "processing_time_seconds": round(elapsed, 1),
            "quality_score": quality_score,
            "aju_number": shipment_id,
        }

        # Log activity asynchronously (fire-and-forget via background task)
        try:
            bg_db = AsyncSessionLocal()
            await create_activity(
                db=bg_db,
                action=ActivityAction.OCR_PROCESS,
                description=f"Processed upload(s) with OCR and intelligent extraction.",
                entity_type="shipment",
                entity_id=None,
                reference_code=None,
                metadata=_log_meta,
                status=_status,
            )
            await bg_db.close()
        except Exception as act_err:
            logger.warning(f"Failed to log activity: {act_err}")

        return JSONResponse(content={
            "success": True,
            "filename": excel_filename,
            "confidence": round(conf * 100),
            "items_count": len(result.entities.items),
            "documents_processed": list(file_paths.keys()),
            "processing_time_seconds": round(elapsed, 1),
            "extraction_confidence": round(conf * 100),
            "quality_score": quality_score,
            "status": status.value,
            "excel_base64": excel_base64,
            "header_fields": header_fields,
            "line_items": line_items,
            "quality_report": quality_report,
            "aju_number": shipment_id,
            "total_amount": str(total_amount) if total_amount else None,
        })

    except HTTPException:
        _cleanup()
        raise
    except Exception as exc:
        _cleanup()
        try:
            bg_db = AsyncSessionLocal()
            await create_activity(
                db=bg_db,
                action=ActivityAction.OCR_PROCESS,
                description="OCR processing failed.",
                entity_type="shipment",
                metadata={"error": str(exc)},
                status="failed",
            )
            await bg_db.close()
        except Exception:
            pass
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# API: Activities / Audit Log
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/activities", tags=["activities"])
async def list_activities(
    action: Optional[str] = Query(None, description="Filter by action type"),
    search: Optional[str] = Query(None, description="Search in description or reference_code"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List activities with pagination, filtering, and search."""
    query = select(Activity).order_by(Activity.created_at.desc())

    if action:
        query = query.where(Activity.action == action)
    if status:
        query = query.where(Activity.status == status)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Activity.description.ilike(search_term),
                Activity.reference_code.ilike(search_term),
            )
        )

    # Total count
    count_query = select(func.count(Activity.id))
    if action:
        count_query = count_query.where(Activity.action == action)
    if status:
        count_query = count_query.where(Activity.status == status)
    if search:
        search_term = f"%{search}%"
        count_query = count_query.where(
            or_(
                Activity.description.ilike(search_term),
                Activity.reference_code.ilike(search_term),
            )
        )
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginated results
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()

    def parse_meta(act: Activity):
        if act.event_data:
            try:
                return json.loads(act.event_data)
            except Exception:
                return {}
        return {}

    activities = [
        {
            "id": act.id,
            "action": act.action,
            "description": act.description,
            "entity_type": act.entity_type,
            "entity_id": act.entity_id,
            "reference_code": act.reference_code,
            "metadata": parse_meta(act),
            "status": act.status,
            "created_at": act.created_at.isoformat() if act.created_at else None,
        }
        for act in items
    ]

    return {
        "items": activities,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@app.get("/api/activities/stats", tags=["activities"])
async def get_activity_stats(db: AsyncSession = Depends(get_db)):
    """Get summary statistics for the activity log."""
    total_result = await db.execute(select(func.count(Activity.id)))
    total_events = total_result.scalar() or 0

    ocr_result = await db.execute(
        select(func.count(Activity.id)).where(Activity.action == ActivityAction.OCR_PROCESS.value)
    )
    ocr_runs = ocr_result.scalar() or 0

    submission_actions = [
        ActivityAction.DECLARATION_SEND.value,
        ActivityAction.DECLARATION_APPROVE.value,
    ]
    submission_result = await db.execute(
        select(func.count(Activity.id)).where(Activity.action.in_(submission_actions))
    )
    ceisa_submissions = submission_result.scalar() or 0

    last_result = await db.execute(
        select(Activity.created_at).order_by(Activity.created_at.desc()).limit(1)
    )
    last_activity_row = last_result.scalar_one_or_none()
    last_activity = last_activity_row.isoformat() if last_activity_row else None

    return {
        "total_events": total_events,
        "ocr_runs": ocr_runs,
        "ceisa_submissions": ceisa_submissions,
        "last_activity": last_activity,
    }


@app.get("/api/dashboard", tags=["dashboard"])
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """
    Get dashboard statistics from database.

    Status System:
    - Draft Valid: OCR result with confidence > 50%
    - Draft Invalid: OCR result with confidence < 50% (cannot be sent)
    - Sent: Shipment sent to CEISA system
    - Failed: Shipment rejected by CEISA system
    - Approved: Draft Valid that was accepted by CEISA system

    Dashboard Metrics:
    - CEISA Ready: Draft Valid + Sent count (ready for CEISA)
    - Needs Review: Draft Invalid count (cannot be sent)
    - CEISA Approved: Approved count (accepted by CEISA)
    """
    try:
        # Count total shipments
        total_result = await db.execute(select(func.count(Shipment.id)))
        total_shipments = total_result.scalar() or 0

        # Count by status
        draft_valid_result = await db.execute(
            select(func.count(Shipment.id)).where(Shipment.status == ShipmentStatus.DRAFT_VALID)
        )
        draft_valid = draft_valid_result.scalar() or 0

        draft_invalid_result = await db.execute(
            select(func.count(Shipment.id)).where(Shipment.status == ShipmentStatus.DRAFT_INVALID)
        )
        draft_invalid = draft_invalid_result.scalar() or 0

        sent_result = await db.execute(
            select(func.count(Shipment.id)).where(Shipment.status == ShipmentStatus.SENT)
        )
        sent = sent_result.scalar() or 0

        failed_result = await db.execute(
            select(func.count(Shipment.id)).where(Shipment.status == ShipmentStatus.FAILED)
        )
        failed = failed_result.scalar() or 0

        approved_result = await db.execute(
            select(func.count(Shipment.id)).where(Shipment.status == ShipmentStatus.APPROVED)
        )
        approved = approved_result.scalar() or 0

        # Calculate summary stats based on new status system
        saved_records = total_shipments
        ceisa_ready = draft_valid + sent  # Draft Valid + Sent = ready for CEISA
        needs_review = draft_invalid  # Draft Invalid = needs review (cannot be sent)
        ceisa_approved = approved  # Approved = accepted by CEISA

        # Get all shipments for document type analysis and confidence calculation
        all_shipments_result = await db.execute(select(Shipment))
        all_shipments = all_shipments_result.scalars().all()

        # Count document types
        ci_count = 0
        pl_count = 0
        bl_count = 0
        total_confidence = 0.0
        confidence_count = 0

        for s in all_shipments:
            docs = json.loads(s.documents_processed) if s.documents_processed else []
            if "CI" in docs:
                ci_count += 1
            if "PL" in docs:
                pl_count += 1
            if "BL" in docs:
                bl_count += 1
            if s.extraction_confidence is not None and s.extraction_confidence > 0:
                total_confidence += s.extraction_confidence
                confidence_count += 1

        avg_confidence = round((total_confidence / confidence_count * 100), 1) if confidence_count > 0 else 0

        # Activity volume = total shipments created
        activity_volume = total_shipments

        return {
            "success": True,
            "summary": {
                "saved_records": saved_records,
                "ceisa_ready": ceisa_ready,
                "needs_review": needs_review,
                "ceisa_approved": ceisa_approved,
            },
            "operational": {
                "ci_count": ci_count,
                "pl_count": pl_count,
                "bl_count": bl_count,
                "ceisa_ready_count": ceisa_ready,
                "avg_confidence": avg_confidence,
                "activity_volume": activity_volume,
            },
            "status_breakdown": {
                "draft_valid": draft_valid,
                "draft_invalid": draft_invalid,
                "sent": sent,
                "failed": failed,
                "approved": approved,
            }
        }
    except Exception as e:
        logger.error(f"Failed to get dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def serve_index():
    """Serve the main page (Dashboard)."""
    index_path = Path(__file__).parent / "dashboard.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="dashboard.html not found")


@app.get("/dashboard")
async def serve_dashboard():
    """Serve the dashboard page."""
    dash_path = Path(__file__).parent / "dashboard.html"
    if dash_path.exists():
        return FileResponse(str(dash_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="dashboard.html not found")


@app.get("/smart-upload")
async def serve_smart_upload():
    """Serve the Smart Upload page."""
    upload_path = Path(__file__).parent / "smart_upload.html"
    if upload_path.exists():
        return FileResponse(str(upload_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="smart_upload.html not found")


@app.get("/declarations")
async def serve_declarations():
    """Serve the declarations page."""
    decl_path = Path(__file__).parent / "declarations.html"
    if decl_path.exists():
        return FileResponse(str(decl_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="declarations.html not found")


@app.get("/activity")
async def serve_activity():
    """Serve the activity / audit log page."""
    activity_path = Path(__file__).parent / "activity.html"
    if activity_path.exists():
        return FileResponse(str(activity_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="activity.html not found")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "engine_available": ENGINE_AVAILABLE,
        "engine_dir": str(ENGINE_DIR)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
