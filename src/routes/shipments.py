import base64
import json
import logging
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.shipment import Shipment, ShipmentStatus, get_local_time
from models.activity import Activity, ActivityAction

logger = logging.getLogger("ocr_web")
router = APIRouter(prefix="/api", tags=["shipments"])

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
MAX_FILE_SIZE_MB = 20

ENGINE_AVAILABLE = False
HybridExtractor = None
ExcelExporter = None

try:
    ENGINE_DIR = Path(__file__).parent.parent.parent / "ml"
    import sys
    sys.path.insert(0, str(ENGINE_DIR))
    from ml.src.extraction.hybrid_engine import HybridExtractor as _HE
    from ml.src.excel.exporter import ExcelExporter as _EE
    HybridExtractor = _HE
    ExcelExporter = _EE
    ENGINE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"OCR Engine not available: {e}")


def generate_reference_code() -> str:
    return f"CD-{uuid.uuid4().hex[:8].upper()}"


# Seed Endpoints

@router.post("/seed", tags=["dev"])
async def seed_database(db: AsyncSession = Depends(get_db)):
    from services import seed_shipments
    from models.database import SessionLocal
    sync_db = SessionLocal()
    try:
        count = seed_shipments(sync_db)
        return {"message": f"Seeded {count} sample shipments."}
    finally:
        sync_db.close()


@router.post("/seed/activities", tags=["dev"])
async def seed_activities(db: AsyncSession = Depends(get_db)):
    from services import seed_activities
    from models.database import SessionLocal
    sync_db = SessionLocal()
    try:
        count = seed_activities(sync_db)
        return {"message": f"Seeded {count} activity records."}
    finally:
        sync_db.close()


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


# CRUD

@router.get("/shipments")
async def list_shipments(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Shipment)
    count_query = select(func.count(Shipment.id))

    if status:
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


@router.get("/shipments/{shipment_id}")
async def get_shipment(shipment_id: int, db: AsyncSession = Depends(get_db)):
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
        "ceisa_id_header": s.ceisa_id_header,
        "header_fields": json.loads(s.header_fields) if s.header_fields else {},
        "line_items": json.loads(s.line_items) if s.line_items else [],
        "quality_report": json.loads(s.quality_report) if s.quality_report else {},
        "excel_base64": s.excel_data,
        "file_size_kb": s.file_size_kb,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.post("/shipments/{shipment_id}/send")
