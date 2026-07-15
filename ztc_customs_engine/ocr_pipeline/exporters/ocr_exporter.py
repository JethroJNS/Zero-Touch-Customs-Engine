"""OCR result exporters."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd

from ..models import DocumentResult, OCRToken, PageResult
from ..utils import ensure_dir, get_logger

logger = get_logger(__name__)


class OCRResultExporter:
    """Export OCR results to various formats.

    Currently supports:
      - Excel (.xlsx) via pandas
      - CSV (.csv)
      - JSON (.json) for debugging
    """

    def __init__(self, output_dir: Path | str | None = None) -> None:
        """
        Parameters
        ----------
        output_dir : Path | str, optional
            Default output directory. Created if it doesn't exist.
        """
        self.output_dir = Path(output_dir) if output_dir else Path("output")
        if self.output_dir:
            ensure_dir(self.output_dir)

    def to_excel(
        self,
        document_result: DocumentResult,
        output_path: Path | str | None = None,
        sheet_name: str = "OCR Results",
    ) -> Path:
        """Export OCR results to an Excel file.

        Output columns: Text | Confidence | Bounding Box

        Parameters
        ----------
        document_result : DocumentResult
            Full OCR result for a document.
        output_path : Path | str, optional
            Output file path. Auto-generates from document name if None.
        sheet_name : str
            Name of the Excel sheet tab.

        Returns
        -------
        Path
            Path to the saved Excel file.
        """
        rows: List[dict] = []
        for page in document_result.pages:
            for token in page.tokens:
                rows.append({
                    "Page": page.page_number + 1,
                    "Text": token.text,
                    "Confidence": round(token.confidence, 4),
                    "Bounding Box": str(token.bbox),
                })

        df = pd.DataFrame(rows)

        if not rows:
            logger.warning("No OCR tokens to export for '%s'",
                            document_result.document_name)
            # Create empty placeholder
            df = pd.DataFrame(columns=["Page", "Text", "Confidence", "Bounding Box"])

        if output_path is None:
            output_path = self.output_dir / f"{document_result.document_name}_hasil_ocr.xlsx"
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Auto-fit column widths
            worksheet = writer.sheets[sheet_name]
            for col_idx, col in enumerate(df.columns):
                max_len = max(
                    df[col].astype(str).map(len).max(),
                    len(col),
                ) + 2
                worksheet.column_dimensions[
                    chr(65 + col_idx)  # type: ignore[arg-type]
                ].width = min(max_len, 60)

        logger.info(
            "Exported Excel: %s (%d tokens from %d page(s))",
            output_path,
            len(rows),
            len(document_result.pages),
        )
        return output_path

    def to_csv(
        self,
        document_result: DocumentResult,
        output_path: Path | str | None = None,
    ) -> Path:
        """Export OCR results to a CSV file."""
        if output_path is None:
            output_path = self.output_dir / f"{document_result.document_name}_hasil_ocr.csv"
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        rows = []
        for page in document_result.pages:
            for token in page.tokens:
                rows.append({
                    "page": page.page_number + 1,
                    "text": token.text,
                    "confidence": round(token.confidence, 4),
                    "bbox_x1": token.bbox[0],
                    "bbox_y1": token.bbox[1],
                    "bbox_x2": token.bbox[2],
                    "bbox_y2": token.bbox[3],
                })

        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)

        logger.info("Exported CSV: %s (%d tokens)", output_path, len(rows))
        return output_path

    def to_json(
        self,
        document_result: DocumentResult,
        output_path: Path | str | None = None,
        include_layoutlm3: bool = True,
    ) -> Path:
        """Export OCR results as structured JSON (for debugging)."""
        import json

        if output_path is None:
            output_path = self.output_dir / f"{document_result.document_name}_ocr_debug.json"
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        data = {
            "document_name": document_result.document_name,
            "document_path": str(document_result.document_path),
            "total_tokens": document_result.total_tokens,
            "overall_avg_confidence": round(document_result.overall_avg_confidence, 4),
            "pages": [
                {
                    "page_number": p.page_number,
                    "width": p.width,
                    "height": p.height,
                    "avg_confidence": round(p.avg_confidence, 4),
                    "tokens": [
                        {
                            "text": t.text,
                            "confidence": round(t.confidence, 4),
                            "bbox": t.bbox,
                        }
                        for t in p.tokens
                    ],
                }
                for p in document_result.pages
            ],
        }

        if include_layoutlm3 and document_result.layoutlm3_data:
            if isinstance(document_result.layoutlm3_data, list):
                data["layoutlm3"] = [
                    {
                        "image_path": str(doc.image_path),
                        "words": doc.words,
                        "normalized_boxes": doc.normalized_boxes,
                    }
                    for doc in document_result.layoutlm3_data
                ]
            else:
                doc = document_result.layoutlm3_data
                data["layoutlm3"] = {
                    "image_path": str(doc.image_path),
                    "words": doc.words,
                    "normalized_boxes": doc.normalized_boxes,
                }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("Exported JSON: %s", output_path)
        return output_path
