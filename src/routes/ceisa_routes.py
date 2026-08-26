from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

_SRC_DIR = Path(__file__).parent.parent
_ML_DIR = _SRC_DIR.parent / "ml"
sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_ML_DIR))

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.shipment import Shipment, get_local_time
from sqlalchemy import select
from sqlalchemy.orm import Session as SyncSession
from models.database import SessionLocal

from ceisa import CeisaClient, CeisaSubmissionResult, CeisaAPIError, config as ceisa_config

logger = logging.getLogger("ceisa_routes")
router = APIRouter(prefix="/api/ceisa", tags=["CEISA 4.0"])


def _get_shipment_sync(shipment_id: int) -> Shipment:
    # Get shipment synchronously (for CEISA client which is sync-ish).
    db = SessionLocal()
    try:
        s = db.get(Shipment, shipment_id)
        if not s:
            raise ValueError(f"Shipment {shipment_id} not found")
        return s
    finally:
        db.close()


def _build_entities_from_shipment(s: Shipment):
    from ml.src.extraction.merger import ShipmentEntities
    from ml.src.extraction.items import ItemEntity

    entities = ShipmentEntities()

    # Parse header fields
    header_data = {}
    if s.header_fields:
        try:
            header_data = json.loads(s.header_fields) if isinstance(s.header_fields, str) else s.header_fields
        except Exception:
            pass

    # Parse line items
    items_data = []
    if s.line_items:
        try:
            items_data = json.loads(s.line_items) if isinstance(s.line_items, str) else s.line_items
        except Exception:
            pass

    # Map header fields → ShipmentEntities attributes
    mapping = {
        "invoice_number": "invoice_number",
        "invoice_date": "invoice_date",
        "currency": "currency",
        "incoterms": "incoterms",
        "total_amount": "total_amount",
        "freight": "freight",
        "netto": "total_net_weight",
        "bruto": "total_gross_weight",
        "port_of_loading": "port_of_loading",
        "port_of_discharge": "port_of_discharge",
        "country_of_origin": "country_of_origin",
        "seller_name": "seller_name",
        "seller_address": "seller_address",
        "buyer_name": "buyer_name",
        "buyer_address": "buyer_address",
        "shipper_name": "shipper_name",
        "shipper_address": "shipper_address",
        "consignee_name": "consignee_name",
        "consignee_address": "consignee_address",
        "container_numbers": "container_numbers",
        "seal_numbers": "seal_numbers",
        "number_of_packages": "number_of_packages",
        "packaging_type": "packaging_type",
        "vessel_name": "vessel_name",
        "voyage_number": "voyage_number",
        "payment_terms": "payment_terms",
        "bl_number": "bl_number",
        "bl_date": "bl_date",
    }

    for src_key, dest_attr in mapping.items():
        value = header_data.get(src_key)
        if value is not None:
            setattr(entities, dest_attr, value)

    # Fallbacks
    if not entities.invoice_number:
        entities.invoice_number = s.reference_code
    if not entities.invoice_date and s.created_at:
        entities.invoice_date = s.created_at.strftime("%Y-%m-%d")
    if not entities.total_amount and s.total_amount:
        entities.total_amount = s.total_amount

    # Map line items
    for item_data in items_data:
        if not isinstance(item_data, dict):
            continue
        item = ItemEntity(
            hs_code=item_data.get("hs_code") or item_data.get("hs"),
            description=item_data.get("description") or item_data.get("uraian"),
            quantity=item_data.get("quantity") or item_data.get("jumlahSatuan"),
            unit=item_data.get("unit") or item_data.get("kodeSatuan"),
            unit_price=item_data.get("unit_price") or item_data.get("hargaSatuan"),
            amount=item_data.get("amount") or item_data.get("hargaPerolehan") or item_data.get("fob"),
            net_weight=item_data.get("net_weight") or item_data.get("netto"),
            gross_weight=item_data.get("gross_weight") or item_data.get("bruto"),
            country_of_origin=item_data.get("country_of_origin"),
            packaging=item_data.get("packaging") or item_data.get("kodeKemasan"),
        )
        entities.items.append(item)

    # Quality metadata
    entities.extraction_confidence = s.extraction_confidence or 0.0

    return entities

    # Quality metadata
    entities.extraction_confidence = s.extraction_confidence or 0.0

    return entities


@router.get("/config", tags=["CEISA 4.0"])
async def check_config():
    # Check if CEISA credentials are configured.
    return {
        "configured": ceisa_config.is_configured,
        "env": ceisa_config.env,
        "auth_url": ceisa_config.auth_url,
        "document_url": ceisa_config.document_url,
        "message": (
            "CEISA credentials configured. Ready to submit."
            if ceisa_config.is_configured
            else "CEISA not configured. Set CEISA_USERNAME and CEISA_PASSWORD in .env"
        ),
    }


