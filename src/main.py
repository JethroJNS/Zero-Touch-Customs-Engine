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
class ShipmentStatus(str, enum.Enum):
    DRAFT_VALID = "Draft Valid"
    DRAFT_INVALID = "Draft Invalid"
    APPROVED_VALID = "Approved Valid"
    APPROVED_INVALID = "Approved Invalid"
    SENT = "Sent"
    FAILED = "Failed"


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
            samples = [
                {"aju_number": "AJU-2025-1201", "reference_code": "CD-UCCCDEP1", "filename": "INV-2025-1201.pdf", "excel_filename": "AJU-2025-1201_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 175,000,000.00", "extraction_confidence": 1.0, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 256, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2025-1002", "reference_code": "CD-GT8GJ4H1", "filename": "INV-2025-1002.pdf", "excel_filename": "AJU-2025-1002_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 154,250,000.00", "extraction_confidence": 0.95, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 198, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0901", "reference_code": "CD-TBNZQK7Y", "filename": "INV-2026-0901.pdf", "excel_filename": "AJU-2026-0901_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 190,500,000.00", "extraction_confidence": 0.98, "quality_score": "high", "status": ShipmentStatus.APPROVED_VALID, "file_size_kb": 312, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0315", "reference_code": "CD-QAWBPENN", "filename": "INV-2026-0315.pdf", "excel_filename": "AJU-2026-0315_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 59,680.00", "extraction_confidence": 0.85, "quality_score": "medium", "status": ShipmentStatus.APPROVED_VALID, "file_size_kb": 89, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0018", "reference_code": "CD-JQVSDCE", "filename": "INV-2026-0018.pdf", "excel_filename": "AJU-2026-0018_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 518,500.00", "extraction_confidence": 0.45, "quality_score": "low", "status": ShipmentStatus.DRAFT_INVALID, "file_size_kb": 156, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0319", "reference_code": "CD-KLSMNRTO", "filename": "INV-2026-0319.pdf", "excel_filename": "AJU-2026-0319_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 89,200,000.00", "extraction_confidence": 0.55, "quality_score": "low", "status": ShipmentStatus.DRAFT_INVALID, "file_size_kb": 201, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0425", "reference_code": "CD-PRTVWXYZ", "filename": "INV-2026-0425.pdf", "excel_filename": "AJU-2026-0425_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 234,500,000.00", "extraction_confidence": 0.92, "quality_score": "high", "status": ShipmentStatus.APPROVED_VALID, "file_size_kb": 178, "created_at": now, "updated_at": now},
                {"aju_number": "AJU-2026-0510", "reference_code": "CD-ABCFGH12", "filename": "INV-2026-0510.pdf", "excel_filename": "AJU-2026-0510_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 12,340,000.00", "extraction_confidence": 0.0, "quality_score": "low", "status": ShipmentStatus.FAILED, "file_size_kb": 45, "created_at": now, "updated_at": now},
            ]

            for data in samples:
                db.add(Shipment(**data))
            db.commit()
            logger.info(f"Auto-seeded {len(samples)} sample shipments.")
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
            {"aju_number": "AJU-2025-1201", "reference_code": "CD-UCCCDEP1", "filename": "INV-2025-1201.pdf", "excel_filename": "AJU-2025-1201_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 175,000,000.00", "extraction_confidence": 1.0, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 256},
            {"aju_number": "AJU-2025-1002", "reference_code": "CD-GT8GJ4H1", "filename": "INV-2025-1002.pdf", "excel_filename": "AJU-2025-1002_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 154,250,000.00", "extraction_confidence": 1.0, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 198},
            {"aju_number": "AJU-2026-0901", "reference_code": "CD-TBNZQK7Y", "filename": "INV-2026-0901.pdf", "excel_filename": "AJU-2026-0901_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 190,500,000.00", "extraction_confidence": 0.98, "quality_score": "high", "status": ShipmentStatus.APPROVED_VALID, "file_size_kb": 312},
            {"aju_number": "AJU-2026-0315", "reference_code": "CD-QAWBPENN", "filename": "INV-2026-0315.pdf", "excel_filename": "AJU-2026-0315_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 59,680.00", "extraction_confidence": 0.85, "quality_score": "medium", "status": ShipmentStatus.APPROVED_VALID, "file_size_kb": 89},
            {"aju_number": "AJU-2026-0018", "reference_code": "CD-JQVSDCE", "filename": "INV-2026-0018.pdf", "excel_filename": "AJU-2026-0018_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 518,500.00", "extraction_confidence": 0.45, "quality_score": "low", "status": ShipmentStatus.DRAFT_INVALID, "file_size_kb": 156},
        ]

        for data in samples:
            db.add(Shipment(**data))
        db.commit()
        logger.info(f"Seeded {len(samples)} sample shipments.")
        return {"message": f"Seeded {len(samples)} sample shipments."}
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

        shipment = Shipment(
            aju_number=body.get("aju_number"),
            reference_code=reference_code,
            filename=body.get("filename", ""),
            excel_filename=body.get("excel_filename"),
            documents_processed=json.dumps(body.get("documents_processed", [])),
            total_amount=body.get("total_amount"),
            extraction_confidence=body.get("extraction_confidence", 0) / 100,
            quality_score=body.get("quality_score", "medium"),
            status=ShipmentStatus(body.get("status", "Draft Valid")),
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

        invoice_number = getattr(result.entities, 'invoice_number', None)
        if conf >= 0.80 and invoice_number:
            status = ShipmentStatus.APPROVED_VALID
        elif conf >= 0.50:
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
    except Exception:
        _cleanup()
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def serve_index():
    """Serve the main page."""
    index_path = Path(__file__).parent / "smart_upload.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="smart_upload.html not found")


@app.get("/declarations")
async def serve_declarations():
    """Serve the declarations page."""
    decl_path = Path(__file__).parent / "declarations.html"
    if decl_path.exists():
        return FileResponse(str(decl_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="declarations.html not found")


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
