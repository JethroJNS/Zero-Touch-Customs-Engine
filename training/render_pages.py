from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # website/

import fitz  # PyMuPDF
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("render")

DATASET_DIR = Path(__file__).parent.parent / "training_dataset"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "rendered"


def render_all_pages() -> tuple[int, int]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    shipments = sorted(d for d in DATASET_DIR.iterdir() if d.is_dir() and not d.name.startswith("."))
    total_rendered = 0
    total_pages = 0

    for shipment in shipments:
        shipment_out = OUTPUT_DIR / shipment.name
        shipment_out.mkdir(exist_ok=True)

        for pdf_path in sorted(shipment.glob("*.pdf")):
            doc = fitz.open(str(pdf_path))
            num_pages = len(doc)
            for page_num in range(num_pages):
                page = doc[page_num]
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_name = f"{pdf_path.stem}_p{page_num}.png"
                pix.save(str(shipment_out / img_name))
                total_pages += 1
            doc.close()
            logger.info(f"  {pdf_path.name}: {num_pages} pages")

        total_rendered += 1
        logger.info(f"[{total_rendered}/{len(shipments)}] {shipment.name}")

    return total_pages, len(shipments)


def main():
    logger.info(f"Rendering PDFs: {DATASET_DIR} → {OUTPUT_DIR}")
    t0 = time.time()
    pages, shipments = render_all_pages()
    elapsed = time.time() - t0
    logger.info(f"\nDone: {pages} pages from {shipments} shipments in {elapsed:.1f}s")
    logger.info(f"Images: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
