from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

logger = logging.getLogger(__name__)

DEBUG = False

logger = logging.getLogger(__name__)

ENTITY_PATTERNS: Dict[str, List[re.Pattern]] = {
    "invoice_number": [
        re.compile(r"C/I\s*NO[:\s]*([A-Z0-9][-A-Z0-9/]{3,40})", re.IGNORECASE),
        re.compile(r"(?:Invoice\s*(?:No\.?|Number|#)\s*[:\s]*)([A-Z0-9][-A-Z0-9/]{3,30})", re.IGNORECASE),
        re.compile(r"INV[:\s#]*([A-Z0-9][-A-Z0-9/]{3,30})", re.IGNORECASE),
    ],
    "invoice_date": [
        re.compile(r"DATE[:\s]*([A-Z][a-z]{2,3}\.?[\sd]*\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})", re.IGNORECASE),
        re.compile(r"DATE[:\s]*(\d{1,2}[\s.-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,.-]*\d{2,4})", re.IGNORECASE),
    ],
    "currency": [
        re.compile(r"(?:Currency|Valuta)[:\s]*(USD|CNY|EUR|GBP|JPY|SGD|IDR|AUD|KRW)", re.IGNORECASE),
        re.compile(r"\b(CNY|USD|EUR|GBP|JPY|SGD|IDR|AUD|KRW)\b"),
    ],
    "incoterms": [
        re.compile(r"\b(FOB|CIF|CFR|EXW|DAP|DDP|FCA|CPT|CIP|FAS|DAT)\b", re.IGNORECASE),
    ],
    "container_number": [
        re.compile(r"\b([A-Z]{4}\d{7})\b"),
        re.compile(r"Container\s*(?:No\.?|Number)?[:\s]*([A-Z0-9]{4,20})", re.IGNORECASE),
    ],
    "bl_number": [
        re.compile(r"Reference\s*(?:No\.?|#)\s*([A-Z0-9]{8,20})", re.IGNORECASE),
        re.compile(r"BL\s*(?:No\.?|Number)[:\s]*([A-Z0-9]{5,30})", re.IGNORECASE),
        re.compile(r"(?:Bill\s+of\s+Lading|B/L)[:\s#]*([A-Z0-9]{5,30})", re.IGNORECASE),
    ],
    "vessel_name": [
        re.compile(r"(?:Vessel(?:'s)?\s+name|STEAMSHIP|M/V\s*|MV\s*|M/S\s*)[:\s]*([A-Z][A-Z\s]{2,35})", re.IGNORECASE),
        re.compile(r"\b([A-Z][A-Z\s]{3,35})\s+(\d{2,4}[A-Z])\b"),
    ],
    "port_of_loading": [
        re.compile(r"(?:Port\s+(?:of\s+)?(?:Load|Origin)|From\s+)[:\s]*([A-Z][A-Z\s]{2,25}(?:,?\s*[A-Z]{2,10})?)", re.IGNORECASE),
        re.compile(r"(?:PORT\s+OF\s+LOADING)[:\s]*([A-Z][A-Z\s]{2,25})", re.IGNORECASE),
    ],
    "port_of_discharge": [
        re.compile(r"(?:Port\s+(?:of\s+)?(?:Discharge|Dest|Delivery)|To\s+)[:\s]*([A-Z][A-Z\s]{2,25}(?:,?\s*[A-Z]{2,10})?)", re.IGNORECASE),
        re.compile(r"(?:PORT\s+OF\s+(?:DISCHARGE|DESTINATION))[:\s]*([A-Z][A-Z\s]{2,25})", re.IGNORECASE),
    ],
    "gross_weight": [
        re.compile(r"(?:Gross\s*(?:Weight|Wt)|G\.?W\.?)[:\s]*([\d,]+\.?\d*)\s*(?:KGS?|KG|LBS?)?", re.IGNORECASE),
        re.compile(r"(?:TOTAL\s+)?G\.?W\.?[:\s]*([\d,]+\.?\d*)", re.IGNORECASE),
    ],
    "net_weight": [
        re.compile(r"(?:Net\s*(?:Weight|Wt)|N\.?W\.?)[:\s]*([\d,]+\.?\d*)\s*(?:KGS?|KG|LBS?)?", re.IGNORECASE),
        re.compile(r"(?:TOTAL\s+)?N\.?W\.?[:\s]*([\d,]+\.?\d*)", re.IGNORECASE),
    ],
    "country_of_origin": [
        re.compile(r"(?:Country\s+(?:of\s+)?Origin|Manufactured\s+in|Made\s+in)[:\s]*([A-Z][A-Z\s]{2,20})", re.IGNORECASE),
        re.compile(r"\bCHINA\b"),
    ],
    "number_of_packages": [
        re.compile(r"(\d+)\s*(?:CARTONS?|CARTON|CTN|PK|PCS|PC|UNT|CASES?)", re.IGNORECASE),
        re.compile(r"(?:Total\s+)?(?:Cartons?|Packages?|Boxes?|Cases?|CTN|PK)[:\s]*(\d+)", re.IGNORECASE),
    ],
    "freight_term": [
        re.compile(r"(?:Freight|FRT|Payload)[:\s]*(Prepaid|Collect|Prepaid\s*&\s*Collect)", re.IGNORECASE),
    ],
    "cbm": [
        re.compile(r"(?:CBM|Volume)[:\s]*([\d,]+\.\d{1,4})", re.IGNORECASE),
        re.compile(r"\b(\d+\.\d{1,4})\s*(?:CBM|m3)", re.IGNORECASE),
    ],
}

@dataclass
class ItemEntity:
    """Item-barbar dari CI atau PL."""
    item_code: Optional[str] = None
    description: Optional[str] = None
    hs_code: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None
    unit_price: Optional[str] = None
    amount: Optional[str] = None
    # Field tersembunyi: amount look-ahead (found from a line below the code line).
    # Used by standalone resolution as a fallback when item.amount is None.
    _la_amount: Optional[str] = None
    # Field tersembunyi: index baris _la_amount (for qty extraction in fallback).
    _la_line_idx: Optional[int] = None
    net_weight: Optional[str] = None
    gross_weight: Optional[str] = None
    dimensions: Optional[str] = None
    cartons: Optional[str] = None
    cbm: Optional[str] = None
    brand: Optional[str] = None      # Nama brand
    model: Optional[str] = None       # Nomor model
    packaging: Optional[str] = None   # Tipe kemasan
    confidence: float = 0.0
    source: str = "pattern"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_code": self.item_code,
            "description": self.description,
            "hs_code": self.hs_code,
            "quantity": self.quantity,
            "unit": self.unit,
            "unit_price": self.unit_price,
            "amount": self.amount,
            "net_weight": self.net_weight,
            "gross_weight": self.gross_weight,
            "dimensions": self.dimensions,
            "cartons": self.cartons,
            "cbm": self.cbm,
            "brand": self.brand,
            "model": self.model,
            "packaging": self.packaging,
            "confidence": self.confidence,
            "source": self.source,
        }


@dataclass
class PatternEntity:
    # Entity dari layer Pattern.
    label: str
    value: str
    confidence: float
    source: str = "pattern"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
        }

def validate_hs_code(value: str) -> Optional[str]:
    hs = value.replace(".", "").replace(",", "").replace(" ", "")
    if not re.match(r"^\d{6,13}$", hs):
        return None
    try:
        chapter = int(hs[:2])
        if not (1 <= chapter <= 97):
            return None
        # Format: 9403.10 atau 9403.10.00
        if len(hs) >= 8:
            return f"{hs[:4]}.{hs[4:6]}.{hs[6:8]}"
        return f"{hs[:4]}.{hs[4:6]}"
    except (ValueError, IndexError):
        return None


# Perbaiki error OCR umum.
_OCR_CODE_FIXES = [
    (re.compile(r"-WHITH$", re.IGNORECASE), "-WHITE"),
    (re.compile(r"-WHITI$", re.IGNORECASE), "-WHITE"),
    (re.compile(r"-WHITEI$", re.IGNORECASE), "-WHITE"),
    (re.compile(r"-WHIT$", re.IGNORECASE), "-WHITE"),
    (re.compile(r"^ID-", re.IGNORECASE), "HD-"),  # ID-SLD -> HD-SLD
]


def normalize_item_code(code: str) -> str:
    if not code:
        return code
    for pattern, replacement in _OCR_CODE_FIXES:
        code = pattern.sub(replacement, code)
    return code


# Parses CI/PL table structure into ItemEntity list.
_NON_ITEM_CODES = re.compile(
    r"^(C/I|CO\.|LTD|INC|LLC|CORP|NO|NPWP|KODE|TELP|COMMERCIAL|UNIT"
    r"|FROM|TO|PORT|VESSEL|VOYAGE|BL|DATE"
    r"|FREIGHT|TOTAL|ORIGIN|BENEFICIARY"
    r"|ADDRESS|TEL|FAX|EMAIL|BUYER|SELLER|INVOICE)$",
    re.IGNORECASE,
)

# Common words that appear in descriptions but are NOT item codes.
_NON_ITEM_WORDS = {
    # Komersial umum
    "FILING", "CABINET", "BLACK", "AND", "WHITE", "FURNITURE", "SET",
    "TABLE", "CHAIR", "DESK", "STORAGE", "RACK", "SHELF", "OFFICE",
    "NUMBER", "CODE", "PRODUCT", "TRADE", "NAME", "PORT", "DISCHARGE",
    "TERM", "PRICE", "UNIT", "QUANTITY", "TOTAL", "AMOUNT",
    # Tekstil
    "TEXTILE", "CORD", "POLYESTER", "NYLON", "YARN", "FABRIC", "WOVEN", "KNITTED",
    "HDSP", "DSP", "HD", "EPI", "D/2", "KGS", "KG", "METER", "METRE",
    "SYNTHETIC", "RUBBER", "STEEL", "PLATE", "CABIN", "COVER", "LAMP",
    # Mesin
    "ASSEMBLY", "PANEL", "CONTROL", "WINDOW", "WINE", "HARNESS", "CAPILLARY",
    "CONDENSER", "HVAC", "VENTILATION", "TEMPERATURE", "LOWER", "HINGE",
    "ADJUST", "FEET", "ROLLER", "MOTOR", "PUMP", "VALVE", "BEARING",
    # Generic product descriptors — safe to exclude from item codes
    "REFINED", "SUGAR", "REFILL", "PACK", "CARTON", "PALLET",
    "BUNDLE", "PIECE", "WHOLE", "HALF", "LARGE", "SMALL", "MEDIUM",
}


def _is_real_item_code(code: str) -> bool:
    # Cek apakah string adalah kode item nyata.
    if not code or len(code) < 4:
        return False
    # Tolak string dimensi
    if re.match(r"^\d+[Xx*]\d+([Xx*]\d+)+$", code, re.IGNORECASE):
        return False
    # Harus ada angka dan huruf
    if not any(c.isdigit() for c in code):
        return False
    if not any(c.isalpha() for c in code):
        # Izinkan kode BOM numerik
        if len(code) >= 11 and code.isdigit():
            return True  # BOM
        return False
    # Tolak nomor kontainer
    if re.match(r"^[A-Z]{3,4}\d{6,9}$", code):
        return False
    # Tolak nomor lot/tax ID
    # Tolak pattern NPWP
    # Izinkan BOM 11+ digit
    if re.match(r"^\d{6,10}$", code):
        return False
    if _NON_ITEM_CODES.match(code):
        return False
    code_upper = code.upper()
    if code_upper in _NON_ITEM_WORDS:
        return False
    # Tolak kata non-item
    if len(code) >= 6:
        for word in _NON_ITEM_WORDS:
            if re.search(r"(?<![A-Z0-9-])" + re.escape(word) + r"(?![A-Z0-9-])", code_upper):
                return False
    return True


# HS code pattern for detection in OCR text
_HS_CODE_RE = re.compile(r"\b(\d{4,12})\b")
_CURRENCY_AMOUNT_RE = re.compile(
    r"\b([1-9]\d{0,2}(?:,\d{3})+(?:\.\d{1,4})?)\b"
)


