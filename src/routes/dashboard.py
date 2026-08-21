"""
Dashboard API route.
Provides summary statistics for the dashboard page.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.shipment import Shipment, ShipmentStatus

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
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

        # Calculate summary stats
        saved_records = total_shipments
        ceisa_ready = draft_valid + sent
        needs_review = draft_invalid
        ceisa_approved = approved

        # Get all shipments for document type analysis
        all_shipments_result = await db.execute(select(Shipment))
        all_shipments = all_shipments_result.scalars().all()

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
        raise HTTPException(status_code=500, detail=str(e))
