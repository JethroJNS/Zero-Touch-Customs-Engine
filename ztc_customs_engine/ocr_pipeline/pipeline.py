"""Main OCR pipeline — orchestrates all components.

This is the central entry point that wires together:
  1. DocumentLoader   → PDF/image → numpy images
  2. PreprocessingPipeline → image enhancement
  3. OCREngine        → PaddleOCR text extraction
  4. LayoutLMv3Formatter → LayoutLMv3-ready data
  5. OCRResultExporter → Excel/CSV/JSON output
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

from .loaders import DocumentLoader
from .preprocessing import PreprocessingPipeline, PreprocessingConfig
from .engine import OCREngine
from .engine.layoutlm3_formatter import LayoutLMv3Formatter
from .exporters import OCRResultExporter
from .models import DocumentResult, LayoutLMv3Document, PageResult
from .utils import ensure_dir, get_logger

logger = get_logger(__name__)


class OCRPipeline:
    """End-to-end OCR pipeline for Zero-Touch Customs Engine.

    Example
    -------
    >>> pipeline = OCRPipeline()
    >>> result = pipeline.process("dokumen/CIPL.pdf")
    >>> # result.layoutlm3_data ready for LayoutLMv3
    """

    def __init__(
        self,
        preprocessing_config: PreprocessingConfig | None = None,
        ocr_lang: str = "en",
        use_gpu: bool = True,
        save_page_images: bool = True,
        page_images_dir: Path | str | None = "page_images",
        output_dir: Path | str | None = "output",
    ) -> None:
        """
        Parameters
        ----------
        preprocessing_config : PreprocessingConfig, optional
            Preprocessing steps configuration. All enabled by default.
        ocr_lang : str
            Language for PaddleOCR ('en', 'ch', etc.).
        use_gpu : bool
            Use GPU for OCR if available.
        save_page_images : bool
            Save rendered page images to disk.
        page_images_dir : Path | str, optional
            Directory for saved page images.
        output_dir : Path | str, optional
            Directory for exported results.
        """
        self.preprocessing_config = preprocessing_config or PreprocessingConfig()

        self.page_images_dir = (
            Path(page_images_dir) if page_images_dir else None
        )
        self.output_dir = Path(output_dir) if output_dir else Path("output")

        if self.page_images_dir:
            ensure_dir(self.page_images_dir)
        if self.output_dir:
            ensure_dir(self.output_dir)

        # Initialize components
        self.loader = DocumentLoader(
            dpi=300,
            output_dir=self.page_images_dir,
        )
        self.preprocessing = PreprocessingPipeline(self.preprocessing_config)
        self.ocr_engine = OCREngine(lang=ocr_lang, use_gpu=use_gpu)
        self.layoutlm3_formatter = LayoutLMv3Formatter()
        self.exporter = OCRResultExporter(output_dir=self.output_dir)

        logger.info(
            "OCRPipeline initialized — preprocessing=%s, gpu=%s, lang=%s",
            self.preprocessing_config,
            use_gpu,
            ocr_lang,
        )

    def process(
        self,
        document_path: Path | str,
        run_preprocessing: bool = True,
        export_excel: bool = True,
        export_csv: bool = False,
        export_json: bool = True,
    ) -> DocumentResult:
        """Run the full OCR pipeline on a single document.

        Parameters
        ----------
        document_path : Path | str
            Path to the document (PDF or image).
        run_preprocessing : bool
            Whether to apply image preprocessing.
        export_excel : bool
            Export results to Excel.
        export_csv : bool
            Export results to CSV.
        export_json : bool
            Export results to JSON (for debugging).

        Returns
        -------
        DocumentResult
            Full OCR result including LayoutLMv3-ready data.
        """
        doc_path = Path(document_path)
        logger.info("=" * 60)
        logger.info("Processing document: %s", doc_path.name)
        logger.info("=" * 60)

        # ── Step 1: Load document ───────────────────────────────────────────
        pages_raw = self.loader.load(doc_path)
        logger.info("Loaded %d page(s)", len(pages_raw))

        # ── Step 2: Preprocess + OCR ────────────────────────────────────────
        all_page_results: List[PageResult] = []

        for page_num, raw_img, saved_path in pages_raw:
            # Preprocess
            if run_preprocessing:
                processed_img = self.preprocessing.apply(raw_img)
            else:
                processed_img = raw_img

            # OCR
            page_result = self.ocr_engine.recognize(processed_img, page_num)
            page_result.image_path = saved_path
            all_page_results.append(page_result)

        # ── Step 3: Build DocumentResult ─────────────────────────────────────
        doc_result = DocumentResult(
            document_path=doc_path,
            document_name=doc_path.stem,
            pages=all_page_results,
        )

        # ── Step 4: LayoutLMv3 formatting ──────────────────────────────────
        layoutlm3_docs = self.layoutlm3_formatter.format_document(doc_result)
        logger.info(
            "LayoutLMv3 data prepared: %d page(s)",
            len(layoutlm3_docs),
        )

        # ── Step 5: Export ─────────────────────────────────────────────────
        if export_excel:
            xlsx_path = self.exporter.to_excel(doc_result)
            logger.info("Excel exported: %s", xlsx_path)

        if export_csv:
            csv_path = self.exporter.to_csv(doc_result)
            logger.info("CSV exported: %s", csv_path)

        if export_json:
            json_path = self.exporter.to_json(doc_result)
            logger.info("JSON exported: %s", json_path)

        # ── Summary ─────────────────────────────────────────────────────────
        logger.info("-" * 60)
        logger.info(
            "Pipeline complete — %s | %d pages | %d tokens | avg conf=%.2f%%",
            doc_result.document_name,
            len(doc_result.pages),
            doc_result.total_tokens,
            doc_result.overall_avg_confidence * 100,
        )
        logger.info("-" * 60)

        return doc_result

    def process_multiple(
        self,
        document_paths: List[Path | str],
        run_preprocessing: bool = True,
        export_excel: bool = True,
        export_csv: bool = False,
        export_json: bool = True,
    ) -> List[DocumentResult]:
        """Process multiple documents sequentially.

        Parameters
        ----------
        document_paths : List[Path | str]
            List of document paths.
        run_preprocessing : bool
            Whether to apply preprocessing.
        export_excel : bool
            Export each result to Excel.
        export_csv : bool
            Export each result to CSV.
        export_json : bool
            Export each result to JSON.

        Returns
        -------
        List[DocumentResult]
            One result per document.
        """
        results: List[DocumentResult] = []
        for doc_path in document_paths:
            result = self.process(
                doc_path,
                run_preprocessing=run_preprocessing,
                export_excel=export_excel,
                export_csv=export_csv,
                export_json=export_json,
            )
            results.append(result)
        return results