@router.post("/submit/{shipment_id}", tags=["CEISA 4.0"])
async def submit_to_ceisa(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Fetch shipment
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Check if already submitted
    if s.ceisa_id_header:
        raise HTTPException(
            status_code=409,
            detail=f"Shipment already submitted to CEISA. idHeader={s.ceisa_id_header}",
        )

    # Check credentials
    if not ceisa_config.is_configured:
        raise HTTPException(
            status_code=503,
            detail="CEISA credentials not configured. Set CEISA_USERNAME and CEISA_PASSWORD in .env",
        )

    # Build entities from stored data
    try:
        entities = _build_entities_from_shipment(s)
    except Exception as e:
        logger.error(f"Failed to build entities for shipment {shipment_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to build CEISA document: {e}")

    # Submit to CEISA
    async with CeisaClient() as client:
        try:
            result = await client.submit_document(
                entities=entities,
                shipment_id=s.reference_code,
            )
        except CeisaAPIError as e:
            logger.error(f"CEISA API error for shipment {shipment_id}: {e}")
            raise HTTPException(status_code=502, detail=str(e))

    if result.success:
        # Update shipment
        from models.shipment import ShipmentStatus
        from models.activity import ActivityAction, create_activity

        s.status = ShipmentStatus.SENT
        s.ceisa_id_header = result.id_header
        s.updated_at = get_local_time()

        await db.commit()

        # Log activity
        await create_activity(
            db=db,
            action=ActivityAction.DECLARATION_SEND,
            description=f"Declaration {s.reference_code} submitted to CEISA 4.0. idHeader={result.id_header}",
            entity_type="shipment",
            entity_id=s.id,
            reference_code=s.reference_code,
            metadata={
                "id_header": result.id_header,
                "aju_number": s.aju_number,
                "ceisa_status": result.status,
            },
            status="sent",
        )

        return {
            "success": True,
            "id_header": result.id_header,
            "status": result.status,
            "message": result.message,
            "shipment_id": s.id,
            "reference_code": s.reference_code,
        }
    else:
        # Validation or API error
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "status": result.status,
                "message": result.message,
                "raw_response": result.raw_response,
                "shipment_id": s.id,
                "reference_code": s.reference_code,
            },
        )


@router.get("/status/{id_header}", tags=["CEISA 4.0"])
async def get_ceisa_status(id_header: str):
    # Check the processing status of a submitted CEISA document.
    if not ceisa_config.is_configured:
        raise HTTPException(status_code=503, detail="CEISA not configured")

    async with CeisaClient() as client:
        try:
            status_data = await client.get_status(id_header)
            return status_data
        except CeisaAPIError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to get CEISA status for {id_header}: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate/{shipment_id}", tags=["CEISA 4.0"])
async def validate_ceisa_document(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Validate a shipment's data against CEISA API without actually submitting.
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    if not ceisa_config.is_configured:
        raise HTTPException(status_code=503, detail="CEISA not configured")

    try:
        entities = _build_entities_from_shipment(s)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build document: {e}")

    async with CeisaClient() as client:
        try:
            result = await client.validate_document(entities)
        except CeisaAPIError as e:
            return {
                "success": False,
                "valid": False,
                "error": str(e),
                "message": e.message,
            }

    return {
        "valid": result.success,
        "success": result.success,
        "status": result.status,
        "message": result.message,
        "raw_response": result.raw_response,
    }


@router.get("/preview/{shipment_id}", tags=["CEISA 4.0"])
async def preview_ceisa_document(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    try:
        entities = _build_entities_from_shipment(s)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build document: {e}")

    from ceisa import CeisaMapper
    mapper = CeisaMapper()
    doc_json = mapper.map_document(entities)

    return {
        "shipment_id": s.id,
        "reference_code": s.reference_code,
        "document": doc_json,
        "items_count": len(doc_json.get("barang", [])),
        "nomorAju": doc_json.get("nomorAju"),
        "note": "This is a preview only — no data has been sent to CEISA",
    }


async def submit_shipment_ceisa(shipment_id: int, db: AsyncSession) -> CeisaSubmissionResult:
    # Core CEISA submission logic, used by both the CEISA router
    from models.shipment import ShipmentStatus

    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise ValueError(f"Shipment {shipment_id} not found")

    entities = _build_entities_from_shipment(s)

    async with CeisaClient() as client:
        return await client.submit_document(entities=entities, shipment_id=s.reference_code)
