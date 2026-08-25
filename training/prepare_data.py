from __future__ import annotations

import json
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.training.dataset import (
    LabeledDatasetBuilder,
    summarize_dataset,
    LABEL_TO_ID,
    NUM_LABELS,
)
from typing import Dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("prepare_data")

DATASET_DIR = Path(__file__).parent.parent / "training_dataset"
OUTPUT_DIR = Path(__file__).parent.parent / "data"
TRAIN_RATIO = 0.8


def process_all_shipments(
    dataset_dir: Path,
    builder: LabeledDatasetBuilder,
) -> tuple[list, list, dict]:
    shipment_dirs = sorted([
        d for d in dataset_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ])

    all_pages = []
    failed = []

    for i, shipment_dir in enumerate(shipment_dirs, 1):
        logger.info(f"[{i}/{len(shipment_dirs)}] Processing: {shipment_dir.name}")
        try:
            pages = builder.process_shipment(shipment_dir)
            all_pages.extend(pages)
            logger.info(f"  → {len(pages)} labeled pages")
        except Exception as e:
            logger.warning(f"  ✗ Failed: {e}")
            failed.append(shipment_dir.name)

    stats = summarize_dataset(all_pages)
    return all_pages, failed, stats


def train_val_split(
    pages: list,
    train_ratio: float = 0.8,
    seed: int = 42,
) -> tuple[list, list]:
    random.seed(seed)

    shipment_pages: dict = {}
    for page in pages:
        shipment_pages.setdefault(page.shipment_id, []).append(page)

    shipment_ids = list(shipment_pages.keys())
    random.shuffle(shipment_ids)

    n_train = int(len(shipment_ids) * train_ratio)
    train_ids = set(shipment_ids[:n_train])
    val_ids = set(shipment_ids[n_train:])

    train_pages = [p for p in pages if p.shipment_id in train_ids]
    val_pages = [p for p in pages if p.shipment_id in val_ids]

    return train_pages, val_pages


def save_jsonl(pages: list, builder: LabeledDatasetBuilder, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for page in pages:
            record = builder.to_layoutxlm_dict(page)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info(f"Saved {len(pages)} pages → {output_path}")


def save_stats(stats: dict, failed: list, output_path: Path) -> None:
    stats["failed_shipments"] = failed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    logger.info(f"Stats → {output_path}")


def save_label_map(output_dir: Path) -> None:
    label_map = {
        "label_to_id": LABEL_TO_ID,
        "id_to_label": {v: k for k, v in LABEL_TO_ID.items()},
        "num_labels": NUM_LABELS,
    }
    path = output_dir / "label_map.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(label_map, f, ensure_ascii=False, indent=2)
    logger.info(f"Label map → {path}")


def print_summary(pages: list, stats: dict) -> None:
    print("\n" + "=" * 60)
    print("  DATASET SUMMARY")
    print("=" * 60)
    print(f"  Total labeled pages:  {stats['total_pages']}")
    print(f"  Total words:          {stats['total_words']:,}")
    print(f"  Labeled words:        {stats['labeled_words']:,} "
          f"({stats['label_coverage']:.1%})")
    print(f"  Total entity spans:   {stats['total_spans']}")
    print(f"\n  Entity distribution (top 20):")
    for entity, count in list(stats["entity_counts"].items())[:20]:
        bar = "█" * min(count, 50)
        print(f"    {entity:<30} {count:>4}  {bar}")
    print("=" * 60)


def main() -> None:
    import json as _json
    logger.info("=" * 60)
    logger.info("  LayoutXLM Data Preparation")
    logger.info("=" * 60)

    ocr_results: Dict = {}
    ocr_json = OUTPUT_DIR / "ocr_results.json"
    if ocr_json.exists():
        logger.info(f"Loading pre-computed OCR results: {ocr_json}")
        with open(ocr_json, encoding="utf-8") as f:
            ocr_results = _json.load(f)
        logger.info(f"  → {len(ocr_results)} images with OCR results")

    builder = LabeledDatasetBuilder(
        similarity_threshold=0.75,
        use_paddle_fallback=False,
    )
    builder.reader.ocr_results = ocr_results

    all_pages, failed, stats = process_all_shipments(DATASET_DIR, builder)

    if not all_pages:
        logger.error("No labeled pages found. Check dataset.")
        return

    logger.info(f"\n✓ Processed {len(all_pages)} labeled pages "
                f"from {len(all_pages) - len(failed)} shipments")

    # Train/val split (by shipment)
    train_pages, val_pages = train_val_split(all_pages, TRAIN_RATIO)
    logger.info(f"Train: {len(train_pages)} pages, Val: {len(val_pages)} pages")

    # Save outputs
    save_jsonl(train_pages, builder, OUTPUT_DIR / "train.jsonl")
    save_jsonl(val_pages, builder, OUTPUT_DIR / "val.jsonl")
    save_stats(stats, failed, OUTPUT_DIR / "stats.json")
    save_label_map(OUTPUT_DIR)

    # Print summary
    print_summary(all_pages, stats)

    # Verify JSONL integrity
    for split, pages in [("train", train_pages), ("val", val_pages)]:
        path = OUTPUT_DIR / f"{split}.jsonl"
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        logger.info(f"Verified {split}.jsonl: {len(lines)} records")

    logger.info("\n✓ Data preparation complete!")
    logger.info(f"  Output: {OUTPUT_DIR}/")
    logger.info(f"  Next: python finetune_v4.py --data-dir {OUTPUT_DIR} --output-dir ml/models/layoutlmv3-customs")


if __name__ == "__main__":
    main()
