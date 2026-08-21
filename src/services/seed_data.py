"""
Seed data service for development.
Provides sample shipment and activity records.
"""
import json
import logging
from datetime import timedelta
from sqlalchemy.orm import Session
from models.shipment import Shipment, ShipmentStatus, get_local_time
from models.activity import Activity, ActivityAction

logger = logging.getLogger("ocr_web")


def _generate_reference_code() -> str:
    return f"CD-{uuid.uuid4().hex[:8].upper()}"


def seed_shipments(db: Session, clear_existing: bool = False) -> int:
    """Seed the database with sample shipment records."""
    if clear_existing:
        db.query(Shipment).delete()
        db.commit()

    if db.query(Shipment).count() > 0:
        return 0

    now = get_local_time()
    samples = [
        {"aju_number": "AJU-2025-1201", "reference_code": "CD-UCCCDEP1", "filename": "INV-2025-1201.pdf", "excel_filename": "AJU-2025-1201_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 175,000,000.00", "extraction_confidence": 0.92, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 256},
        {"aju_number": "AJU-2025-1002", "reference_code": "CD-GT8GJ4H1", "filename": "INV-2025-1002.pdf", "excel_filename": "AJU-2025-1002_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 154,250,000.00", "extraction_confidence": 0.88, "quality_score": "high", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 198},
        {"aju_number": "AJU-2026-0901", "reference_code": "CD-TBNZQK7Y", "filename": "INV-2026-0901.pdf", "excel_filename": "AJU-2026-0901_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 190,500,000.00", "extraction_confidence": 0.98, "quality_score": "high", "status": ShipmentStatus.APPROVED, "file_size_kb": 312},
        {"aju_number": "AJU-2026-0315", "reference_code": "CD-QAWBPENN", "filename": "INV-2026-0315.pdf", "excel_filename": "AJU-2026-0315_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 59,680.00", "extraction_confidence": 0.85, "quality_score": "medium", "status": ShipmentStatus.APPROVED, "file_size_kb": 89},
        {"aju_number": "AJU-2026-0425", "reference_code": "CD-PRTVWXYZ", "filename": "INV-2026-0425.pdf", "excel_filename": "AJU-2026-0425_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 234,500,000.00", "extraction_confidence": 0.95, "quality_score": "high", "status": ShipmentStatus.APPROVED, "file_size_kb": 178},
        {"aju_number": "AJU-2026-0618", "reference_code": "CD-SENT001", "filename": "INV-2026-0618.pdf", "excel_filename": "AJU-2026-0618_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 456,000,000.00", "extraction_confidence": 0.99, "quality_score": "high", "status": ShipmentStatus.SENT, "file_size_kb": 245},
        {"aju_number": "AJU-2026-0018", "reference_code": "CD-JQVSDCE", "filename": "INV-2026-0018.pdf", "excel_filename": "AJU-2026-0018_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 518,500.00", "extraction_confidence": 0.45, "quality_score": "low", "status": ShipmentStatus.DRAFT_INVALID, "file_size_kb": 156},
        {"aju_number": "AJU-2026-0319", "reference_code": "CD-KLSMNRTO", "filename": "INV-2026-0319.pdf", "excel_filename": "AJU-2026-0319_ceisa.xlsx", "documents_processed": '["CI", "PL", "BL"]', "total_amount": "INR 89,200,000.00", "extraction_confidence": 0.40, "quality_score": "low", "status": ShipmentStatus.DRAFT_INVALID, "file_size_kb": 201},
        {"aju_number": "AJU-2026-0510", "reference_code": "CD-ABCFGH12", "filename": "INV-2026-0510.pdf", "excel_filename": "AJU-2026-0510_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 12,340,000.00", "extraction_confidence": 0.0, "quality_score": "low", "status": ShipmentStatus.FAILED, "file_size_kb": 45},
        {"aju_number": "AJU-2026-0701", "reference_code": "CD-DIVERSE1", "filename": "INV-2026-0701.pdf", "excel_filename": "AJU-2026-0701_ceisa.xlsx", "documents_processed": '["CI"]', "total_amount": "INR 78,500,000.00", "extraction_confidence": 0.78, "quality_score": "medium", "status": ShipmentStatus.DRAFT_VALID, "file_size_kb": 112},
        {"aju_number": "AJU-2026-0702", "reference_code": "CD-DIVERSE2", "filename": "INV-2026-0702.pdf", "excel_filename": "AJU-2026-0702_ceisa.xlsx", "documents_processed": '["CI", "PL"]', "total_amount": "INR 320,000,000.00", "extraction_confidence": 0.91, "quality_score": "high", "status": ShipmentStatus.APPROVED, "file_size_kb": 189},
    ]

    for data in samples:
        data["created_at"] = now
        data["updated_at"] = now
        db.add(Shipment(**data))

    db.commit()
    logger.info(f"Seeded {len(samples)} sample shipments.")
    return len(samples)


def seed_activities(db: Session, clear_existing: bool = False) -> int:
    """Seed the activities table with sample audit log records."""
    if clear_existing:
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
    return len(samples)
