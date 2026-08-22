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

    # Register routers
    from routes.shipments import router as shipments_router
    from routes.activities import router as activities_router
    from routes.dashboard import router as dashboard_router
    from routes.pages import router as pages_router

    app.include_router(shipments_router)
    app.include_router(activities_router)
    app.include_router(dashboard_router)
    app.include_router(pages_router)

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
