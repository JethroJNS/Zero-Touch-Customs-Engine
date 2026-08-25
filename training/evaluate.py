from __future__ import annotations

import argparse
import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any

import torch
import numpy as np
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForTokenClassification, AutoProcessor
from tqdm import tqdm

logger = logging.getLogger("evaluate")


class EvalDataset(Dataset):
    def __init__(self, jsonl_path, tokenizer, max_length=512):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.samples = []
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    self.samples.append(json.loads(line))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sample = self.samples[idx]
        words = sample["text"]
        bboxes = sample["bboxes"]
        labels = sample["labels"]

        encoding = self.tokenizer(
            words, is_split_into_words=True,
            max_length=self.max_length, padding="max_length",
            truncation=True, return_tensors="pt",
        )
        word_ids = encoding.word_ids()
        aligned_labels = []
        for word_id in word_ids:
            if word_id is None:
                aligned_labels.append(-100)
            else:
                aligned_labels.append(labels[word_id] if word_id < len(labels) else -100)

        encoding = {k: v.squeeze(0) for k, v in encoding.items()}
        encoding["labels"] = torch.tensor(aligned_labels)
        encoding["bboxes"] = torch.tensor(
            bboxes[:self.max_length] if len(bboxes) <= self.max_length
            else [[0,0,0,0]]*self.max_length
        )
        return encoding


def collate_fn(batch):
    result = {}
    for key in batch[0]:
        if key == "bboxes":
            max_len = max(b["bboxes"].shape[0] for b in batch)
            padded = []
            for b in batch:
                pad_len = max_len - b["bboxes"].shape[0]
                padded.append(
                    torch.cat([b["bboxes"], torch.zeros(pad_len, 4)], dim=0)
                    if pad_len > 0 else b["bboxes"]
                )
            result[key] = torch.stack(padded)
        else:
            result[key] = torch.stack([b[key] for b in batch])
    return result


def compute_metrics(
    all_preds: List[int],
    all_labels: List[int],
    id_to_label: Dict[int, str],
) -> Dict[str, Any]:
    # Group by sample
    # For simplicity, compute token-level then aggregate
    entity_stats: Dict[str, Dict] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    O_id = 0

    # Also compute exact match (full span)
    span_preds: Dict[str, int] = {}
    span_labels: Dict[str, int] = {}

    prev_entity = None
    prev_start = 0
    for i, (pred, label) in enumerate(zip(all_preds, all_labels)):
        if label == -100:
            continue

        pred_name = id_to_label.get(pred, "O")
        label_name = id_to_label.get(label, "O")

        # Token-level counts
        if pred != label:
            if label != O_id:
                entity_stats[label_name]["fn"] += 1
            if pred != O_id:
                entity_stats[pred_name]["fp"] += 1

        # Build span for exact match
        is_pred_entity = pred != O_id
        is_label_entity = label != O_id

        # Entity span tracking (simplified: adjacent same-entity tokens)
        # Token-level correction
        if label != O_id:
            entity_stats[label_name]["tp"] += 1

    # Recalculate properly
    entity_stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    for i, (pred, label) in enumerate(zip(all_preds, all_labels)):
        if label == -100:
            continue
        pred_name = id_to_label.get(pred, "O")
        label_name = id_to_label.get(label, "O")

        if pred == label:
            if label != O_id:
                entity_stats[label_name]["tp"] += 1
        else:
            if label != O_id:
                entity_stats[label_name]["fn"] += 1
            if pred != O_id:
                entity_stats[pred_name]["fp"] += 1

    # Per-entity P/R/F1
    results = {"entity_metrics": {}}
    total_tp = total_fp = total_fn = 0

    for entity, counts in sorted(entity_stats.items()):
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        total_tp += tp
        total_fp += fp
        total_fn += fn
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-8)
        results["entity_metrics"][entity] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
        }

    # Overall
    overall_prec = total_tp / max(total_tp + total_fp, 1)
    overall_rec = total_tp / max(total_tp + total_fn, 1)
    overall_f1 = 2 * overall_prec * overall_rec / max(overall_prec + overall_rec, 1e-8)
    results["overall"] = {
        "precision": round(overall_prec, 4),
        "recall": round(overall_rec, 4),
        "f1": round(overall_f1, 4),
    }
    results["total_tokens"] = len([l for l in all_labels if l != -100])
    results["total_entities"] = total_tp + total_fn

    return results


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate LayoutXLM NER model")
    parser.add_argument("--model", required=True, help="Path to model or HuggingFace name")
    parser.add_argument("--data-dir", default="./data", help="Directory with val.jsonl")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--output", default=None, help="Save results to JSON file")
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    device = torch.device("cpu") if args.cpu else torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    data_dir = Path(args.data_dir)

    # Load label map
    with open(data_dir / "label_map.json", encoding="utf-8") as f:
        label_map = json.load(f)
    id_to_label = label_map["id_to_label"]

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    # Dataset
    val_dataset = EvalDataset(
        data_dir / "val.jsonl",
        tokenizer=tokenizer,
        max_length=args.max_length,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size,
        shuffle=False, num_workers=0, collate_fn=collate_fn,
    )

    logger.info(f"Model: {args.model}")
    logger.info(f"Val samples: {len(val_dataset)}")
    logger.info(f"Device: {device}")

    # Load model
    model = AutoModelForTokenClassification.from_pretrained(args.model)
    model.to(device)
    model.eval()

    # Predict
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for batch in tqdm(val_loader, desc="Evaluating"):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            bboxes = batch["bboxes"].to(device)
            labels = batch["labels"]

            outputs = model(input_ids=input_ids, attention_mask=attention_mask, bbox=bboxes)
            preds = outputs.logits.argmax(dim=-1).cpu().tolist()

            for pred_seq, label_seq in zip(preds, labels.tolist()):
                for p, l in zip(pred_seq, label_seq):
                    all_preds.append(p)
                    all_labels.append(l)

    # Compute metrics
    results = compute_metrics(all_preds, all_labels, id_to_label)

    # Print
    print("\n" + "=" * 70)
    print(f"  EVALUATION — {args.model}")
    print("=" * 70)
    print(f"  Total tokens:       {results['total_tokens']:,}")
    print(f"  Total entities:    {results['total_entities']:,}")
    print(f"\n  OVERALL:")
    print(f"  Precision:         {results['overall']['precision']:.2%}")
    print(f"  Recall:           {results['overall']['recall']:.2%}")
    print(f"  F1 Score:         {results['overall']['f1']:.2%}")

    em = results.get("entity_metrics", {})
    entity_rows = [
        (name, m) for name, m in em.items()
        if name != "O" and (m["tp"] + m["fn"] + m["fp"]) > 0
    ]

    if entity_rows:
        print(f"\n  PER-ENTITY F1 (sorted by F1):")
        print(f"  {'Entity':<30} {'P':>7} {'R':>7} {'F1':>7} {'Support':>8}")
        print(f"  {'-'*30} {'-'*7} {'-'*7} {'-'*7} {'-'*8}")
        for name, m in sorted(entity_rows, key=lambda x: -x[1]["f1"]):
            support = m["tp"] + m["fn"]
            print(f"  {name:<30} {m['precision']:>7.2%} {m['recall']:>7.2%} {m['f1']:>7.2%} {support:>8}")
    print("=" * 70)

    # Save
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Results → {out_path}")


if __name__ == "__main__":
    main()
