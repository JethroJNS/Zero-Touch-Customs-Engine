import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from services.training_service import training_service

logger = logging.getLogger("training_routes")

router = APIRouter(prefix="/api/training", tags=["training"])

# Paths - use absolute path based on this file's location
_SCRIPT_DIR = Path(__file__).parent  # src/routes/
# Try multiple possible locations for training_dataset
_POSSIBLE_ROOTS = [
    _SCRIPT_DIR.parent.parent,                    # .../Zero-Touch-Customs-Engine/
    _SCRIPT_DIR.parent.parent.parent,             # .../Kerja Praktik/
    Path(__file__).resolve().parent.parent.parent,  # Absolute fallback
]
# Use first existing directory
_PROJECT_ROOT = next((r for r in _POSSIBLE_ROOTS if r.exists()), _SCRIPT_DIR.parent.parent)
DATASET_DIR = _PROJECT_ROOT / "training_dataset"


# Models
class DatasetInfo(BaseModel):
    name: str
    files: Dict[str, bool]
    status: str


class StatsResponse(BaseModel):
    total: int
    complete: int
    partial: int
    missing: int


class StatusResponse(BaseModel):
    status: str
    metrics: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ProgressResponse(BaseModel):
    status: str
    step: str
    percent: float
    logs: List[str]
    metrics: Optional[Dict[str, Any]] = None


class DatasetListResponse(BaseModel):
    datasets: List[DatasetInfo]


# Helper functions
def get_dataset_files(aju_dir: Path) -> Dict[str, bool]:
    # Check which files exist in a dataset folder
    name = aju_dir.name
    return {
        "ci": any(aju_dir.glob(f"{name}_CI.pdf")) or any(aju_dir.glob(f"{name}_CI.PDF")),
        "pl": any(aju_dir.glob(f"{name}_PL.pdf")) or any(aju_dir.glob(f"{name}_PL.PDF")),
        "bl": any(aju_dir.glob(f"{name}_BL.pdf")) or any(aju_dir.glob(f"{name}_BL.PDF")),
        "xlsx": any(aju_dir.glob(f"{name}.xlsx")) or any(aju_dir.glob(f"{name}.XLSX")),
    }


def get_dataset_status(files: Dict[str, bool]) -> str:
    all_present = all(files.values())
    any_present = any(files.values())

    if not any_present:
        return "missing"
    elif all_present:
        return "complete"
    else:
        return "partial"


def list_all_datasets() -> List[DatasetInfo]:
    datasets = []

    if not DATASET_DIR.exists():
        return datasets

    for aju_dir in sorted(DATASET_DIR.iterdir()):
        if not aju_dir.is_dir():
            continue

        files = get_dataset_files(aju_dir)
        datasets.append(DatasetInfo(
            name=aju_dir.name,
            files=files,
            status=get_dataset_status(files),
        ))

    return datasets


# Routes
@router.get("/stats", response_model=StatsResponse)
async def get_training_stats():
    datasets = list_all_datasets()

    return StatsResponse(
        total=len(datasets),
        complete=sum(1 for d in datasets if d.status == "complete"),
        partial=sum(1 for d in datasets if d.status == "partial"),
        missing=sum(1 for d in datasets if d.status == "missing"),
    )


@router.get("/datasets", response_model=DatasetListResponse)
async def list_datasets():
    datasets = list_all_datasets()
    return DatasetListResponse(datasets=datasets)


