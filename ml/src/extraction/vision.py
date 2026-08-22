from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests

from .items import ItemEntity

logger = logging.getLogger(__name__)

# API CONFIGURATION
DEFAULT_API_BASE = "https://api.adacode.ai/v1"
DEFAULT_MODEL = "gpt-4o"
DEFAULT_API_KEY_ENV = "ADACODE_API_KEY"
FALLBACK_API_KEY_ENV = "OPENAI_API_KEY"

# Extraction confidence threshold
MIN_ITEMS_THRESHOLD = 3
MIN_CONFIDENCE_THRESHOLD = 0.3


# SYSTEM PROMPT
SYSTEM_PROMPT = """You are an expert Indonesian customs data extraction specialist for CEISA 4.0.

Given a scanned Commercial Invoice, Bill of Lading, or Packing List, extract ALL information
in EXACT JSON format. Be precise with numbers — copy them verbatim from the document.

## DOCUMENT TYPES
1. **Commercial Invoice (CI)** — primary document, contains: invoice number, date, seller, buyer,
   incoterms, currency, line items (item code, HS code, description, qty, unit, unit price,
   amount), total amount, port of loading, port of discharge.
2. **Bill of Lading (BL)** — shipping document, contains: BL number, date, shipper, consignee,
   notify party, vessel name, voyage number, port of loading, port of discharge,
   container numbers, seal numbers, number of packages, gross weight, measurement (CBM).
3. **Packing List (PL)** — packing details, contains: item descriptions, number of cartons,
   dimensions, CBM, net weight, gross weight per item.

## EXTRACTION RULES

### Numbers
- Always extract raw numeric values as-is (e.g., "1,234.56" → 1234.56)
- Handle both US format (1,234.56) and European format (1.234,56)
- Weight units: extract with unit (e.g., "1,234 KGS" → 1234 and unit "KGS")
- Currency: extract 3-letter ISO code (USD, CNY, EUR, etc.)

### HS Codes
- Extract the FULL code (8-10 digits), not just the chapter
- Format: just digits, no dots (e.g., "5902.20.20" → "59022020")

### Parties
- NAMA ENTITAS (party name): Full company name as printed
- ALAMAT ENTITAS (address): Full address, keep line breaks
- KODE NEGARA: 2-letter ISO code (CN=China, ID=Indonesia, SG=Singapore, etc.)

### Ports
- Extract full port name (e.g., "NINGBO, CHINA" → "NINGBO")
- Maps to UN/LOCODE during post-processing

### Line Items
- Each item as a separate object with ALL fields
- HS, description, quantity, unit, unit_price, amount are REQUIRED
- Include net_weight and gross_weight if present
- If unit_price × quantity ≠ amount, note the discrepancy

### Container Numbers
- Format: OWNERCODE + 7 digits (e.g., "OOLU1234567")
- Extract ALL container numbers from the document

## OUTPUT FORMAT

Return a JSON object with this EXACT structure (no extra text, no markdown code blocks):

{
  "invoice_number": "...",
  "invoice_date": "DD/MM/YYYY",
  "bl_number": "...",
  "bl_date": "DD/MM/YYYY",
  "seller_name": "...",
  "seller_address": "...",
  "buyer_name": "...",
  "buyer_address": "...",
  "shipper_name": "...",
  "shipper_address": "...",
  "consignee_name": "...",
  "consignee_address": "...",
  "notify_party_name": "...",
  "notify_party_address": "...",
  "vessel_name": "...",
  "voyage_number": "...",
  "port_of_loading": "...",
  "port_of_discharge": "...",
  "currency": "USD",
  "incoterms": "FOB",
  "total_amount": 12345.67,
  "total_quantity": 100,
  "total_net_weight": 1234.5,
  "total_gross_weight": 1456.7,
  "number_of_packages": 50,
  "container_numbers": ["OOLU1234567", "OOLU1234568"],
  "seal_numbers": ["SL12345", "SL12346"],
  "items": [
    {
      "item_code": "HD-SLD-001",
      "hs_code": "59022020",
      "description": "POLYESTER DRAWER SLIDE",
      "quantity": 100,
      "unit": "PIECES",
      "unit_price": 2.50,
      "amount": 250.00,
      "net_weight": 12.5,
      "gross_weight": 15.0,
      "cartons": 5,
      "dimensions": "30X20X10CM"
    }
  ],
  "confidence": 0.95,
  "warnings": []
}

IMPORTANT:
- Return ONLY the JSON object, no markdown, no explanation
- confidence: 0.0-1.0 (how sure you are the extraction is correct)
- warnings: any ambiguous values or OCR difficulties encountered
- For missing fields, use null (not empty string or omitted key)
"""


