from __future__ import annotations

import re
import datetime
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import logging

from config import POSTPROC_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class NormalizedValue:
    """A normalized value with original and cleaned form."""
    original: str
    normalized: str
    confidence: float   # 0.0 - 1.0
    method: str         # 'exact', 'parsed', 'inferred', 'invalid'

    def __bool__(self) -> bool:
        return bool(self.normalized)


class EntityNormalizer:
    # Normalizes entity values to standard formats for CEISA export.
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or POSTPROC_CONFIG
        self._date_formats = self.config.get("date_formats", [])
        self._default_date_fmt = self.config.get("default_date_format", "%Y-%m-%d")
        self._currency_codes = dict.fromkeys(self.config.get("currency_codes", []))
        self._incoterms_codes = set(self.config.get("incoterms_codes", []))
        self._port_codes = self.config.get("port_codes", {})
        self._country_codes = self.config.get("country_codes", {})
        self._unit_codes = self.config.get("unit_codes", {})
        self._packaging_codes = self.config.get("packaging_codes", {})
        self._vessel_flag_codes = self.config.get("vessel_flag_codes", {})

    def normalize_date(self, value: str) -> NormalizedValue:
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip()

        for fmt in self._date_formats:
            try:
                parsed = datetime.datetime.strptime(original, fmt)
                return NormalizedValue(
                    original=original,
                    normalized=parsed.strftime(self._default_date_fmt),
                    confidence=1.0,
                    method="parsed",
                )
            except ValueError:
                continue

        # Fuzzy parsing
        normalized = self._fuzzy_date_parse(original)
        if normalized:
            return NormalizedValue(
                original=original, normalized=normalized,
                confidence=0.7, method="inferred",
            )

        return NormalizedValue(
            original=original, normalized=original,
            confidence=0.0, method="unparsed",
        )

    def _fuzzy_date_parse(self, text: str) -> Optional[str]:
        text = text.strip()

        # DD MMM YYYY (e.g., "05 Jan 2026")
        m = re.search(r"(\d{1,2})\s+(\w{3,9})\s+(\d{4})", text)
        if m:
            day, month_str, year = m.groups()
            month_num = self._month_to_num(month_str)
            if month_num:
                return f"{year}-{month_num:02d}-{int(day):02d}"

        # DD/MM/YYYY or DD-MM-YYYY
        m = re.search(r"(\d{1,2})[\s\-/.](\d{1,2})[\s\-/.](\d{4})", text)
        if m:
            d, mo, y = m.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d}"

        # YYYY-MM-DD
        m = re.search(r"(\d{4})[\-](\d{1,2})[\-](\d{1,2})", text)
        if m:
            y, mo, d = m.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d}"

        return None

    def _month_to_num(self, month_str: str) -> Optional[int]:
        months = {
            "jan": 1, "january": 1, "feb": 2, "february": 2,
            "mar": 3, "march": 3, "apr": 4, "april": 4,
            "may": 5, "jun": 6, "june": 6,
            "jul": 7, "july": 7, "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10, "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        return months.get(month_str.lower()[:3])

    def normalize_number(self, value: str) -> NormalizedValue:
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip()
        cleaned = original

        # European format: 1.234,56
        if re.match(r"^\d{1,3}(\.\d{3})*,\d{1,2}$", cleaned):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        # US format: 1,234.56
        elif re.match(r"^\d{1,3}(,\d{3})*\.\d{1,2}$", cleaned):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = re.sub(r"[\s,]+", "", cleaned)

        try:
            float(cleaned)
            return NormalizedValue(
                original=original, normalized=cleaned,
                confidence=1.0, method="parsed",
            )
        except ValueError:
            return NormalizedValue(
                original=original, normalized=original,
                confidence=0.0, method="invalid",
            )

    def normalize_weight(self, value: str) -> NormalizedValue:
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        cleaned = re.sub(
            r"\s*(KGS?|KG|LBS?|LB|MT|TONS?)\s*$", "",
            str(value).strip(), flags=re.IGNORECASE
        )
        result = self.normalize_number(cleaned)

        if result and result.normalized:
            val = float(result.normalized)
            if "mt" in str(value).lower() or "ton" in str(value).lower():
                val *= 1000
            result.normalized = str(val)

        return result

    def normalize_currency(self, value: str) -> NormalizedValue:
        # Normalize currency to standard 3-letter ISO code.
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip().upper()
        if original in self._currency_codes:
            return NormalizedValue(
                original=value, normalized=original,
                confidence=1.0, method="exact",
            )
        mapped = self._currency_codes.get(original)
        if mapped:
            return NormalizedValue(
                original=value, normalized=mapped,
                confidence=0.9, method="mapped",
            )
        return NormalizedValue(
            original=value, normalized=original,
            confidence=0.5, method="inferred",
        )

    def normalize_country(self, value: str) -> NormalizedValue:
        # Normalize country name to ISO 2-letter code.
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip().upper()
        if len(original) == 2 and original.isalpha():
            return NormalizedValue(
                original=value, normalized=original,
                confidence=1.0, method="exact",
            )
        for name, code in self._country_codes.items():
            if name.upper() in original or original in name.upper():
                return NormalizedValue(
                    original=value, normalized=code,
                    confidence=0.95, method="mapped",
                )
        return NormalizedValue(
            original=value, normalized=original,
            confidence=0.3, method="inferred",
        )

    def normalize_port(self, value: str) -> NormalizedValue:
        # Normalize port name to UN/LOCODE.
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip().upper()
        if original in self._port_codes.values():
            return NormalizedValue(
                original=value, normalized=original,
                confidence=1.0, method="exact",
            )
        for name, code in self._port_codes.items():
            if name.upper() in original or original in name.upper():
                return NormalizedValue(
                    original=value, normalized=code,
                    confidence=0.9, method="mapped",
                )
        return NormalizedValue(
            original=value, normalized=original,
            confidence=0.5, method="inferred",
        )

    def normalize_incoterms(self, value: str) -> NormalizedValue:
        # Normalize incoterms to standard uppercase codes.
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip().upper()
        if original in self._incoterms_codes:
            return NormalizedValue(
                original=value, normalized=original,
                confidence=1.0, method="exact",
            )
        return NormalizedValue(
            original=value, normalized=original,
            confidence=0.5, method="inferred",
        )

    def normalize_unit(self, value: str) -> NormalizedValue:
        # Normalize unit of measurement to customs code.
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip().upper()
        if original in self._unit_codes:
            return NormalizedValue(
                original=value, normalized=self._unit_codes[original],
                confidence=1.0, method="mapped",
            )
        return NormalizedValue(
            original=value, normalized=original,
            confidence=0.5, method="inferred",
        )

    def normalize_packaging(self, value: str) -> NormalizedValue:
        # Normalize packaging type to customs code.
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip().upper()
        if original in self._packaging_codes:
            return NormalizedValue(
                original=value, normalized=self._packaging_codes[original],
                confidence=1.0, method="mapped",
            )
        return NormalizedValue(
            original=value, normalized=original,
            confidence=0.5, method="inferred",
        )

    def normalize_hs_code(self, value: str) -> NormalizedValue:
        # Validate and normalize HS code (6-10 digits).
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip()
        cleaned = re.sub(r"[\.\s]", "", original)

        if re.match(r"^\d{6,13}$", cleaned):
            try:
                chapter = int(cleaned[:2])
                if not (1 <= chapter <= 97):
                    return NormalizedValue(
                        original=original, normalized=original,
                        confidence=0.0, method="invalid_chapter",
                    )
                # Format with dots
                if len(cleaned) == 6:
                    formatted = f"{cleaned[:4]}.{cleaned[4:6]}"
                elif len(cleaned) >= 8:
                    formatted = f"{cleaned[:4]}.{cleaned[4:6]}.{cleaned[6:8]}"
                else:
                    formatted = cleaned
                return NormalizedValue(
                    original=original, normalized=formatted,
                    confidence=1.0, method="parsed",
                )
            except (ValueError, IndexError):
                pass

        return NormalizedValue(
            original=original, normalized=original,
            confidence=0.0, method="invalid",
        )

    def normalize_container_number(self, value: str) -> NormalizedValue:
        # Validate container number format (4 letters + 7 digits).
        if not value or str(value).strip() == "":
            return NormalizedValue(original=value, normalized="", confidence=0.0, method="empty")

        original = str(value).strip().upper()
        cleaned = re.sub(r"[\s\-]", "", original)

        if re.match(r"^[A-Z]{4}\d{7}$", cleaned):
            return NormalizedValue(
                original=original, normalized=cleaned,
                confidence=1.0, method="parsed",
            )
        return NormalizedValue(
            original=original, normalized=cleaned,
            confidence=0.0, method="invalid",
        )

    def normalize(self, value: str, entity_type: str) -> NormalizedValue:
        if not value or str(value).strip() == "":
            return NormalizedValue(
                original=value, normalized="",
                confidence=0.0, method="empty",
            )

        normalizers = {
            "invoice_date": self.normalize_date,
            "bl_date": self.normalize_date,
            "issue_date": self.normalize_date,
            "invoice_number": lambda v: NormalizedValue(v, str(v).strip().upper(), 0.5, "as_is"),
            "bl_number": lambda v: NormalizedValue(v, str(v).strip().upper(), 0.8, "cleaned"),
            "currency": self.normalize_currency,
            "incoterms": self.normalize_incoterms,
            "country_of_origin": self.normalize_country,
            "country_of_destination": self.normalize_country,
            "port_of_loading": self.normalize_port,
            "port_of_discharge": self.normalize_port,
            "item_hs_code": self.normalize_hs_code,
            "hs_code": self.normalize_hs_code,
            "total_amount": self.normalize_number,
            "total_quantity": self.normalize_number,
            "item_quantity": self.normalize_number,
            "item_unit_price": self.normalize_number,
            "item_amount": self.normalize_number,
            "total_net_weight": self.normalize_weight,
            "total_gross_weight": self.normalize_weight,
            "net_weight": self.normalize_weight,
            "gross_weight": self.normalize_weight,
            "container_number": self.normalize_container_number,
            "unit": self.normalize_unit,
            "item_unit": self.normalize_unit,
            "packaging_type": self.normalize_packaging,
        }

        normalizer = normalizers.get(entity_type)
        if normalizer:
            return normalizer(value)

        return NormalizedValue(
            original=value,
            normalized=str(value).strip(),
            confidence=0.5,
            method="cleaned",
        )

    def normalize_entities(self, entities) -> Dict[str, Any]:
        def norm(value, entity_type):
            if value is None or str(value).strip() == "":
                return ""
            result = self.normalize(str(value), entity_type)
            return result.normalized

        def norm_list(values, entity_type):
            return [norm(v, entity_type) for v in values] if values else []

        from src.extraction.items import ItemEntity
        from src.extraction.merger import ShipmentEntities

        result: Dict[str, Any] = {
            "invoice_number": norm(entities.invoice_number, "invoice_number"),
            "invoice_date": norm(entities.invoice_date, "invoice_date"),
            "bl_number": norm(entities.bl_number, "bl_number"),
            "bl_date": norm(entities.bl_date, "bl_date"),
            "currency": norm(entities.currency, "currency"),
            "incoterms": norm(entities.incoterms, "incoterms"),
            "total_amount": norm(entities.total_amount, "total_amount"),
            "freight": entities.freight or "",
            "total_quantity": norm(entities.total_quantity, "total_quantity"),
            "total_net_weight": norm(entities.total_net_weight, "net_weight"),
            "total_gross_weight": norm(entities.total_gross_weight, "gross_weight"),
            "port_of_loading": norm(entities.port_of_loading, "port_of_loading"),
            "port_of_discharge": norm(entities.port_of_discharge, "port_of_discharge"),
            "vessel_name": entities.vessel_name or "",
            "voyage_number": entities.voyage_number or "",
            "country_of_origin": norm(entities.country_of_origin, "country_of_origin"),
            "country_of_destination": norm(entities.country_of_destination, "country_of_destination"),
            "seller_name": entities.seller_name or "",
            "seller_address": entities.seller_address or "",
            "buyer_name": entities.buyer_name or "",
            "buyer_address": entities.buyer_address or "",
            "shipper_name": entities.shipper_name or "",
            "shipper_address": entities.shipper_address or "",
            "consignee_name": entities.consignee_name or "",
            "consignee_address": entities.consignee_address or "",
            "notify_party_name": entities.notify_party_name or "",
            "notify_party_address": entities.notify_party_address or "",
            "container_numbers": norm_list(entities.container_numbers, "container_number"),
            "seal_numbers": entities.seal_numbers or [],
            "number_of_packages": norm(entities.number_of_packages, "number_of_packages"),
            "packaging_type": norm(entities.packaging_type, "packaging_type"),
            "items": [],
        }

        # Normalize items
        for item in (entities.items or []):
            item_dict = {
                "item_code": item.item_code or "",
                "description": item.description or "",
                "hs_code": norm(item.hs_code, "hs_code"),
                "quantity": norm(item.quantity, "item_quantity"),
                "unit": norm(item.unit, "item_unit"),
                "unit_price": norm(item.unit_price, "item_unit_price"),
                "amount": norm(item.amount, "item_amount"),
                "net_weight": norm(item.net_weight, "net_weight"),
                "gross_weight": norm(item.gross_weight, "gross_weight"),
                "dimensions": item.dimensions or "",
                "cartons": norm(item.cartons, "number_of_packages"),
                "cbm": item.cbm or "",
                "confidence": item.confidence,
                "source": item.source,
            }
            result["items"].append(item_dict)

        return result