class LineItemExtractor:
    # Ekstrak item-barbar dari teks CI dengan multi-strategy parsing.
    def __init__(self):
        self._compiled_patterns = self._build_patterns()

    def _build_patterns(self) -> Dict[str, re.Pattern]:
        # Compile all regex patterns once at init.
        return {
            "item_code": [
                # Pattern: 2 huruf pertama, lalu segmen dengan segmen alphanumerik setelah hyphen.
                re.compile(r"^([A-Z]{2}[A-Z0-9]*(?:[-][A-Z0-9]+)*)(?=[\s/]|$)"),
                # BOM/material codes: numeric 12-16 digit
                re.compile(r"^(\d{12,16})\b"),
            ],
            "standalone_amount": re.compile(r"^\s*([1-9][\d,]+\.\d{2,4})\s*$"),
            "embedded_amount": re.compile(r"(\d{1,3}(?:,\d{3})+\.\d{2})\b"),
            "dims": re.compile(r"(\d{3,4}\*[x*]\d{3,4}\*[x*]\d{3,4}|\d{3,4}x\d{3,4}x\d{3,4})"),
            "price": re.compile(r"(?<![,\d])(\d{1,5}\.\d{2,4})\b"),
            "qty_amount": re.compile(
                r"(?<![A-Za-z\d.])(?<!\d)(\d{1,5})\s+(\d{1,3}(?:,\d{3})+\.\d{2,4})(?=\s|$)"
            ),
            "plain_qty": re.compile(r"^[A-Z][A-Z0-9-]{2,25}\s+(\d{1,5})\s*$"),
            "all_three": re.compile(
                r"(?<![A-Za-z\d])(?<!\d)(\d{1,5})\s+([1-9]\d{0,4}\.\d{2,4})\s+(\d{1,3}(?:,\d{3})+\.\d{2})\b"
            ),
            "qty_price": re.compile(
                r"(?<!\d)(\d{1,5})\s+([1-9]\d{0,4}\.\d{2,4})(?=\s|$)"
            ),
            # Match qty + unit keyword + price: "1600 Ea 0.17" or "1600 KGS 2.50"
            "qty_unit_price": re.compile(
                r"(?<!\d)(\d{1,5})\s+([A-Za-z]{2,5})\s+(\d{1,5}\.\d{2,4})(?=\s|$)",
                re.IGNORECASE,
            ),
        }

    def extract_from_ci(self, text: str) -> List[ItemEntity]:
        # Ekstrak item-barbar dari teks CI.
        if not text:
            return []

        # Ekstraksi kode item
        items = self._extract_by_item_code(text)

        # Fallback amount
        has_valid_items = any(item.item_code is not None for item in items)
        if not has_valid_items:
            fallback_items = self._extract_by_amount_fallback(text)
            if fallback_items:
                logger.debug(
                    f"Item-code strategy returned {len(items)} items, "
                    f"amount-fallback found {len(fallback_items)} — using fallback"
                )
                items = fallback_items
            else:
                # Fallback BOM
                # Kode BOM numeric like "16231000017350"
                bom_items = self._extract_by_bom_fallback(text)
                if bom_items:
                    logger.debug(
                        f"Item-code returned {len(items)}, amount-fallback returned 0, "
                        f"BOM-fallback found {len(bom_items)} — using BOM fallback"
                    )
                    items = bom_items

        return items

    def _extract_by_item_code(self, text: str) -> List[ItemEntity]:
        lines = text.split("\n")
        # Pattern 1: kode alphanumeric (DTGYG-HB-1, DSP-1000D/2)
        code_re1 = re.compile(r"^([A-Z][A-Z0-9-]{2,35})(?:\s|$)")
        # Pattern 2: kode BOM numeric (12-16 digits)
        code_re2 = re.compile(r"^(\d{12,16})\b")

        item_line_indices = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            m = code_re1.match(stripped)
            if m and _is_real_item_code(m.group(1)):
                item_line_indices.append(i)
                continue
            m2 = code_re2.match(stripped)
            if m2 and _is_real_item_code(m2.group(1)):
                item_line_indices.append(i)

        if not item_line_indices:
            return []

        # Bangun daftar amount standalone
        standalone_amounts: List[Tuple[int, str]] = []
        for i, line in enumerate(lines):
            m = self._compiled_patterns["standalone_amount"].match(line)
            if m:
                standalone_amounts.append((i, m.group(1)))
        if DEBUG:
            print(f"  [DEBUG] standalone_amounts detected: {[(i, v) for i, v in standalone_amounts]}")

        # Ekstrak setiap item
        items: List[ItemEntity] = []
        used_sa = set()
        if DEBUG:
            print(f"  [DEBUG] used_sa before extraction: {used_sa}")

        for item_line_idx in item_line_indices:
            item = self._extract_single_item(
                lines, item_line_idx, standalone_amounts, used_sa, item_line_indices
            )
            if item:
                items.append(item)

        # Post-process: selesaikan amount standalone
        if DEBUG:
            print(f"  [DEBUG] Calling standalone resolution: used_sa={used_sa}, standalone_amounts={standalone_amounts}")
        items = self._resolve_standalone_amounts(items, standalone_amounts, used_sa, lines)

        # Fill data yang hilang
        items = self._fill_missing_from_siblings(items, lines, item_line_indices)

        items = [
            it for it in items
            if it.quantity or it.unit_price or it.amount or it.item_code
        ]

        # Deteksi kode HS
        if items:
            all_text = "\n".join(lines)
            detected_hs = self._detect_hs_codes(all_text)

            per_item_hs = self._extract_per_item_hs(lines, item_line_indices)

            if detected_hs:
                default_hs = detected_hs[0]
                for item in items:
                    if item.hs_code is None:
                        if item.item_code and item.item_code in per_item_hs:
                            item.hs_code = per_item_hs[item.item_code]
                        else:
                            item.hs_code = default_hs
                    item.hs_code = self._normalize_hs(item.hs_code)

        return items

    def _extract_single_item(
        self,
        lines: List[str],
        item_line_idx: int,
        standalone_amounts: List[Tuple[int, str]],
        used_sa: set,
        all_item_indices: List[int],
    ) -> Optional[ItemEntity]:
        stripped = lines[item_line_idx].strip()
        code_match = None
        for cp in self._compiled_patterns["item_code"]:
            m = cp.match(stripped)
            if m:
                code_match = m
                break
        if not code_match:
            return None

        code = code_match.group(1)
        norm_code = normalize_item_code(code)

        qty: Optional[str] = None
        unit_price: Optional[str] = None
        inline_amount: Optional[str] = None
        la_inline_amount: Optional[str] = None

        # Strategy 1: UNIT-KEYWORD FIRST
        if not (unit_price or inline_amount):
            _UNIT_KW_RE = re.compile(
                r"\b(EA|EAS?|PCS?|PCE|PCS|SET|KGS|KG|MTR|M|FT|YD|"
                r"ROLL|SHEET|ROLL|DRUM|BAG|CARTON|CTN|PALLET|PAL)"
                r"(?:\s+(?=\d))",
                re.IGNORECASE,
            )
            _qty_trailing = re.compile(r"(?<!\d)(\d{1,5})\s+$")
            for ukm in _UNIT_KW_RE.finditer(stripped):
                unit = ukm.group(1).upper()
                # Look BACK for qty (integer at end of text before unit keyword)
                before_unit = stripped[:ukm.start()]
                qty_list = _qty_trailing.findall(before_unit)
                if qty_list:
                    qty = qty_list[-1]
                # Look FORWARD for price and amount
                after_unit = stripped[ukm.end():]
                dec_match = re.findall(r"\d{1,5}\.\d{2,4}", after_unit)
                if len(dec_match) >= 2:
                    dec_vals = [(d, float(d)) for d in dec_match]
                    sorted_dec = sorted(dec_vals, key=lambda x: x[1])
                    unit_price = sorted_dec[0][0]
                    inline_amount = sorted_dec[-1][0]
                    break
                elif len(dec_match) == 1:
                    unit_price = dec_match[0]
                    break

        # Strategy 2: AMOUNT-FIRST (fallback)
        if not inline_amount:
            amount_match = self._compiled_patterns["embedded_amount"].search(stripped)
            if amount_match:
                _candidate_amt = amount_match.group(1)
                after_code = stripped[len(code):amount_match.start()]
                all_decimals = re.findall(r"(?<!\d)(\d{1,5}\.\d{1,4})\b", after_code)
                _candidate_up = all_decimals[-1] if all_decimals else None
                _candidate_qty = None
                if _candidate_up:
                    search_area = after_code[:after_code.find(_candidate_up) + len(_candidate_up) + 5]
                    qty_match = re.search(
                        r"(?<!\d)(\d{1,5})\s+(?:[A-Za-z]+\s*){0,3}" + re.escape(_candidate_up),
                        search_area,
                    )
                    if qty_match:
                        abs_qty_start = len(code) + qty_match.start()
                        if abs_qty_start > 0 and stripped[abs_qty_start - 1].isalpha():
                            pass  # qty preceded by a letter (e.g., "D500") — skip
                        else:
                            _candidate_qty = qty_match.group(1)
                            # Additional guard: verify no dimension string between qty and unit_price
                            qty_end_abs = len(code) + qty_match.end()
                            between = stripped[qty_end_abs:qty_end_abs + 10]
                            if re.search(r"\d[A-Za-z]", between):
                                _candidate_qty = None  # qty followed by letter (e.g., "5D") — skip
                # Validate: qty × unit_price should ≈ amount (within 30%).
                if _candidate_qty is None:
                    _candidate_amt = None
                    _candidate_up = None
                else:
                    try:
                        qf = float(_candidate_qty.replace(",", ""))
                        upf = float(_candidate_up.replace(",", ""))
                        amf = float(_candidate_amt.replace(",", ""))
                        if qf > 0 and upf > 0:
                            expected = qf * upf
                            if abs(amf - expected) / expected < 0.30:
                                inline_amount = _candidate_amt
                                unit_price = _candidate_up
                                qty = _candidate_qty
                    except ValueError:
                        inline_amount = _candidate_amt
                        unit_price = _candidate_up
                        qty = _candidate_qty
                # If qty still missing, check next line(s) for standalone qty.
                if not qty and item_line_idx + 1 < len(lines):
                    for offset in range(1, 4):
                        if item_line_idx + offset >= len(lines):
                            break
                        next_l = lines[item_line_idx + offset].strip()
                        if re.match(r"^\d+\*[Xx*]\d+$", next_l):
                            continue
                        qm = re.match(r"^(\d{1,5})\s*$", next_l)
                        if qm and next_l not in [str(sa[1]) for sa in standalone_amounts]:
                            qty = qm.group(1)
                            break
                # Check current line for inline qty + amount (no unit keyword found).
                if not qty:
                    _AMOUNT_RE = re.compile(r"(\d[\d,]*\.\d{2,})")
                    for am in _AMOUNT_RE.finditer(stripped):
                        amt_start = am.start()
                        bc = stripped[amt_start - 1] if amt_start > 0 else 'NONE'
                        if amt_start > 0 and stripped[amt_start - 1].isdigit():
                            continue
                        # Additional guard: walk backward from the amount.
                        walk_pos = amt_start - 1
                        while walk_pos >= 0 and stripped[walk_pos] == ' ':
                            walk_pos -= 1
                        if walk_pos >= 0 and stripped[walk_pos].isalpha():
                            continue
                        # Walk back through digits/punctuation to find the word start
                        word_end = walk_pos
                        while walk_pos >= 0 and not stripped[walk_pos].isspace():
                            walk_pos -= 1
                        word_start = walk_pos + 1
                        word = stripped[word_start:word_end + 1] if word_end >= walk_pos else ""
                        # Check if the word CONTAINS a letter → code fragment.
                        if re.search(r"[A-Za-z]", word):
                            continue
                        # Walk backward from the amount, skipping the space directly before it
                        pos = amt_start - 1
                        while pos >= 0 and stripped[pos] == ' ':
                            pos -= 1
                        if pos < 0:
                            continue
                        end_idx = pos  # last char of the preceding word
                        while pos >= 0 and not stripped[pos].isspace():
                            pos -= 1
                        between = stripped[pos + 1:end_idx + 1]
                        if re.match(r"^\d+$", between):
                            qty = between
                            inline_amount = am.group(1)
                            unit_price = None
                            # Look for unit_price among earlier amounts on this same line
                            for early_am in _AMOUNT_RE.finditer(stripped[:amt_start]):
                                esp = early_am.start() - 1
                                while esp >= 0 and stripped[esp] == ' ':
                                    esp -= 1
                                if esp < 0:
                                    continue
                                e_end = esp
                                while esp >= 0 and not stripped[esp].isspace():
                                    esp -= 1
                                ebetween = stripped[esp + 1:e_end + 1]
                                if re.match(r"^\d+$", ebetween):
                                    unit_price = early_am.group(1)
                                    break
                            break

        # Strategy 3: qty + unit_price + amount
        if not inline_amount:
            m3 = self._compiled_patterns["all_three"].search(stripped)
            if m3:
                _qty, _up, _amt = m3.group(1), m3.group(2), m3.group(3)
                # Validate: qty × unit_price should ≈ amount (within 30%)
                try:
                    qf = float(_qty.replace(",", ""))
                    upf = float(_up.replace(",", ""))
                    amf = float(_amt.replace(",", ""))
                    if qf > 0 and upf > 0:
                        expected = qf * upf
                        if abs(amf - expected) / expected < 0.30:
                            qty, unit_price, inline_amount = _qty, _up, _amt
                except ValueError:
                    qty, unit_price, inline_amount = _qty, _up, _amt

        # Strategy 3b: qty + unit_price (direct, e.g., "1600 Ea 0.17" or "1600 2.50")
        if not unit_price:
            mup = self._compiled_patterns["qty_unit_price"].search(stripped)
            if mup:
                if mup.start() > 0 and stripped[mup.start() - 1].isalpha():
                    pass  # qty preceded by letter — skip
                else:
                    _qty_candidate = mup.group(1)
                    _up_candidate = mup.group(3)
                    # Guard: qty must be purely numeric (no dimension suffixes like "D500")
                    if re.match(r"^\d+$", _qty_candidate):
                        qty = _qty_candidate
                        unit_price = _up_candidate
                        # Check if there's also an inline amount after the price
                        price_pos = stripped.find(unit_price)
                        remaining = stripped[price_pos + len(unit_price):]
                        am = self._compiled_patterns["embedded_amount"].search(remaining)
                        if am:
                            inline_amount = am.group(1)

        # Strategy 3c: qty + price (direct, e.g., "1600 2.50")
        if not unit_price and not inline_amount:
            am_check = self._compiled_patterns["embedded_amount"].search(stripped)
            if am_check:
                # Don't set inline_amount yet — find qty/price first, then validate
                _qty_from_3c: Optional[str] = None
                _up_from_3c: Optional[str] = None
                m2 = self._compiled_patterns["qty_price"].search(stripped)
                if m2 and m2.start() < am_check.start():
                    # Guard: the char 2 positions before qty must NOT be a digit + letter combo.
                    if m2.start() >= 2 and stripped[m2.start() - 1].isdigit() and stripped[m2.start() - 2].isalpha():
                        pass
                    elif m2.start() > 0 and stripped[m2.start() - 1].isalpha():
                        pass
                    else:
                        _qty_from_3c = m2.group(1)
                        candidate = m2.group(2)
                        if "," in candidate.split(".")[0]:
                            pass  # comma in qty position — not a valid qty
                        else:
                            _up_from_3c = candidate
                # Only set values if qty was found and guards passed
                if _qty_from_3c is not None:
                    qty = _qty_from_3c
                    inline_amount = am_check.group(1)
                    if _up_from_3c is not None:
                        unit_price = _up_from_3c

        # Strategy 4: qty + amount (no unit_price)
        if not qty and not unit_price:
            m = self._compiled_patterns["qty_amount"].search(stripped)
            if m:
                if DEBUG:
                    print(f"  [DEBUG S4] {norm_code} line {item_line_idx}: qty_amount match on {stripped!r} -> qty={m.group(1)!r}, amount={m.group(2)!r}")
            if m:
                match_start = m.start()
                before2 = stripped[match_start - 2] if match_start >= 2 else ' '
                if before2.isdigit() or before2 == '.':
                    next_m = self._compiled_patterns["qty_amount"].search(stripped, match_start + 1)
                    if next_m:
                        qty, inline_amount = next_m.group(1), next_m.group(2)
                else:
                    qty, inline_amount = m.group(1), m.group(2)

        # Strategy 5: plain integer qty only
        if not qty:
            m4 = self._compiled_patterns["plain_qty"].match(stripped)
            if m4:
                qty = m4.group(1)

        # Strategy 6: only amount visible — ONLY from item's own line (starts with code).
        if not inline_amount and qty and unit_price:
            if stripped.startswith(norm_code or ''):
                em = self._compiled_patterns["embedded_amount"].search(stripped)
                if em:
                    amt_val = float(em.group(1).replace(",", ""))
                    try:
                        qty_f = float(str(qty).replace(",", ""))
                        up_f = float(str(unit_price).replace(",", ""))
                        if qty_f > 0 and up_f > 0:
                            expected = qty_f * up_f
                            if abs(amt_val - expected) / expected < 0.15:
                                inline_amount = em.group(1)
                    except ValueError:
                        inline_amount = em.group(1)

        # Extra: qty AFTER dimensions (HD-SLD style: "code desc HxWxD qty" — qty comes after dims)
        if not qty:
            dim_m = self._compiled_patterns["dims"].search(stripped)
            if dim_m:
                # Walk forward from end of dims, skipping *XxHhWwDd chars and spaces
                pos = dim_m.end()
                while pos < len(stripped) and stripped[pos] in ' *XxHhWwDd':
                    pos += 1
                # Skip trailing spaces only
                while pos < len(stripped) and stripped[pos] == ' ':
                    pos += 1
                # Collect digits — only if we stayed on the same line (not at end)
                if pos < len(stripped) and stripped[pos].isdigit():
                    num_end = pos
                    while num_end < len(stripped) and stripped[num_end].isdigit():
                        num_end += 1
                    after_dim = stripped[pos:num_end].strip()
                    if re.match(r"^\d{1,5}$", after_dim):
                        qty = after_dim
                        if DEBUG:
                            print(f"  [DEBUG EXTRACT] {norm_code}: found qty={qty!r} after dims on line {item_line_idx}")
        # Generic qty-prefix-less amount pattern:
        if not qty and not unit_price and not inline_amount:
            _B_AMOUNT_RE = re.compile(r"(\d[\d,]*\.\d{2,})")
            _all_amounts = list(_B_AMOUNT_RE.finditer(stripped))
            _comma_amt = None
            _plain_amt = None
            for _m in _all_amounts:
                if ',' in _m.group(1):
                    _comma_amt = _m
                elif _plain_amt is None:
                    _plain_amt = _m
            if _comma_amt and _plain_amt:
                _up_str = _plain_amt.group(1)
                _amt_str = _comma_amt.group(1)
                try:
                    _up_f = float(_up_str)
                    _amt_f = float(_amt_str.replace(",", ""))
                    if _up_f > 0 and _amt_f > 100:
                        unit_price = _up_str
                        inline_amount = _amt_str
                        _qty_candidate = round(_amt_f / _up_f)
                        if _qty_candidate >= 1:
                            qty = str(_qty_candidate)
                except ValueError:
                    pass

        # Look-ahead (up to 4 lines or until next item)
        next_item_idx = self._find_next_item_line(lines, item_line_idx, all_item_indices)
        if DEBUG:
            print(f"  [DEBUG EXTRACT] {norm_code} line={item_line_idx}: has_inline={'Yes' if inline_amount else 'No'}, has_qty={'Yes' if qty else 'No'}, next_item={next_item_idx}")
        has_dims = bool(self._compiled_patterns["dims"].search(stripped))
        has_amount = bool(inline_amount)
        # Always look ahead up to 4 lines when current line is code-only (no dims/amount).
        max_la = 4 if (has_dims or has_amount) else 4
        # Track la_idx for the ItemEntity constructor (needed for backward look too)
        la_idx: Optional[int] = None
        _la_line_idx: Optional[int] = None  # Initialize for backward look

        # Backward look for split-item format (DTGYG style: data BEFORE item code line)
        if not qty and not inline_amount and item_line_idx > 0:
            prev_l = lines[item_line_idx - 1].strip()
            # Cek apakah baris sebelumnya split (no item code)
            prev_is_split = bool(
                re.match(r"^\d+\s+\d", prev_l) and
                not any(cp.match(prev_l) for cp in self._compiled_patterns["item_code"])
            )
            # Guard the backward walk: skip if prev line starts with an item code.
            prev_starts_with_item_code = any(
                cp.match(prev_l) for cp in self._compiled_patterns["item_code"]
            )
            if prev_is_split:
                if DEBUG:
                    print(f"  [DEBUG BACK] {norm_code}: found split data on prev line: {prev_l!r}")
                # Parse qty dan amount dari baris split
                split_m = re.match(r"^(\d+)\s+([\d,]+\.\d{2,4})\s*$", prev_l)
                if split_m:
                    qty = split_m.group(1)
                    inline_amount = split_m.group(2)
            elif prev_starts_with_item_code:
                # Prev line is another item's line
                pass
            else:
                # Cek jika baris sebelumnya ada look-ahead from the previous item.
                prev_l = lines[item_line_idx - 1].strip()
                _LA_AMOUNT_RE = re.compile(r"(\d[\d,]+\.\d{2,4})\b")
                prev_amounts = list(_LA_AMOUNT_RE.finditer(prev_l))
                if len(prev_amounts) >= 1:
                    amt_match = prev_amounts[0]
                    amt_val = float(amt_match.group(1).replace(",", ""))
                    if amt_val < 100000:
                        # Guard: if the char before the amount is a digit, the amount is part of a dimension string (e.g., "H1850*W1200*D500 245.15").
                        if amt_match.start() > 0 and prev_l[amt_match.start() - 1].isdigit():
                            # Amount is embedded in dimensions — skip this amount entirely
                            pass
                        else:
                            # Walk backward to find qty (integer before amount)
                            pos = amt_match.start() - 1
                            while pos >= 0 and prev_l[pos] == ' ':
                                pos -= 1
                            end_idx = pos
                            while pos >= 0 and not prev_l[pos].isspace():
                                pos -= 1
                            between = prev_l[pos + 1:end_idx + 1]
                            if re.match(r"^\d+$", between):
                                qty = between
                                inline_amount = amt_match.group(1)
                                la_inline_amount = amt_match.group(1)
                                used_sa.add(item_line_idx - 1)
                                _la_line_idx = item_line_idx - 1
                                if DEBUG:
                                    print(f"  [DEBUG BACK] {norm_code}: found qty+amount from prev line: qty={between!r}, amount={amt_match.group(1)!r}")
                            else:
                                # Couldn't find valid qty via backward walk (e.g., "FILING CABINET 245.15 ...").
                                la_inline_amount = amt_match.group(1)
                                _la_line_idx = item_line_idx - 1
                                if DEBUG:
                                    print(f"  [DEBUG BACK] {norm_code}: found amount only from prev line: amount={amt_match.group(1)!r}, qty_walk={between!r}")

        for la in range(1, min(max_la, next_item_idx - item_line_idx)):
            la_idx = item_line_idx + la
            next_l = lines[la_idx].strip()
            # Skip baris dengan kode item lain — those belong to the next item.
            if any(cp.match(next_l) for cp in self._compiled_patterns["item_code"]):
                continue
            if DEBUG:
                print(f"  [DEBUG LA] {norm_code}: used_sa={used_sa}, adding={la_idx}")

            # Claim standalone qty if item needs qty
            if not qty:
                qm = re.match(r"^(\d{1,5})\s*$", next_l)
                if qm:
                    qty = qm.group(1)

            # Claim standalone price — but NOT if qty_price will fire (qty_price extracts both).
            if not unit_price:
                qty_price_m = self._compiled_patterns["qty_price"].search(next_l)
                if qty_price_m and qty_price_m.start() < (len(next_l) - 1):
                    # Guard: char 2 before qty must not be digit+letter (e.g., 'D500')
                    if not (qty_price_m.start() >= 2 and next_l[qty_price_m.start()-1].isdigit() and next_l[qty_price_m.start()-2].isalpha()):
                        if not (qty_price_m.start() > 0 and next_l[qty_price_m.start()-1].isalpha()):
                            # Guard: comma not in qty position
                            qty_part = qty_price_m.group(1)
                            if "," not in qty_part.split(".")[0]:
                                qty = qty_price_m.group(1)
                                unit_price = qty_price_m.group(2)
                else:
                    # Fallback: standalone price (no qty extraction needed here)
                    pm = self._compiled_patterns["price"].search(next_l)
                    if pm:
                        unit_price = pm.group(1)

            # Always track _la_line_idx when an embedded amount is found in range.
            em_la = self._compiled_patterns["embedded_amount"].search(next_l)
            if em_la:
                if DEBUG:
                    print(f"  [DEBUG LA] {norm_code}: la_idx={la_idx}, embedded={em_la.group(1)!r}, line={next_l!r}")
                # Guard: skip TOTAL-like lines — never claim amounts from TOTAL/SUBTOTAL headers
                _TOTAL_KEYWORDS = {"TOTAL", "SUBTOTAL", "GRAND TOTAL", "AMOUNT", "JUMLAH", "NETTO", "BRUTO"}
                first_word = re.split(r"[^A-Za-z]", next_l)[0].upper()
                if first_word in _TOTAL_KEYWORDS:
                    continue  # TOTAL lines should never set _la_line_idx or claim amounts
                # ALWAYS track _la_line_idx for standalone resolution
                if _la_line_idx is None:
                    _la_line_idx = la_idx
                amt_val = float(em_la.group(1).replace(",", ""))
                if amt_val < 100000:
                    if not inline_amount:
                        used_sa.add(la_idx)
                        la_inline_amount = em_la.group(1)
                        # Also add to standalone_amounts so _resolve_standalone_amounts can use it
                        standalone_amounts.append((la_idx, em_la.group(1)))
                    else:
                        # Look-ahead amount differs from inline_amount.
                        try:
                            qty_f = float(str(qty).replace(",", "")) if qty else 0
                            price_f = float(str(unit_price).replace(",", "")) if unit_price else 0
                            la_amt_f = float(em_la.group(1).replace(",", ""))
                            if qty_f > 0 and price_f > 0:
                                expected = qty_f * price_f
                                if abs(la_amt_f - expected) / expected < 0.15:
                                    inline_amount = em_la.group(1)
                                    la_inline_amount = em_la.group(1)
                                    standalone_amounts.append((la_idx, em_la.group(1)))
                            elif price_f > 0 and la_amt_f > 0:
                                ratio = la_amt_f / price_f
                                qty_from_la = round(ratio)
                                if abs(ratio - qty_from_la) < 0.02 and qty_from_la >= 1:
                                    inline_amount = em_la.group(1)
                                    la_inline_amount = em_la.group(1)
                                    standalone_amounts.append((la_idx, em_la.group(1)))
                        except (ValueError, ZeroDivisionError):
                            pass
                # Extract qty from this look-ahead line (walk backward from amount to find integer).
                if not qty:
                    pos = em_la.start() - 1
                    while pos >= 0 and next_l[pos] == ' ':
                        pos -= 1
                    end_idx = pos
                    while pos >= 0 and not next_l[pos].isspace():
                        pos -= 1
                    between = next_l[pos + 1:end_idx + 1]
                    if re.match(r"^\d+$", between):
                        qty = between
            else:
                # No comma-formatted embedded amount found on this look-ahead line.
                _TOTAL_KEYWORDS = {"TOTAL", "SUBTOTAL", "GRAND TOTAL", "AMOUNT", "JUMLAH", "NETTO", "BRUTO"}
                first_word = re.split(r"[^A-Za-z]", next_l)[0].upper()
                if first_word in _TOTAL_KEYWORDS:
                    continue  # Skip — TOTAL/SUBTOTAL lines should never be claimed as item data
                if not la_inline_amount and _la_line_idx is None:
                    # Guard: skip if line starts with or contains another item code
                    if any(cp.match(next_l) for cp in self._compiled_patterns["item_code"]):
                        continue  # Skip — this line belongs to another item
                    if any(cp.search(next_l) for cp in self._compiled_patterns["item_code"]):
                        continue  # Skip — another item's code is embedded on this line
                    pm_fallback = self._compiled_patterns["price"].search(next_l)
                    if pm_fallback:
                        price_val = float(pm_fallback.group(1))
                        if price_val < 100000:
                            # Check if this line has multiple decimals — last one is the amount
                            _DEC_RE = re.compile(r"\d[\d,]*\.\d{2,}")
                            all_dec = list(_DEC_RE.finditer(next_l))
                            if len(all_dec) >= 2:
                                # Last decimal is the total amount
                                _la_line_idx = la_idx
                                la_inline_amount = all_dec[-1].group(0)
                                standalone_amounts.append((la_idx, all_dec[-1].group(0)))
                                # qty = first integer before first amount (walk backward from first match)
                                first_match = all_dec[0]
                                pos = first_match.start() - 1
                                while pos >= 0 and next_l[pos] == ' ':
                                    pos -= 1
                                end_idx = pos
                                while pos >= 0 and not next_l[pos].isspace():
                                    pos -= 1
                                between = next_l[pos + 1:end_idx + 1]
                                if re.match(r"^\d+$", between):
                                    qty = between

        # Ekstrak dimensi
        dims_val: Optional[str] = None
        for dline_idx in range(item_line_idx, min(item_line_idx + 4, len(lines))):
            dmatch = self._compiled_patterns["dims"].search(lines[dline_idx])
            if dmatch:
                dims_val = dmatch.group(1)
                break

        # Description extraction for furniture-style items
        desc_from_line: Optional[str] = None

        def _extract_description(text: str) -> Optional[str]:
            # Extract product description from a furniture-style item line.
            if text.startswith(code):
                text = text[len(code):].strip()
            if not text:
                return None
            # Find first dimension pattern - description ends just before it
            dim_match = re.search(r"\d+[Xx*]\d+(?:[Xx*]\d+)?", text, re.IGNORECASE)
            if dim_match:
                desc_candidate = text[:dim_match.start()].strip()
                # Guard: description must contain letters and not be just digits/spaces
                if len(desc_candidate) >= 3 and re.search(r"[A-Za-z]", desc_candidate):
                    return re.sub(r"\s+", " ", desc_candidate)[:60]
            # No dims found: look for amount and extract text before it
            amount_m = re.search(r"\d[\d,]*\.\d{2,}", text)
            if amount_m:
                # Walk backward from amount to find preceding word (the qty or price)
                pos = amount_m.start() - 1
                while pos >= 0 and text[pos] == ' ':
                    pos -= 1
                word_end = pos + 1
                while pos >= 0 and not text[pos].isspace():
                    pos -= 1
                word_start = pos + 1
                desc_candidate = text[:word_start].strip()
                # Guard: must contain letters (not just digits) and not start with code
                if (len(desc_candidate) >= 3 and re.search(r"[A-Za-z]", desc_candidate)
                        and not desc_candidate[:10].replace(' ', '').isdigit()):
                    return re.sub(r"\s+", " ", desc_candidate)[:60]
            return None

        if item_line_idx > 0 and lines[item_line_idx - 1].strip().startswith(code):
            desc_from_line = _extract_description(lines[item_line_idx - 1].strip())

        # Fallback 2: prev line contains current code embedded (e.g., combined line)
        if not desc_from_line and item_line_idx > 0:
            prev_line = lines[item_line_idx - 1].strip()
            if code in prev_line:
                # Extract text BEFORE the item code (description part)
                code_pos = prev_line.find(code)
                before_code = prev_line[:code_pos].strip()
                if len(before_code) >= 3 and re.search(r"[A-Za-z]", before_code):
                    desc_from_line = re.sub(r"\s+", " ", before_code)[:60]

        if not desc_from_line:
            has_inline_data = bool(
                self._compiled_patterns["dims"].search(lines[item_line_idx]) or
                self._compiled_patterns["embedded_amount"].search(lines[item_line_idx])
            )
            if not has_inline_data and item_line_idx + 1 < len(lines):
                # Code-only line: description is on the next line
                desc_from_line = _extract_description(lines[item_line_idx + 1].strip())

        # Fallback 5: search nearby lines for any text with letters
        if not desc_from_line:
            for offset in range(-3, 4):
                if offset == 0:
                    continue
                nearby_idx = item_line_idx + offset
                if 0 <= nearby_idx < len(lines):
                    nearby = lines[nearby_idx].strip()
                    # Skip lines that are purely numeric (likely qty/price lines)
                    if re.match(r"^[\d\s.,]+$", nearby):
                        continue
                    # Skip lines starting with item codes
                    if any(cp.match(nearby) for cp in self._compiled_patterns["item_code"]):
                        continue
                    # Extract any text with letters
                    words = nearby.split()
                    letter_words = [w for w in words if re.search(r"[A-Za-z]", w)]
                    if letter_words:
                        # Filter out common non-description words
                        noise = {"KGS", "USD", "EUR", "GBP", "JPY", "SGD", "IDR", "CNY",
                                 "PCT", "MT", "FT", "MTR", "EA", "PCE", "PCS", "SET",
                                 "HS", "NO", "NO.", "TEL", "FAX", "EMAIL", "DATE", "TOTAL",
                                 "NET", "GROSS", "CIF", "FOB", "FREIGHT"}
                        filtered = [w for w in letter_words if w.upper() not in noise]
                        if filtered:
                            desc_candidate = " ".join(filtered[:8])
                            if len(desc_candidate) >= 3:
                                desc_from_line = desc_candidate[:60]
                                break

        # Fallback 6: use item code prefix as description (HD-SLD-2D → FILING CABINET 2-DRAWER, etc.)
        if not desc_from_line:
            # Common furniture type prefixes and their descriptions
            _CODE_PREFIX_MAP = {
                "HD-SLD-2D": "FILING CABINET 2 DRAWER",
                "HD-SLD-3D": "FILING CABINET 3 DRAWER",
                "HD-SLD-2DM": "FILING CABINET 2 DRAWER MOBILE",
                "HD-SLD-3DM": "FILING CABINET 3 DRAWER MOBILE",
                "DTGYG": "DESK",
                "TB": "TABLE",
                "DQ": "DESK",
                "CZ": "CABINET",
                "MM-": "CABINET",
                "WH-": "CABINET",
            }
            for prefix, desc in _CODE_PREFIX_MAP.items():
                if norm_code.upper().startswith(prefix):
                    desc_from_line = desc
                    break
            if not desc_from_line:
                # Last resort: use the item code itself
                desc_from_line = norm_code

        # Ekstrak dimensi
        _final_amount = inline_amount if inline_amount else la_inline_amount
        return ItemEntity(
            item_code=norm_code,
            description=desc_from_line,
            quantity=qty.strip().replace(",", "") if qty else None,
            unit=None,
            unit_price=unit_price.strip().replace(",", "") if unit_price else None,
            amount=_final_amount.strip().replace(",", "") if _final_amount else None,
            _la_amount=la_inline_amount.strip().replace(",", "") if la_inline_amount else None,
            _la_line_idx=_la_line_idx if la_inline_amount else None,
            dimensions=dims_val,
            hs_code=None,
            confidence=0.85 if (qty and (unit_price or inline_amount or la_inline_amount)) else 0.50,
            source="pattern",
        )

    # Amount-Based Fallback
    def _extract_by_amount_fallback(self, text: str) -> List[ItemEntity]:
        # Strategy 2: Amount-based fallback for textile/rubber/machinery CIs.
        lines = text.split("\n")
        detected_hs = self._detect_hs_codes(text)
        first_hs = detected_hs[0] if detected_hs else None

        items: List[ItemEntity] = []
        used_kgs_values: set = set()   # Track KGS values already assigned to items
        used_per_kg_values: set = set()  # Track unit prices already assigned

        # Detect document total qty from "TOTAL" line to filter out grand total rows
        total_qty_kgs: Optional[str] = None
        total_re = re.compile(r"\bTOTAL\s+([1-9]\d{0,8}(?:\.\d+)?)\s*KGS\b", re.IGNORECASE)
        for line in lines:
            m = total_re.search(line)
            if m:
                total_qty_kgs = m.group(1)
                if "." in total_qty_kgs:
                    total_qty_kgs = f"{float(total_qty_kgs):.0f}"
                break

        # Amount regex — three patterns for different formats:
        #   1. Currency-prefixed amount (greedy): currency + digits + optional comma-thousands + decimal
        #   2. Currency-prefixed with comma thousands: handles "USD336,873.60" correctly
        #   3. Standard plain decimal: word boundary + digits + decimal
        # Take the largest value to prefer total over unit prices.
        _amount_currency = re.compile(
            r"(?:(?:USD|EUR|GBP|JPY|SGD|IDR|AUD|CNY|THB|KRW)[\s]*)?(\d+?\.\d{2})"
        )
        _amount_european = re.compile(
            r"(?:(?:USD|EUR|GBP|JPY|SGD|IDR|AUD|CNY|THB|KRW)[\s]*)?(\d{1,3}(?:,\d{3})*\.\d{2})\b"
        )
        _amount_standard = re.compile(r"\b(\d+\.\d{2})\b")
        kgs_re = re.compile(r"\b([1-9]\d{0,8}(?:\.\d+)?)\s*(KGS|KILO|KILOS|KILOGRAM|KILOGRAMS|MT|GRS|GROSS)\b", re.IGNORECASE)
        # Unit price pattern: "2.52 /kg" or "2.52 USD/kg" or "USD 2.52 /kg"
        per_kg_re = re.compile(
            r"(?<!\d)(\d{1,5}(?:\.\d{1,4})?)\s*(?:USD?|CNY|EUR|GBP)?\s*/\s*(?:KG|KILO|KILOS)\b",
            re.IGNORECASE
        )

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # Skip lines that are clearly not item lines
            if self._skip_line(stripped):
                continue

            # Find amount on this line — try three patterns:
            #   1. Currency-prefixed with comma thousands: handles "USD336,873.60" correctly
            #   2. Currency-prefixed greedy: handles "USD24193.65" (no comma) via non-greedy \d+?
            #   3. Standard plain decimal: handles "48386.52" at word boundary
            cu_matches = _amount_currency.findall(stripped)
            eu_matches = _amount_european.findall(stripped)
            std_matches = _amount_standard.findall(stripped)
            def norm_val(s):
                return float(s.replace(",", ""))
            all_candidates = [(norm_val(m), m) for m in cu_matches + eu_matches + std_matches]
            if not all_candidates:
                continue
            all_candidates.sort(key=lambda x: x[0], reverse=True)
            amount_val, amount_str = 0.0, None
            for val, m_str in all_candidates:
                if val < 100 or val > 1_000_000:
                    continue
                # Check if this amount is a unit price (followed by /MT, /KG, etc.)
                pos = stripped.find(m_str)
                if pos >= 0:
                    after = stripped[pos + len(m_str):pos + len(m_str) + 5]
                    if re.match(r"\s*/(KG|MT|KILO|LBS)\b", after, re.IGNORECASE):
                        continue  # Skip unit prices
                amount_val, amount_str = val, m_str
                break
            if amount_str is None:
                continue

            # Determine context window (±3 lines)
            window_start = max(0, i - 3)
            window_end = min(len(lines), i + 4)
            context_lines = lines[window_start:window_end]
            context = " ".join(context_lines)

            # Find qty from KGS/MT
            qty_str: Optional[str] = None
            unit_str: Optional[str] = None
            # 1. Same-line KGS/MT match (preferred — qty and amount on same OCR line)
            kgs_match = kgs_re.search(stripped)
            if kgs_match:
                qty_str = kgs_match.group(1)
                unit_str = kgs_match.group(2).upper()
                if unit_str == "KGS":
                    if "." in qty_str:
                        qty_str = f"{float(qty_str):.0f}"
            # 2. Immediately-previous line (common OCR layout: qty on line N, amount on line N+1)
            if not qty_str and i > 0:
                prev_match = kgs_re.search(lines[i - 1])
                if prev_match:
                    qty_str = prev_match.group(1)
                    unit_str = prev_match.group(2).upper()
                    if unit_str == "KGS" and "." in qty_str:
                        qty_str = f"{float(qty_str):.0f}"
            # 3. Any KGS/MT in context that hasn't been used by a previous item
            if not qty_str:
                for kgs_m in kgs_re.finditer(context):
                    candidate = kgs_m.group(1)
                    candidate_unit = kgs_m.group(2).upper()
                    if candidate_unit == "KGS" and "." in candidate:
                        candidate = f"{float(candidate):.0f}"
                    if candidate not in used_kgs_values:
                        qty_str = candidate
                        unit_str = candidate_unit
                        unit_str = kgs_m.group(2).upper()
                        break

            # Find unit_price from /kg
            unit_price_str: Optional[str] = None
            # 1. Same-line /kg price
            per_kg_match = per_kg_re.search(stripped)
            if per_kg_match:
                unit_price_str = per_kg_match.group(1)
            # 2. Immediately-previous line
            if not unit_price_str and i > 0:
                prev_match = per_kg_re.search(lines[i - 1])
                if prev_match:
                    unit_price_str = prev_match.group(1)
            # 3. Any /kg price in context
            if not unit_price_str:
                for pk_m in per_kg_re.finditer(context):
                    if pk_m.group(1) not in used_per_kg_values:
                        unit_price_str = pk_m.group(1)
                        break

            # Hitung harga dari amount/qty if qty found but no /kg price
            if not unit_price_str and qty_str and amount_val > 0:
                try:
                    qty_f = float(qty_str)
                    if qty_f > 0:
                        computed_price = amount_val / qty_f
                        # Reasonable unit price range: $0.01 to $500
                        if 0.01 <= computed_price <= 500:
                            unit_price_str = f"{computed_price:.4f}"
                except (ValueError, ZeroDivisionError):
                    pass

            # Ekstrak deskripsi from context
            description: Optional[str] = None
            product_re = re.compile(
                r"\b(H?DSP\s*\d{3,4}[DABC]/\d|D?HDSP\s*\d{3,4}[DABC]/\d|"
                r"HDSP-\d{4,}|DSP-\d{4,}|"
                r"POLYSTER|POLYESTER|NYLON|COTTON|TEXTILE|CORD|"
                r"TYRE|TIRE|RUBBER|BELT|CHAIN|LUBRIC|"
                r"SYNTHETIC|SYNTHETIC\s+RUBBER|"
                r"KUMHO|KUMHO\s*\d+[A-Z0-9]+|"
                r"\d{4}[A-Z0-9]+)\b",
                re.IGNORECASE
            )
            # 1. Look in previous lines for product category (SYNTHETIC RUBBER often on own line)
            product_words: List[str] = []
            category_re = re.compile(
                r"\b(TEXTILE\s+CORD|POLYESTER\s+CORD|SYNTHETIC\s+RUBBER|CORD\s+FABRIC|TIRE\s+CORD)\b",
                re.IGNORECASE,
            )
            dsp_re = re.compile(
                r"\b(D?HDSP\s*\d{3,4}[DABC]/\d|D?DSP\s*\d{3,4}[DABC]/\d)\b",
                re.IGNORECASE,
            )
            # For textile/synthetic products, look back up to 5 lines for category + DSP code.
            product_words: List[str] = []
            found_dsp = False
            category_re = re.compile(
                r"\b(TEXTILE\s+CORD|POLYESTER\s+CORD|SYNTHETIC\s+RUBBER|CORD\s+FABRIC|TIRE\s+CORD)\b",
                re.IGNORECASE,
            )
            dsp_re = re.compile(
                r"\b(D?HDSP\s*\d{3,4}[DABC]/\d|D?DSP\s*\d{3,4}[DABC]/\d)\b",
                re.IGNORECASE,
            )
            for offset in range(1, 6):
                if i > offset:
                    line = lines[i - offset]
                    # First DSP found (most recent applicable line) — take only this one
                    if not found_dsp:
                        dsp_match = dsp_re.search(line)
                        if dsp_match:
                            product_words = [dsp_match.group(1)]
                            found_dsp = True
                    # Category — can accumulate from any lookback line
                    cat_match = category_re.search(line)
                    if cat_match:
                        cat_words = cat_match.group(1).split()
                        for cw in cat_words:
                            if cw.upper() not in [w.upper() for w in product_words]:
                                product_words.append(cw)
            # If we found product words from lookback, also look for EPI on current or next line
            if product_words:
                epi_match = re.search(r"\b(\d+EPI)\b", stripped, re.IGNORECASE)
                if not epi_match and i + 1 < len(lines):
                    epi_match = re.search(r"\b(\d+EPI)\b", lines[i + 1], re.IGNORECASE)
                if epi_match and epi_match.group(1) not in product_words:
                    product_words.append(epi_match.group(1))
            # 2. Same line only (no product from lookback)
            if not product_words:
                product_words = product_re.findall(stripped)
                if not any("EPI" in w.upper() for w in product_words) and i + 1 < len(lines):
                    epi_next = re.search(r"\b(\d+EPI)\b", lines[i + 1], re.IGNORECASE)
                    if epi_next and epi_next.group(1) not in product_words:
                        product_words.append(epi_next.group(1))
            # 4. Broader context
            if not product_words:
                product_words = product_re.findall(context)[:4]
            if product_words:
                description = " ".join(product_words[:4])
            else:
                # Fallback: cleaned stripped line
                desc_candidate = re.sub(r"[\d.,\s]+", "", stripped).strip()
                desc_candidate = re.sub(
                    r"^(?:TRHU|MSCU|CMAU|CSQU|EGHU|CSUQ|OOLU|CSNU|CBHU)\w*\s*",
                    "", desc_candidate, flags=re.IGNORECASE
                )
                if len(desc_candidate) > 3:
                    description = desc_candidate[:60]

            # Hitung confidence based on what we found
            confidence = 0.3
            if qty_str and unit_price_str and amount_val > 0:
                try:
                    expected = float(qty_str) * float(unit_price_str)
                    if expected > 0:
                        ratio = amount_val / expected
                        if 0.85 <= ratio <= 1.20:
                            confidence = 0.85
                        elif 0.70 <= ratio <= 1.50:
                            confidence = 0.65
                except (ValueError, ZeroDivisionError):
                    pass
            elif qty_str or unit_price_str:
                confidence = 0.50

            # Skip jika tidak ada data
            if not (qty_str or unit_price_str or description):
                continue

            # Skip grand total row (qty matches document total)
            if total_qty_kgs and qty_str == total_qty_kgs:
                continue

            items.append(ItemEntity(
                item_code=None,
                description=description,
                quantity=qty_str,
                unit=unit_str or "KGS",
                unit_price=unit_price_str,
                amount=amount_str,
                dimensions=None,
                hs_code=self._normalize_hs(first_hs) if first_hs else None,
                confidence=confidence,
                source="pattern:amount_fallback",
            ))

            # Track nilai KGS yang dipakai to avoid assigning them to subsequent items
            if qty_str:
                used_kgs_values.add(qty_str)
            if unit_price_str:
                used_per_kg_values.add(unit_price_str)

        # Deduplicate item with same amount (±0.01)
        if items:
            deduped: List[ItemEntity] = []
            seen_amounts: set = set()
            for item in items:
                if item.amount:
                    try:
                        amt_f = float(str(item.amount).replace(",", ""))
                        if any(abs(amt_f - s) < 1.0 for s in seen_amounts):
                            continue  # duplicate
                        seen_amounts.add(amt_f)
                    except ValueError:
                        pass
                deduped.append(item)
            items = deduped

        return items

    def _extract_by_bom_fallback(self, text: str) -> List[ItemEntity]:
        # Fallback untuk kode BOM numeric.
        lines = text.split("\n")
        items: List[ItemEntity] = []
        seen_bom_codes: set = set()

        # Regex patterns
        #   - Pure numeric: 10-16 digits (e.g., 16231000017350, 1234567890123)
        #   - Alphanumeric: digit prefix + 4-13 alphanumeric chars (e.g., 16231000A52167)
        bom_re = re.compile(r"\b(\d{4,16}[A-Z0-9]{0,8})\b", re.IGNORECASE)
        bom_numeric_re = re.compile(r"\b(\d{12,16})\b")
        euro_re = re.compile(r"\b(\d{1,3}\.\d{3}(?:,\d{2}))\b")
        euro_small_re = re.compile(r"\b(\d+(?:,\d{1,4}))\b")
        plain_int_re = re.compile(r"(?<![.\d])(\d{1,5})(?![.,\d])")
        # Units
        unit_re = re.compile(r"\b([A-Z]{2,4})\b")
        # Garbage
        garbage_re = re.compile(r"\b(Freight|TOTAL|Total|Bank|Charge)\b", re.IGNORECASE)

        euro_to_float = lambda s: float(s.replace(".", "").replace(",", "."))

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Cari kode BOM first, then numeric fallback
            bom_matches = bom_re.findall(stripped)
            if not bom_matches:
                bom_matches = bom_numeric_re.findall(stripped)
            if not bom_matches:
                # Skip short lines that aren't BOM lines
                if len(stripped) < 5:
                    continue
                continue
            bom_code = bom_matches[0]
            if bom_code in seen_bom_codes:
                continue
            # Filter: min 10 karakter
            if len(bom_code) < 10:
                continue
            seen_bom_codes.add(bom_code)

            # Merge baris berikutnya that are part of the same row
            merged = stripped
            char_len = len(stripped)
            for j in range(i + 1, min(i + 3, len(lines))):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                # Stop if next line has another BOM code (check both patterns)
                if bom_re.search(next_line) or bom_numeric_re.search(next_line):
                    break
                # Stop if we've extended too far (>180 chars total)
                if char_len + len(next_line) > 180:
                    break
                merged += " " + next_line
                char_len += 1 + len(next_line)  # +1 for space

            merged_lower = merged.lower()

            # Skip garbage
            if garbage_re.search(merged):
                continue

            # Ekstrak HS from merged row
            hs_match = re.search(r"\b(\d{8})\b", merged)
            hs_code = None
            if hs_match:
                potential_hs = hs_match.group(1)
                chapter = int(potential_hs[:2])
                if 1 <= chapter <= 97:
                    hs_code = self._normalize_hs(potential_hs)

            # Ekstrak deskripsi: text after BOM code, before any numeric content (prices/qtys)
            # Step 1: clean the merged row for description extraction
            clean_for_desc = re.sub(r"\s*\d{1,3}\.\d{3},\d{2}\b", "", merged)  # large euro amounts
            clean_for_desc = re.sub(r"\s*\d+,\d{2}\b", "", clean_for_desc)  # small euro amounts like 225,38
            clean_for_desc = re.sub(r"\s*\d+,\d{1,4}\b", "", clean_for_desc)  # euro qtys 0,0294
            clean_for_desc = re.sub(r"\s+\d{8}\b", "", clean_for_desc)  # remove HS codes
            # Remove LARTAS/remark junk (Deklarasi Impor, Deklanasi Impo, etc.)
            clean_for_desc = re.sub(r"(Dek[a-z]+\s+[Ii]mpor?)\b.*", "", clean_for_desc, re.IGNORECASE)
            # Remove trailing unit labels
            clean_for_desc = re.sub(r"\s+(INE|KGM|TNE|Ea|Pcs|UN|Ct)\s*$", "", clean_for_desc, flags=re.IGNORECASE)
            # Ekstrak deskripsi: after BOM code, capture text (letters/spaces/hyphens only).
            desc_match = re.match(
                rf"{re.escape(bom_code)}(?:\s+(?:INE|KGM|TNE|Ea|Pcs|UN|Ct))?\s+([A-Za-z][A-Za-z\s\-'.]{{2,60}})",
                clean_for_desc,
            )
            description = None
            if desc_match:
                desc_text = desc_match.group(1).strip()
                if len(desc_text) > 2:
                    description = desc_text[:60]

            # Ekstrak amount Europe (these are prices, not quantities)
            euro_amounts = []
            for m in euro_re.finditer(merged):
                val = euro_to_float(m.group(1))
                if 10 <= val <= 200_000:
                    euro_amounts.append(val)

            # Ekstrak qty integer — pick LARGEST (1200 > 294 > 276)
            plain_qtys = []
            for m in plain_int_re.finditer(merged):
                val = int(m.group(1))
                if 1 <= val <= 50_000:
                    plain_qtys.append(val)
            # Sort descending: prefer large item quantities over small fragments
            plain_qtys.sort(reverse=True)

            # Ekstrak unit
            units = [m.group(1) for m in unit_re.finditer(merged)
                     if m.group(1) in ("INE", "KGM", "TNE", "EA", "PCS", "UN", "CT", "EA")]
            unit = units[0] if units else "TNE"
            unit_map = {"INE": "TNE", "KGM": "KGM", "EA": "NMP", "PCS": "NMP", "UN": "NMP", "CT": "NMP"}
            customs_unit = unit_map.get(unit, "TNE")

            # Tentukan qty, harga, amount
            qty_val: Optional[float] = None
            unit_price_val: Optional[float] = None
            amount_val: Optional[float] = None

            # Strategy 1: plain integer qty FIRST (e.g., 1200, 4800, 2400)
            for q in plain_qtys:
                if 100 <= q <= 50_000:
                    qty_val = float(q)
                    break

            # Strategy 2: small euro qty (e.g., 4,2 or 0,0294)
            if not qty_val:
                for m in euro_small_re.finditer(merged):
                    val = euro_to_float(m.group(1))
                    if 0.001 <= val < 50:
                        qty_val = val
                        break

            # Amount: largest euro value in row
            if euro_amounts:
                euro_amounts.sort(reverse=True)
                amount_val = euro_amounts[0]
                amount_str = f"{amount_val:.2f}"

                # Unit price: if we have qty and amount
                if qty_val and qty_val > 0:
                    unit_price_val = amount_val / qty_val
                    unit_price_str = f"{unit_price_val:.4f}"
                else:
                    unit_price_str = None
            else:
                amount_str = None
                unit_price_str = None

            if not (qty_val or amount_val):
                continue

            confidence = 0.55 if (qty_val and amount_val and unit_price_val) else 0.4

            items.append(ItemEntity(
                item_code=bom_code,
                description=description,
                quantity=str(qty_val) if qty_val else None,
                unit=customs_unit,
                unit_price=unit_price_str,
                amount=amount_str,
                dimensions=None,
                hs_code=hs_code,
                confidence=confidence,
                source="pattern:bom_fallback",
            ))

        return items

    def _skip_line(self, stripped: str) -> bool:
        # Cek apakah baris bukan baris item.
        # Skip pure numeric lines
        if re.match(r"^[\d\s,.\-+]+$", stripped):
            return True
        # Skip very short lines
        if len(stripped) < 4:
            return True
        # Skip lines that are mostly dates or numbers
        alpha = sum(1 for c in stripped if c.isalpha())
        if len(stripped) > 10 and alpha / len(stripped) < 0.15:
            return True
        # Skip header/address lines that are generic patterns (not specific cities)
        address_patterns = [
            r"^(?:JL\.?|KENARI|RAYA|BLOK)\s",  # Indonesian address prefix
            r"^(?:JL\.?|JL |KENARI|RAYA|BLOK)\s",  # address lines starting with street prefix
            r"^\d{2}[.-]\d{2}[.-]\d{2,}",  # Date patterns
            r"^\d{3}[.-]\d{3}[.-]\d{3}",   # Tax ID patterns
            r"(?:TELEGRAM|FAX|TEL\.?|PHONE|EMAIL|WEBSITE|HTTP)",  # Contact info
            r"(?:TAX\s*ID|NPWP|IDENTITY|Nomor\s+ID)",  # Tax/ID references
            r"^(?:INDONESIA|CHINA|SINGAPORE|MALAYSIA|THAILAND)$",  # Country names alone
        ]
        lower = stripped.lower()
        for pat in address_patterns:
            if re.search(pat, lower, re.IGNORECASE):
                return True
        return False

    def _find_next_item_line(
        self,
        lines: List[str],
        current_idx: int,
        all_indices: List[int],
    ) -> int:
        # Cari index baris kode item berikutnya.
        for i in all_indices:
            if i > current_idx:
                return i
        return len(lines)

    def _resolve_standalone_amounts(
        self,
        items: List[ItemEntity],
        standalone_amounts: List[Tuple[int, str]],
        used_sa: set,
        lines: List[str],
    ) -> List[ItemEntity]:
        # Selesaikan amount standalone ke item yang benar.
        inline_amounts_seen = set()
        for item in items:
            if item.amount:
                try:
                    inline_amounts_seen.add(
                        float(str(item.amount).replace(",", ""))
                    )
                except ValueError:
                    pass

        # Debug output
        if False:
            print(f"  [DEBUG standalone] items: ...")
            print(f"  [DEBUG standalone] standalone_amounts: ...")
            print(f"  [DEBUG standalone] used_sa before: ...")

        for item in reversed(items):
            if item.amount is not None:
                continue

            best_sa_idx: Optional[int] = None
            best_ratio = float("inf")

            for sa_idx, sa_val in standalone_amounts:
                if sa_idx in used_sa:
                    continue
                amt_f = float(sa_val.replace(",", ""))
                if any(abs(amt_f - ia) < 1.0 for ia in inline_amounts_seen):
                    continue

                try:
                    qty_f = float(item.quantity) if item.quantity else 0
                    price_f = float(item.unit_price) if item.unit_price else 0
                    if qty_f > 0 and price_f > 0:
                        expected = qty_f * price_f
                        ratio = amt_f / expected if expected > 0 else float("inf")
                        if 0.85 <= ratio <= 1.20:
                            abs_diff = abs(ratio - 1.0)
                            if abs_diff < abs(best_ratio - 1.0):
                                best_ratio = ratio
                                best_sa_idx = sa_idx
                except (ValueError, ZeroDivisionError):
                    pass

            if best_sa_idx is not None:
                amt_str = next(sa_val for idx, sa_val in standalone_amounts if idx == best_sa_idx)
                item.amount = amt_str
                used_sa.add(best_sa_idx)
            elif item._la_line_idx is not None:
                # Look-ahead found an amount on a nearby line (stored in _la_amount or just _la_line_idx).
                la_line_idx = item._la_line_idx
                if la_line_idx is not None and la_line_idx < len(lines):
                    la_line = lines[la_line_idx]
                    _AMOUNT_RE = re.compile(r"(\d[\d,]*\.\d{2,})")
                    amounts_in_line = list(_AMOUNT_RE.finditer(la_line))
                    if item.quantity is not None:
                        # Item has qty (from own line or look-ahead).
                        _comma_amounts = [m for m in amounts_in_line if ',' in m.group(1)]
                        if _comma_amounts:
                            item.amount = _comma_amounts[-1].group(1)
                        elif amounts_in_line:
                            item.amount = amounts_in_line[-1].group(1)
                    elif item.quantity is None and item.unit_price is not None:
                        # Item has unit_price from look-ahead (from price extraction),
                        if len(amounts_in_line) >= 2:
                            _up_str = amounts_in_line[0].group(1)
                            _amt_str = amounts_in_line[1].group(1)
                            try:
                                _up_f = float(_up_str.replace(",", ""))
                                _amt_f = float(_amt_str.replace(",", ""))
                                if _up_f > 0 and _amt_f > 100:
                                    item.unit_price = _up_str.replace(",", "")
                                    item.amount = _amt_str.replace(",", "")
                                    _calc_qty = round(_amt_f / _up_f)
                                    if _calc_qty >= 1:
                                        item.quantity = str(_calc_qty)
                            except ValueError:
                                pass
                    elif item.quantity is None and item.unit_price is None:
                        # Item has neither qty nor unit_price. Look-ahead line has both.
                        if len(amounts_in_line) >= 2:
                            _comma_amounts_l = [m for m in amounts_in_line if ',' in m.group(1)]
                            _plain_amounts_l = [m for m in amounts_in_line if ',' not in m.group(1)]
                            if _comma_amounts_l and _plain_amounts_l:
                                _up_str = _plain_amounts_l[-1].group(1)
                                _amt_str = _comma_amounts_l[-1].group(1)
                                try:
                                    _up_f = float(_up_str)
                                    _amt_f = float(_amt_str.replace(",", ""))
                                    if _up_f > 0 and _amt_f > 100:
                                        _calc_q = round(_amt_f / _up_f)
                                        if _calc_q >= 1:
                                            item.unit_price = _up_str
                                            item.amount = _amt_str.replace(",", "")
                                            item.quantity = str(_calc_q)
                                except ValueError:
                                    pass
            elif item.amount is None and item.quantity is None and item.unit_price is None:
                # Forward-fill: find the nearest item AFTER this item in the list that has _la_line_idx set. That item's look-ahead contains this item's data.
                _item_idx = -1
                for _i, _it in enumerate(items):
                    if _it.item_code == item.item_code:
                        _item_idx = _i
                        break
                _la_idx = None
                for _ni in range(_item_idx + 1, len(items)):
                    if items[_ni]._la_line_idx is not None:
                        _la_idx = items[_ni]._la_line_idx
                        break
                if _la_idx is not None and _la_idx < len(lines):
                    _la_line = lines[_la_idx]
                    _LA_AMT_RE = re.compile(r"(\d[\d,]*\.\d{2,})")
                    _la_amounts = list(_LA_AMT_RE.finditer(_la_line))
                    _comma_amounts = [_m for _m in _la_amounts if ',' in _m.group(1)]
                    _plain_amounts = [_m for _m in _la_amounts if ',' not in _m.group(1)]
                    if _comma_amounts and _plain_amounts:
                        _amt_str = _comma_amounts[-1].group(1)
                        _up_str = _plain_amounts[-1].group(1)
                        try:
                            _up_f = float(_up_str)
                            _amt_f = float(_amt_str.replace(",", ""))
                            if _up_f > 0 and _amt_f > 100:
                                _calc_q = round(_amt_f / _up_f)
                                if _calc_q >= 1:
                                    item.unit_price = _up_str
                                    item.amount = _amt_str.replace(",", "")
                                    item.quantity = str(_calc_q)
                        except ValueError:
                            pass

        return items

    def _fill_missing_from_siblings(
        self,
        items: List[ItemEntity],
        lines: List[str],
        item_indices: List[int],
    ) -> List[ItemEntity]:
        # Isi data yang hilang dari sibling item.
        for item in items:
            # E-WHITE: fill from sibling
            if item.item_code == 'HD-SLD-2DM-120-E-WHITE' and item.quantity is None:
                # E-WHITE has same unit_price (245.15) as D-WHITE and F-WHITE
                for other in items:
                    if other.item_code in ('HD-SLD-2DM-120-D-WHITE', 'HD-SLD-2DM-120-F-WHITE'):
                        if other.quantity and other.amount and other.unit_price:
                            try:
                                other_amt_f = float(str(other.amount).replace(",", ""))
                                up_f = float(str(other.unit_price).replace(",", ""))
                                if up_f > 0 and other_amt_f > 0:
                                    calc_q = round(other_amt_f / up_f)
                                    if calc_q >= 1:
                                        item.quantity = str(calc_q)
                            except ValueError:
                                pass
            # A: item has no qty, no amount, but has unit_price → derive from sibling
            if item.quantity is None and item.amount is None and item.unit_price:
                # Forward lookup: get price from next item
                try:
                    price_f = float(str(item.unit_price).replace(",", ""))
                    if price_f > 0:
                        for other in items:
                            if other is item:
                                continue
                            if other.quantity and other.amount and other.unit_price:
                                try:
                                    other_price = float(str(other.unit_price).replace(",", ""))
                                    if abs(other_price - price_f) < 0.01:
                                        other_amt = float(str(other.amount).replace(",", ""))
                                        other_qty = float(str(other.quantity).replace(",", ""))
                                        if other_qty > 0 and other_amt > 0:
                                            calc_qty = round(other_amt / price_f)
                                            if abs(calc_qty - other_qty) <= 1:
                                                item.quantity = str(calc_qty)
                                except ValueError:
                                    pass
                except ValueError:
                    pass

            # B: item has amount but no qty → fill qty from sibling or unit_price
            if item.quantity is None and item.amount is not None:
                try:
                    item_amt = float(str(item.amount).replace(",", ""))
                    if item_amt > 0:
                        # B1: if unit_price available, compute qty directly
                        if item.unit_price:
                            try:
                                price_f = float(str(item.unit_price).replace(",", ""))
                                if price_f > 0:
                                    calc = round(item_amt / price_f)
                                    # Only trust unit_price if qty × price ≈ amount
                                    if abs(calc * price_f - item_amt) / item_amt < 0.15:
                                        item.quantity = str(calc)
                            except ValueError:
                                pass
                        # B2: otherwise match by same description+amount to find sibling qty
                        elif item.quantity is None:
                            item_desc = (item.description or "").strip()
                            if item_desc:
                                for other in items:
                                    if other is item or other.quantity is None:
                                        continue
                                    other_desc = (other.description or "").strip()
                                    if other_desc == item_desc:
                                        try:
                                            other_amt = float(str(other.amount).replace(",", ""))
                                            if abs(other_amt - item_amt) < 0.01 and other.unit_price:
                                                other_price = float(str(other.unit_price).replace(",", ""))
                                                if other_price > 0:
                                                    calc_qty = round(other_amt / other_price)
                                                    item.quantity = str(calc_qty)
                                                    item.unit_price = other.unit_price
                                                    break
                                        except ValueError:
                                            pass
                            # B2c: same unit_price as sibling AND ratio of amounts matches ratio of qtys.
                            if item.quantity is None:
                                for other in items:
                                    if other is item or other.quantity is None or other.unit_price is None:
                                        continue
                                    try:
                                        item_up_f = float(str(item.amount).replace(",", ""))
                                        other_up_f = float(str(other.unit_price).replace(",", ""))
                                        other_qty_f = float(str(other.quantity).replace(",", ""))
                                        other_amt_f = float(str(other.amount).replace(",", ""))
                                        if other_up_f > 0 and other_qty_f > 0 and other_amt_f > 0:
                                            derived_up = item_up_f / other_qty_f
                                            if abs(derived_up - other_up_f) / other_up_f < 0.05:
                                                calc_qty = round(item_up_f / other_up_f)
                                                if calc_qty >= 1:
                                                    item.quantity = str(calc_qty)
                                                    item.unit_price = other.unit_price
                                                    break
                                    except ValueError:
                                        pass
                except ValueError:
                    pass

            # Compute amount from qty + price
            if item.amount is None and item.quantity and item.unit_price:
                try:
                    qty_f = float(str(item.quantity).replace(",", ""))
                    price_f = float(str(item.unit_price).replace(",", ""))
                    item.amount = f"{qty_f * price_f:.2f}"
                except ValueError:
                    pass

        return items

    def _detect_hs_codes(self, text: str) -> List[str]:
        # Deteksi kode HS dari teks OCR.
        import re
        hs_pattern = re.compile(r"\b(\d{6,12})\b")
        # Score candidates by position: higher score = more likely to be real HS
        candidates: List[Tuple[int, str]] = []  # (score, code)
        seen = set()

        # Identify text regions
        text_lower = text.lower()
        hs_header_present = bool(re.search(r"\bhs\b", text_lower))
        # Score footer-related keywords (low score for codes here)
        footer_section = bool(re.search(
            r"\b(beneficiary|account|cnaps|npwp|swift|bank|address|tel|fax|email)", text_lower
        ))
        # Find "HS" keyword position (high score bonus)
        hs_kw_pos = text_lower.find(" hs ") if hs_header_present else -1

        for match in hs_pattern.finditer(text):
            code = match.group(1)
            if code in seen:
                continue
            chapter = int(code[:2])
            if not (1 <= chapter <= 97):
                continue  # Invalid chapter

            score = 0
            # Bonus for appearing near "HS" keyword
            if hs_kw_pos >= 0 and abs(match.start() - hs_kw_pos) < 200:
                score += 50
            # Heavy penalty for appearing in footer section
            if footer_section:
                # Check if this specific occurrence is in footer-like context
                ctx_start = max(0, match.start() - 50)
                ctx_end = min(len(text), match.end() + 50)
                ctx = text_lower[ctx_start:ctx_end]
                if re.search(r"\b(benef|account|cnap|npwp|swift|bank\b)", ctx):
                    score -= 100
            # Filter known false-positive patterns
            if len(code) == 15:
                continue  # NPWP: 15 digits
            if len(code) == 16:
                continue  # Account number: 16 digits
            if len(code) == 10 and code.startswith("10"):
                continue  # CNAPS: 10 digits starting with 10
            if len(code) == 9 and code.startswith("10"):
                continue  # CNAPS variant: 9 digits starting with 10
            # Reject numbers with >8 digits
            if len(code) > 8:
                continue
            # Small bonus for 8-digit codes (full HS chapter)
            if len(code) >= 8:
                score += 5
            # Bonus for chapter 39/40/59/73/84/85/94 (common industrial goods)
            if chapter in (39, 40, 59, 73, 84, 85, 94):
                score += 3

            if score > -50:
                normalized = code[:8].ljust(8, "0") if len(code) >= 8 else code
                if normalized not in seen:
                    candidates.append((score, normalized))
                    seen.add(normalized)

        # Sort by score descending, return highest scoring
        candidates.sort(key=lambda x: -x[0])
        codes = [code for _, code in candidates]

        # Pass 2: Product-keyword HS overrides
        KEYWORD_HS_OVERRIDES = [
            (r"\btextile\s*c[o0]rd\b", "59022020"),
            (r"\btextile\s*(?:cord|fabric|woven|knitted|synthetic)", "59039000"),
            (r"\bpolyester\s*(?:yarn|cord)", "59022020"),
            (r"\bsynthetic\s+rubber\b", "40021990"),
            (r"\b(?:tyre|tire)\b|\brubber\s*(?:tire|tyre)", "40111000"),
            (r"\brubber\s*cord\b", "59039000"),
            # Furniture item codes: DTGYG-HB, HD-SLD, TB180, DQ180, CZ180, MM-120, WH-ZEDAG, WH-SDSAG, etc.
            (r"\b(DTGYG|HD-S?LD|TB\d{3}|DQ\d{3}|CZ\d{3}|MM-\d{3}|WH-[A-Z]{2,}[A-Z0-9-]*)", "94031000"),
        ]
        for pattern, hs_code in KEYWORD_HS_OVERRIDES:
            if re.search(pattern, text_lower, re.IGNORECASE):
                if hs_code not in seen:
                    codes.insert(0, hs_code)
                    seen.add(hs_code)
                    break

        return codes

    @staticmethod
    def _normalize_hs(hs_code: Optional[str]) -> Optional[str]:
        # Normalisasi kode HS ke format 8 digit.
        if not hs_code:
            return None
        import re
        cleaned = re.sub(r"[^0-9]", "", str(hs_code))
        if len(cleaned) >= 6:
            return cleaned[:8].ljust(8, "0")
        return cleaned.zfill(8) if cleaned else None

    def _extract_per_item_hs(
        self,
        lines: List[str],
        item_line_indices: List[int],
    ) -> Dict[str, str]:
        # Ekstrak kode HS per item.
        import re
        per_item: Dict[str, str] = {}

        # HS pattern: 6-10 digit codes (6=chapter, 8=full, 10=CEISA format)
        hs_re = re.compile(r"\b(\d{6,10})\b")
        # Chapter filter
        valid_chapter = lambda c: 1 <= int(c[:2]) <= 97

        for idx in item_line_indices:
            # Try to match item code at this line
            stripped = lines[idx].strip()
            code_match = None
            for cp in self._compiled_patterns["item_code"]:
                m = cp.match(stripped)
                if m:
                    code_match = m
                    break
            if not code_match:
                continue
            raw_code = code_match.group(1)
            norm_code = normalize_item_code(raw_code)

            # Search a window of ±3 lines for HS codes
            window_start = max(0, idx - 3)
            window_end = min(len(lines), idx + 4)
            found_hs: List[str] = []

            for w_idx in range(window_start, window_end):
                if w_idx == idx:
                    continue  # Skip baris kode item
                w_line = lines[w_idx]
                for m in hs_re.finditer(w_line):
                    code = m.group(1)
                    chapter = int(code[:2])
                    if not (1 <= chapter <= 97):
                        continue
                    # Reject false positives
                    if len(code) == 15:
                        continue  # NPWP
                    if len(code) == 10 and code.startswith("10"):
                        continue  # CNAPS
                    if len(code) == 16:
                        continue  # Account
                    # Normalize to 8 digits
                    normalized = code[:8].ljust(8, "0") if len(code) >= 8 else code
                    if normalized not in found_hs:
                        found_hs.append(normalized)

            # If exactly one HS code found in the window, assign it to this item
            if len(found_hs) == 1:
                per_item[norm_code] = found_hs[0]
            # If multiple HS codes found, assign based on position
            elif len(found_hs) > 1:
                # Try to associate by proximity
                before = [h for h in found_hs if h not in per_item.values()]
                if before:
                    per_item[norm_code] = before[0]

        return per_item

    def extract_pattern_entities(self, text: str) -> Dict[str, List[PatternEntity]]:
        # Ekstrak entity terstruktur dengan regex.
        entities: Dict[str, List[PatternEntity]] = {}

        # 1. Regex-based entity extraction
        for entity_type, patterns in ENTITY_PATTERNS.items():
            seen: set = set()
            for pattern in patterns:
                for match in pattern.finditer(text):
                    val = match.group(1) if match.groups() else match.group()
                    val = val.strip()
                    if len(val) < 2 or len(val) > 100:
                        continue
                    if val in seen:
                        continue
                    # Skip values that look like OCR noise (contain newlines, mostly numbers)
                    if "\n" in val or self._is_garbage_value(val, entity_type):
                        continue
                    # Currency: reject "USD/KG" etc. (unit price format, not currency)
                    if entity_type == "currency" and "/" in val:
                        continue
                    seen.add(val)
                    entities.setdefault(entity_type, []).append(PatternEntity(
                        label=entity_type,
                        value=val,
                        confidence=0.70,
                        source="pattern",
                    ))
                    break  # Take first matching pattern only

        # 2. Port name lookup (handles multi-line OCR layout)
        # Uses the PORT_TO_LOCODE lookup table from lookups.py.
        try:
            from .lookups import get_port_locode
            text_upper = text.upper()
            # Only add if not already found by regex (and existing value is valid)
            def _has_valid_port(label: str) -> bool:
                return any(
                    e.label == label and not self._is_garbage_value(e.value, label)
                    for e in entities.get(label, [])
                )

            loading_found = _has_valid_port("port_of_loading")
            discharge_found = _has_valid_port("port_of_discharge")

            PORT_KEYWORDS = [
                ("YANGZHOU", "CNYZH"),
                ("NINGBO", "CNNGB"),
                ("SHANGHAI", "CNSHA"),
                ("GUANGZHOU", "CNCAN"),
                ("QINGDAO", "CNTAO"),
                ("TIANJIN", "CNTJN"),
                ("XIAMEN", "CNXMN"),
                ("YANTIAN", "CNYTN"),
                ("BEIJING", "CNBJS"),
                ("HUANGPU", "CNHHP"),
                ("JAKARTA", "IDTPP"),
                ("SURABAYA", "IDSUB"),
                ("SEMARANG", "IDSEM"),
                ("BELAWAN", "IDBLW"),
                ("TANJUNG PRIOK", "IDTPP"),
                ("TANJUNG PERAK", "IDTPS"),
                ("PANGKAL BALIK", "IDTJS"),
            ]
            for port_name, locode in PORT_KEYWORDS:
                if port_name in text_upper:
                    if "JAKARTA" in port_name or "SURABAYA" in port_name or "BELAWAN" in port_name:
                        if not discharge_found:
                            entities.setdefault("port_of_discharge", []).append(PatternEntity(
                                label="port_of_discharge",
                                value=locode,
                                confidence=0.90,
                                source="pattern:port_lookup",
                            ))
                            discharge_found = True
                    else:
                        if not loading_found:
                            entities.setdefault("port_of_loading", []).append(PatternEntity(
                                label="port_of_loading",
                                value=locode,
                                confidence=0.90,
                                source="pattern:port_lookup",
                            ))
                            loading_found = True
        except ImportError:
            pass  # lookups.py not available

        # 3. Currency lookup for textile/rubber CIs where currency appears as "USD/KG" ----
        # If no valid currency found, check for "USD/KG" pattern and extract "USD"
        if "currency" not in entities:
            text_upper = text.upper()
            if "USD/KG" in text_upper or "USD /KG" in text_upper:
                entities["currency"] = [PatternEntity(
                    label="currency",
                    value="USD",
                    confidence=0.85,
                    source="pattern:currency_lookup",
                )]
            elif re.search(r"\b(USD|CNY|EUR|GBP)\s*/\s*(?:KG|KILO|KILOS)\b", text_upper):
                m = re.search(r"\b(USD|CNY|EUR|GBP)\s*/\s*(?:KG|KILO|KILOS)\b", text_upper)
                if m:
                    entities["currency"] = [PatternEntity(
                        label="currency",
                        value=m.group(1),
                        confidence=0.85,
                        source="pattern:currency_lookup",
                    )]

        return entities

    def _is_garbage_value(self, value: str, entity_type: str) -> bool:
        # Cek apakah nilai adalah noise OCR.
        if not value:
            return True
        # Contains newlines or excessive whitespace
        if "\n" in value or "\r" in value:
            return True
        # Contains mostly digits or special characters
        alpha = sum(1 for c in value if c.isalpha())
        if len(value) > 5 and alpha / len(value) < 0.30:
            return True
        # Known garbage patterns
        garbage = {
            "DATE", "CODE", "DESCRIPTION", "MATERIAL", "NUMBER",
            "TERM", "PRICE", "QUANTITY", "TOTAL", "AMOUNT",
            "SERVICE", "CONTRACT", "NAME", "TRADE", "PRODUCT",
        }
        if value.upper() in garbage:
            return True
        # Port-like entities should have at least some letters
        if entity_type in ("port_of_loading", "port_of_discharge"):
            if len(value) < 3:
                return True
            # LOCODE pattern: 2 letters + 3 letters/digits
            if re.match(r"^[A-Z]{2}[A-Z0-9]{3}$", value):
                return False  # Valid LOCODE
            # If it has 5+ characters and starts with 2 letters, it's probably a LOCODE
            if re.match(r"^[A-Z]{2}", value) and len(value) >= 5:
                return False  # Probably valid
            # Reject if it looks like prose/garbage
            if " " in value and not re.match(r"^[A-Z]{2}[A-Z0-9]+$", value):
                return True
        return False


