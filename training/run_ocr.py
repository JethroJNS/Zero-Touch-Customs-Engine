from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import PIL.Image
from paddleocr import PaddleOCR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_ocr")


def run_ocr_on_images(
    rendered_dir: Path,
    output_path: Path,
    use_gpu: bool = False,
) -> Dict[str, Any]:
    ocr = PaddleOCR(
        lang="en",
        use_angle_cls=False,
        show_log=False,
        use_gpu=use_gpu,
    )

    image_paths = sorted(rendered_dir.rglob("*.png"))
    results = {}

    for i, img_path in enumerate(image_paths, 1):
        try:
            img = PIL.Image.open(img_path)
            img_array = np.array(img)
            w, h = img.size

            t0 = time.time()
            ocr_result = ocr.ocr(img_array, cls=False)
            elapsed = time.time() - t0

            words = []
            if ocr_result and ocr_result[0]:
                for line in ocr_result[0]:
                    box = line[0]
                    text = line[1][0]
                    conf = line[1][1]
                    x0 = min(p[0] for p in box)
                    y0 = min(p[1] for p in box)
                    x1 = max(p[0] for p in box)
                    y1 = max(p[1] for p in box)
                    words.append({
                        "text": text,
                        "bbox": [x0, y0, x1, y1],
                        "confidence": conf,
                    })

            results[str(img_path)] = {
                "width": w,
                "height": h,
                "words": words,
                "ocr_time": elapsed,
            }

            if i % 50 == 0:
                logger.info(f"  [{i}/{len(image_paths)}] processed")

        except Exception as e:
            logger.warning(f"OCR failed for {img_path}: {e}")
            results[str(img_path)] = {"error": str(e), "words": []}

        if i == 1:
            logger.info(f"First image: {img_path} → {len(words)} words in {elapsed:.1f}s")

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total_words = sum(len(r.get("words", [])) for r in results.values())
    logger.info(f"\nDone: {len(results)} images, {total_words} words → {output_path}")
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rendered-dir", default="./data/rendered")
    parser.add_argument("--output", default="./data/ocr_results.json")
    parser.add_argument("--use-gpu", action="store_true")
    args = parser.parse_args()

    rendered_dir = Path(args.rendered_dir)
    output_path = Path(args.output)

    if not rendered_dir.exists():
        logger.error(f"Rendered dir not found: {rendered_dir}")
        logger.error("Run render_pages.py first!")
        sys.exit(1)

    logger.info(f"OCR on: {rendered_dir}")
    t0 = time.time()
    results = run_ocr_on_images(rendered_dir, output_path, use_gpu=args.use_gpu)
    logger.info(f"Total time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
