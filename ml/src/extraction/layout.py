from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Callable



if "torch" not in sys.modules:
    try:
        import torch  # noqa: F401
    except OSError:
        pass  

logger = logging.getLogger(__name__)

# Map ke ExtractionStrategy.LAYOUT_ENTITIES di config.py.
@dataclass
class LayoutEntity:
    # Entity hasil ekstraksi LayoutXLM.
    label: str          # Label dari model
    value: str
    confidence: float
    bbox: Tuple[float, float, float, float] = (0, 0, 0, 0)
    page: int = 0
    source: str = "layoutxlm"  

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "page": self.page,
            "source": self.source,
        }


# PEMETAAN LABEL
LAYOUT_TO_NER_MAP: Dict[str, str] = {
    "invoice_number": "invoice_number",
    "invoice_date":   "invoice_date",
    "bl_number":     "bl_number",
    "bl_date":       "bl_date",
    "seller_name":    "seller_name",
    "seller_address": "seller_address",
    "buyer_name":    "buyer_name",
    "buyer_address": "buyer_address",
    "shipper_name":  "shipper_name",
    "shipper_address": "shipper_address",
    "consignee_name": "consignee_name",
    "consignee_address": "consignee_address",
    "notify_party_name": "notify_party_name",
    "notify_party_address": "notify_party_address",
    "vessel_name":   "vessel_name",
    "voyage_number": "voyage_number",
    "port_of_loading": "port_of_loading",
    "port_of_discharge": "port_of_discharge",
    "place_of_receipt": "place_of_receipt",
    "place_of_delivery": "place_of_delivery",
    "currency":      "currency",
    "incoterms":     "incoterms",
    "freight_term":  "freight_term",
    "country_of_origin": "country_of_origin",
    "country_of_destination": "country_of_destination",
    "total_amount":  "total_amount",
    "total_quantity": "total_quantity",
    "total_net_weight": "total_net_weight",
    "total_gross_weight": "total_gross_weight",
    "number_of_packages": "number_of_packages",
    "cbm":           "cbm",
    "container_number": "container_number",
    "seal_number":    "seal_number",
    "item_description": "item_description",
    "item_hs_code":   "item_hs_code",
    "item_quantity":   "item_quantity",
    "item_unit":      "item_unit",
    "item_unit_price": "item_unit_price",
    "item_amount":    "item_amount",
    "item_net_weight": "item_net_weight",
}


