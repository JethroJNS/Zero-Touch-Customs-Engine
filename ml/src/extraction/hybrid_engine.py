from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Union

from config import (
    DOC_TYPE_CI, DOC_TYPE_PL, DOC_TYPE_BL,
    ExtractionStrategy,
)
from ml.src.ocr.engine import OCREngine, OCRResult
from .layout import LayoutExtractor
from .items import LineItemExtractor, PatternEntity
from .validator import CrossValidator
from .merger import Merger, ShipmentEntities
from .vision import VisionModelExtractor, VisionExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class HybridExtractionResult:
    shipment_id: str
    entities: ShipmentEntities
    ocr_results: Dict[str, OCRResult]
    layoutxlm_available: bool
    extraction_time: float
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shipment_id": self.shipment_id,
            "entities": self.entities.to_dict(),
            "ocr_results": {
                doc: r.to_dict() for doc, r in self.ocr_results.items()
            },
            "layoutxlm_available": self.layoutxlm_available,
            "extraction_time_seconds": self.extraction_time,
            "notes": self.notes,
        }


class HybridExtractor:
    # Hybrid NER extractor: kombinasi LayoutXLM + Pattern.
    def __init__(
        self,
        layoutxlm_model: Optional[str] = None,
        use_gpu: bool = False,
        layout_confidence_threshold: float = 0.0,
        vision_api_key: Optional[str] = None,
        vision_model: str = "gpt-4o",
        use_vision_fallback: bool = True,
        vision_min_confidence: float = 0.3,
    ):
        self.layoutxlm_model = layoutxlm_model
        self.use_gpu = use_gpu
        self.layout_confidence_threshold = layout_confidence_threshold
        self.vision_min_confidence = vision_min_confidence

        # OCR engine (CPU)
        self._ocr = OCREngine()

        # Initialize LayoutXLM extractor
        self._layout_extractor = LayoutExtractor(
            model_path=layoutxlm_model,
            use_gpu=use_gpu,
            confidence_threshold=layout_confidence_threshold,
        )

        # Pattern extractors
        self._line_item_extractor = LineItemExtractor()

        # Initialize Vision extractor
        self._vision_extractor = VisionModelExtractor(
            api_key=vision_api_key,
            model=vision_model,
        )
        self._use_vision_fallback = use_vision_fallback

        # Initialize merger
        self._merger = Merger()

        logger.info(
            f"HybridExtractor initialized: "
            f"LayoutXLM={'available' if self._layout_extractor.available else 'fallback'}, "
            f"Vision={'available' if self._vision_extractor.available else 'not configured'}, "
            f"GPU={use_gpu}"
        )

    @property
    def layoutxlm_available(self) -> bool:
        return self._layout_extractor._try_load_model()

    def extract(
        self,
        ocr_results: Dict[str, OCRResult],
        shipment_id: str = "",
    ) -> HybridExtractionResult:
        t0 = time.time()
        notes: List[str] = []
        vision_used = False

        # Extract LayoutXLM entities
        ci_layout = self._extract_layout(ocr_results.get("CI"), "CI")
        bl_layout = self._extract_layout(ocr_results.get("BL"), "BL")
        pl_layout = self._extract_layout(ocr_results.get("PL"), "PL")

        # Extract Pattern entities (numeric, tabular)
        ci_pattern = self._extract_pattern(ocr_results.get("CI"))
        bl_pattern = self._extract_pattern(ocr_results.get("BL"))
        pl_pattern = self._extract_pattern(ocr_results.get("PL"))

        # Extract line items dari CI
        ci_text = ocr_results.get("CI", OCRResult("", "", [], 0)).full_text
        ci_items = []
        if ci_text:
            ci_items = self._line_item_extractor.extract_from_ci(ci_text)

        # Merge semua layers
        entities = self._merger.merge(
            ci_layout=ci_layout,
            ci_pattern=ci_pattern,
            bl_layout=bl_layout,
            bl_pattern=bl_pattern,
            pl_layout=pl_layout,
            pl_pattern=pl_pattern,
            ci_items=ci_items,
            pl_text=ocr_results.get("PL", OCRResult("", "", [], 0)).full_text,
        )

        # Vision LLM fallback
        should_call_vision = (
            self._vision_extractor.available
            and self._use_vision_fallback
            and (
                len(entities.items) < 3
                or entities.extraction_confidence < self.vision_min_confidence
            )
        )

        if should_call_vision:
            vision_result = self._call_vision(ocr_results, shipment_id)
            if vision_result and vision_result.confidence >= 0.5:
                entities = self._fuse_vision(entities, vision_result)
                vision_used = True
                notes.append(
                    f"Vision LLM used (confidence={vision_result.confidence:.2f}, "
                    f"items={len(entities.items)}, "
                    f"time={vision_result.extraction_time_s:.1f}s)"
                )
                logger.info(
                    f"[{shipment_id}] Vision LLM enhanced: "
                    f"confidence={vision_result.confidence:.2f}, "
                    f"items={len(entities.items)}"
                )
            else:
                notes.append("Vision LLM: skipped (low confidence or unavailable)")

        elapsed = time.time() - t0
        notes.append(f"LayoutXLM: {'available' if self.layoutxlm_available else 'fallback'}")
        notes.append(f"Items extracted: {len(entities.items)}")
        notes.append(f"Extraction time: {elapsed:.2f}s")

        # Production logging summary
        quality_report = entities.get_quality_report()
        logger.info(
            f"[{shipment_id}] Hybrid extraction complete: "
            f"items={len(entities.items)}, "
            f"layout={'available' if self.layoutxlm_available else 'fallback'}, "
            f"vision={'used' if vision_used else 'not used'}, "
            f"quality_flag={quality_report['quality_flag']}, "
            f"confidence={entities.extraction_confidence:.2f}, "
            f"time={elapsed:.2f}s"
        )

        # Log missing critical fields
        critical_missing = [
            f for f in ["invoice_number", "currency", "incoterms", "total_amount"]
            if not getattr(entities, f, None)
        ]
        if critical_missing:
            logger.warning(
                f"[{shipment_id}] Critical fields missing: {critical_missing}"
            )

        return HybridExtractionResult(
            shipment_id=shipment_id,
            entities=entities,
            ocr_results=ocr_results,
            layoutxlm_available=self._layout_extractor.available,
            extraction_time=elapsed,
            notes=notes,
        )

    def _call_vision(
        self,
        ocr_results: Dict[str, OCRResult],
        shipment_id: str,
    ) -> Optional[VisionExtractionResult]:
        # Panggil Vision LLM untuk enhanced extraction.
        if not self._vision_extractor.available:
            return None

        ci_result = ocr_results.get("CI")
        bl_result = ocr_results.get("BL")

        ci_image = self._find_image_path(ci_result)
        bl_image = self._find_image_path(bl_result)

        if ci_image:
            try:
                result = self._vision_extractor.extract_from_image(ci_image, doc_type="CI")
                if result and result.confidence >= 0.5:
                    return result
            except Exception as e:
                logger.warning(f"Vision extraction failed for CI: {e}")

        if bl_image:
            try:
                result = self._vision_extractor.extract_from_image(bl_image, doc_type="BL")
                if result and result.confidence >= 0.5:
                    return result
            except Exception as e:
                logger.warning(f"Vision extraction failed for BL: {e}")

        images = []
        doc_types = []
        if ci_image:
            images.append(ci_image)
            doc_types.append("CI")
        if bl_image:
            images.append(bl_image)
            doc_types.append("BL")

        if images:
            try:
                return self._vision_extractor.extract_from_images(images, doc_types)
            except Exception as e:
                logger.warning(f"Vision batch extraction failed: {e}")

        return None

    def _find_image_path(self, ocr_result: Optional[OCRResult]) -> Optional[str]:
        # Cari image path dari OCRResult.
        if ocr_result is None:
            return None

        # Cek apakah file adalah image
        path = Path(ocr_result.file_path)
        if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"):
            if path.exists():
                return str(path)

        # Cek rendered pages directory
        rendered_dir = path.parent
        if rendered_dir.name == "rendered":
            for page_num in range(ocr_result.total_pages):
                page_img = rendered_dir / f"{path.stem}_p{page_num}.png"
                if page_img.exists():
                    return str(page_img)

        return None

    def _fuse_vision(
        self,
        entities: ShipmentEntities,
        vision: VisionExtractionResult,
    ) -> ShipmentEntities:
        # Fuse Vision LLM results ke entities yang ada.
        header_fills = {
            "invoice_number": vision.invoice_number,
            "invoice_date": vision.invoice_date,
            "bl_number": vision.bl_number,
            "bl_date": vision.bl_date,
            "seller_name": vision.seller_name,
            "seller_address": vision.seller_address,
            "buyer_name": vision.buyer_name,
            "buyer_address": vision.buyer_address,
            "shipper_name": vision.shipper_name,
            "shipper_address": vision.shipper_address,
            "consignee_name": vision.consignee_name,
            "consignee_address": vision.consignee_address,
            "notify_party_name": vision.notify_party_name,
            "notify_party_address": vision.notify_party_address,
            "vessel_name": vision.vessel_name,
            "voyage_number": vision.voyage_number,
            "port_of_loading": vision.port_of_loading,
            "port_of_discharge": vision.port_of_discharge,
            "currency": vision.currency,
            "incoterms": vision.incoterms,
            "total_amount": str(vision.total_amount) if vision.total_amount else None,
            "total_quantity": str(vision.total_quantity) if vision.total_quantity else None,
            "total_net_weight": str(vision.total_net_weight) if vision.total_net_weight else None,
            "total_gross_weight": str(vision.total_gross_weight) if vision.total_gross_weight else None,
            "number_of_packages": str(vision.number_of_packages) if vision.number_of_packages else None,
        }

        for field, value in header_fills.items():
            if value and getattr(entities, field, None) is None:
                setattr(entities, field, value)

        if vision.container_numbers:
            existing = set(entities.container_numbers)
            for cn in vision.container_numbers:
                if cn not in existing:
                    entities.container_numbers.append(cn)

        if vision.seal_numbers:
            existing = set(entities.seal_numbers)
            for sn in vision.seal_numbers:
                if sn not in existing:
                    entities.seal_numbers.append(sn)

        if vision.items:
            existing_count = len(entities.items)
            vision_count = len(vision.items)
            vision_conf = vision.confidence
            existing_conf = entities.extraction_confidence

            if vision_count > existing_count or (vision_count == existing_count and vision_conf > existing_conf):
                for item in vision.items:
                    item.source = "vision"
                entities.items = vision.items
                logger.info(
                    f"Vision items adopted: {vision_count} (vs {existing_count}), "
                    f"conf={vision_conf:.2f} (vs {existing_conf:.2f})"
                )

        if vision.items and len(vision.items) > len(entities.items) * 0.5:
            self._merger._compute_totals(entities)

        return entities

    def _extract_layout(
        self,
        ocr_result: Optional[OCRResult],
        doc_type: str,
    ) -> Dict[str, List]:
        # Extract layout entities dengan LayoutXLM.
        if ocr_result is None:
            return {}

        try:
            return self._layout_extractor.extract(ocr_result, doc_type)
        except Exception as e:
            logger.warning(f"LayoutXLM extraction failed for {doc_type}: {e}")
            return {}

    def _extract_pattern(
        self,
        ocr_result: Optional[OCRResult],
    ) -> Dict[str, List[PatternEntity]]:
        # Extract pattern entities.
        if ocr_result is None:
            return {}

        text = ocr_result.full_text
        if not text:
            return {}

        try:
            return self._line_item_extractor.extract_pattern_entities(text)
        except Exception as e:
            logger.warning(f"Pattern extraction failed: {e}")
            return {}

    def extract_from_files(
        self,
        file_paths: Dict[str, str],
        shipment_id: str = "",
    ) -> HybridExtractionResult:
        ocr_results: Dict[str, OCRResult] = {}
        failed_docs = []

        for doc_type, path in file_paths.items():
            if path:
                try:
                    result = self._ocr.read_file(path)
                    if result and result.full_text:
                        ocr_results[doc_type] = result
                        logger.info(
                            f"OCR success for {doc_type}: "
                            f"{len(result.full_text)} chars, "
                            f"{result.total_pages} pages"
                        )
                    else:
                        failed_docs.append(f"{doc_type} (empty result)")
                        logger.warning(f"OCR returned empty result for {doc_type}")
                except FileNotFoundError as e:
                    failed_docs.append(f"{doc_type} (file not found)")
                    logger.warning(f"File not found for {doc_type}: {e}")
                except Exception as e:
                    failed_docs.append(f"{doc_type} ({type(e).__name__}: {e})")
                    logger.warning(f"OCR failed for {doc_type} ({path}): {e}")

        if not ocr_results and failed_docs:
            raise ValueError(
                f"OCR extraction failed for all documents: {', '.join(failed_docs)}. "
                f"Check that file paths are valid and documents are readable."
            )

        return self.extract(ocr_results, shipment_id)

def extract_shipment(
    ocr_results: Dict[str, OCRResult],
    shipment_id: str = "",
    layoutxlm_model: Optional[str] = None,
    use_gpu: bool = False,
) -> ShipmentEntities:
    # One-line extraction function.
    extractor = HybridExtractor(
        layoutxlm_model=layoutxlm_model,
        use_gpu=use_gpu,
    )
    result = extractor.extract(ocr_results, shipment_id)
    return result.entities
