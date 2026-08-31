from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Dataclasses

@dataclass
class FormEGoodsRow:
    row_number: int           # SERI BARANG (1-based)
    hs_code: str = ""        # 6-digit HS code
    quantity: str = ""        # JUMLAH SATUAN
    unit: str = ""            # KODE SATUAN (PE, PC, KGM, etc.)
    description: str = ""      # URAIAN

    # Computed after lookup
    hs_code_int: Optional[int] = None
    bm_rate: float = 0.0     # Bea Masuk rate (%)
    ppn_rate: float = 0.0     # PPN rate (%)
    pph_rate: float = 0.0     # PPh rate (%)
    hs_found: bool = False


# Layout 1: multi-page Form E with "HS CODE: XXXX" pattern and "XXXXPIECES" quantity.
# Strategy: split text into sections by "HS CODE:" markers, extract items per section.

def extract_layout1(text: str) -> List[FormEGoodsRow]:
    lines = text.splitlines()
    rows: List[FormEGoodsRow] = []

    # Regex patterns
    HS_RE = re.compile(
        r"^HS\s+CODE\s*[:\-]\s*(\d{4})(?:[^\d\n](\d{2}))?",
        re.IGNORECASE | re.MULTILINE,
    )
    ITEM_RE = re.compile(r"^([1-9]\d?)\s+(.+)$")
    QTY_RE = re.compile(r"(\d[\d,]*?)\s*PIECESI?\b", re.IGNORECASE)

    SKIP = re.compile(
        r"(?:^TOTAL|^NUMBER|^Kind|^Gross|^Marks\b|^Item\b|^Origin\b|"
        r"^Origin\s+criteria|^Declaration|^Certification|^Importer|^Exporter|"
        r"^undersigned|^RVC\b|^criterion\b|^applied\b|^see\s+Overleaf|^hereby\b|"
        r"^\d{10,}$|^\d{1,5}\.\d+$|^\d{4}$|^HS\s*CODE\b|"
        r"^\d{1,3}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC))",
        re.IGNORECASE
    )
    BAD_DESC = re.compile(
        r"(?:of\s+Annex|Protocol|RVC|certificate|origin\s+criteria|"
        r"preferential|ACFTA|Upgrading|Rule\b|Party|Parties|"
        r"Weight|weight|package|Invoice|invoice)",
        re.IGNORECASE
    )

    # Find HS CODE section boundaries
    hs_section_indices: List[int] = []
    for i, line in enumerate(lines):
        if HS_RE.match(line.strip()):
            hs_section_indices.append(i)

    # Build sections
    sections: List[Tuple[int, int, str]] = []
    for si, start_idx in enumerate(hs_section_indices):
        hs_m = HS_RE.match(lines[start_idx].strip())
        hs_code = (hs_m.group(1) + (hs_m.group(2) or "")) if hs_m else ""
        end_idx = (hs_section_indices[si + 1]
                    if si + 1 < len(hs_section_indices) else len(lines))
        sections.append((start_idx, end_idx, hs_code))

    # Extract items
    seen_items: set = set()

    for si, (start, end, hs_code) in enumerate(sections):
        for i in range(start, end):
            line = lines[i].strip()
            if not line or SKIP.search(line):
                continue

            # Standalone item: just "N"
            if re.match(r"^[1-9]\d?$", line):
                n = int(line)
                if n > 31 or n in seen_items:
                    continue
                seen_items.add(n)
                desc = _find_desc_backward(lines, i, start, SKIP)
                qty = _find_qty_in_range(lines, start, end, i)
                rows.append(_make_row(n, hs_code, qty, "", desc))
                continue

            # Embedded item: "N description"
            m = ITEM_RE.match(line)
            if not m:
                continue
            n = int(m.group(1))
            if n > 31 or n in seen_items:
                continue
            raw_desc = m.group(2).strip()
            if BAD_DESC.search(raw_desc):
                continue
            seen_items.add(n)
            qty = _find_qty_in_range(lines, start, end, i)
            desc = _clean_desc(raw_desc)
            rows.append(_make_row(n, hs_code, qty, "", desc))

    rows.sort(key=lambda r: r.row_number)
    return rows


def _find_desc_backward(
    lines: List[str], item_idx: int, section_start: int, skip_re: re.Pattern
) -> str:
    for back in range(1, 5):
        if item_idx - back < section_start:
            break
        prev = lines[item_idx - back].strip()
        if not prev or skip_re.search(prev):
            continue
        if re.match(r"^\d{10,}$", prev):
            continue
        if re.match(r"^\d{4}$", prev):
            continue
        if len(prev) > 80:
            continue
        return _clean_desc(prev)
    return ""