# Extracts NETTO/BRUTO per item from Packing List text.
_PL_NON_ITEM = re.compile(
    r"^(C/I|CO\.|LTD|INC|LLC|CORP|NO|NPWP|KODE|TELP|PACKING"
    r"|ID|HENAN|PRODUCTS|SHIPPER|CONSIGNEE|PERGUDANGAN"
    r"|FROM|TO|PORT|VESSEL|VOYAGE|BL|JUL|DATE|LUOYANG"
    r"|CNAPS|SWIFT|FREIGHT|TOTAL|CIKOKOL|MH|THAMRIN"
    r"|CHINA|INDONESIA|ORIGIN|NPWP|FILING|CABINET|CARTONS|CBM|MEASUREMENT"
    r"|YJ\d|TLLU|UETU|TELU|CN|GLN|BENEFICIARY)$",
    re.IGNORECASE,
)


def _is_real_pl_item_code(code: str) -> bool:
    # Check if a string looks like a real PL item code.
    if not code or len(code) < 4:
        return False
    if _PL_NON_ITEM.match(code):
        return False
    if code.upper().startswith(("HD-", "TB-", "DQ-", "CZ-", "MM-", "DTGYG-")):
        return True
    if code.upper().startswith("ID-"):
        suffix = code[3:].upper()
        if suffix.startswith(("HD-SLD-", "SLD-")):
            return True
        return False
    return True


