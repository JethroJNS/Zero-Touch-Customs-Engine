import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from models.database import Base, sync_engine, SessionLocal

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ocr_web")

# App factory
def create_app() -> FastAPI:
    app = FastAPI(
        title="Document OCR Extraction Engine",
        description="Upload CI, PL, and BL documents to run CEISA 4.0 extraction pipeline.",
        version="1.0.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Startup events
    @app.on_event("startup")
    async def on_startup():
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _create_tables)
        await loop.run_in_executor(None, _seed_data)
        # Download LayoutLM model from Google Drive FIRST (before OCR warm-up)
        await loop.run_in_executor(None, _download_layoutlm_model)
        # Pre-warm PaddleOCR agar model di-download SEBELUM request pertama
        await loop.run_in_executor(None, _prewarm_ocr)

    def _create_tables():
        try:
            Base.metadata.create_all(bind=sync_engine)
            logger.info("Database tables created / verified.")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")

    def _seed_data():
        from services import seed_shipments, seed_activities
        try:
            db = SessionLocal()
            try:
                seed_shipments(db)
                seed_activities(db)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to seed data: {e}")

    def _download_layoutlm_model():
        import os
        try:
            model_repo = os.environ.get("MODEL_REPO", "")
            model_path_env = os.environ.get("MODEL_PATH", "")
            default_model_path = Path(__file__).parent.parent / "ml" / "models" / "layoutlmv3-v4" / "best_model"

            if model_path_env:
                model_dir = Path(model_path_env)
            else:
                model_dir = default_model_path

            # Check if model already exists
            model_file = model_dir / "model.safetensors"
            if model_file.exists():
                size_mb = model_file.stat().st_size / (1024 * 1024)
                if size_mb > 100:
                    logger.info(f"LayoutLMv3 model already exists at {model_dir} ({size_mb:.1f} MB)")
                    return
                else:
                    logger.warning(f"LayoutLMv3 model file too small ({size_mb:.1f} MB), re-downloading")

            if not model_repo:
                logger.warning("MODEL_REPO not set. Skipping model download.")
                logger.warning("Text-based extraction will be used instead.")
                return

            logger.info(f"Downloading LayoutLMv3 model from HuggingFace: {model_repo}")

            # Use subprocess to run the download script
            import subprocess
            import sys

            script_path = Path(__file__).parent.parent / "download_model_hf.py"
            if not script_path.exists():
                logger.warning(f"Download script not found at {script_path}")
                return

            result = subprocess.run(
                [sys.executable, str(script_path), "--repo", model_repo, "--target-dir", str(model_dir)],
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )

            if result.returncode == 0:
                logger.info("LayoutLMv3 model downloaded successfully from HuggingFace.")
            else:
                logger.warning(f"Failed to download model: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.error("Model download timed out.")
        except Exception as e:
            logger.error(f"Failed to download LayoutLMv3 model: {e}")

    def _prewarm_ocr():
        """Pre-warm PaddleOCR engine at startup so model download happens
        BEFORE any extraction request (avoids memory spike during pipeline)."""
        import gc
        import os
        try:
            # Set torch thread limit SEBELUM import torch
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("MKL_NUM_THREADS", "1")
            os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
            os.environ.setdefault("PYTORCH_DISABLE_INIT", "1")

            import torch
            torch.set_num_threads(1)
            torch.set_flush_denormal(True)

            logger.info("Pre-warming OCR engine (downloading PaddleOCR models if needed)...")

            # Import dan init OCR dengan cara yang lebih safe
            try:
                from ml.src.ocr.engine import OCREngine
                engine = OCREngine()

                # Test dengan dummy image
                import numpy as np
                from PIL import Image
                dummy_img = Image.new("RGB", (100, 20), color=(255, 255, 255))
                engine._process_image(dummy_img, 0)
                logger.info("OCR engine pre-warmed successfully.")
            except Exception as ocr_error:
                logger.warning(f"OCR warm-up failed (will use lazy init): {ocr_error}")
                # OCR will be initialized lazily when first request comes
        except Exception as e:
            logger.warning(f"OCR prewarm skipped: {e}")

    # Register routers
    from routes.shipments import router as shipments_router
    from routes.activities import router as activities_router
    from routes.dashboard import router as dashboard_router
    from routes.pages import router as pages_router
    from routes.ceisa_routes import router as ceisa_router
    from routes.training import router as training_router

    app.include_router(shipments_router)
    app.include_router(activities_router)
    app.include_router(dashboard_router)
    app.include_router(pages_router)
    app.include_router(ceisa_router)
    app.include_router(training_router)

    # Health check
    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    return app


# App instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