@router.post("/datasets/upload")
async def upload_dataset(
    aju: str = Form(...),
    files: List[UploadFile] = File(...),
):
    # Sanitize AJU name
    aju = aju.strip().replace('/', '_').replace('\\', '_')

    if not aju:
        return {"success": False, "error": "AJU number is required"}

    # Create dataset folder
    dataset_dir = DATASET_DIR / aju
    if dataset_dir.exists():
        return {"success": False, "error": f"Dataset '{aju}' already exists"}

    def detect_file_type(filename_lower: str) -> str:
        # CI/Invoice patterns
        ci_patterns = ['ci', 'ci_', 'ci-', 'invoice', 'inv_', 'inv-', 'smu']
        for p in ci_patterns:
            if p in filename_lower:
                return 'ci'

        # PL/Packing List patterns
        pl_patterns = ['pl', 'pl_', 'pl-', 'packing', 'pk', 'pk_', 'pk-']
        for p in pl_patterns:
            if p in filename_lower:
                return 'pl'

        # BL/Bill of Lading patterns
        bl_patterns = ['bl', 'bl_', 'bl-', 'lading', 'hbl', 'mbl', 'awb']
        for p in bl_patterns:
            if p in filename_lower:
                return 'bl'

        # XLSX patterns
        xlsx_patterns = ['.xlsx', '.xls']
        for p in xlsx_patterns:
            if p in filename_lower:
                return 'xlsx'

        # PDF default (if no other indicators)
        if '.pdf' in filename_lower:
            return 'unknown_pdf'

        return 'other'

    try:
        dataset_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        file_type_map = {}

        for file in files:
            if not file.filename:
                continue

            # Get clean filename
            filename = file.filename

            # Handle nested paths
            if '/' in filename:
                filename = filename.split('/')[-1]
            if '\\' in filename:
                filename = filename.split('\\')[-1]

            filename_lower = filename.lower()
            file_type = detect_file_type(filename_lower)

            # Determine target filename
            if file_type == 'ci':
                target_name = f"{aju}_CI.pdf"
            elif file_type == 'pl':
                target_name = f"{aju}_PL.pdf"
            elif file_type == 'bl':
                target_name = f"{aju}_BL.pdf"
            elif file_type == 'xlsx':
                target_name = f"{aju}.xlsx"
            elif file_type == 'unknown_pdf':
                # For unknown PDFs, use order-based assignment
                if not file_type_map.get('ci'):
                    target_name = f"{aju}_CI.pdf"
                    file_type_map['ci'] = True
                elif not file_type_map.get('pl'):
                    target_name = f"{aju}_PL.pdf"
                    file_type_map['pl'] = True
                elif not file_type_map.get('bl'):
                    target_name = f"{aju}_BL.pdf"
                    file_type_map['bl'] = True
                else:
                    target_name = filename
            else:
                target_name = filename

            file_path = dataset_dir / target_name
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
            saved_files.append(target_name)

        files_found = {
            "ci": any(f.endswith(f"{aju}_CI.pdf") for f in saved_files),
            "pl": any(f.endswith(f"{aju}_PL.pdf") for f in saved_files),
            "bl": any(f.endswith(f"{aju}_BL.pdf") for f in saved_files),
            "xlsx": any(f.endswith(f"{aju}.xlsx") for f in saved_files),
        }

        logger.info(f"Uploaded dataset '{aju}' with files: {saved_files}")

        return {
            "success": True,
            "message": f"Dataset '{aju}' uploaded successfully",
            "files": saved_files,
            "status": get_dataset_status(files_found),
        }

    except Exception as e:
        logger.error(f"Failed to upload dataset {aju}: {e}")
        if dataset_dir.exists():
            shutil.rmtree(dataset_dir, ignore_errors=True)
        return {"success": False, "error": str(e)}


@router.delete("/datasets/{aju}")
async def delete_dataset(aju: str):
    dataset_path = DATASET_DIR / aju

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset '{aju}' not found")

    try:
        shutil.rmtree(dataset_path)
        return {"success": True, "message": f"Dataset '{aju}' deleted"}
    except Exception as e:
        logger.error(f"Failed to delete dataset {aju}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_training():
    # Start model training in background
    datasets = list_all_datasets()

    if len(datasets) == 0:
        raise HTTPException(status_code=400, detail="No datasets found")

    complete_count = sum(1 for d in datasets if d.status == "complete")
    if complete_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No complete datasets found. Training requires at least one complete dataset (CI + PL + BL + XLSX)."
        )

    result = training_service.start_training()
    return result


@router.get("/status", response_model=StatusResponse)
async def get_training_status():
    progress = training_service.progress
    return StatusResponse(
        status=progress.status.value,
        metrics=progress.metrics,
        error=progress.error,
    )


@router.get("/progress", response_model=ProgressResponse)
async def get_training_progress():
    progress = training_service.progress
    return ProgressResponse(
        status=progress.status.value,
        step=progress.step,
        percent=progress.percent,
        logs=progress.logs[-50:],
        metrics=progress.metrics,
    )


@router.post("/cancel")
async def cancel_training():
    result = training_service.cancel_training()
    return result