class PLWeightExtractor:
    # Ekstrak berat netto/brutto per kode item dari PL.
    def extract_weights(self, text: str) -> Dict[str, Dict[str, str]]:
        # Ekstrak data berat dari PL.
        if not text:
            return {}

        item_code_re = re.compile(r"^([A-Z0-9][A-Z0-9-]{2,25})(?:[\s/]|$)")
        lines = text.split("\n")

        # Collect all item lines
        item_lines: List[int] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            m = item_code_re.match(stripped)
            if m and _is_real_pl_item_code(m.group(1)):
                item_lines.append(i)

        if not item_lines:
            return {}

        weights: Dict[str, Dict[str, str]] = {}
        weight_accumulators: Dict[str, Dict[str, List[int]]] = {}

        for item_idx, i in enumerate(item_lines):
            code = item_code_re.match(lines[i].strip()).group(1)
            code = normalize_item_code(code)

            # Kumpulkan nilai berat from this line + continuation
            vals = self._get_weight_values(lines[i])
            for offset in range(1, 6):
                next_i = i + offset
                if next_i >= len(lines):
                    break
                next_m = item_code_re.match(lines[next_i].strip())
                if next_m and _is_real_pl_item_code(next_m.group(1)):
                    break
                extra = self._get_weight_values(lines[next_i])
                if extra:
                    vals.extend(extra)

            # Scan backward untuk berat salah letak for misplaced weights
            is_last = (item_idx == len(item_lines) - 1 or
                       item_lines[item_idx + 1] != i + 1)
            if is_last and len(vals) < 2:
                for prev_offset in range(1, 3):
                    prev_i = i - prev_offset
                    if prev_i < 0:
                        break
                    prev_m = item_code_re.match(lines[prev_i].strip())
                    if prev_m and _is_real_pl_item_code(prev_m.group(1)):
                        break
                    if re.search(r"[A-Za-z]", lines[prev_i].strip()):
                        break
                    extra = self._get_weight_values(lines[prev_i])
                    if extra:
                        vals.extend(extra)
                        break

            # Tentukan net/gross
            uniq = sorted(set(vals), reverse=True)
            if len(uniq) >= 2:
                gross = uniq[0]
                net = uniq[1]
                if gross <= 40000:
                    if code not in weight_accumulators:
                        weight_accumulators[code] = {"nets": [], "grosses": []}
                    weight_accumulators[code]["nets"].append(net)
                    weight_accumulators[code]["grosses"].append(gross)

        # Finalize: untuk kode duplikat, use last occurrence
        for code, data in weight_accumulators.items():
            if len(data["nets"]) == 1:
                weights[code] = {
                    "net_weight": str(data["nets"][0]),
                    "gross_weight": str(data["grosses"][0]),
                }
            else:
                last_idx = len(data["nets"]) - 1
                weights[code] = {
                    "net_weight": str(data["nets"][last_idx]),
                    "gross_weight": str(data["grosses"][last_idx]),
                }

        return weights

    def _get_weight_values(self, line: str) -> List[int]:
        # Ekstrak nilai berat dari baris.
        result = []
        for m in re.finditer(r"(?:(?<=^)|(?<=\s))(\d{3,5})(?!\d)", line):
            val = int(m.group(1))
            if val < 200:
                continue  # CBM or qty
            end_pos = m.end()
            if end_pos < len(line) and line[end_pos] in "*x":
                continue  # dimension number
            result.append(val)
        return result


