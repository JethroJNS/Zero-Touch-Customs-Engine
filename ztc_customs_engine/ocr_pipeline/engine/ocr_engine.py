"""PaddleOCR engine wrapper for the Zero-Touch Customs Engine."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
from paddleocr import PaddleOCR

from ..models import OCRToken, PageResult
from ..utils import get_logger

logger = get_logger(__name__)


class OCREngine:
    """PaddleOCR wrapper that returns structured OCRToken lists.

    Attributes
    ----------
    lang : str
        Language code passed to PaddleOCR (default 'en').
    use_angle_cls : bool
        Whether to use angle classification (90° rotation detection).
    use_gpu : bool
        Whether to use GPU acceleration.
    """

    def __init__(
        self,
        lang: str = "en",
        use_angle_cls: bool = True,
        use_gpu: bool = True,
        show_log: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        lang : str
            Language model: 'en', 'ch', 'japan', 'korean', etc.
        use_angle_cls : bool
            Enable angle classification for rotated text.
        use_gpu : bool
            Use GPU if available (CUDA).
        show_log : bool
            Suppress PaddleOCR internal logs if False.
        """
        self.lang = lang
        logger.info("Initializing PaddleOCR (lang=%s, use_gpu=%s, angle_cls=%s)",
                    lang, use_gpu, use_angle_cls)

        self._engine = PaddleOCR(
            lang=lang,
            use_angle_cls=use_angle_cls,
            use_gpu=use_gpu,
            show_log=show_log,
        )
        logger.info("PaddleOCR initialized successfully")

    def recognize(
        self,
        image: np.ndarray,
        page_number: int = 0,
    ) -> PageResult:
        """Run OCR on a single image and return structured results.

        Parameters
        ----------
        image : np.ndarray
            Input image as numpy array (BGR or grayscale).
        page_number : int
            Zero-based page index (used in the result object).

        Returns
        -------
        PageResult
            Contains list of OCRToken objects plus image metadata.
        """
        logger.debug("Running OCR on page %d (image shape: %s)",
                     page_number, image.shape)

        # PaddleOCR accepts BGR images
        result = self._engine.ocr(image, cls=True)

        tokens: List[OCRToken] = []
        if result and result[0]:
            for line in result[0]:
                # PaddleOCR line format:
                # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]], (text, confidence)
                points = line[0]      # 4 corner points of the bounding box
                text = line[1][0]    # recognized text string
                confidence = float(line[1][1])

                # Convert 4-point polygon to [x1, y1, x2, y2] axis-aligned bbox
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                bbox = [float(min(xs)), float(min(ys)),
                        float(max(xs)), float(max(ys))]

                tokens.append(OCRToken(
                    text=text,
                    bbox=bbox,
                    confidence=confidence,
                ))

        height, width = image.shape[:2]
        page_result = PageResult(
            page_number=page_number,
            tokens=tokens,
            width=width,
            height=height,
        )

        logger.info(
            "Page %d: %d token(s) extracted, avg_conf=%.2f%%",
            page_number,
            len(tokens),
            page_result.avg_confidence * 100,
        )
        return page_result

    def recognize_batch(
        self,
        images: List[np.ndarray],
        page_numbers: List[int] | None = None,
    ) -> List[PageResult]:
        """Run OCR on multiple images sequentially.

        Parameters
        ----------
        images : List[np.ndarray]
            List of input images.
        page_numbers : List[int], optional
            Zero-based page indices. Auto-generates 0..N if None.

        Returns
        -------
        List[PageResult]
            One result per image.
        """
        if page_numbers is None:
            page_numbers = list(range(len(images)))

        results: List[PageResult] = []
        for img, page_num in zip(images, page_numbers):
            results.append(self.recognize(img, page_num))
        return results