def _find_qty_in_range(
    lines: List[str], start: int, end: int, item_idx: int
) -> str:
    QTY_RE = re.compile(r"(\d[\d,]*?)\s*PIECESI?\b", re.IGNORECASE)
    search_start = max(start, item_idx - 2)
    search_end = min(end, item_idx + 4)
    ctx = " ".join(lines[search_start:search_end])
    m = QTY_RE.search(ctx)
    if m:
        return m.group(1).replace(",", "")
    return ""


def _clean_desc(raw: str) -> str:
    desc = re.sub(r"[\x00-\x1f]", "", raw)
    desc = re.sub(r"\bN/?M\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\bJOUTER\b", "OUTER", desc, flags=re.IGNORECASE)
    desc = re.sub(r'"[^"]*"', "", desc)
    desc = re.sub(r"\d{3,}\s*PIECESI?\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\d{1,2}\s*PIECESI?\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\bPE\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r'\s*[A-Z]{3,}\d{4,}[A-Z0-9]*\s*$', "", desc)
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc[:200] if len(desc) >= 2 else ""


def _make_row(n: int, hs: str, qty: str, unit: str, desc: str) -> FormEGoodsRow:
    row = FormEGoodsRow(row_number=n, hs_code=hs, quantity=qty, unit=unit, description=desc)
    if row.hs_code:
        padded = row.hs_code[:6].ljust(8, "0")  # Normalize to 8-digit
        try:
            row.hs_code_int = int(padded)
            rates = _get_tariff(row.hs_code_int)
            row.bm_rate = rates["bm"]
            row.ppn_rate = rates["ppn"]
            row.pph_rate = rates["pph"]
            row.hs_found = rates["found"]
        except ValueError:
            pass
    return row


# Layout 2: e-CO. OCR puts HS code and unit on SEPARATE lines:
#   Line 53: "... N/M 560392 53944.0000 035 USD ... KKCU- 14/04/2026"
#   Line 54: "PE"
# Strategy: find HS code line, look at adjacent lines for unit.

HS_CODE_RE = re.compile(r"(\d{6,8})\b")
QTY_DECIMAL_RE = re.compile(r"(\d[\d,]*\.\d+)")
ROW_NUM_RE = re.compile(r"^\s*(\d+)\b")
UNIT_LINE_RE = re.compile(r"^\s*([A-Z]{2})\s*$")


def extract_layout2(text: str) -> List[FormEGoodsRow]:
    lines = text.splitlines()
    rows: List[FormEGoodsRow] = []
    seen_items: set = set()

    # Lines to skip
    SKIP_RE = re.compile(
        r"(?:Signatory|Declaration|Certification|Disclaimer|TOTAL:|Page\s|"
        r"Beneficiary|Applicant|Invoice\s+No|NPWP:|TEL:|Phone|"
        r"^\d{10,}$|^Hs\s+Code|^Gross\s+Weight|^N/M\s*$|"
        r"^FORM E\b|^CERTIFICATE|^ACFTA|Origin Country|Issuing Country|"
        r"Item\s+Quantity|Invoice Number|Invoice Date|Currency|"
        r"^\s*[A-Z][A-Z\s]{10,}$|"
        r"^\d{1,3}\s+of\s+\d)",  # "1 0f 1" footer
        re.IGNORECASE
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or SKIP_RE.search(stripped):
            continue

        # Find HS code (6-8 digits) on this line
        hs_match = HS_CODE_RE.search(stripped)
        if not hs_match:
            continue

        hs_raw = hs_match.group(1)
        if hs_raw.startswith("0") or len(hs_raw) < 6:
            continue

        hs_code = hs_raw[:6]  # Normalize to 6 digits

        # First try: unit immediately after HS on same line
        unit = ""
        after_hs = stripped[hs_match.end():hs_match.end() + 5]
        um = re.match(r"\s+([A-Z]{2})\b", after_hs)
        if um:
            unit = um.group(1)
        else:
            # Check next line for unit
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                um2 = UNIT_LINE_RE.match(next_line)
                if um2:
                    unit = um2.group(1)
                elif (len(next_line) <= 4
                      and re.match(r"^[A-Z]{2,4}$", next_line)):
                    unit = next_line[:2]

        # Quantity: measurement immediately after HS code
        qty = ""
        after_hs_region = stripped[hs_match.end():hs_match.end() + 15]
        m_after = re.match(r"[\s,]*([\d,]*\.\d+)\b", after_hs_region)
        if m_after:
            candidate = m_after.group(1).replace(",", "")
            try:
                val = float(candidate)
                if 1 <= val <= 999999:
                    qty = candidate
            except ValueError:
                pass

        # Fallback: last decimal before currency/date
        if not qty:
            currency_pos = min(
                stripped.find("USD"), stripped.find("CNY"),
                stripped.find("EUR"), stripped.find("SGD"),
            )
            if currency_pos < 0:
                currency_pos = len(stripped)
            search_area = stripped[:currency_pos]
            qty_matches = list(QTY_DECIMAL_RE.finditer(search_area))
            for m in reversed(qty_matches):
                candidate = m.group(1).replace(",", "")
                try:
                    val = float(candidate)
                    if 1 <= val <= 999999:
                        qty = candidate
                        break
                except ValueError:
                    continue

        # Row number: leading digits
        # Note: Layout 2 often starts with "N/M description ..." not a number.
        # In that case we assign sequential row numbers.
        row_m = ROW_NUM_RE.match(stripped)
        row_num = int(row_m.group(1)) if row_m else None

        # Description: extract from the line (before HS code)
        desc = ""
        if row_m:
            before_hs = stripped[:hs_match.start()].strip()
            desc = re.sub(r"^N/M\b", "", before_hs, flags=re.IGNORECASE).strip()
            desc = re.sub(r"[\d,]+(\.\d+)?\s*", "", desc).strip()
            desc = re.sub(r"^\d+\s+", "", desc).strip()
            if len(desc) < 3:
                desc = ""
            desc = desc[:100]

        # Skip invalid row numbers (but allow HS lines without row numbers for Layout 2)
        if row_num is not None:
            if row_num > 100:
                continue
            if row_num in seen_items:
                continue
            seen_items.add(row_num)
        elif not unit:
            # HS line without unit and without row number — skip
            continue
        # For Layout 2 HS lines with unit but no row_num: use next sequential number

        # For Layout 2 HS lines with unit but no row_num: use next sequential number
        actual_row_num = row_num
        if actual_row_num is None:
            actual_row_num = len(seen_items) + 1
            while actual_row_num in seen_items:
                actual_row_num += 1
            seen_items.add(actual_row_num)

        rows.append(_make_row(actual_row_num, hs_code, qty, unit, desc))

    rows.sort(key=lambda r: r.row_number)
    return rows


# Unified Entry Point

def extract_form_e(text: str, layout: str = "") -> List[FormEGoodsRow]:
    if not layout:
        layout = _detect_layout(text)

    if layout == "Layout 1":
        return extract_layout1(text)
    elif layout == "Layout 2":
        return extract_layout2(text)
    else:
        result = extract_layout2(text)
        if not result:
            result = extract_layout1(text)
        return result


def _detect_layout(text: str) -> str:
    if re.search(r"Page\s+\d+\s+of\s+\d+", text, re.IGNORECASE):
        return "Layout 1"
    if re.search(r"HS\s+CODE\s*[:\-]", text, re.IGNORECASE):
        return "Layout 1"
    if re.search(r"Electronic\s+Certificate", text, re.IGNORECASE):
        return "Layout 2"
    hs_legacy = len(re.findall(r"HS\s+CODE\s*[:\-]", text, re.IGNORECASE))
    hs_anchor = len(re.findall(r"\d{6}\s+[A-Z]{2}\b", text))
    if hs_legacy >= hs_anchor:
        return "Layout 1"
    return "Layout 2"


# Tariff Lookup

_TARIFF_CACHE: Dict[int, Dict[str, Any]] = {}
_TARIFF_LOADED = False


def _ensure_tariff_loaded() -> None:
    global _TARIFF_LOADED
    if _TARIFF_LOADED:
        return
    try:
        import json
        from pathlib import Path

        search_paths = [
            Path(__file__).parent / "data" / "hs_code_tax_mapping.json",
            Path(__file__).parent.parent.parent / "data" / "hs_code_tax_mapping.json",
        ]
        for path in search_paths:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for hs_str, rates in data.items():
                    try:
                        hs_code = int(hs_str)
                        # Parse percentage strings like "10.0%" -> float 10.0
                        def parse_pct(val):
                            if isinstance(val, str) and val.endswith("%"):
                                return float(val.rstrip("%"))
                            return float(val) if val else 0.0

                        _TARIFF_CACHE[hs_code] = {
                            "bm": parse_pct(rates.get("BM", "0%")),
                            "ppn": parse_pct(rates.get("PPN", "0%")),
                            "pph": parse_pct(rates.get("PPH", "0%")),
                            "found": True,
                        }
                    except (ValueError, TypeError):
                        continue
                logger.info(f"HS tariff loaded: {len(_TARIFF_CACHE)} entries")
                _TARIFF_LOADED = True
                return
        logger.warning("hs_code_tax_mapping.json not found")
    except Exception as e:
        logger.warning(f"Failed to load HS tariff: {e}")
    _TARIFF_LOADED = True


def _get_tariff(hs_code: int) -> Dict[str, Any]:
    _ensure_tariff_loaded()

    if hs_code in _TARIFF_CACHE:
        return _TARIFF_CACHE[hs_code]

    # Try 4-digit prefix match
    prefix4 = hs_code // 10000
    for cached, rates in _TARIFF_CACHE.items():
        if cached // 10000 == prefix4:
            logger.info(f"HS {hs_code}: using 4-digit prefix match {cached}")
            return rates

    return {"bm": 0.0, "ppn": 12.0, "pph": 2.5, "found": False}
