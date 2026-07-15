"""Typed data classes for OCR pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from pathlib import Path


@dataclass
class OCRToken:
    """Single OCR token with text, bounding box, and confidence.

    Attributes
    ----------
    text : str
        Recognized text content.
    bbox : List[float]
        Bounding box as [x1, y1, x2, y2] (top-left and bottom-right coords).
    confidence : float
        OCR confidence score between 0.0 and 1.0.
    """

    text: str
    bbox: List[float]
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be in [0.0, 1.0], got {self.confidence}"
            )

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "bbox": self.bbox,
            "confidence": self.confidence,
        }


@dataclass
class PageResult:
    """OCR result for a single document page.

    Attributes
    ----------
    page_number : int
        Zero-based page index.
    tokens : List[OCRToken]
        All tokens extracted from this page.
    image_path : Optional[Path]
        Path to the page image (if saved).
    width : int
        Image width in pixels.
    height : int
        Image height in pixels.
    """

    page_number: int
    tokens: List[OCRToken] = field(default_factory=list)
    image_path: Optional[Path] = None
    width: int = 0
    height: int = 0

    @property
    def full_text(self) -> str:
        """Concatenate all token texts with spaces."""
        return " ".join(t.text for t in self.tokens)

    @property
    def avg_confidence(self) -> float:
        """Average confidence across all tokens."""
        if not self.tokens:
            return 0.0
        return sum(t.confidence for t in self.tokens) / len(self.tokens)


@dataclass
class DocumentResult:
    """OCR result for an entire document.

    Attributes
    ----------
    document_path : Path
        Path to the source document.
    document_name : str
        Filename without path.
    pages : List[PageResult]
        Per-page OCR results.
    layoutlm3_data : Optional[LayoutLMv3Document]
        Data formatted for LayoutLMv3.
    """

    document_path: Path
    document_name: str
    pages: List[PageResult] = field(default_factory=list)
    layoutlm3_data: Optional[LayoutLMv3Document] = None

    @property
    def total_tokens(self) -> int:
        return sum(len(p.tokens) for p in self.pages)

    @property
    def overall_avg_confidence(self) -> float:
        tokens = [t for p in self.pages for t in p.tokens]
        if not tokens:
            return 0.0
        return sum(t.confidence for t in tokens) / len(tokens)


@dataclass
class LayoutLMv3Document:
    """Data formatted for LayoutLMv3 fine-tuning / inference.

    Normalized bounding boxes use coordinate space 0–1000
    to be model-agnostic (independent of image resolution).
    """

    image_path: Path
    words: List[str]
    normalized_boxes: List[List[int]]  # each: [x1, y1, x2, y2] in 0-1000
    original_boxes: List[List[float]]  # each: [x1, y1, x2, y2] in pixels
    image_width: int
    image_height: int

    def __len__(self) -> int:
        return len(self.words)


@dataclass
class PreprocessingConfig:
    """Configuration for preprocessing pipeline.

    All flags default to True so that a minimal pipeline
    still improves OCR quality. Set individual flags to False
    to disable specific steps.
    """

    grayscale: bool = True
    adaptive_threshold: bool = True
    deskew: bool = True
    noise_removal: bool = True
    resize_scale: float = 2.0  # 0 = disabled, > 0 = upscale factor

    # Advanced parameters
    threshold_block_size: int = 11
    threshold_c: int = 2
    morph_kernel_size: int = 3
    morph_iterations: int = 1
    target_long_edge: int = 0  # 0 = no resize; otherwise max long-edge px


