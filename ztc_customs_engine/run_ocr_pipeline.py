"""Zero-Touch Customs Engine — OCR Pipeline entry point.

Usage:
    python -m ztc_customs_engine.run_ocr_pipeline
    python -m ztc_customs_engine.run_ocr_pipeline --doc dokumen/CIPL.pdf
    python -m ztc_customs_engine.run_ocr_pipeline --docs dokumen/ --no-preprocessing
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the package root is on the path
# File: C:/Users/Acer/zero-touch-customs-engine/ztc_customs_engine/run_ocr_pipeline.py
# parent = ztc_customs_engine/, parent.parent = zero-touch-customs-engine/
sys.path.insert(0, str(Path(__file__).parent.parent))

from ztc_customs_engine.ocr_pipeline import (
    OCRPipeline,
    PreprocessingConfig,
)
from ztc_customs_engine.ocr_pipeline.utils import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Zero-Touch Customs Engine — OCR Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m ztc_customs_engine.run_ocr_pipeline --doc dokumen/CIPL.pdf
  python -m ztc_customs_engine.run_ocr_pipeline --docs dokumen/ --output-dir output/
  python -m ztc_customs_engine.run_ocr_pipeline --doc dokumen/BL.pdf --no-preprocessing
        """,
    )
    parser.add_argument(
        "--doc",
        type=Path,
        help="Path to a single document (PDF or image)",
    )
    parser.add_argument(
        "--docs",
        type=Path,
        help="Path to a directory containing documents",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory for exported results (default: output/)",
    )
    parser.add_argument(
        "--page-images-dir",
        type=Path,
        default=Path("page_images"),
        help="Directory to save rendered page images (default: page_images/)",
    )
    parser.add_argument(
        "--no-preprocessing",
        action="store_true",
        help="Skip image preprocessing",
    )
    parser.add_argument(
        "--preprocessing-only",
        nargs="+",
        type=str,
        help="List of preprocessing steps to enable (grayscale, adaptive_threshold, deskew, noise_removal)",
    )
    parser.add_argument(
        "--no-export-excel",
        action="store_true",
        help="Skip Excel export",
    )
    parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Also export results to CSV",
    )
    parser.add_argument(
        "--no-export-json",
        action="store_true",
        help="Skip JSON export",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="en",
        help="PaddleOCR language (default: en)",
    )
    parser.add_argument(
        "--no-gpu",
        action="store_true",
        help="Disable GPU acceleration",
    )
    return parser.parse_args()


def discover_documents(dir_path: Path) -> list[Path]:
    """Find all supported documents in a directory (deduplicated)."""
    extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    seen: set[str] = set()
    docs = []
    for ext in extensions:
        for pattern in [f"*{ext}", f"*{ext.upper()}"]:
            for f in sorted(dir_path.glob(pattern)):
                if f.suffix.lower() not in seen:
                    seen.add(f.suffix.lower())
                    docs.append(f)
    return docs


def build_preprocessing_config(args: argparse.Namespace) -> PreprocessingConfig:
    """Build PreprocessingConfig from CLI arguments."""
    cfg = PreprocessingConfig()

    if args.preprocessing_only:
        # Disable all, then re-enable listed steps
        cfg.grayscale = "grayscale" in args.preprocessing_only
        cfg.adaptive_threshold = "adaptive_threshold" in args.preprocessing_only
        cfg.deskew = "deskew" in args.preprocessing_only
        cfg.noise_removal = "noise_removal" in args.preprocessing_only
        cfg.resize_scale = 0
    elif args.no_preprocessing:
        cfg.grayscale = False
        cfg.adaptive_threshold = False
        cfg.deskew = False
        cfg.noise_removal = False
        cfg.resize_scale = 0

    return cfg


def main() -> None:
    args = parse_args()

    # Configure logging
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Determine document list
    doc_paths: list[Path] = []
    if args.doc:
        doc_paths = [Path(args.doc)]
    elif args.docs:
        docs_dir = Path(args.docs)
        if not docs_dir.is_dir():
            logger.error("Not a directory: %s", docs_dir)
            sys.exit(1)
        doc_paths = discover_documents(docs_dir)
        if not doc_paths:
            logger.error("No supported documents found in: %s", docs_dir)
            sys.exit(1)
    else:
        # Default: use dokumen/
        default_dir = Path("dokumen")
        if default_dir.exists():
            doc_paths = discover_documents(default_dir)
            if not doc_paths:
                logger.error("No documents found in ./dokumen/")
                sys.exit(1)
        else:
            logger.error("No --doc or --docs specified and ./dokumen/ not found.")
            logger.error("Usage: python -m ztc_customs_engine.run_ocr_pipeline --doc <file>")
            sys.exit(1)

    logger.info("Documents to process: %s", [p.name for p in doc_paths])

    # Build config
    cfg = build_preprocessing_config(args)

    # Initialize pipeline
    pipeline = OCRPipeline(
        preprocessing_config=cfg,
        ocr_lang=args.lang,
        use_gpu=not args.no_gpu,
        save_page_images=True,
        page_images_dir=args.page_images_dir,
        output_dir=args.output_dir,
    )

    # Process
    try:
        if len(doc_paths) == 1:
            result = pipeline.process(
                doc_paths[0],
                run_preprocessing=not args.no_preprocessing,
                export_excel=not args.no_export_excel,
                export_csv=args.export_csv,
                export_json=not args.no_export_json,
            )
            logger.info("✅ OCR complete: %s", result.document_name)
            logger.info(
                "   %d pages | %d tokens | avg conf %.1f%%",
                len(result.pages),
                result.total_tokens,
                result.overall_avg_confidence * 100,
            )
        else:
            results = pipeline.process_multiple(
                doc_paths,
                run_preprocessing=not args.no_preprocessing,
                export_excel=not args.no_export_excel,
                export_csv=args.export_csv,
                export_json=not args.no_export_json,
            )
            logger.info("✅ All documents processed: %d/%d", len(results), len(doc_paths))
            for r in results:
                logger.info(
                    "   %-30s | %2d pages | %4d tokens | conf %5.1f%%",
                    r.document_name,
                    len(r.pages),
                    r.total_tokens,
                    r.overall_avg_confidence * 100,
                )
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
