from __future__ import annotations

import io
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import logging

import numpy as np
from PIL import Image

import fitz  # PyMuPDF

from config import OCR_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class OCRWord:
    # A single OCR-detected word with position and confidence.
    text: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    page: int = 0

    @property
    def x1(self) -> float:
        return self.bbox[0]

    @property
    def y1(self) -> float:
        return self.bbox[1]

    @property
    def x2(self) -> float:
        return self.bbox[2]

    @property
    def y2(self) -> float:
        return self.bbox[3]

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "page": self.page,
        }


@dataclass
class OCRLine:
    # A line of text (grouped words).
    text: str
    confidence: float
    bbox: Tuple[float, float, float, float]
    page: int = 0
    words: List[OCRWord] = field(default_factory=list)

    @property
    def x1(self) -> float:
        return self.bbox[0]

    @property
    def y1(self) -> float:
        return self.bbox[1]

    @property
    def x2(self) -> float:
        return self.bbox[2]

    @property
    def y2(self) -> float:
        return self.bbox[3]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "page": self.page,
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class OCRPage:
    # Full OCR result for one page.
    page_num: int
    text: str
    lines: List[OCRLine]
    words: List[OCRWord]
    width: float
    height: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_num": self.page_num,
            "text": self.text,
            "lines": [l.to_dict() for l in self.lines],
            "words": [w.to_dict() for w in self.words],
            "width": self.width,
            "height": self.height,
        }


@dataclass
class OCRResult:
    file_path: str
    file_type: str          # 'pdf' or 'image'
    pages: List[OCRPage]
    total_pages: int = 0

    def __post_init__(self):
        if self.total_pages == 0 and self.pages:
            self.total_pages = len(self.pages)

    @property
    def full_text(self) -> str:
        # Concatenate all page texts with double newlines between pages.
        return "\n\n".join(p.text for p in self.pages)

    @property
    def all_words(self) -> List[OCRWord]:
        return [w for p in self.pages for w in p.words]

    @property
    def all_lines(self) -> List[OCRLine]:
        return [l for p in self.pages for l in p.lines]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_type": self.file_type,
            "total_pages": self.total_pages,
            "pages": [p.to_dict() for p in self.pages],
            "full_text": self.full_text,
        }

    def get_page(self, page_num: int) -> Optional[OCRPage]:
        if 0 <= page_num < len(self.pages):
            return self.pages[page_num]
        return None

    def get_region_words(
        self,
        x1: float, y1: float,
        x2: float, y2: float,
        page_num: Optional[int] = None,
    ) -> List[OCRWord]:
        """Get all words within a bounding box region."""
        words = []
        for w in self.all_words:
            if page_num is not None and w.page != page_num:
                continue
            # Check overlap
            if (w.x1 < x2 and w.x2 > x1 and w.y1 < y2 and w.y2 > y1):
                words.append(w)
        return words


