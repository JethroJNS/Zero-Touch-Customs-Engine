"""
Cross-Validator — resolves conflicts between LayoutXLM and Pattern outputs.

When both layers extract the same entity, the validator decides which wins:
  - For LAYOUT entities: LayoutXLM wins (spatial context)
  - For PATTERN entities: Pattern wins (format precision)
  - For ambiguous cases: highest confidence wins

Conflict resolution rules:
  1. Same entity, different values:
       - If one is clearly invalid (failed validation), use the valid one
       - If both valid, use the one with higher confidence
       - If same confidence, prefer Pattern for numeric, LayoutXLM for text
  2. Entity only in one layer (other returned empty):
       - Always use the non-empty result
  3. OCR error correction:
       - Pattern detects potential OCR errors (ID→HD, WHITH→WHITE)
       - If LayoutXLM extracted the wrong value, replace with Pattern's normalized value
  4. Confidence boost:
       - If both layers agree on a value (cross-validation passed), boost confidence
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from .layout import LayoutEntity, LayoutExtractor
from .items import PatternEntity, ItemEntity, validate_hs_code, normalize_item_code

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of cross-validation for a single entity."""
    label: str
    value: str
    confidence: float
    source: str          # "layoutxlm", "pattern", or "merged"
    validation_method: str  # "direct", "cross_validated", "corrected", "fallback"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "method": self.validation_method,
            "notes": self.notes,
        }


