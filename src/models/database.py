import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

# Database URL dari environment atau default
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/ocr_engine"
)

# Async engine untuk FastAPI
async_database_url = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(async_database_url, poolclass=NullPool, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine untuk startup/seeding
sync_engine = create_engine(DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=sync_engine)

# Base class untuk models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """Database dependency untuk FastAPI."""
    async with AsyncSessionLocal() as session:
        yield session
