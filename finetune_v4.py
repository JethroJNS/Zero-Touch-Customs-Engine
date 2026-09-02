import argparse
import json
import logging
import math
import random
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn
from seqeval.metrics import classification_report, f1_score, precision_score, recall_score
from torch.cuda.amp import autocast, GradScaler
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    get_cosine_schedule_with_warmup,
)

logger = logging.getLogger(__name__)


class LayoutLMv3NerDataset(Dataset):
    def __init__(self, jsonl_path: str, tokenizer,
                 max_length: int = 512,
                 label_to_id: Optional[Dict] = None,
                 id_to_label: Optional[Dict] = None):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.label_to_id = label_to_id or {}
        self.id_to_label = id_to_label or {}
        self.samples: List[Dict] = []
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    self.samples.append(json.loads(line))
        logger.info(f"Loaded {len(self.samples)} samples from {jsonl_path}")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        sample = self.samples[idx]
        words = sample["text"]
        bboxes_raw = sample["bboxes"]
        labels_raw = sample["labels"]

        def to_id(lbl):
            if lbl == "O" or lbl == 0:
                return 0
            if isinstance(lbl, int) and lbl > 0:
                return lbl
            return self.label_to_id.get(lbl, 0)

        split_words, split_bboxes, word_labels = [], [], []
        for w, b, l in zip(words, bboxes_raw, labels_raw):
            parts = w.split()
            if not parts:
                continue
            lbl_id = to_id(l)
            for part in parts:
                split_words.append(part)
                split_bboxes.append(b)
                word_labels.append(lbl_id)

        page_w = sample.get("width", 1) or 1
        page_h = sample.get("height", 1) or 1
        norm_bboxes = [
            [
                max(0, min(1000, int(b[0] / page_w * 1000))),
                max(0, min(1000, int(b[1] / page_h * 1000))),
                max(0, min(1000, int(b[2] / page_w * 1000))),
                max(0, min(1000, int(b[3] / page_h * 1000))),
            ]
            for b in split_bboxes
        ]

        encoding = self.tokenizer(
            text=split_words, boxes=norm_bboxes,
            max_length=self.max_length, padding="max_length",
            truncation=True, return_tensors="pt",
        )

        word_ids = encoding.word_ids()
        aligned_labels = []
        aligned_label_str = []  # For seqeval
        for wid in word_ids:
            if wid is None:
                aligned_labels.append(-100)
                aligned_label_str.append("PAD")
            elif wid < len(word_labels):
                aligned_labels.append(word_labels[wid])
                aligned_label_str.append(self.id_to_label.get(word_labels[wid], "O"))
            else:
                aligned_labels.append(-100)
                aligned_label_str.append("PAD")

        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "bbox": encoding["bbox"].squeeze(0),
            "labels": torch.tensor(aligned_labels, dtype=torch.long),
            "label_str": aligned_label_str,
        }


def collate_fn(batch: List[Dict]) -> Dict[str, Any]:
    # Collate with proper padding for variable-length samples.
    result = {}
    for key in ["input_ids", "attention_mask", "labels"]:
        result[key] = torch.stack([b[key] for b in batch])
    # bbox padding
    max_len = max(b["bbox"].shape[0] for b in batch)
    padded_bboxes = []
    for b in batch:
        pad_len = max_len - b["bbox"].shape[0]
        padded_bboxes.append(
            torch.cat([b["bbox"], torch.zeros(pad_len, 4, dtype=torch.long)], dim=0)
            if pad_len > 0 else b["bbox"]
        )
    result["bbox"] = torch.stack(padded_bboxes)
    # label strings (list of lists)
    result["label_str"] = [b["label_str"] for b in batch]
    return result


@torch.no_grad()
def evaluate_entity_f1(model, dataloader, device, id_to_label: Dict[int, str],
                       desc: str = "Evaluating"):
    # Compute entity-level F1 using seqeval (chunk-level evaluation).
    model.eval()
    all_true_seqs: List[List[str]] = []
    all_pred_seqs: List[List[str]] = []

    for batch in tqdm(dataloader, desc=desc):
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        bbox = batch["bbox"].to(device)
        label_strs: List[List[str]] = batch["label_str"]

        with autocast(enabled=torch.cuda.is_available()):
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, bbox=bbox)
        preds = outputs.logits.argmax(dim=-1).cpu().numpy()

        for seq_preds, seq_label_str in zip(preds, label_strs):
            true_seq: List[str] = []
            pred_seq: List[str] = []
            for p, t in zip(seq_preds, seq_label_str):
                if t != "PAD":
                    true_seq.append(t)
                    pred_seq.append(id_to_label.get(p, "O"))
            if true_seq:
                all_true_seqs.append(true_seq)
                all_pred_seqs.append(pred_seq)

    if not all_true_seqs:
        return {"entity_f1": 0.0, "entity_precision": 0.0, "entity_recall": 0.0,
                "pct_entity_pred": 0.0, "all_o_pct": 100.0}

    f1 = f1_score(all_true_seqs, all_pred_seqs)
    prec = precision_score(all_true_seqs, all_pred_seqs)
    rec = recall_score(all_true_seqs, all_pred_seqs)

    any_entity_pred = sum(1 for s in all_pred_seqs if any(t != "O" for t in s))
    total = len(all_pred_seqs)

    return {
        "entity_f1": round(f1 * 100, 2),
        "entity_precision": round(prec * 100, 2),
        "entity_recall": round(rec * 100, 2),
        "pct_entity_pred": round(any_entity_pred / max(total, 1) * 100, 1),
        "all_o_pct": round((total - any_entity_pred) / max(total, 1) * 100, 1),
        "n_seqs": total,
        "n_seqs_with_pred": any_entity_pred,
        "all_true_seqs": all_true_seqs,
        "all_pred_seqs": all_pred_seqs,
    }


