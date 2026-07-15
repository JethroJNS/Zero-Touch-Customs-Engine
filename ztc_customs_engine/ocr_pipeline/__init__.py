"""Top-level exports for the OCR pipeline package."""
from __future__ import annotations

from .pipeline import OCRPipeline
from .models import (
    OCRToken,
    PageResult,
    DocumentResult,
    LayoutLMv3Document,
    PreprocessingConfig,
)
from .loaders import DocumentLoader
from .preprocessing import PreprocessingPipeline
from .engine import OCREngine
from .engine.layoutlm3_formatter import LayoutLMv3Formatter
from .exporters import OCRResultExporter

__all__ = [
    # Core pipeline
    "OCRPipeline",
    # Components
    "DocumentLoader",
    "PreprocessingPipeline",
    "OCREngine",
    "LayoutLMv3Formatter",
    "OCRResultExporter",
    # Data models
    "OCRToken",
    "PageResult",
    "DocumentResult",
    "LayoutLMv3Document",
    "PreprocessingConfig",
]
