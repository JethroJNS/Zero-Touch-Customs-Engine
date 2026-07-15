"""Document loaders: PDF, JPG, JPEG, PNG → list of numpy images."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np

from ..utils import ensure_dir, get_logger

logger = get_logger(__name__)


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | {".pdf"}


class DocumentLoader:
    """Loads documents (PDF or image files) and returns page images.

    PDF pages are rendered at 300 DPI by default for high-quality OCR.
    """

    def __init__(
        self,
        dpi: int = 300,
        output_dir: Path | None = None,
    ) -> None:
        """
        Parameters
        ----------
        dpi : int
            Rendering DPI for PDF pages.
        output_dir : Path, optional
            Directory to save rendered page images.
        """
        self.dpi = dpi
        self.output_dir = output_dir
        if output_dir:
            ensure_dir(output_dir)

    def load(self, file_path: Path) -> List[Tuple[int, np.ndarray, Path | None]]:
        """Load a document and return a list of page images.

        Parameters
        ----------
        file_path : Path
            Path to the document (PDF or image).

        Returns
        -------
        List[Tuple[int, np.ndarray, Path | None]]
            List of (page_number, image_array, image_path) tuples.
            image_path is None if not saved to disk.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If the file format is not supported.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        logger.info("Loading document: %s (type: %s)", file_path.name, suffix)

        if suffix == ".pdf":
            return self._load_pdf(file_path)
        elif suffix in SUPPORTED_IMAGE_EXTENSIONS:
            return self._load_image(file_path)
        else:
            raise ValueError(
                f"Unsupported file format: {suffix}. "
                f"Supported: {SUPPORTED_EXTENSIONS}"
            )

    def _load_pdf(self, pdf_path: Path) -> List[Tuple[int, np.ndarray, Path | None]]:
        """Render each PDF page as a numpy image."""
        doc = fitz.open(str(pdf_path))
        pages: List[Tuple[int, np.ndarray, Path | None]] = []

        logger.info("Rendering PDF '%s' with %d page(s) at %d DPI",
                     pdf_path.name, len(doc), self.dpi)

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Render page to pixmap at specified DPI
            # zoom = dpi / 72 (72 is the default PDF DPI)
            zoom = self.dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Convert pixmap to numpy array (RGB → BGR for OpenCV)
            img_data = np.frombuffer(pix.samples, dtype=np.uint8)
            img_data = img_data.reshape(pix.height, pix.width, pix.n)
            # PyMuPDF pixmap returns RGB, OpenCV needs BGR
            img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)

            # Optionally save page image
            saved_path: Path | None = None
            if self.output_dir:
                saved_path = self.output_dir / f"{pdf_path.stem}_page_{page_num + 1}.png"
                cv2.imwrite(str(saved_path), img_bgr)
                logger.debug("Saved page %d to %s", page_num + 1, saved_path)

            pages.append((page_num, img_bgr, saved_path))

        doc.close()
        logger.info("PDF '%s' rendered to %d page image(s)", pdf_path.name, len(pages))
        return pages

    def _load_image(self, img_path: Path) -> List[Tuple[int, np.ndarray, Path | None]]:
        """Load a single image file."""
        img = cv2.imread(str(img_path))
        if img is None:
            raise IOError(f"Failed to load image: {img_path}")

        saved_path: Path | None = None
        if self.output_dir:
            saved_path = self.output_dir / f"{img_path.stem}_original{img_path.suffix}"
            cv2.imwrite(str(saved_path), img)

        logger.info("Loaded image '%s' (%dx%d)",
                     img_path.name, img.shape[1], img.shape[0])
        return [(0, img, saved_path)]
