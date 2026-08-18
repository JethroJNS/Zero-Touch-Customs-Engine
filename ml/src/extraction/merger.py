"""
Merger — Combines LayoutXLM headers + Pattern items into unified output.

Produces a ShipmentEntities object ready for CEISA export.

Output structure:
  - Header entities: from validated LayoutXLM + Pattern cross-validation
  - Line items: from Pattern line item extractor (PL→CI merged)
  - Cross-document: BL data merged into appropriate fields
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .layout import LayoutEntity
from .items import ItemEntity, PatternEntity
from .validator import ValidationResult, CrossValidator

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# SHIPMENT ENTITIES
# Unified output format for all extracted data.
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ShipmentEntities:
    """
    Complete extracted entities for a shipment.

    Populated by the HybridExtractor from both LayoutXLM and Pattern outputs.
    """
    # ── Header / Identifier ──────────────────────────────────
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    bl_number: Optional[str] = None
    bl_date: Optional[str] = None
    currency: Optional[str] = None
    incoterms: Optional[str] = None
    total_amount: Optional[str] = None
    freight: Optional[str] = None
    payment_terms: Optional[str] = None

    # ── Weight totals ──────────────────────────────────────
    total_quantity: Optional[str] = None
    total_net_weight: Optional[str] = None
    total_gross_weight: Optional[str] = None

    # ── Transportation ────────────────────────────────────────
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    vessel_name: Optional[str] = None
    voyage_number: Optional[str] = None
    country_of_origin: Optional[str] = None
    country_of_destination: Optional[str] = None

    # ── Parties ─────────────────────────────────────────────
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

    # ── Container / Packaging ──────────────────────────────
    container_numbers: List[str] = field(default_factory=list)
    seal_numbers: List[str] = field(default_factory=list)
    number_of_packages: Optional[str] = None
    packaging_type: Optional[str] = None

    # ── Line items ─────────────────────────────────────────
    items: List[ItemEntity] = field(default_factory=list)

    # ── Metadata ──────────────────────────────────────────
    extraction_confidence: float = 0.0
    layout_entities_count: int = 0
    pattern_entities_count: int = 0
    validation_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        quality_report = self.get_quality_report()
        return {
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "bl_number": self.bl_number,
            "bl_date": self.bl_date,
            "currency": self.currency,
            "incoterms": self.incoterms,
            "total_amount": self.total_amount,
            "freight": self.freight,
            "payment_terms": self.payment_terms,
            "total_quantity": self.total_quantity,
            "total_net_weight": self.total_net_weight,
            "total_gross_weight": self.total_gross_weight,
            "port_of_loading": self.port_of_loading,
            "port_of_discharge": self.port_of_discharge,
            "vessel_name": self.vessel_name,
            "voyage_number": self.voyage_number,
            "country_of_origin": self.country_of_origin,
            "country_of_destination": self.country_of_destination,
            "seller_name": self.seller_name,
            "seller_address": self.seller_address,
            "buyer_name": self.buyer_name,
            "buyer_address": self.buyer_address,
            "shipper_name": self.shipper_name,
            "shipper_address": self.shipper_address,
            "consignee_name": self.consignee_name,
            "consignee_address": self.consignee_address,
            "notify_party_name": self.notify_party_name,
            "notify_party_address": self.notify_party_address,
            "container_numbers": self.container_numbers,
            "seal_numbers": self.seal_numbers,
            "number_of_packages": self.number_of_packages,
            "packaging_type": self.packaging_type,
            "items": [i.to_dict() for i in self.items],
            "extraction_confidence": self.extraction_confidence,
            # Production quality metadata
            "quality_flag": quality_report["quality_flag"],
            "quality_report": quality_report,
            "validation_notes": self.validation_notes,
        }

    def compute_confidence(self) -> float:
        """Compute overall extraction confidence from individual confidences."""
        confidences = []

        # Header entities (exclude None)
        header_vals = [
            self.invoice_number, self.invoice_date, self.bl_number, self.bl_date,
            self.currency, self.incoterms, self.total_amount,
            self.port_of_loading, self.port_of_discharge,
            self.vessel_name, self.voyage_number,
            self.seller_name, self.buyer_name,
        ]
        header_count = sum(1 for v in header_vals if v)
        confidences.append(header_count / max(len(header_vals), 1))

        # Item completeness
        if self.items:
            item_confidences = [i.confidence for i in self.items if i]
            avg_item_conf = sum(item_confidences) / len(item_confidences) if item_confidences else 0
            # Penalize if more than 30% of items are low-quality
            low_quality_count = sum(1 for i in self.items if getattr(i, 'source', '') == 'low_quality')
            low_quality_ratio = low_quality_count / len(self.items)
            quality_penalty = 1.0 - (low_quality_ratio * 0.3)
            item_coverage = len(self.items) / max(len(self.items), 1)
            confidences.append((avg_item_conf * quality_penalty + item_coverage) / 2)

        return sum(confidences) / len(confidences) if confidences else 0.0

    def get_quality_report(self) -> Dict[str, Any]:
        """
        Generate a production-quality report with detailed metrics.

        Returns a dict with extraction quality indicators suitable for
        human review workflow and monitoring dashboards.
        """
        # Required fields for CEISA 4.0
        required_fields = {
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "currency": self.currency,
            "incoterms": self.incoterms,
            "total_amount": self.total_amount,
            "port_of_loading": self.port_of_loading,
            "port_of_discharge": self.port_of_discharge,
            "vessel_name": self.vessel_name,
            "seller_name": self.seller_name,
            "buyer_name": self.buyer_name,
        }

        missing_fields = [k for k, v in required_fields.items() if not v]
        low_quality_items = [i for i in self.items if getattr(i, 'source', '') == 'low_quality']

        # Overall quality flags
        quality_flag = "PASS"
        if len(missing_fields) > 5:
            quality_flag = "FAIL"
        elif len(missing_fields) > 2:
            quality_flag = "REVIEW"
        elif self.extraction_confidence < 0.5:
            quality_flag = "REVIEW"

        return {
            "quality_flag": quality_flag,
            "overall_confidence": round(self.extraction_confidence, 3),
            "items_total": len(self.items),
            "items_low_quality": len(low_quality_items),
            "items_high_quality": len(self.items) - len(low_quality_items),
            "header_fields_missing": missing_fields,
            "header_fields_total": len(required_fields),
            "header_fields_present": len(required_fields) - len(missing_fields),
        }


# ═══════════════════════════════════════════════════════════════════════════
# MERGER
# ═══════════════════════════════════════════════════════════════════════════

class Merger:
    """
    Merges LayoutXLM header entities and Pattern items into ShipmentEntities.

    Handles:
      1. Cross-validation via CrossValidator
      2. Multi-document merging (CI + PL + BL → single ShipmentEntities)
      3. Confidence scoring
      4. Field prioritization (CI > BL > PL for conflicting values)
    """

    def __init__(self):
        self.validator = CrossValidator()

    def merge(
        self,
        ci_layout: Dict[str, List[LayoutEntity]],
        ci_pattern: Dict[str, List[PatternEntity]],
        bl_layout: Dict[str, List[LayoutEntity]],
        bl_pattern: Dict[str, List[PatternEntity]],
        pl_layout: Dict[str, List[LayoutEntity]],
        pl_pattern: Dict[str, List[PatternEntity]],
        ci_items: List[ItemEntity],
        pl_text: str,
    ) -> ShipmentEntities:
        """
        Merge all document results into a single ShipmentEntities.

        Priority: CI > BL > PL for header fields.
        Items come from CI (Pattern layer), enhanced with PL weights.
        """
        entities = ShipmentEntities()

        # ── Step 1: Validate header entities ──────────────────────────
        ci_validated = self.validator.validate_header_entities(ci_layout, ci_pattern)
        bl_validated = self.validator.validate_header_entities(bl_layout, bl_pattern)
        pl_validated = self.validator.validate_header_entities(pl_layout, pl_pattern)

        # ── Step 2: Fill fields with priority CI > BL > PL ───────────
        self._fill_header_field(entities, ci_validated, "invoice_number", "CI")
        self._fill_header_field(entities, ci_validated, "invoice_date", "CI")
        self._fill_header_field(entities, ci_validated, "bl_number", "CI")
        self._fill_header_field(entities, bl_validated, "bl_number", "BL")
        self._fill_header_field(entities, ci_validated, "bl_date", "CI")
        self._fill_header_field(entities, bl_validated, "bl_date", "BL")
        self._fill_header_field(entities, ci_validated, "currency", "CI")
        self._fill_header_field(entities, ci_validated, "incoterms", "CI")
        self._fill_header_field(entities, ci_validated, "total_amount", "CI")
        self._fill_header_field(entities, ci_validated, "freight", "CI")

        # Parties: CI for seller/buyer, BL for shipper/consignee
        self._fill_header_field(entities, ci_validated, "seller_name", "CI")
        self._fill_header_field(entities, ci_validated, "seller_address", "CI")
        self._fill_header_field(entities, ci_validated, "buyer_name", "CI")
        self._fill_header_field(entities, ci_validated, "buyer_address", "CI")
        self._fill_header_field(entities, bl_validated, "shipper_name", "BL")
        self._fill_header_field(entities, bl_validated, "shipper_address", "BL")
        self._fill_header_field(entities, bl_validated, "consignee_name", "BL")
        self._fill_header_field(entities, bl_validated, "consignee_address", "BL")
        self._fill_header_field(entities, bl_validated, "notify_party_name", "BL")
        self._fill_header_field(entities, bl_validated, "notify_party_address", "BL")

        # Fallback: when parties are unlabeled in the primary document,
        # try to infer from shipper/consignee in secondary documents.
        # This is a generic fallback — no specific company names are hardcoded.
        if not entities.seller_name and entities.shipper_name:
            entities.seller_name = entities.shipper_name
            entities.seller_address = entities.shipper_address
        if not entities.buyer_name and entities.consignee_name:
            entities.buyer_name = entities.consignee_name
            entities.buyer_address = entities.consignee_address

        # Transportation
        self._fill_header_field(entities, ci_validated, "port_of_loading", "CI")
        self._fill_header_field(entities, bl_validated, "port_of_loading", "BL")
        self._fill_header_field(entities, ci_validated, "port_of_discharge", "CI")
        self._fill_header_field(entities, bl_validated, "port_of_discharge", "BL")
        self._fill_header_field(entities, bl_validated, "vessel_name", "BL")
        self._fill_header_field(entities, bl_validated, "voyage_number", "BL")
        self._fill_header_field(entities, ci_validated, "country_of_origin", "CI")
        self._fill_header_field(entities, bl_validated, "country_of_origin", "BL")
        self._fill_header_field(entities, ci_validated, "country_of_destination", "CI")

        # Containers / Packaging
        self._fill_multi_value(entities, ci_pattern, "container_number")
        self._fill_multi_value(entities, bl_pattern, "container_number")
        self._fill_multi_value(entities, ci_pattern, "seal_number")
        self._fill_multi_value(entities, bl_pattern, "seal_number")
        self._fill_header_field(entities, ci_validated, "number_of_packages", "CI")
        self._fill_header_field(entities, pl_validated, "number_of_packages", "PL")
        self._fill_header_field(entities, pl_validated, "freight_term", "PL")

        # Weight totals
        self._fill_header_field(entities, ci_validated, "total_net_weight", "CI")
        self._fill_header_field(entities, pl_validated, "total_net_weight", "PL")
        self._fill_header_field(entities, ci_validated, "total_gross_weight", "CI")
        self._fill_header_field(entities, pl_validated, "total_gross_weight", "PL")

        # ── Step 3: Validate and assign items ─────────────────────────
        validated_items = self.validator.validate_items(ci_items)
        entities.items = validated_items

        # ── Step 4: PL → CI weight merge ────────────────────────────
        if pl_text:
            from .items import PLMerger
            merger = PLMerger()
            entities.items = merger.merge(entities.items, pl_text)

        # ── Step 5: Compute totals ────────────────────────────────────
        self._compute_totals(entities)

        # ── Step 6: Overall confidence ─────────────────────────────────
        entities.extraction_confidence = entities.compute_confidence()
        entities.validation_notes = self.validator.get_validation_log()
        entities.layout_entities_count = sum(
            len(v) for v in [ci_layout, bl_layout, pl_layout]
        )
        entities.pattern_entities_count = len(ci_items)

        # ── Step 7: Production quality report ───────────────────────────
        quality_report = entities.get_quality_report()
        logger.info(
            f"Extraction quality: flag={quality_report['quality_flag']}, "
            f"confidence={quality_report['overall_confidence']:.2f}, "
            f"items={quality_report['items_total']} "
            f"(high={quality_report['items_high_quality']}, "
            f"low={quality_report['items_low_quality']}), "
            f"missing_headers={len(quality_report['header_fields_missing'])}"
        )

        return entities

    def _fill_header_field(
        self,
        entities: ShipmentEntities,
        validated: Dict[str, ValidationResult],
        field_name: str,
        source: str,
    ) -> None:
        """Fill a header field from validation results if source matches."""
        result = validated.get(field_name)
        if result is None or not result.value:
            return

        # All validation results are included regardless of source
        # (validator already chose the best one)
        current = getattr(entities, field_name, None)
        if current is None or current == "":
            setattr(entities, field_name, result.value)
        elif current != result.value:
            # Already filled — skip (higher priority already won)
            pass

    def _fill_multi_value(
        self,
        entities: ShipmentEntities,
        pattern_entities: Dict[str, List[PatternEntity]],
        field_name: str,
    ) -> None:
        """Fill a multi-value field (container_numbers, seal_numbers, etc.)."""
        values = pattern_entities.get(field_name, [])
        current = getattr(entities, field_name, [])
        for pe in values:
            if pe.value not in current:
                current.append(pe.value)
        setattr(entities, field_name, current)

    def _compute_totals(self, entities: ShipmentEntities) -> None:
        """Compute aggregate totals from line items."""
        if not entities.items:
            return

        # Total quantity
        total_qty = 0
        total_amount = 0.0
        total_net = 0.0
        total_gross = 0.0

        for item in entities.items:
            if item.quantity:
                try:
                    total_qty += float(str(item.quantity).replace(",", ""))
                except ValueError:
                    pass
            if item.amount:
                try:
                    total_amount += float(str(item.amount).replace(",", ""))
                except ValueError:
                    pass
            if item.net_weight:
                try:
                    total_net += float(str(item.net_weight).replace(",", ""))
                except ValueError:
                    pass
            if item.gross_weight:
                try:
                    total_gross += float(str(item.gross_weight).replace(",", ""))
                except ValueError:
                    pass

        if total_qty > 0:
            ml_total_qty_str = entities.total_quantity
            if ml_total_qty_str:
                # ML-extracted total exists — validate vs computed sum
                try:
                    ml_total_qty = float(str(ml_total_qty_str).replace(",", ""))
                    if total_qty > 0 and abs(ml_total_qty - total_qty) / total_qty > 0.25:
                        # Significant mismatch (>25%): flag as inconsistency
                        entities.validation_notes.append(
                            f"[JT_CONSISTENCY] ML total={ml_total_qty:.0f} vs "
                            f"item sum={total_qty:.0f} (diff={abs(ml_total_qty - total_qty):.0f}). "
                            f"Using item sum. Items may need review."
                        )
                        logger.warning(
                            f"[JT] Inconsistency: ML={ml_total_qty:.0f}, "
                            f"items sum={total_qty:.0f}, items={len(entities.items)}"
                        )
                        # Prefer item-sum over ML total when they disagree significantly
                        entities.total_quantity = str(int(total_qty))
                except ValueError:
                    entities.total_quantity = str(int(total_qty))
            else:
                # No ML total — use computed sum
                entities.total_quantity = str(int(total_qty))

        if total_amount > 0 and entities.total_amount is None:
            entities.total_amount = f"{total_amount:.2f}"
        if total_net > 0 and entities.total_net_weight is None:
            entities.total_net_weight = f"{total_net:.2f}"
        if total_gross > 0 and entities.total_gross_weight is None:
            entities.total_gross_weight = f"{total_gross:.2f}"
