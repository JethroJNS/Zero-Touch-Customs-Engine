from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


def _get_template_path(filename: str) -> Path:
    # Resolve template path relative to src/ directory.
    return Path(__file__).parent.parent / "templates" / filename


@router.get("/")
async def serve_index():
    # Serve the main page (Dashboard).
    path = _get_template_path("dashboard.html")
    if path.exists():
        return FileResponse(str(path), media_type="text/html")
    raise HTTPException(status_code=404, detail="dashboard.html not found")


@router.get("/dashboard")
async def serve_dashboard():
    # Serve the dashboard page.
    path = _get_template_path("dashboard.html")
    if path.exists():
        return FileResponse(str(path), media_type="text/html")
    raise HTTPException(status_code=404, detail="dashboard.html not found")


@router.get("/smart-upload")
async def serve_smart_upload():
    # Serve the Smart Upload page.
    path = _get_template_path("smart_upload.html")
    if path.exists():
        return FileResponse(str(path), media_type="text/html")
    raise HTTPException(status_code=404, detail="smart_upload.html not found")


@router.get("/declarations")
async def serve_declarations():
    # Serve the declarations page.
    path = _get_template_path("declarations.html")
    if path.exists():
        return FileResponse(str(path), media_type="text/html")
    raise HTTPException(status_code=404, detail="declarations.html not found")


@router.get("/activity")
async def serve_activity():
    # Serve the activity / audit log page.
    path = _get_template_path("activity.html")
    if path.exists():
        return FileResponse(str(path), media_type="text/html")
    raise HTTPException(status_code=404, detail="activity.html not found")


@router.get("/model-training")
async def serve_model_training():
    # Serve the model training page.
    path = _get_template_path("model_training.html")
    if path.exists():
        return FileResponse(str(path), media_type="text/html")
    raise HTTPException(status_code=404, detail="model_training.html not found")