def print_seqeval_report(all_true_seqs, all_pred_seqs, id_to_label):
    # Print seqeval classification report.
    try:
        report = classification_report(all_true_seqs, all_pred_seqs, digits=3)
        print("\n" + "=" * 60)
        print("ENTITY-LEVEL CLASSIFICATION REPORT")
        print("=" * 60)
        print(report)
        print("=" * 60)
    except Exception as e:
        print(f"Could not generate report: {e}")


def train_epoch(model, dataloader, optimizer, scheduler, device,
               class_weights: torch.Tensor, scaler, use_fp16: bool) -> float:
    model.train()
    total_loss = 0.0
    n_batches = 0

    for batch in tqdm(dataloader, desc="Training"):
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        bbox = batch["bbox"].to(device)
        labels = batch["labels"].to(device)

        optimizer.zero_grad()

        with autocast(enabled=use_fp16):
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, bbox=bbox)
            logits = outputs.logits

            loss_fct = nn.CrossEntropyLoss(weight=class_weights, reduction='none')
            loss = loss_fct(logits.view(-1, logits.size(-1)), labels.view(-1))
            mask = (labels.view(-1) != -100).float()
            loss = (loss * mask).sum() / mask.sum().clamp(min=1)

        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optimizer)
        scaler.update()
        scheduler.step()

        total_loss += loss.item()
        n_batches += 1

    return total_loss / n_batches