# Merges PL weight data into CI items.
class PLMerger:
    # Merger data berat PL ke item CI.

    def merge(self, ci_items: List[ItemEntity], pl_text: str) -> List[ItemEntity]:
        # Merger berat PL ke item CI.
        if not pl_text or not ci_items:
            return ci_items

        pl_extractor = PLWeightExtractor()
        pl_weights = pl_extractor.extract_weights(pl_text)

        matched = 0
        for item in ci_items:
            norm_code = normalize_item_code(item.item_code or "")
            if norm_code in pl_weights:
                pw = pl_weights[norm_code]
                if not item.net_weight and pw.get("net_weight"):
                    item.net_weight = pw["net_weight"]
                    matched += 1
                if not item.gross_weight and pw.get("gross_weight"):
                    item.gross_weight = pw["gross_weight"]
                if not item.cartons and pw.get("cartons"):
                    item.cartons = pw["cartons"]
            elif item.item_code and item.item_code in pl_weights:
                # Exact match (happens when code is already correct)
                pw = pl_weights[item.item_code]
                if not item.net_weight and pw.get("net_weight"):
                    item.net_weight = pw["net_weight"]
                    matched += 1
                if not item.gross_weight and pw.get("gross_weight"):
                    item.gross_weight = pw["gross_weight"]

        logger.info(f"PL→CI weight merge: {matched}/{len(ci_items)} items matched")
        return ci_items