# FALLBACK TEXT-BASED
_INVOICE_NUMBER_RE = re.compile(
    r"(?:INV(?:OICE)?\.?|Invoice\s*(?:No\.?|Number|#)\s*[:\s]*)([A-Z0-9][\-A-Z0-9/]{3,40})",
    re.IGNORECASE,
)
_BL_NUMBER_RE = re.compile(
    r"(?:BL\s*(?:No\.?|Number)\s*[:\s#]*|Bill\s+of\s+Lading\s*[:\s#]*)([A-Z0-9]{5,30})",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"(?:Date|Tanggal|Issued)[:\s]*(\d{1,2}[\s.\-/]"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,.\-/]*\d{2,4})",
    re.IGNORECASE,
)
_CONTAINER_RE = re.compile(r"\b([A-Z]{4}\d{7})\b")
_SEAL_RE = re.compile(r"Seal(?:\s*No\.?|Number)?[:\s]*([A-Z0-9]{4,20})", re.IGNORECASE)
_VESSEL_RE = re.compile(
    r"(?:Vessel|STEAMSHIP|M/V\s*|MV\s*|M/S\s*)[:\s]*([A-Z][A-Z\s]{2,35})",
    re.IGNORECASE,
)
_PORT_RE = re.compile(
    r"(?:Port\s+(?:of\s+)?(?:Load|Origin|Discharge|Destination)|From|To)[:\s]*([A-Z][A-Z\s]{2,25})",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(r"\b(USD|CNY|EUR|GBP|JPY|SGD|IDR|AUD|KRW)\b")
_INCOTERMS_RE = re.compile(
    r"\b(FOB|CIF|CFR|EXW|DAP|DDP|FCA|CPT|CIP|FAS|DAT)\b",
    re.IGNORECASE,
)
_COUNTRY_RE = re.compile(
    r"(?:Country\s+(?:of\s+)?(?:Origin|Destination)|Made\s+in)[:\s]*([A-Z][A-Z\s]{2,25})",
    re.IGNORECASE,
)
_SELLER_RE = re.compile(
    r"^([A-Z][A-Z]{2,}[A-Za-z\s.,\-']{2,35}?(?:CO\.?|LTD\.?|INC\.?|LLC|PTE|CORP))",
    re.MULTILINE,
)
_BUYER_RE = re.compile(
    r"(?:Buyer|Consignee|Importer)[:\s]+([A-Z][A-Z\s.,\-']{3,50}?)(?=\s+(?:Invoice|No\.|DATE|TEL|FAX|JL\.|EMAIL|$))",
    re.IGNORECASE,
)
_BUYER_PT_RE = re.compile(r"(PT\s+[A-Z][A-Z\s]{3,50}(?:CO\.?|LTD\.?|INC\.?)?\.?)")

# PATTERN PARTY BL
# Akhiran perusahaan valid
_BL_COMPANY_SUFFIX = r"(?:CO\.?|LTD\.?|INC\.?|LLC|PTE|CORP|CORPORATION|MANUFACTURING)"

# Multi-word company
_BL_COMPANY_MULTI_RE = re.compile(
    r"\b([A-Z][A-Z][A-Za-z \t]{1,50}?(?<! AS\b)(?:"
    r"CORPORATION|LIMITED|LTD\.?|INC\.?|CO\.?|LLC|MANUFACTURING)"
    r")\b",
    re.IGNORECASE,
)

# Pattern perusahaan PT
_BL_PT_RE = re.compile(
    r"(PT\.?[ \t]+[A-Za-z0-9][A-Za-z0-9 \t]{2,50}(?:CO\.?,?[ \t]*LTD\.?|CO\.?|LTD\.?|INC\.?)?)"
)

# Indikator alamat Indonesia/Korea
_BL_ASIA_ADDR_RE = re.compile(
    r"(?:JL\.?|KENARI|RAYA|BLOK|G3|CIKARANG|DELTA|SILICON|CICU|"
    r"HARYONO|KAV\.?|PANCORAN|JAKARTA|BEKASI|INDONESIA|"
    r"(?<![A-Z-])SEOUL|(?<![A-Z-])KOREA|(?<![A-Z-])BUSAN|TOWERS|FLOOR|CHEONGGYECH|ROAD|"
    r"(?<![A-Z-])BANGKOK|(?<![A-Z-])THAILAND|SUKHUMVIT|KLONGTOEY)",
    re.IGNORECASE,
)

# Notify label (OCR-robust): handles "Notify Party" → "Not i fy Par ty"
_BL_NOTIFY_LABEL_RE = re.compile(
    r"(?i)(NOTIFY|PAR ?TY|NON.?NEGOTIABLE|AS ?NOTIFY|IFY)", re.IGNORECASE
)

# Consignee label (OCR-robust): handles "Consignee" → "Consigree"
_BL_CONSIGNEE_LABEL_RE = re.compile(
    r"(?i)(CONSIG|IMPORTER|BUYER)", re.IGNORECASE
)


class LayoutExtractor:
    # LayoutXLM-based header entity extractor.
    def __init__(
        self,
        model_path: Optional[str] = None,
        use_gpu: bool = False,
        confidence_threshold: float = 0.05,
    ):
        self.model_path = model_path
        self.use_gpu = use_gpu
        self.confidence_threshold = confidence_threshold
        self._model = None
        self._tokenizer = None
        self._model_loaded = False
        self._layout_model = None  # Lazy import

    @property
    def available(self) -> bool:
        # True if LayoutXLM model is available.
        return self._model_loaded

    def _try_load_model(self) -> bool:
        # Attempt to load the trained LayoutLMv3 model. Returns True on success.
        if self._model_loaded:
            return True

        try:
            import json
            import os
            from transformers import AutoModelForTokenClassification, AutoTokenizer
            from pathlib import Path

            device = "cuda" if (self.use_gpu and torch.cuda.is_available()) else "cpu"

            if self.model_path:
                model_dir = Path(self.model_path)
            else:
                # Check MODEL_PATH environment variable
                model_path_env = os.environ.get("MODEL_PATH", "")
                if model_path_env:
                    model_dir = Path(model_path_env)
                else:
                    # Default: trained LayoutLMv3 v4 model (63.13% entity F1)
                    model_dir = Path(__file__).parent.parent.parent / "models" / "layoutlmv3-v4" / "best_model"

            if not model_dir.exists():
                logger.warning(
                    f"Trained LayoutLMv3 model not found at {model_dir}. "
                    "Using text-based fallback."
                )
                return False

            # Load tokenizer and model
            self._tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
            self._model = AutoModelForTokenClassification.from_pretrained(str(model_dir))

            # Load label map dari model directory (model.saved dengan model)
            label_map_path = model_dir / "label_map.json"
            if label_map_path.exists():
                with open(label_map_path) as f:
                    raw_map = json.load(f)
                self._id_to_label = {int(k): v for k, v in raw_map["id_to_label"].items()}
                self._label_to_id = raw_map["label_to_id"]
            else:
                self._id_to_label = self._model.config.id2label
                self._label_to_id = self._model.config.label2id

            self._model.to(device)
            self._model.eval()
            self._device = device
            self._model_loaded = True
            logger.info(f"Trained LayoutLMv3 model loaded from {model_dir} (device={device})")
            return True

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.warning(
                f"LayoutLMv3 model unavailable ({type(e).__name__}: {e}). "
                "Using text-based fallback."
                + (f"\n  Traceback: {tb[:500]}" if "shm.dll" in str(e) else "")
            )
            self._model_loaded = False
            return False

    def extract(
        self,
        ocr_result,
        doc_type: str = "CI",
    ) -> Dict[str, List[LayoutEntity]]:
        # Extract layout-aware entities from OCR results.
        if not self._model_loaded:
            self._try_load_model()

        if self._model_loaded:
            return self._extract_model(ocr_result, doc_type)
        else:
            return self._extract_fallback(ocr_result, doc_type)

    def _extract_model(
        self,
        ocr_result,
        doc_type: str,
    ) -> Dict[str, List[LayoutEntity]]:
        # Extract using trained LayoutLMv3 model.
        all_items = []
        for page in ocr_result.pages:
            for item in page.words:
                all_items.append({
                    "text": item.text,
                    "bbox": item.bbox,
                    "page": page.page_num,
                })

        if not all_items:
            return {}

        # Group by page
        page_groups: Dict[int, List] = {}
        for item in all_items:
            page_groups.setdefault(item["page"], []).append(item)

        all_entities: List[LayoutEntity] = []

        for page_num, items in page_groups.items():
            page_entities = self._extract_page_model(items, page_num, doc_type)
            all_entities.extend(page_entities)

        # BL party post-processing
        if doc_type == "BL" and all_entities:
            bl_party_labels: set = set()
            text = ocr_result.full_text
            def add_bl(label: str, value: str, confidence: float):
                if value and len(value.strip()) >= 2:
                    all_entities.append(LayoutEntity(
                        label=label, value=value.strip(),
                        confidence=confidence,
                        source="bl_party_fallback",
                    ))
            self._extract_bl_parties(text, add_bl, bl_party_labels)

        # Deduplicate
        seen = set()
        deduped = []
        for e in all_entities:
            key = (e.label, e.value)
            if key not in seen:
                seen.add(key)
                deduped.append(e)

        # Supplement missing party fields dengan text-based fallback
        extracted_labels: Dict[str, float] = {e.label: e.confidence for e in deduped}
        text = ocr_result.full_text

        def add_supplement(label: str, value: str, confidence: float):
            existing_conf = extracted_labels.get(label, 0.0)
            # Cek jika entity yang ada terlihat seperti label
            existing_is_label = False
            for ex_val, ex_conf in [(e.value, e.confidence) for e in deduped if e.label == label]:
                # Label-like: contains "/"
                if "/" in ex_val or re.match(r"^[A-Z][A-Za-z\s/]+$", ex_val):
                    existing_is_label = True
                    break
            # Add jika: tidak ada, OR existing label-like, OR existing conf <= supplement conf
            if value and len(value.strip()) >= 3 and (
                existing_conf < 0.01
                or existing_is_label
                or confidence >= existing_conf
            ):
                # Jika replace existing entities (label-like atau low conf), remove dulu
                if existing_conf >= 0.01:
                    deduped[:] = [e for e in deduped if e.label != label]
                deduped.append(LayoutEntity(
                    label=label, value=value.strip(),
                    confidence=confidence,
                    bbox=(0, 0, 0, 0),
                    page=1,
                ))
                extracted_labels[label] = confidence

        # Seller dari CI: cari baris pertama yang terlihat seperti nama perusahaan
        if doc_type == "CI" and extracted_labels.get("seller_name", 0.0) < 0.70:
            lines = text.split("\n")
            for i, line in enumerate(lines[:8]):
                line = line.strip()
                if len(line) < 8:
                    continue
                if re.match(r"^[A-Z][A-Z\s/]{0,20}:", line):
                    continue
                if any(k in line.upper() for k in ["INVOICE", "DATE", "NO.:", "NUMBER", "AND", "FOR"]):
                    continue
                if re.match(r"^\d", line):
                    continue
                if any(k in line.upper() for k in ["JL.", "JL ", "ROAD", "STREET", "FLOOR", "TOWER", "BLOK"]):
                    continue
                if "/" in line and not line.endswith(".CO") and not line.endswith(".LTD") and not line.endswith(".INC"):
                    continue
                cleaned = re.sub(r"\s+\d{4}[-/]\d{2}[-/]\d{2}\s*$", "", line).strip()
                if len(cleaned) >= 8:
                    add_supplement("seller_name", cleaned, 0.65)
                    break

        # Buyer from CI: look for "BUYER:" or "IMPORTER:" label
        if doc_type == "CI" and extracted_labels.get("buyer_name", 0.0) < 0.70:
            buyer_pattern = re.compile(
                r"(?:BUYER|IMPORTER|CONSIGNEE|PEMBELI)[:\s]+([A-Z][A-Z\s.,\-']{3,60}?)"
                r"(?=\s*(?:INVOICE|DATE|JL\.|TEL|FAX|TAX|ADDRESS|NO\.|KS\.|,INDUSTRIAL|,BLOK|\n|$))",
                re.IGNORECASE,
            )
            for m in buyer_pattern.finditer(text):
                name = m.group(1).strip()
                if len(name) >= 5:
                    add_supplement("buyer_name", name, 0.75)
                    break

        # PL weight supplement
        if doc_type == "PL":
            pl_text = text
            # Cari TOTAL line (bisa "TOTAL", "Total", "TOTAL:", dll.)
            for line in pl_text.split('\n'):
                stripped = line.strip()
                if stripped.upper().startswith('TOTAL'):
                    nums = re.findall(r'[\d,]+\.?\d*', stripped)
                    valid_nums = []
                    for n in nums:
                        clean = n.replace(',', '')
                        try:
                            val = float(clean)
                            if val > 100:
                                valid_nums.append(val)
                        except ValueError:
                            pass
                    if len(valid_nums) >= 2:
                        netto = valid_nums[-2]
                        brutto = valid_nums[-1]
                        if 100 < netto < 500000 and 100 < brutto < 500000:
                            deduped[:] = [e for e in deduped
                                          if e.label not in ('total_net_weight', 'total_gross_weight')]
                            deduped.append(LayoutEntity(
                                label='total_net_weight', value=f'{netto:.2f}',
                                confidence=0.97, bbox=(0, 0, 0, 0), page=1,
                                source='pl_weight_fallback',
                            ))
                            deduped.append(LayoutEntity(
                                label='total_gross_weight', value=f'{brutto:.2f}',
                                confidence=0.97, bbox=(0, 0, 0, 0), page=1,
                                source='pl_weight_fallback',
                            ))
                            extracted_labels['total_net_weight'] = 0.97
                            extracted_labels['total_gross_weight'] = 0.97
                    break

        # BL "SAME AS CONSIGNEE" -> resolve ke actual consignee name
        if doc_type == "BL":
            for e in deduped:
                if e.label == "notify_party_name" and e.value.upper().startswith("SAME AS"):
                    if e.label == "notify_party_name":
                        for ce in deduped:
                            if ce.label == "consignee_name":
                                e.value = ce.value
                                e.confidence = 0.92
                                e.source = "bl_notify_resolved"
                                extracted_labels["notify_party_name"] = 0.92
                                break

        # Group by normalized name
        return self._group_entities(deduped)

    def _extract_page_model(
        self,
        items: List[Dict],
        page_num: int,
        doc_type: str,
    ) -> List[LayoutEntity]:
        # Run LayoutLMv3 inference on a single page.
        import torch

        texts = [item["text"] for item in items]
        bboxes = [item["bbox"] for item in items]

        WINDOW_SIZE = 200
        STRIDE = 100
        entities = []

        start = 0
        while start < len(texts):
            end = min(start + WINDOW_SIZE, len(texts))
            window_texts = texts[start:end]
            window_bboxes = bboxes[start:end]

            # Split setiap text span jadi words, duplicate bbox per word.
            words = []
            word_bboxes = []
            for t, b in zip(window_texts, window_bboxes):
                parts = t.split()
                if not parts:
                    continue
                for part in parts:
                    words.append(part)
                    word_bboxes.append(b)

            if not words:
                start += STRIDE
                continue

            # Normalize bboxes ke [0, 1000] (LayoutLMv3 convention)
            page_w = max((b[2] for b in word_bboxes), default=1)
            page_h = max((b[3] for b in word_bboxes), default=1)
            if page_w == 0: page_w = 1
            if page_h == 0: page_h = 1

            norm_bboxes = [
                [
                    max(0, min(1000, int(b[0] / page_w * 1000))),
                    max(0, min(1000, int(b[1] / page_h * 1000))),
                    max(0, min(1000, int(b[2] / page_w * 1000))),
                    max(0, min(1000, int(b[3] / page_h * 1000))),
                ]
                for b in word_bboxes
            ]

            try:
                encoding = self._tokenizer(
                    text=words,
                    boxes=norm_bboxes,
                    max_length=512,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt",
                )
            except Exception:
                start += STRIDE
                continue

            for k, v in encoding.items():
                if hasattr(v, "to"):
                    encoding[k] = v.to(self._device)

            with torch.no_grad():
                outputs = self._model(**encoding)
                logits = outputs.logits

            probs = torch.softmax(logits, dim=-1)
            preds = torch.argmax(logits, dim=-1)

            # Convert predictions -> entities
            page_entities = self._preds_to_entities(
                preds[0], probs[0], encoding,
                words, word_bboxes, page_num,
            )
            entities.extend(page_entities)
            start += STRIDE

        return entities

    def _preds_to_entities(
        self,
        preds,
        probs,
        encoding,
        texts: List[str],
        bboxes: List,
        page_num: int,
    ) -> List[LayoutEntity]:
        # Convert LayoutLMv3 fine-tuned predictions to LayoutEntity objects.
        id2label = self._id_to_label
        entities = []
        word_ids = encoding.word_ids(batch_index=0)

        current_label = None
        current_value_parts = []
        current_bbox = (0, 0, 0, 0)
        current_conf = 0.0
        current_word_idx = None

        for idx, (pred_id, prob_row) in enumerate(zip(preds, probs)):
            word_idx = word_ids[idx]
            if word_idx is None:
                continue  # Skip special tokens (CLS, SEP, PAD)

            # Skip duplicate predictions untuk word original yang sama.
            if word_idx == current_word_idx:
                continue

            label = id2label.get(int(pred_id), "O")
            confidence = float(prob_row[pred_id])

            # Filter by confidence threshold
            if confidence < self.confidence_threshold:
                label = "O"

            if label == "O":
                if current_label and current_value_parts:
                    value = " ".join(current_value_parts).strip()
                    if value:
                        entities.append(LayoutEntity(
                            label=current_label,
                            value=value,
                            confidence=current_conf,
                            bbox=current_bbox,
                            page=page_num,
                        ))
                current_label = None
                current_value_parts = []
                continue

            if label.startswith("B-"):
                # Flush previous entity
                if current_label and current_value_parts:
                    value = " ".join(current_value_parts).strip()
                    if value:
                        entities.append(LayoutEntity(
                            label=current_label,
                            value=value,
                            confidence=current_conf,
                            bbox=current_bbox,
                            page=page_num,
                        ))

                entity_name = label[2:]
                current_label = entity_name
                current_value_parts = [texts[word_idx]] if word_idx < len(texts) else []
                current_bbox = bboxes[word_idx] if word_idx < len(bboxes) else (0, 0, 0, 0)
                current_conf = confidence
                current_word_idx = word_idx

            elif label.startswith("I-") and current_label:
                entity_name = label[2:]
                if entity_name == current_label:
                    if word_idx < len(texts):
                        current_value_parts.append(texts[word_idx])
                    current_conf = max(current_conf, confidence)
                    current_word_idx = word_idx
                # Jika I- label tidak match B- yang aktif, flush dan mulai baru
                else:
                    if current_value_parts:
                        value = " ".join(current_value_parts).strip()
                        if value:
                            entities.append(LayoutEntity(
                                label=current_label,
                                value=value,
                                confidence=current_conf,
                                bbox=current_bbox,
                                page=page_num,
                            ))
                    current_label = entity_name
                    current_value_parts = [texts[word_idx]] if word_idx < len(texts) else []
                    current_bbox = bboxes[word_idx] if word_idx < len(bboxes) else (0, 0, 0, 0)
                    current_conf = confidence
                    current_word_idx = word_idx

        # Final flush
        if current_label and current_value_parts:
            value = " ".join(current_value_parts).strip()
            if value:
                entities.append(LayoutEntity(
                    label=current_label,
                    value=value,
                    confidence=current_conf,
                    bbox=current_bbox,
                    page=page_num,
                ))

        # Post-process: deduplicate and clean entity list
        entities = self._deduplicate_entities(entities)

        return entities

    def _deduplicate_entities(
        self,
        entities: List[LayoutEntity],
    ) -> List[LayoutEntity]:
        # Three-pass cleaning for LayoutXLM token-per-word outputs:
        # 1. Merge same-label entities sharing the SAME bbox → full multi-word names
        # 2. Merge consecutive same-label fragments on the SAME line (y within 10px) into a full name (for entities tagged word-by-word).
        # 3. Deduplicate by (label, value) keeping highest confidence.
        
        # Pass 1: merge by shared bbox
        bbox_groups: Dict[Tuple[str, Tuple], List[LayoutEntity]] = {}
        for e in entities:
            key = (e.label, tuple(round(x) for x in e.bbox))
            bbox_groups.setdefault(key, []).append(e)

        by_bbox: List[LayoutEntity] = []
        for key, group in bbox_groups.items():
            label = key[0]
            if len(group) == 1:
                by_bbox.append(group[0])
            else:
                # Sort by x (ascending) to get left-to-right order
                sorted_group = sorted(group, key=lambda x: x.bbox[0])
                combined_value = " ".join(se.value for se in sorted_group)
                total_len = sum(len(se.value) for se in sorted_group)
                avg_conf = (
                    sum(se.confidence * len(se.value) for se in sorted_group) / total_len
                    if total_len > 0 else sorted_group[0].confidence
                )
                first, last = sorted_group[0], sorted_group[-1]
                merged_bbox = (first.bbox[0], first.bbox[1], last.bbox[2], last.bbox[3])
                by_bbox.append(LayoutEntity(
                    label=label,
                    value=combined_value,
                    confidence=avg_conf,
                    bbox=merged_bbox,
                    page=first.page,
                ))

        # Pass 2: merge consecutive same-label entities on same line
        sorted_ents = sorted(by_bbox, key=lambda e: (e.page or 0, round(e.bbox[1]), e.bbox[0]))

        merged2: List[LayoutEntity] = []
        i = 0
        while i < len(sorted_ents):
            e = sorted_ents[i]
            same_line_group = [e]
            j = i + 1
            while j < len(sorted_ents):
                next_e = sorted_ents[j]
                if next_e.label != e.label:
                    break
                # Same label: cek jika di page yang sama dan dalam 10px vertically
                if (next_e.page or 0) != (e.page or 0):
                    break
                if abs(next_e.bbox[1] - e.bbox[1]) > 10:
                    break
                same_line_group.append(next_e)
                j += 1

            if len(same_line_group) == 1:
                merged2.append(e)
            else:
                combined_value = " ".join(se.value for se in same_line_group)
                total_len = sum(len(se.value) for se in same_line_group)
                avg_conf = (
                    sum(se.confidence * len(se.value) for se in same_line_group) / total_len
                    if total_len > 0 else same_line_group[0].confidence
                )
                first, last = same_line_group[0], same_line_group[-1]
                merged2.append(LayoutEntity(
                    label=e.label,
                    value=combined_value,
                    confidence=avg_conf,
                    bbox=(first.bbox[0], first.bbox[1], last.bbox[2], last.bbox[3]),
                    page=e.page,
                ))
            i = j

        # Pass 3: deduplicate by (label, value)
        seen: Dict[Tuple[str, str], LayoutEntity] = {}
        for e in merged2:
            key = (e.label, e.value)
            if key not in seen or e.confidence > seen[key].confidence:
                seen[key] = e
        return list(seen.values())

    def _classify_match(
        self,
        value: str,
        doc_type: str,
    ) -> Optional[Tuple[str, str, float]]:
        # Classify a MATCH entity into a specific type using rules.
        import re

        value = value.strip()
        if not value or len(value) < 2:
            return None

        date_iso = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', value)
        if date_iso:
            if doc_type in ("CI", "PL"):
                return "invoice_date", value, 0.95
            return "bl_date", value, 0.95

        date_dmy = re.match(r'^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})$', value)
        if date_dmy:
            d, m, y = date_dmy.groups()
            return ("invoice_date" if doc_type in ("CI", "PL") else "bl_date",
                    f"{y}-{int(m):02d}-{int(d):02d}", 0.90)

        # Text month dates
        text_month = re.match(r'^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$', value)
        if text_month:
            return ("invoice_date" if doc_type in ("CI", "PL") else "bl_date",
                    value, 0.85)

        # HS Code (8+ digits, valid chapter)
        hs = value.replace(".", "").replace(",", "").replace(" ", "")
        if re.match(r'^\d{8,10}$', hs):
            try:
                chapter = int(hs[:2])
                if 1 <= chapter <= 97:
                    return "item_hs_code", hs, 0.95
            except ValueError:
                pass

        # Container (4 letters + 7 digits)
        if re.match(r'^[A-Z]{4}\d{7}$', value):
            return "container_number", value, 0.98

        # BL Number
        if re.match(r'^[A-Z]{4}\d{7,12}$', value):
            return "bl_number", value, 0.95

        # Invoice Number
        if doc_type in ("CI", "PL"):
            if re.match(r'^(INV|INV\.|INVOICE|FACTUR)?[\s\-:]*[A-Z0-9]{4,}$', value, re.IGNORECASE):
                return "invoice_number", value, 0.90

        # Currency
        currency = re.search(r'\b(USD|EUR|GBP|IDR|JPY|CNY|SGD|THB|MYR|HKD|KRW|TWD)\b', value, re.IGNORECASE)
        if currency:
            return "currency", currency.group().upper(), 0.98

        # Incoterms
        incoterms = re.search(r'\b(FOB|CIF|CFR|EXW|DAP|DDP|FCA|CPT|CIP|FAS|DAT)\b', value, re.IGNORECASE)
        if incoterms:
            return "incoterms", incoterms.group().upper(), 0.98

        # Vessel name
        vessel_clean = re.sub(r'^(VESSEL\s*NAME\s*:?\s*)', '', value, flags=re.IGNORECASE).strip()
        if vessel_clean and not vessel_clean[0].isdigit() and len(vessel_clean) > 2:
            return "vessel_name", vessel_clean, 0.85

        # Country
        country = re.search(
            r'\b(CHINA|INDONESIA|SINGAPORE|MALAYSIA|THAILAND|JAPAN|KOREA|HONG\s*KONG|'
            r'TAIWAN|VIETNAM|INDIA|USA|GERMANY|UK|AUSTRALIA)\b',
            value, re.IGNORECASE,
        )
        if country:
            return "country_of_origin", country.group().upper(), 0.95

        # Port names
        port_match = re.match(r'^([A-Z][A-Z\s]{2,25}(?:,?\s*[A-Z]{2,10})?)$', value)
        if port_match and len(value) > 3 and not value[0].isdigit():
            return "port_of_loading", value.strip(), 0.75

        # Company names (multi-word, capitalized)
        if (len(value) > 5 and not value[0].isdigit()
                and not re.search(r'\d{4,}', value)
                and re.search(r'[A-Z]{3,}', value)
                and not re.search(r'^(THE|AND|OF|FOR|TO|NO\.|INV|INVOICE|BL|B/L|DATE|TERM)', value, re.IGNORECASE)):
            if doc_type == "BL":
                return "shipper_name", value, 0.75
            return "seller_name", value, 0.70

        return None

    def _extract_fallback(
        self,
        ocr_result,
        doc_type: str,
    ) -> Dict[str, List[LayoutEntity]]:
        # Text-based fallback when LayoutXLM model is unavailable.
        text = ocr_result.full_text
        if not text:
            return {}

        entities: List[LayoutEntity] = []
        all_words = ocr_result.all_words

        def add(label: str, value: str, confidence: float,
                bbox: Tuple = (0, 0, 0, 0), page: int = 0):
            if value and len(value.strip()) >= 2:
                entities.append(LayoutEntity(
                    label=label, value=value.strip(),
                    confidence=confidence, bbox=bbox, page=page,
                    source="layout_fallback",
                ))

        # Invoice Number
        for m in _INVOICE_NUMBER_RE.finditer(text):
            add("invoice_number", m.group(1), 0.80)

        # BL Number
        for m in _BL_NUMBER_RE.finditer(text):
            add("bl_number", m.group(1), 0.85)

        # Dates
        for m in _DATE_RE.finditer(text):
            add("invoice_date" if doc_type in ("CI", "PL") else "bl_date",
                m.group(1), 0.80)

        # Container Numbers
        for m in _CONTAINER_RE.finditer(text):
            add("container_number", m.group(1), 0.98)

        # Seal Numbers
        for m in _SEAL_RE.finditer(text):
            add("seal_number", m.group(1), 0.85)

        # Vessel Name
        for m in _VESSEL_RE.finditer(text):
            add("vessel_name", m.group(1), 0.80)

        # Ports
        for m in _PORT_RE.finditer(text):
            add("port_of_loading", m.group(1), 0.75)

        # Currency
        for m in _CURRENCY_RE.finditer(text):
            add("currency", m.group(1), 0.95)

        # Incoterms
        for m in _INCOTERMS_RE.finditer(text):
            add("incoterms", m.group(1), 0.95)

        # Countries
        for m in _COUNTRY_RE.finditer(text):
            add("country_of_origin", m.group(1), 0.90)

        # Seller / Exporter
        _SELLER_NOISE = {"QUANTITY", "UNIT", "PRICE", "DESCRIPTION", "TEXTILE", "CORD",
                         "PRODUCT", "NUMBER", "CODE", "MATERIAL", "LOT", "DATE", "NAME"}
        for m in _SELLER_RE.finditer(text):
            v = m.group(1).strip()
            v_words = set(w.upper() for w in re.split(r"[\s,\.\-]+", v))
            # Reject jika terlalu pendek, contain product keywords, atau mostly capital letters
            if len(v) < 10:
                continue
            if v_words & _SELLER_NOISE:
                continue
            # Reject jika tidak ada lowercase letters (kemungkinan document structure)
            if not any(c.islower() for c in v):
                continue
            add("seller_name", v, 0.70)

        # Buyer / Importer
        _BUYER_RE = re.compile(
            r"(?:Buyer|Consignee|Importer)[:\s]+([A-Z][A-Z\s.,\-']{3,50}?)(?=\s+(?:Invoice|No\.|DATE|TEL|FAX|JL\.|EMAIL|$))",
            re.IGNORECASE,
        )
        for m in _BUYER_RE.finditer(text):
            add("buyer_name", m.group(1).strip(), 0.75)
        for m in _BUYER_PT_RE.finditer(text):
            add("buyer_name", m.group(1).strip(), 0.80)

        # BL-specific party extraction ─────────────────────────────
        bl_party_labels: set = set()  # Track what we've added
        if doc_type == "BL":
            self._extract_bl_parties(text, add, bl_party_labels)

        # Deduplicate
        seen = set()
        deduped = []
        for e in entities:
            key = (e.label, e.value)
            if key not in seen:
                seen.add(key)
                deduped.append(e)

        return self._group_entities(deduped)

    def _extract_bl_parties(
        self,
        text: str,
        add: Callable,
        seen_labels: set,
    ) -> None:
        # Extract shipper, consignee, and notify-party from BL text.
        # 1. Shipper extraction
        # Strategy:
        #   a) Line-by-line: nama perusahaan nyata pertama sebelum "Consignee" label
        #   b) Fallback: Thailand/Korean address lines sebagai shipper section
        header = text[:800]
        lines = header.split('\n')

        # Cari posisi label "Consignee" / "CONSIG" untuk tahu dimana header berakhir
        consignee_pos = len(header)
        for label_m in _BL_CONSIGNEE_LABEL_RE.finditer(header):
            consignee_pos = label_m.start()
            break

        # Skip lines that are labels, not company names
        _SKIP_LABEL_RE = re.compile(
            r"(?:Export\s+References?|BILL\s+OF\s+LADING|NOT\s+NEGOTIABLE|"
            r"ORIGINAL|JOINT\s+SERVICE|MERCHANT|SHIPPER|CONSIGNEE|NOTIFY\s+PARTY|"
            r"EVERGREEN|BANGKOK\s+THAILAND)",
            re.I,
        )

        for line in lines:
            if len(line) > consignee_pos:
                break
            line_stripped = line.strip()
            if _SKIP_LABEL_RE.search(line_stripped):
                continue
            for m in _BL_COMPANY_MULTI_RE.finditer(line_stripped):
                name = m.group(1).strip()
                if len(name) < 8:
                    continue
                if name.upper().startswith("SHIPPE"):
                    continue
                if re.search(r"(?:MERCHANT|SHIPPING|AGENCY|AS\s+CARRIER|EVERGREEN)", name, re.I):
                    continue
                if sum(c.isalpha() for c in name) < len(name) * 0.5:
                    continue
                add("shipper_name", name, 0.80)
                seen_labels.add("shipper_name")
                break

        # 1b. Country extraction from shipper address lines
        if "country_of_origin" not in seen_labels:
            # Search in lines before the consignee section
            for line in lines[:8]:
                country_match = re.search(
                    r"(?<![A-Z-])(THAILAND|KOREA|CHINA|MALAYSIA|SINGAPORE|INDONESIA|VIETNAM)\b",
                    line, re.I
                )
                if country_match:
                    add("country_of_origin", country_match.group(1).upper(), 0.85)
                    seen_labels.add("country_of_origin")
                    break

        # 2. Consignee extraction
        # Cari keyword "CONSIG", lalu cari PT. company dalam 300 chars setelahnya
        if "consignee_name" not in seen_labels:
            for label_m in _BL_CONSIGNEE_LABEL_RE.finditer(text):
                search_start = label_m.end()
                search_window = text[search_start:search_start + 400]
                pt_match = _BL_PT_RE.search(search_window)
                if pt_match:
                    name = pt_match.group(1).strip()
                    if name.upper().startswith("AS CARRIER"):
                        continue
                    add("consignee_name", name, 0.82)
                    seen_labels.add("consignee_name")
                    break

        # 3. Notify Party extraction
        if "notify_party_name" not in seen_labels:
            for label_m in _BL_NOTIFY_LABEL_RE.finditer(text):
                # Only match "NON-NEGOTIABLE" (not "Par ty" alone)
                if label_m.group(1).upper().replace("-", "").replace(" ", "") in ("NONNEGOTIABLE",):
                    if label_m.start() < 500:
                        continue
                    # Search window: hanya cari "SAME AS" untuk decide apakah ada party
                    search_window = text[label_m.end():label_m.end() + 300]
                    if search_window.strip().upper().startswith("SAME AS"):
                        continue
                    # Look for PT. company in the notify section
                    pt_match = _BL_PT_RE.search(search_window)
                    if pt_match:
                        name = pt_match.group(1).strip()
                        add("notify_party_name", name, 0.82)
                        seen_labels.add("notify_party_name")
                        break
                    # NOTE: Company fallback sengaja omitted di sini.

        # 4. Shipper from Asian address pattern (fallback)
        if "shipper_name" not in seen_labels:
            for m in _BL_COMPANY_MULTI_RE.finditer(text[:1500]):
                name = m.group(1).strip()
                if len(name) < 10:
                    continue
                if name.upper().startswith("SHIPPE"):
                    continue
                pos = text.find(name)
                if pos < 0:
                    continue
                after = text[pos:pos + 200]
                if _BL_ASIA_ADDR_RE.search(after):
                    add("shipper_name", name, 0.78)
                    seen_labels.add("shipper_name")
                    break

    def _group_entities(
        self,
        entities: List[LayoutEntity],
    ) -> Dict[str, List[LayoutEntity]]:
        # Group LayoutEntity list by normalized label.
        grouped: Dict[str, List[LayoutEntity]] = {}
        for e in entities:
            # Apply LAYOUT_TO_NER_MAP
            norm_label = LAYOUT_TO_NER_MAP.get(e.label, e.label)
            grouped.setdefault(norm_label, []).append(e)
        return grouped

    def get_best(
        self,
        grouped: Dict[str, List[LayoutEntity]],
        label: str,
    ) -> Optional[LayoutEntity]:
        # Get the highest-confidence entity for a label.
        entities = grouped.get(label, [])
        if not entities:
            return None
        return max(entities, key=lambda e: e.confidence)

    def get_all(
        self,
        grouped: Dict[str, List[LayoutEntity]],
        label: str,
    ) -> List[str]:
        # Get all values for a label (useful for multi-value entities).
        return [e.value for e in grouped.get(label, [])]