def parse_args():
    parser = argparse.ArgumentParser(description="LayoutLMv3 v4 — Entity-weighted training")
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--label-map", default=None)  # falls back to data_dir / "label_map.json" if None
    parser.add_argument("--output-dir", default="./models/layoutlmv3-v4")
    parser.add_argument("--model-name", default="microsoft/layoutlmv3-base")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--base-lr", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--entity-weight", type=float, default=5.0)
    parser.add_argument("--o-weight", type=float, default=0.1)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--train-file", default="train.jsonl")
    parser.add_argument("--val-file", default="val.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def main():
    # Setup HuggingFace cache to persist across runs
    import os
    cache_dir = os.environ.get("HF_HOME", "/app/.hf_cache")
    os.makedirs(cache_dir, exist_ok=True)
    os.environ["HF_HOME"] = cache_dir
    os.environ["TRANSFORMERS_CACHE"] = cache_dir
    args = parse_args()
    set_seed(args.seed)

    device = torch.device("cpu" if args.cpu else torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    use_fp16 = not args.cpu and torch.cuda.is_available()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    data_dir = Path(args.data_dir)
    # Auto-detect label map: prefer data/label_map.json (from prepare_data.py pipeline),
    # fall back to label_map_v2.json (pre-built v2 dataset)
    if args.label_map:
        label_map_path = Path(args.label_map)
    elif (data_dir / "label_map.json").exists():
        label_map_path = data_dir / "label_map.json"
    else:
        label_map_path = data_dir / "label_map_v2.json"

    with open(label_map_path, encoding="utf-8") as f:
        label_map = json.load(f)
    label_to_id = label_map["label_to_id"]
    id_to_label = {int(k): v for k, v in label_map["id_to_label"].items()}
    num_labels = label_map["num_labels"]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Device: {device}, fp16: {use_fp16}")
    logger.info(f"Model: {args.model_name}")
    logger.info(f"Labels: {num_labels} ({len(label_to_id)} in map)")
    logger.info(f"Class weights: O={args.o_weight}, entity={args.entity_weight}")
    logger.info(f"Effective batch: {args.batch_size * args.grad_accum}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)

    train_dataset = LayoutLMv3NerDataset(
        data_dir / args.train_file, tokenizer=tokenizer,
        max_length=args.max_length, label_to_id=label_to_id, id_to_label=id_to_label,
    )
    val_dataset = LayoutLMv3NerDataset(
        data_dir / args.val_file, tokenizer=tokenizer,
        max_length=args.max_length, label_to_id=label_to_id, id_to_label=id_to_label,
    )
    logger.info(f"Train: {len(train_dataset)} | Val: {len(val_dataset)}")

    # Label distribution
    dist = Counter()
    for s in train_dataset.samples:
        for l in s["labels"]:
            dist["O" if l == "O" or l == 0 else "entity"] += 1
    total = sum(dist.values())
    logger.info(f"Train label dist: O={dist['O']/total*100:.1f}% entity={dist['entity']/total*100:.1f}%")

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True,
                              num_workers=0, collate_fn=collate_fn)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False,
                            num_workers=0, collate_fn=collate_fn)

    logger.info(f"Loading model: {args.model_name}")
    # Enable transformers logging to show download progress
    import os
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    logging.getLogger("transformers").setLevel(logging.INFO)
    logging.getLogger("huggingface_hub").setLevel(logging.INFO)
    logger.info("Downloading model from HuggingFace (this may take a few minutes on first run)...")
    model = AutoModelForTokenClassification.from_pretrained(
        args.model_name, num_labels=num_labels,
        id2label=id_to_label, label2id=label_to_id,
    )
    model.to(device)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(f"Trainable: {trainable/1e6:.1f}M / {sum(p.numel() for p in model.parameters())/1e6:.1f}M")

    # Class weights: O = o_weight, entities = entity_weight
    class_weights = torch.ones(num_labels, device=device, dtype=torch.float32)
    class_weights[0] = args.o_weight
    class_weights[1:] = args.entity_weight
    logger.info(f"Class weights: {class_weights[:5].tolist()}... (O=0, entities=5x)")

    # Optimizer
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.base_lr, weight_decay=args.weight_decay)

    # Scheduler
    steps_per_epoch = len(train_loader) // args.grad_accum
    total_steps = steps_per_epoch * args.epochs
    warmup_steps = int(total_steps * args.warmup_ratio)
    scheduler = get_cosine_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
    )
    logger.info(f"Steps: {total_steps} total, {warmup_steps} warmup, {args.grad_accum} grad accum")

    scaler = GradScaler(enabled=use_fp16 and torch.cuda.is_available())

    # Training loop
    best_f1 = 0.0
    best_true_seqs = []
    best_pred_seqs = []
    patience_counter = 0
    history = []

    logger.info("=" * 64)
    logger.info(f"Training: {args.epochs} epochs, entity_w={args.entity_weight}, o_w={args.o_weight}")
    logger.info(f"LR={args.base_lr}, warmup={args.warmup_ratio}, eff_batch={args.batch_size * args.grad_accum}")
    logger.info("=" * 64)

    for epoch in range(1, args.epochs + 1):
        logger.info(f"\n--- Epoch {epoch}/{args.epochs} ---")

        train_loss = train_epoch(
            model, train_loader, optimizer, scheduler, device,
            class_weights, scaler, use_fp16
        )

        val_metrics = evaluate_entity_f1(model, val_loader, device, id_to_label)
        val_f1 = val_metrics["entity_f1"]

        logger.info(
            f"  Train loss: {train_loss:.4f} | "
            f"Val entity_F1: {val_f1:.2f}% | "
            f"P: {val_metrics['entity_precision']:.2f}% | "
            f"R: {val_metrics['entity_recall']:.2f}% | "
            f"entity_pred_pct: {val_metrics['pct_entity_pred']:.1f}% | "
            f"all_O_pct: {val_metrics['all_o_pct']:.1f}%"
        )

        history.append({
            "epoch": epoch,
            "train_loss": round(train_loss, 4),
            "entity_f1": val_f1,
            "entity_precision": val_metrics["entity_precision"],
            "entity_recall": val_metrics["entity_recall"],
        })

        # Save best model
        if val_f1 > best_f1:
            best_f1 = val_f1
            best_true_seqs = val_metrics["all_true_seqs"]
            best_pred_seqs = val_metrics["all_pred_seqs"]
            patience_counter = 0
            best_path = output_dir / "best_model"
            if best_path.exists():
                shutil.rmtree(best_path)
            model.save_pretrained(best_path)
            tokenizer.save_pretrained(best_path)
            with open(best_path / "label_map.json", "w", encoding="utf-8") as f:
                json.dump(label_map, f, ensure_ascii=False, indent=2)
            logger.info(f"  *** New best entity_F1={best_f1:.2f}% — saved ***")
        else:
            patience_counter += 1
            logger.info(f"  No improvement. Patience: {patience_counter}/{args.patience}")
            if patience_counter >= args.patience:
                logger.info(f"Early stopping at epoch {epoch}")
                break

    # Print best model report
    if best_true_seqs and best_pred_seqs:
        print_seqeval_report(best_true_seqs, best_pred_seqs, id_to_label)

    # Save final model
    final_path = output_dir / "final_model"
    model.save_pretrained(final_path)
    tokenizer.save_pretrained(final_path)
    with open(output_dir / "history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'='*64}")
    logger.info(f"Best entity F1: {best_f1:.2f}%")
    logger.info(f"Models saved to: {output_dir}")
    logger.info(f"{'='*64}")


if __name__ == "__main__":
    main()
