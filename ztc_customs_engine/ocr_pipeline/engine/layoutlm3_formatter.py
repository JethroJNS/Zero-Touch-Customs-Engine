"""LayoutLMv3 data formatter.

Prepares OCR results in the format required by LayoutLMv3 fine-tuning
and inference pipelines.

LayoutLMv3 expects:
  - image : PIL.Image or path to image file
  - words : List[str]  — token-level word strings
  - boxes : List[List[int]]  — normalized [x1, y1, x2, y2] in [0, 1000]

This formatter produces exactly those three fields so it can be
directly consumed by a HuggingFace Trainer or pipeline.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

from ..models import DocumentResult, LayoutLMv3Document, PageResult, OCRToken
from ..utils import normalize_bbox, get_logger

logger = get_logger(__name__)

# Normalization constant used by LayoutLMv3
NORM_SCALE = 1000


class LayoutLMv3Formatter:
    """Formats OCR results into LayoutLMv3-compatible structures.

    This class does NOT run LayoutLMv3 — it only prepares the data
    that LayoutLMv3 expects as input.

    Usage
    -----
    >>> formatter = LayoutLMv3Formatter()
    >>> doc_data = formatter.format(document_result, image_path)
    >>> # doc_data.words, doc_data.normalized_boxes ready for LayoutLMv3
    """

    def __init__(self, norm_scale: int = NORM_SCALE) -> None:
        """
        Parameters
        ----------
        norm_scale : int
            Upper bound of the normalized coordinate space.
            LayoutLMv3 uses 1000 by convention.
        """
        self.norm_scale = norm_scale

    def format_page(
        self,
        page_result: PageResult,
        image_path: Path,
    ) -> LayoutLMv3Document:
        """Format a single page's OCR result for LayoutLMv3.

        Parameters
        ----------
        page_result : PageResult
            OCR result from a single page.
        image_path : Path
            Path to the page image file.

        Returns
        -------
        LayoutLMv3Document
            Formatted data with normalized boxes in [0, norm_scale].
        """
        words: List[str] = []
        normalized_boxes: List[List[int]] = []
        original_boxes: List[List[float]] = []

        for token in page_result.tokens:
            words.append(token.text)
            original_boxes.append(token.bbox)
            normalized_boxes.append(
                normalize_bbox(
                    token.bbox,
                    img_width=page_result.width,
                    img_height=page_result.height,
                    norm=self.norm_scale,
                )
            )

        doc = LayoutLMv3Document(
            image_path=image_path,
            words=words,
            normalized_boxes=normalized_boxes,
            original_boxes=original_boxes,
            image_width=page_result.width,
            image_height=page_result.height,
        )

        logger.debug(
            "Page %d: formatted %d tokens for LayoutLMv3",
            page_result.page_number,
            len(words),
        )
        return doc

    def format_document(
        self,
        document_result: DocumentResult,
        merged_image_path: Path | None = None,
    ) -> List[LayoutLMv3Document]:
        """Format all pages of a document for LayoutLMv3.

        LayoutLMv3 processes one page at a time, so this returns
        one LayoutLMv3Document per page.

        Parameters
        ----------
        document_result : DocumentResult
            Full document OCR result.
        merged_image_path : Path, optional
            Path to a merged/stitched full-document image.
            If provided, this image is used for the LayoutLMv3Document.
            Otherwise uses per-page image paths.

        Returns
        -------
        List[LayoutLMv3Document]
            One formatted document per page.
        """
        formatted_pages: List[LayoutLMv3Document] = []

        for page in document_result.pages:
            if page.image_path:
                img_path = page.image_path
            elif merged_image_path:
                img_path = merged_image_path
            else:
                raise ValueError(
                    f"No image path available for page {page.page_number}. "
                    "Set output_dir in DocumentLoader to save page images."
                )

            doc = self.format_page(page, img_path)
            formatted_pages.append(doc)

        # Attach to the document result for later access
        document_result.layoutlm3_data = formatted_pages[0] if len(formatted_pages) == 1 else formatted_pages  # type: ignore[assignment]

        logger.info(
            "Document '%s': formatted %d page(s) for LayoutLMv3",
            document_result.document_name,
            len(formatted_pages),
        )
        return formatted_pages

    def to_huggingface_dict(
        self,
        layoutlm3_doc: LayoutLMv3Document,
    ) -> dict:
        """Convert a LayoutLMv3Document to a HuggingFace-compatible dict.

        This output is directly usable as a feature sample for:
          - `LayoutLMv3Processor` / `AutoProcessor`
          - `Trainer` with a custom collate function
          - Direct model input construction

        Parameters
        ----------
        layoutlm3_doc : LayoutLMv3Document

        Returns
        -------
        dict
            {
                "image": PIL.Image,
                "words": List[str],
                "boxes": List[List[int]],   # normalized 0-1000
            }
        """
        image = Image.open(layoutlm3_doc.image_path)

        return {
            "image": image,
            "words": layoutlm3_doc.words,
            "boxes": layoutlm3_doc.normalized_boxes,
        }

    def to_tokenizer_dict(
        self,
        layoutlm3_doc: LayoutLMv3Document,
    ) -> dict:
        """Extract just the token/box data (without PIL image) for tokenizer input.

        Use this when you want to test tokenization separately from image encoding.

        Returns
        -------
        dict
            {
                "words": List[str],
                "boxes": List[List[int]],
            }
        """
        return {
            "words": layoutlm3_doc.words,
            "boxes": layoutlm3_doc.normalized_boxes,
        }