async def send_shipment(shipment_id: int, db: AsyncSession = Depends(get_db)):
    # Delegate to the CEISA submission endpoint
    from routes.ceisa_routes import submit_shipment_ceisa
    from ceisa import config as ceisa_config, CeisaAPIError
    from fastapi import HTTPException

    if not ceisa_config.is_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "CEISA credentials not configured. "
                "Set CEISA_USERNAME and CEISA_PASSWORD in .env file, "
                "or use POST /api/ceisa/submit/{id} after configuring."
            ),
        )

    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    if s.ceisa_id_header:
        raise HTTPException(
            status_code=409,
            detail=f"Shipment already submitted to CEISA. idHeader={s.ceisa_id_header}",
        )

    try:
        ceisa_result = await submit_shipment_ceisa(shipment_id, db)
    except CeisaAPIError as e:
        raise HTTPException(status_code=502, detail=f"CEISA API error: {e}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if ceisa_result.success:
        s.status = ShipmentStatus.SENT
        s.ceisa_id_header = ceisa_result.id_header
        s.updated_at = get_local_time()
        await db.commit()

        await create_activity(
            db=db,
            action=ActivityAction.DECLARATION_SEND,
            description=f"Declaration {s.reference_code} submitted to CEISA 4.0. idHeader={ceisa_result.id_header}",
            entity_type="shipment",
            entity_id=s.id,
            reference_code=s.reference_code,
            metadata={
                "id_header": ceisa_result.id_header,
                "aju_number": s.aju_number,
                "confidence": round(s.extraction_confidence * 100) if s.extraction_confidence else 0,
            },
            status="sent",
        )
        return {
            "message": "Declaration submitted to CEISA 4.0",
            "id": s.id,
            "status": s.status.value,
            "ceisa_id_header": ceisa_result.id_header,
            "ceisa_status": ceisa_result.status,
        }
    else:
        raise HTTPException(
            status_code=422,
            detail={
                "message": ceisa_result.message,
                "ceisa_status": ceisa_result.status,
                "raw_response": ceisa_result.raw_response,
            },
        )


@router.patch("/shipments/{shipment_id}/status")
async def update_shipment_status(
    shipment_id: int,
    status: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
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


@router.delete("/shipments/{shipment_id}")
async def delete_shipment(shipment_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    ref_code = s.reference_code
    await db.execute(delete(Shipment).where(Shipment.id == shipment_id))
    await db.commit()

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


@router.get("/shipments/{shipment_id}/download")
async def download_shipment_excel(shipment_id: int, db: AsyncSession = Depends(get_db)):
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


# Save Extraction Result

@router.post("/shipments")
async def create_shipment(request: Request, db: AsyncSession = Depends(get_db)):
    # Simpan hasil ekstraksi ke database.
    body = await request.json()

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


# OCR Extraction

@router.post("/extract")
async def extract_documents(request: Request, db: AsyncSession = Depends(get_db)):
    # Jalankan pipeline OCR+ekstraksi pada dokumen CI, PL, BL.
    if not ENGINE_AVAILABLE or HybridExtractor is None:
        raise HTTPException(
            status_code=503,
            detail="OCR extraction engine not available.",
        )

    form = await request.form()

    def get_file(key: str):
        for k in [key.upper(), key.lower()]:
            val = form.get(k)
            if val and hasattr(val, "filename") and val.filename:
                return k, val
        return None, None

    ci_key, ci_file = get_file("CI")
    pl_key, pl_file = get_file("PL")
    bl_key, bl_file = get_file("BL")
    fe_key, fe_file = get_file("FE")

    uploaded = {}
    for doc_type, file in [("CI", ci_file), ("PL", pl_file), ("BL", bl_file), ("FE", fe_file)]:
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

    def _cleanup():
        if work_dir.exists():
            try:
                shutil.rmtree(work_dir)
                logger.info(f"Cleaned up working directory: {work_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up {work_dir}: {e}")

    try:
        file_paths: dict = {}
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

        # Form E goods (for BARANGTARIF sheet)
        form_e_goods = []
        fe_goods = getattr(result.entities, 'form_e_goods', []) or []
        for g in fe_goods:
            form_e_goods.append({
                'row_number': g.row_number,
                'hs_code': g.hs_code,
                'quantity': g.quantity,
                'unit': g.unit,
                'description': g.description,
                'bm_rate': round(g.bm_rate, 2),
                'ppn_rate': round(g.ppn_rate, 2),
                'pph_rate': round(g.pph_rate, 2),
                'hs_found': g.hs_found,
            })

        quality_report = {}
        if hasattr(result.entities, 'get_quality_report'):
            quality_report = result.entities.get_quality_report()

        total_amount = getattr(result.entities, 'total_amount', None)

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

        await create_activity(
            db=db,
            action=ActivityAction.OCR_PROCESS,
            description=f"Processed upload(s) with OCR and intelligent extraction.",
            entity_type="shipment",
            entity_id=None,
            reference_code=None,
            metadata=_log_meta,
            status=_status,
        )

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
            "form_e_goods": form_e_goods,
            "form_e_count": len(form_e_goods),
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
            await create_activity(
                db=db,
                action=ActivityAction.OCR_PROCESS,
                description="OCR processing failed.",
                entity_type="shipment",
                metadata={"error": str(exc)},
                status="failed",
            )
        except Exception:
            pass
        raise
    finally:
        _cleanup()