@dataclass
class VisionExtractionResult:
    # Result dari VisionModelExtractor.
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    bl_number: Optional[str] = None
    bl_date: Optional[str] = None
    seller_name: Optional[str] = None
    seller_address: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_address: Optional[str] = None
    shipper_name: Optional[str] = None
    shipper_address: Optional[str] = None
    consignee_name: Optional[str] = None
    consignee_address: Optional[str] = None
    notify_party_name: Optional[str] = None
    notify_party_address: Optional[str] = None
    vessel_name: Optional[str] = None
    voyage_number: Optional[str] = None
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    currency: Optional[str] = None
    incoterms: Optional[str] = None
    total_amount: Optional[float] = None
    total_quantity: Optional[float] = None
    total_net_weight: Optional[float] = None
    total_gross_weight: Optional[float] = None
    number_of_packages: Optional[int] = None
    container_numbers: List[str] = field(default_factory=list)
    seal_numbers: List[str] = field(default_factory=list)
    items: List[ItemEntity] = field(default_factory=list)
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)
    source: str = "vision"
    extraction_time_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["items"] = [i.to_dict() for i in self.items]
        return d


class VisionModelExtractor:
    # Vision-based extraction using GPT-4o.
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        timeout: int = 120,
        max_retries: int = 2,
        confidence_threshold: float = 0.0,
    ):
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.confidence_threshold = confidence_threshold

        # Resolve API key
        self.api_key = (
            api_key
            or os.environ.get(DEFAULT_API_KEY_ENV)
            or os.environ.get(FALLBACK_API_KEY_ENV)
            or ""
        )

        # Resolve API base
        self.api_base = (
            (api_base or os.environ.get("OPENAI_API_BASE") or DEFAULT_API_BASE).rstrip("/")
        )

        self._available = bool(self.api_key)

        if self._available:
            logger.info(f"VisionModelExtractor ready: model={model}, base={self.api_base}")
        else:
            logger.warning(
                "VisionModelExtractor: No API key found. "
                f"Set {DEFAULT_API_KEY_ENV} or {FALLBACK_API_KEY_ENV} env variable."
            )

    @property
    def available(self) -> bool:
        return self._available

    def extract_from_image(
        self,
        image_path: str | Path,
        doc_type: str = "CI",
        extra_instructions: str = "",
    ) -> VisionExtractionResult:
        if not self._available:
            logger.debug("VisionModelExtractor not available (no API key)")
            return VisionExtractionResult()

        t0 = time.time()
        path = Path(image_path)
        if not path.exists():
            logger.error(f"Image not found: {image_path}")
            return VisionExtractionResult()

        try:
            with open(path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            return VisionExtractionResult()

        doc_label = {
            "CI": "Commercial Invoice",
            "BL": "Bill of Lading",
            "PL": "Packing List",
        }.get(doc_type.upper(), "Trade Document")

        user_prompt = f"""Extract all structured data from this {doc_label}.

Document type: {doc_label}
Filename: {path.name}

{extra_instructions}

Return the JSON object now:"""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{path.suffix.lstrip('.').lower()};base64,{img_data}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ]

        result = self._call_api(messages)

        if result is None:
            logger.warning(f"Vision API call failed for {image_path} after {self.max_retries} retries")
            return VisionExtractionResult()

        result.extraction_time_s = time.time() - t0
        return result

    def extract_from_images(
        self,
        image_paths: List[str | Path],
        doc_types: Optional[List[str]] = None,
        extra_instructions: str = "",
    ) -> VisionExtractionResult:
        if not self._available:
            return VisionExtractionResult()

        if doc_types is None:
            doc_types = ["CI"] * len(image_paths)

        t0 = time.time()
        content_parts = []

        for img_path, doc_type in zip(image_paths, doc_types):
            path = Path(img_path)
            try:
                with open(path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                ext = path.suffix.lstrip(".").lower()
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{ext};base64,{img_data}",
                        "detail": "high",
                    },
                })
                content_parts.append({
                    "type": "text",
                    "text": f"[End of {doc_type} document. Begin next document.]",
                })
            except Exception as e:
                logger.error(f"Failed to encode {img_path}: {e}")
                continue

        user_prompt = (
            f"Extract all structured data from the following {len(image_paths)} document images. "
            "Merge all information into a single JSON object. "
            "Prefer data from the Commercial Invoice for totals and parties. "
            "Use Packing List for carton counts and weights. "
            "Use Bill of Lading for shipping details.\n\n"
            f"{extra_instructions}\n\nReturn the JSON object now:"
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    *content_parts,
                ],
            },
        ]

        result = self._call_api(messages)
        if result is None:
            return VisionExtractionResult()

        result.extraction_time_s = time.time() - t0
        return result

    def _call_api(
        self,
        messages: List[Dict[str, Any]],
    ) -> Optional[VisionExtractionResult]:
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }

        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return self._parse_response(content)
                elif resp.status_code == 429:
                    # Rate limited — wait and retry
                    logger.warning("Vision API rate limited, waiting 10s...")
                    time.sleep(10)
                    continue
                else:
                    logger.warning(
                        f"Vision API error {resp.status_code}: {resp.text[:200]}"
                    )
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return None

            except requests.exceptions.Timeout:
                logger.warning(f"Vision API timeout (attempt {attempt + 1})")
                if attempt < self.max_retries:
                    time.sleep(5)
                    continue
            except Exception as e:
                logger.error(f"Vision API exception: {e}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return None

        return None

    def _parse_response(self, content: str) -> Optional[VisionExtractionResult]:
        # Parse response ke VisionExtractionResult.
        # Try direct JSON parse
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                try:
                    raw = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            else:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        raw = json.loads(content[start:end])
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse Vision API response: {content[:200]}")
                        return None
                else:
                    logger.warning(f"No JSON found in Vision response: {content[:200]}")
                    return None

        # Map to VisionExtractionResult
        try:
            items = []
            for item_data in raw.get("items") or []:
                item = ItemEntity(
                    item_code=item_data.get("item_code"),
                    description=item_data.get("description"),
                    hs_code=str(item_data["hs_code"]) if item_data.get("hs_code") else None,
                    quantity=str(item_data["quantity"]) if item_data.get("quantity") is not None else None,
                    unit=item_data.get("unit"),
                    unit_price=str(item_data["unit_price"]) if item_data.get("unit_price") is not None else None,
                    amount=str(item_data["amount"]) if item_data.get("amount") is not None else None,
                    net_weight=str(item_data["net_weight"]) if item_data.get("net_weight") is not None else None,
                    gross_weight=str(item_data["gross_weight"]) if item_data.get("gross_weight") is not None else None,
                    dimensions=item_data.get("dimensions"),
                    cartons=str(item_data["cartons"]) if item_data.get("cartons") is not None else None,
                    confidence=item_data.get("confidence", 0.8),
                    source="vision",
                )
                items.append(item)

            return VisionExtractionResult(
                invoice_number=raw.get("invoice_number"),
                invoice_date=raw.get("invoice_date"),
                bl_number=raw.get("bl_number"),
                bl_date=raw.get("bl_date"),
                seller_name=raw.get("seller_name"),
                seller_address=raw.get("seller_address"),
                buyer_name=raw.get("buyer_name"),
                buyer_address=raw.get("buyer_address"),
                shipper_name=raw.get("shipper_name"),
                shipper_address=raw.get("shipper_address"),
                consignee_name=raw.get("consignee_name"),
                consignee_address=raw.get("consignee_address"),
                notify_party_name=raw.get("notify_party_name"),
                notify_party_address=raw.get("notify_party_address"),
                vessel_name=raw.get("vessel_name"),
                voyage_number=raw.get("voyage_number"),
                port_of_loading=raw.get("port_of_loading"),
                port_of_discharge=raw.get("port_of_discharge"),
                currency=raw.get("currency"),
                incoterms=raw.get("incoterms"),
                total_amount=raw.get("total_amount"),
                total_quantity=raw.get("total_quantity"),
                total_net_weight=raw.get("total_net_weight"),
                total_gross_weight=raw.get("total_gross_weight"),
                number_of_packages=raw.get("number_of_packages"),
                container_numbers=raw.get("container_numbers") or [],
                seal_numbers=raw.get("seal_numbers") or [],
                items=items,
                confidence=raw.get("confidence", 0.0),
                warnings=raw.get("warnings") or [],
            )

        except Exception as e:
            logger.error(f"Failed to map Vision response to result: {e}")
            return None

    def estimate_cost(
        self,
        num_images: int,
        model: Optional[str] = None,
    ) -> float:
        # Estimate API cost.
        m = model or self.model

        cost_per_1k_input_tokens = 0.005   # GPT-4o
        cost_per_1k_output_tokens = 0.015

        estimated_input_tokens = 2500 * num_images
        estimated_output_tokens = 1500

        total = (
            (estimated_input_tokens / 1000) * cost_per_1k_input_tokens * num_images
            + (estimated_output_tokens / 1000) * cost_per_1k_output_tokens * num_images
        )
        return round(total, 4)