class CrossValidator:
    """
    Cross-validates and resolves conflicts between LayoutXLM and Pattern outputs.

    Resolution strategy:
      - LAYOUT entities: LayoutXLM wins (except OCR error corrections)
      - PATTERN entities: Pattern wins
      - Cross-layer entities: highest confidence wins
      - OCR error correction: Pattern normalization overrides LayoutXLM
    """

    # LayoutXLM wins for these (spatial context matters more than format)
    LAYOUT_DOMINANT = {
        "invoice_number", "invoice_date", "bl_number", "bl_date",
        "seller_name", "seller_address", "buyer_name", "buyer_address",
        "shipper_name", "shipper_address", "consignee_name", "consignee_address",
        "notify_party_name", "notify_party_address",
        "vessel_name", "voyage_number",
        "port_of_loading", "port_of_discharge",
        "place_of_receipt", "place_of_delivery",
        "country_of_origin", "country_of_destination",
        "description_of_goods",
        "freight_term",
    }

    # Pattern wins for these (format precision matters more)
    PATTERN_DOMINANT = {
        "incoterms",  # LayoutLM often confuses "TOTAL CIF" → CIF with incoterm CIF
        "item_code", "item_hs_code", "item_quantity",
        "item_unit_price", "item_amount",
        "total_amount", "total_quantity",
        "total_net_weight", "total_gross_weight",
        "net_weight_per_item", "gross_weight_per_item",
        "cbm", "total_cbm", "measurement",
        "container_number", "seal_number",
        "number_of_packages", "number_of_cartons",
    }

    def __init__(self):
        self._validation_log: List[str] = []

    def validate_header_entities(
        self,
        layout_entities: Dict[str, List[LayoutEntity]],
        pattern_entities: Dict[str, List[PatternEntity]],
    ) -> Dict[str, ValidationResult]:
        """
        Validate header-level entities from both layers.

        Args:
            layout_entities: Dict[str, List[LayoutEntity]] from LayoutXLM
            pattern_entities: Dict[str, List[PatternEntity]] from Pattern

        Returns:
            Dict[str, ValidationResult] — best value for each entity
        """
        results: Dict[str, ValidationResult] = {}
        all_labels = set(layout_entities.keys()) | set(pattern_entities.keys())

        for label in all_labels:
            layout_vals = layout_entities.get(label, [])
            pattern_vals = pattern_entities.get(label, [])

            result = self._resolve_single(
                label, layout_vals, pattern_vals
            )
            results[label] = result

            if result.notes:
                self._validation_log.append(
                    f"  [{label}] {result.validation_method}: "
                    f"{result.value!r} ({result.confidence:.2f}) — {result.notes}"
                )

        return results

    def _resolve_single(
        self,
        label: str,
        layout_vals: List[LayoutEntity],
        pattern_vals: List[PatternEntity],
    ) -> ValidationResult:
        """Resolve a single entity label from both layers."""
        layout_best = self._best_layout(layout_vals) if layout_vals else None
        pattern_best = self._best_pattern(pattern_vals) if pattern_vals else None

        # ── Case: both empty ─────────────────────────────────
        if layout_best is None and pattern_best is None:
            return ValidationResult(
                label=label, value="", confidence=0.0,
                source="none", validation_method="no_data",
            )

        # ── Case: only LayoutXLM has this ─────────────────────
        if pattern_best is None and layout_best is not None:
            # Validate single-source values (e.g. reject "KUMHO" as incoterms)
            val = self._post_validate(layout_best, label)
            return ValidationResult(
                label=label,
                value=val.value,
                confidence=val.confidence,
                source="layoutxlm",
                validation_method="direct",
            )

        # ── Case: only Pattern has this ────────────────────────
        if layout_best is None and pattern_best is not None:
            return ValidationResult(
                label=label,
                value=pattern_best.value,
                confidence=pattern_best.confidence,
                source="pattern",
                validation_method="direct",
            )

        # ── Case: both have values ───────────────────────────
        assert layout_best is not None and pattern_best is not None

        # Use label-specific validation (handles incoterms, party name fixes, etc.)
        winner, method = self._validate_label(layout_best, pattern_best, label)
        if winner is None:
            return ValidationResult(
                label=label,
                value="",
                confidence=0.0,
                source="none",
                validation_method="rejected",
            )

        return ValidationResult(
            label=label,
            value=winner.value,
            confidence=winner.confidence,
            source=getattr(winner, 'source', 'unknown'),
            validation_method=method,
        )

    def _best_layout(self, vals: List[LayoutEntity]) -> Optional[LayoutEntity]:
        if not vals:
            return None
        # For currency: prefer plain ISO codes over formatted strings like "(USD/KG)" or "USD336,873.60"
        if any(v.label == "currency" for v in vals):
            VALID_CURRENCY = {"USD", "CNY", "EUR", "GBP", "JPY", "SGD", "IDR", "AUD", "KRW"}
            # Clean values: must be pure ISO code (letters only, no digits/punctuation)
            valid = [
                v for v in vals
                if v.label == "currency"
                and v.value.strip().upper() in VALID_CURRENCY
                and re.match(r"^[A-Z]{3}$", v.value.strip().upper())
            ]
            if valid:
                return max(valid, key=lambda e: e.confidence)
            # If no valid ISO currency found, try to clean up the best candidate
            best = max(vals, key=lambda e: e.confidence)
            # If best looks like "USD336,873.60", strip the number
            if re.match(r"^(USD|CNY|EUR|GBP|JPY|SGD|IDR|AUD|KRW)([\d,.]+)", best.value):
                m = re.match(r"^([A-Z]{3})", best.value)
                if m:
                    clean = m.group(1)
                    return LayoutEntity(
                        label=best.label, value=clean, confidence=best.confidence,
                        bbox=best.bbox, page=best.page, source=best.source,
                    )
        return max(vals, key=lambda e: e.confidence)

    def _best_pattern(self, vals: List[PatternEntity]) -> Optional[PatternEntity]:
        if not vals:
            return None
        return max(vals, key=lambda e: e.confidence)

    # Valid incoterms for Indonesian CEISA 4.0
    VALID_INCOTERMS = {"FOB", "CIF", "CFR", "EXW", "DAP", "DDP", "FCA", "CPT", "CIP", "FAS", "DAT"}

    def _layout_wins(
        self,
        layout_best: LayoutEntity,
        pattern_best: PatternEntity,
        label: str,
    ) -> Tuple[Any, str]:
        """LayoutXLM wins for layout-dominant entities, unless validation fails."""
        # ── Incoterms validation ──────────────────────────────────────────
        # LayoutLM model often confuses brand names (KUMHO) with incoterms.
        # If layout value is not a valid incoterm, prefer pattern's value.
        if label == "incoterms":
            layout_ok = layout_best.value.upper() in self.VALID_INCOTERMS
            pattern_ok = pattern_best and pattern_best.value.upper() in self.VALID_INCOTERMS
            if not layout_ok and pattern_ok:
                return pattern_best, "incoterm_validated"
            if layout_ok and not pattern_ok:
                return layout_best, "layout_validated"

        # ── Seller/Buyer validation ─────────────────────────────────────────
        # LayoutLM model may confuse product keywords (MATERIALS, CORD, etc.)
        # with party names. If layout value is suspiciously short or contains
        # product keywords, prefer pattern if it has a more complete name.
        if label in ("seller_name", "buyer_name", "shipper_name", "consignee_name",
                     "notify_party_name"):
            layout_val = layout_best.value
            pattern_val = pattern_best.value if pattern_best else ""
            # Generic product/material keywords that should NOT appear as party names.
            # This list contains product categories, not specific company names.
            product_keywords = {
                "MATERIALS", "MATERIAL", "CORD", "TEXTILE", "SYNTHETIC",
                "RUBBER", "DSP", "HDSP", "POLYESTER", "NYLON",
                "NUMBER", "CODE", "PRODUCT", "FURNITURE", "OFFICE",
            }
            layout_words = set(w.upper() for w in re.split(r"[\s,\-\.]+", layout_val))
            layout_is_product = (
                len(layout_val.split()) <= 2 or  # Too short (likely product fragment)
                (layout_words & product_keywords)  # Contains product keyword
            )
            if layout_is_product and len(pattern_val) > len(layout_val):
                # Pattern has a more complete/correct name
                return pattern_best, "party_validated"

        # Check for OCR error correction by Pattern
        corrected = self._check_ocr_correction(layout_best.value, pattern_best.value, label)
        if corrected:
            return corrected, "corrected"

        # Cross-validation: if values match, boost confidence
        if self._values_match(layout_best.value, pattern_best.value):
            layout_best.confidence = min(layout_best.confidence * 1.1, 1.0)
            return layout_best, "cross_validated"

        # Otherwise LayoutXLM wins for layout-dominant
        return layout_best, "layout_wins"

    def _pattern_wins(
        self,
        layout_best: LayoutEntity,
        pattern_best: PatternEntity,
        label: str,
    ) -> Tuple[Any, str]:
        """Pattern wins for pattern-dominant entities."""
        # Always prefer Pattern for strict-format entities
        # (HS code validation, item code normalization)
        if label in ("item_hs_code", "item_code", "container_number"):
            validated = self._validate_strict_format(pattern_best.value, label)
            if validated:
                return validated, "format_validated"
            # Fall back to LayoutXLM if Pattern fails validation
            return layout_best, "fallback_after_validation_fail"

        # Cross-validation
        if self._values_match(layout_best.value, pattern_best.value):
            pattern_best.confidence = min(pattern_best.confidence * 1.1, 1.0)
            return pattern_best, "cross_validated"

        # Pattern wins for format-dominant
        return pattern_best, "pattern_wins"

    def _higher_confidence_wins(
        self,
        layout_best: LayoutEntity,
        pattern_best: PatternEntity,
        label: str,
    ) -> Tuple[Any, str]:
        """Higher confidence wins for ambiguous entities."""
        if layout_best.confidence >= pattern_best.confidence:
            return layout_best, "confidence_wins_layout"
        return pattern_best, "confidence_wins_pattern"

    def _post_validate(self, entity: LayoutEntity, label: str) -> LayoutEntity:
        """
        Post-validate a single-source entity value.
        Rejects clearly invalid values (e.g., brand names mislabeled as incoterms).
        Returns the original entity if valid, or an empty/confidence=0 entity if invalid.
        """
        val = entity.value.upper().strip()

        # Incoterms: reject if not a valid incoterm code
        if label == "incoterms":
            if val not in self.VALID_INCOTERMS:
                logger.info(f"  [incoterms] Rejected invalid LayoutXLM value: {entity.value!r}")
                # Return entity with zero confidence (caller should try pattern or search document text)
                return LayoutEntity(
                    label=entity.label,
                    value="",
                    confidence=0.0,
                    bbox=entity.bbox,
                    page=entity.page,
                    source=entity.source,
                )

        return entity

    def _validate_label(
        self, layout_best: Optional[LayoutEntity], pattern_best: Optional[PatternEntity], label: str
    ) -> Tuple[Any, str]:
        """
        Validate/resolve a specific label, checking for invalid values even in
        single-source cases. Returns (value, method).
        """
        # ── Pattern-dominant: Pattern always wins ─────────────────────
        if label in self.PATTERN_DOMINANT:
            if pattern_best:
                # Validate strict format fields
                if label in ("item_hs_code", "item_code", "container_number"):
                    validated = self._validate_strict_format(pattern_best.value, label)
                    if validated:
                        return validated, "format_validated"
                    # Fall back to LayoutXLM if Pattern fails
                    if layout_best:
                        return layout_best, "fallback_after_validation_fail"
                    return None, "no_valid_pattern"
                return pattern_best, "pattern_dominant"
            # Pattern absent — use LayoutXLM
            if layout_best:
                return layout_best, "layout_fallback"
            return None, "no_data"

        # ── Incoterms: check validity regardless of which layer has it ─────────
        if label == "incoterms":
            layout_val = layout_best.value.upper().strip() if layout_best else ""
            pattern_val = pattern_best.value.upper().strip() if pattern_best else ""
            layout_ok = layout_val in self.VALID_INCOTERMS
            pattern_ok = pattern_val in self.VALID_INCOTERMS
            if layout_ok and pattern_ok:
                # Both valid — use higher confidence
                if layout_best and pattern_best and layout_best.confidence >= pattern_best.confidence:
                    return layout_best, "confidence_wins_layout"
                elif pattern_best:
                    return pattern_best, "confidence_wins_pattern"
                return layout_best, "confidence_wins_layout"
            if not layout_ok and pattern_ok:
                return pattern_best, "incoterm_validated"
            if layout_ok and not pattern_ok:
                return layout_best, "layout_validated"
            # Neither valid: return empty (try document text search later)
            return None, "incoterms_invalid"

        # Default: delegate to higher confidence
        if layout_best and pattern_best:
            return self._higher_confidence_wins(layout_best, pattern_best, label)
        if layout_best:
            return self._post_validate(layout_best, label), "direct"
        if pattern_best:
            return pattern_best, "pattern_direct"
        return None, "no_data"

    def _values_match(self, v1: str, v2: str) -> bool:
        """Check if two values match (case-insensitive, stripped)."""
        return v1.strip().lower() == v2.strip().lower()

    def _check_ocr_correction(
        self,
        layout_value: str,
        pattern_value: str,
        label: str,
    ) -> Optional[Any]:
        """
        Check if Pattern provides an OCR-corrected version of LayoutXLM's value.
        E.g., LayoutXLM: 'ID-SLD-3D-1DRW-A-WHITEI'  Pattern: 'HD-SLD-3D-1DRW-A-WHITE'
        """
        # Item code OCR correction
        if label in ("item_code", "seller_name", "buyer_name"):
            norm_layout = normalize_item_code(layout_value)
            if norm_layout != layout_value and pattern_value == norm_layout:
                # Pattern has the corrected version
                from .items import PatternEntity
                corrected = PatternEntity(
                    label=pattern_value,
                    value=norm_layout,
                    confidence=0.95,
                    source="pattern_ocr_correction",
                )
                return corrected

        # HS code chapter validation
        if label == "item_hs_code":
            layout_valid = validate_hs_code(layout_value)
            pattern_valid = validate_hs_code(pattern_value)
            if layout_valid is None and pattern_valid is not None:
                # LayoutXLM gave invalid HS, Pattern corrected it
                from .items import PatternEntity
                return PatternEntity(
                    label=pattern_value,
                    value=pattern_valid,
                    confidence=0.95,
                    source="pattern_hs_correction",
                )

        return None

    def _validate_strict_format(
        self,
        value: str,
        label: str,
    ) -> Optional[PatternEntity]:
        """Validate a value against strict format requirements."""
        if label == "item_hs_code":
            valid = validate_hs_code(value)
            if valid:
                return PatternEntity(
                    label=label,
                    value=valid,
                    confidence=0.95,
                    source="pattern_validated",
                )
        elif label == "container_number":
            if re.match(r"^[A-Z]{4}\d{7}$", value):
                return PatternEntity(
                    label=label,
                    value=value,
                    confidence=0.98,
                    source="pattern_validated",
                )
        return None

    def validate_items(
        self,
        pattern_items: List[ItemEntity],
        layout_items: Optional[List[ItemEntity]] = None,
    ) -> List[ItemEntity]:
        """
        Validate and annotate Pattern line items.

        Annotations:
          - confidence field set based on data completeness
          - cross-field validation (qty × price ≈ amount)
          - OCR corrections applied
          - Cross-validation with LayoutXLM (if available)
          - Items below minimum confidence threshold are flagged

        Production thresholds:
          - MIN_CONFIDENCE = 0.35: below this → item marked low_quality
          - AMOUNT_TOLERANCE = 0.20: qty × price must match amount within 20%
        """
        MIN_CONFIDENCE = 0.35  # Below this: flag as low_quality, don't reject
        AMOUNT_TOLERANCE = 0.20  # 20% tolerance for qty × price ≈ amount

        validated_items = []

        for item in pattern_items:
            # Normalize item code
            if item.item_code:
                item.item_code = normalize_item_code(item.item_code)

            # Validate HS code
            if item.hs_code:
                validated_hs = validate_hs_code(item.hs_code)
                if validated_hs:
                    item.hs_code = validated_hs
                else:
                    item.hs_code = None  # Reject invalid HS

            # ── Cross-field validation: qty × unit_price ≈ amount ───────────────
            amount_flag = None  # "valid", "warning", "critical"
            if item.quantity and item.unit_price and item.amount:
                try:
                    qty_f = float(str(item.quantity).replace(",", ""))
                    up_f = float(str(item.unit_price).replace(",", ""))
                    am_f = float(str(item.amount).replace(",", ""))
                    if qty_f > 0 and up_f > 0 and am_f > 0:
                        expected = qty_f * up_f
                        ratio = abs(am_f - expected) / expected
                        if ratio <= 0.05:
                            amount_flag = "valid"
                        elif ratio <= AMOUNT_TOLERANCE:
                            amount_flag = "warning"
                        else:
                            amount_flag = "critical"
                            logger.info(
                                f"  [validation] Item '{item.item_code or item.description}': "
                                f"qty×price={expected:.2f} vs amount={am_f:.2f} "
                                f"(ratio={ratio:.1%} — exceeds {AMOUNT_TOLERANCE:.0%})"
                            )
                except (ValueError, ZeroDivisionError):
                    amount_flag = None

            # ── Compute confidence based on data completeness + validation ───────
            fields_populated = sum([
                bool(item.item_code),
                bool(item.quantity),
                bool(item.unit_price),
                bool(item.amount),
                bool(item.hs_code),
                bool(item.net_weight),
                bool(item.gross_weight),
                bool(item.dimensions),
            ])

            base_confidence = 0.4 + 0.07 * fields_populated
            # Boost if cross-field validation passes
            if amount_flag == "valid":
                base_confidence = min(base_confidence * 1.15, 1.0)
            elif amount_flag == "warning":
                base_confidence = min(base_confidence * 0.95, 1.0)
            elif amount_flag == "critical":
                base_confidence = min(base_confidence * 0.70, 1.0)

            item.confidence = base_confidence

            # ── Flag low-quality items for human review ──────────────────────────
            if item.confidence < MIN_CONFIDENCE:
                item.source = "low_quality"
                logger.info(
                    f"  [validation] Low-confidence item: "
                    f"code={item.item_code!r}, conf={item.confidence:.2f} < {MIN_CONFIDENCE}"
                )
            else:
                item.source = "hybrid"

            validated_items.append(item)

        return validated_items

    def get_validation_log(self) -> List[str]:
        """Return the validation log for debugging."""
        return self._validation_log

    def print_validation_summary(self) -> None:
        """Print a summary of all validation decisions."""
        if not self._validation_log:
            logger.info("CrossValidator: no conflicts to report")
            return
        logger.info("CrossValidator summary:")
        for entry in self._validation_log:
            logger.info(entry)