class OCREngine:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        from paddleocr import PaddleOCR

        self.config = (config or OCR_CONFIG.copy()).copy()
        self.config["use_gpu"] = False  # Selalu CPU

        # Only pass lang to avoid unsupported args in new PaddleOCR versions
        lang = self.config.get("lang", "en")
        self._ocr = PaddleOCR(lang=lang)
        logger.info("OCREngine initialized (CPU mode)")

    def _render_pdf_page(self, pdf_doc, page_num: int, dpi: int = 300) -> Image.Image:
        # Konversi PDF ke PIL Image.
        page = pdf_doc[page_num]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_data = pix.tobytes("png")
        return Image.open(io.BytesIO(img_data))

    def _words_to_lines(
        self,
        words: List,
        page_width: float,
        page_height: float,
        page_num: int,
    ) -> Tuple[List[OCRLine], List[OCRWord]]:
        # Konversi PaddleOCR result ke OCRLine/OCRWord objects.
        if not words:
            return [], []

        ocr_words = []
        for w in words:
            text = w[1][0] if isinstance(w[1], (list, tuple)) else str(w[1])
            conf = float(w[1][1]) if isinstance(w[1], (list, tuple)) and len(w[1]) > 1 else 1.0
            bbox_raw = w[0]

            # Konversi [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] ke [x1,y1,x3,y3]
            if isinstance(bbox_raw, list) and len(bbox_raw) == 4:
                xs = [pt[0] for pt in bbox_raw]
                ys = [pt[1] for pt in bbox_raw]
                x1, x2 = min(xs), max(xs)
                y1, y2 = min(ys), max(ys)
            else:
                x1, y1, x2, y2 = bbox_raw[0], bbox_raw[1], bbox_raw[2], bbox_raw[3]

            ocr_words.append(OCRWord(
                text=text,
                confidence=conf,
                bbox=(float(x1), float(y1), float(x2), float(y2)),
                page=page_num,
            ))

        sorted_words = sorted(
            ocr_words,
            key=lambda w: (round(w.y1 / 15) * 15, w.x1)
        )

        lines_dict: Dict[int, List[OCRWord]] = {}
        for word in sorted_words:
            line_key = round(word.y1 / 10) * 10
            lines_dict.setdefault(line_key, []).append(word)

        ocr_lines = []
        for line_key in sorted(lines_dict.keys()):
            line_words = sorted(lines_dict[line_key], key=lambda w: w.x1)
            line_text = " ".join(w.text for w in line_words)
            line_conf = sum(w.confidence for w in line_words) / len(line_words)
            xs = [w.x1 for w in line_words] + [w.x2 for w in line_words]
            ys = [w.y1 for w in line_words] + [w.y2 for w in line_words]
            line_bbox = (min(xs), min(ys), max(xs), max(ys))

            ocr_lines.append(OCRLine(
                text=line_text,
                confidence=line_conf,
                bbox=line_bbox,
                page=page_num,
                words=line_words,
            ))

        return ocr_lines, ocr_words

    def _process_image(self, img: Image.Image, page_num: int = 0) -> OCRPage:
        img_array = np.array(img.convert("RGB"))
        result = self._ocr.ocr(img_array)

        words: List = []
        if result and result[0]:
            for line_result in result[0]:
                if line_result:
                    words.append(line_result)

        lines, ocr_words = self._words_to_lines(
            words, img.width, img.height, page_num
        )
        full_text = "\n".join(l.text for l in lines)

        return OCRPage(
            page_num=page_num,
            text=full_text,
            lines=lines,
            words=ocr_words,
            width=float(img.width),
            height=float(img.height),
        )

    def read_file(self, file_path: str | Path) -> OCRResult:
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return self._read_pdf(file_path)
        elif suffix in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}:
            return self._read_image(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

    def _read_pdf(self, file_path: Path) -> OCRResult:
        doc = fitz.open(file_path)
        pages = []

        for page_num in range(len(doc)):
            img = self._render_pdf_page(doc, page_num)
            page = self._process_image(img, page_num)
            page.width = float(img.width)
            page.height = float(img.height)
            pages.append(page)

        doc.close()
        logger.info(f"PDF {file_path.name}: {len(pages)} pages OCR'd")

        return OCRResult(
            file_path=str(file_path),
            file_type="pdf",
            pages=pages,
            total_pages=len(pages),
        )

    def _read_image(self, file_path: Path) -> OCRResult:
        img = Image.open(file_path).convert("RGB")
        page = self._process_image(img, page_num=0)

        return OCRResult(
            file_path=str(file_path),
            file_type="image",
            pages=[page],
            total_pages=1,
        )

    def read_multiple(
        self,
        file_paths: List[str | Path],
    ) -> Dict[str, Optional[OCRResult]]:
        # Memproses multiple files. Returns dict mapping path → OCRResult.
        results = {}
        for fp in file_paths:
            try:
                results[str(fp)] = self.read_file(fp)
            except Exception as e:
                logger.warning(f"OCR failed for {fp}: {e}")
                results[str(fp)] = None
        return results
