from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


# EXCHANGE RATES (NDPBM - Nilai Dasar Perhitungan Bea Masuk)
EXCHANGE_RATES: Dict[str, Tuple[float, float, str]] = {
    # Kode mata uang -> (buy, sell, per X units)
    "USD": (15450.0, 15650.0, "1 USD"),
    "CNY": (2640.0, 2700.0, "1 CNY"),
    "EUR": (16800.0, 17100.0, "1 EUR"),
    "GBP": (19500.0, 19800.0, "1 GBP"),
    "JPY": (105.0, 110.0, "100 JPY"),
    "SGD": (11400.0, 11600.0, "1 SGD"),
    "MYR": (3450.0, 3550.0, "1 MYR"),
    "KRW": (11.0, 12.0, "1 KRW"),
    "HKD": (1970.0, 2020.0, "1 HKD"),
    "AUD": (10200.0, 10400.0, "1 AUD"),
    "THB": (440.0, 455.0, "1 THB"),
    "IDR": (1.0, 1.0, "1 IDR"),
}


def get_ndpbm_rate(currency_code: str) -> float:
    # Get the NDPBM (buy rate) for a currency.
    if not currency_code:
        return 1.0
    code = currency_code.upper().strip()
    if code == "IDR":
        return 1.0
    rate = EXCHANGE_RATES.get(code)
    if rate:
        return rate[0]
    return 1.0


def convert_to_idr(amount: float, currency_code: str) -> float:
    # Convert an amount in foreign currency to IDR using NDPBM.
    rate = get_ndpbm_rate(currency_code)
    return amount * rate


FREIGHT_RATES: Dict[str, float] = {
    # Ukuran kontainer -> rate USD per kontainer
    "20": 800.0,
    "40": 1400.0,
    "40HQ": 1500.0,
    "45": 1600.0,
    "TANK": 2500.0,
    "LCL": 50.0,
}


def get_freight_cost(
    container_type: str,
    num_containers: int = 1,
    cbm: float = 0.0,
) -> float:
    # Estimate biaya freight untuk shipment container.
    if not container_type:
        container_type = "20"
    ct = container_type.upper().strip()

    if ct == "LCL" or cbm > 0 and num_containers == 0:
        rate = FREIGHT_RATES.get("LCL", 50.0)
        return rate * max(cbm, 1.0)

    rate = FREIGHT_RATES.get(ct, FREIGHT_RATES.get("20", 800.0))
    return rate * num_containers


# INSURANCE RATES
INSURANCE_MIN_USD = 20.0
INSURANCE_MAX_USD = 500.0
INSURANCE_RATE = 0.005  # 0.5%


def calculate_insurance(cif_value_usd: float) -> float:
    # Hitung biaya asuransi berdasarkan nilai CIF.
    if cif_value_usd <= 0:
        return 0.0
    insurance = cif_value_usd * INSURANCE_RATE
    return max(INSURANCE_MIN_USD, min(insurance, INSURANCE_MAX_USD))


# TAX HELPERS

BM_RATE_DEFAULT = 0.05  # 5% Bea Masuk default
PPN_RATE = 0.11         # 11% PPN (Pajak Pertambahan Nilai)
PPH_RATE = 0.00         # 0% PPh for regular importers (varies)
PPI_RATE = 0.00         # 0% Penalty rate


def calculate_bm(fob_usd: float, freight_usd: float, insurance_usd: float, bm_tariff_pct: float) -> float:
    # Hitung Bea Masuk (Import Duty).
    cif = fob_usd + freight_usd + insurance_usd
    bm_rate = bm_tariff_pct / 100.0
    return cif * bm_rate


def calculate_ppn(bm_usd: float, cif_usd: float) -> float:
    # Hitung PPN.
    return (cif_usd + bm_usd) * PPN_RATE


def calculate_cif(
    fob_usd: float,
    freight_usd: float,
    insurance_usd: float,
) -> float:
    # Hitung CIF value.
    return fob_usd + freight_usd + insurance_usd


def calculate_nilaipabean(
    fob_usd: float,
    freight_usd: float,
    insurance_usd: float,
    bm_tariff_pct: float,
) -> Dict[str, float]:
    # Calculate all Nilain Pabean components.
    cif = calculate_cif(fob_usd, freight_usd, insurance_usd)
    bm = calculate_bm(fob_usd, freight_usd, insurance_usd, bm_tariff_pct)
    ppn = calculate_ppn(bm, cif)
    pph = 0.0  # varies by importer type
    nilaipabean = bm + cif
    total = nilaipabean + ppn + pph

    return {
        "cif": round(cif, 2),
        "bm": round(bm, 2),
        "ppn": round(ppn, 2),
        "pph": round(pph, 2),
        "nilaipabean": round(nilaipabean, 2),
        "total": round(total, 2),
    }


# FOB/CIF CALCULATION

def calc_fob_from_total(
    total_amount: float,
    currency: str,
    incoterm: str,
    freight_usd: float = 0.0,
    insurance_usd: float = 0.0,
) -> float:
    # Derive FOB from total amount based on incoterm.
    if not incoterm:
        return total_amount

    incoterm_upper = incoterm.upper().strip()
    is_cif = incoterm_upper in {"CIF", "CIP", "CFR", "CPT"}

    if is_cif:
        return total_amount - freight_usd - insurance_usd
    else:
        return total_amount


# AMOUNT PARSING

def parse_amount(value: str) -> float:
    # Parse string amount jadi float.
    if not value:
        return 0.0

    s = str(value).strip()

    # Remove currency symbols and text
    s = re.sub(r"[A-Z$€£¥₹Rp]", "", s)
    s = s.strip()

    # Handle parentheses as negative
    negative = "(" in s and ")" in s
    s = re.sub(r"[()]", "", s)

    # Detect format
    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        # Check which separator appears last (decimal marker)
        last_dot = s.rfind(".")
        last_comma = s.rfind(",")
        if last_dot > last_comma:
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif has_comma:
        # Could be European decimal or US thousands
        match = re.search(r",(\d{1,3})$", s)
        if match:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    try:
        result = float(s)
        return -result if negative else result
    except ValueError:
        return 0.0


def format_amount(value: float, currency: str = "USD") -> str:
    # Format float amount dengan prefix currency.
    if currency in ("USD", "EUR", "SGD", "AUD"):
        prefix = f"{currency} "
        return f"{prefix}{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    elif currency == "IDR":
        return f"Rp {value:,.0f}".replace(",", ".")
    else:
        return f"{value:,.2f}"


# HS CODE UTILITIES

def extract_hs_chapter(hs_code: str) -> str:
    # Ekstrak HS chapter (2 digit pertama).
    if not hs_code:
        return ""
    cleaned = re.sub(r"[^0-9]", "", hs_code)
    return cleaned[:2] if len(cleaned) >= 2 else cleaned


def validate_hs_code(hs_code: str) -> bool:
    # Validasi format HS code.
    if not hs_code:
        return False
    cleaned = re.sub(r"[^0-9]", "", hs_code)
    return len(cleaned) >= 6 and len(cleaned) <= 12


# AGGREGATION HELPERS

def sum_amounts(amounts: List[str]) -> float:
    # Sum list amount strings.
    total = 0.0
    for a in amounts:
        if a:
            total += parse_amount(str(a))
    return total


def sum_weights(weights: List[str]) -> float:
    # Sum list weight strings (dalam kg).
    total = 0.0
    for w in weights:
        if w:
            total += parse_amount(str(w))
    return total


# WEIGHT CONVERSION

KG_PER_LB = 0.453592
KG_PER_TON = 1000.0
KG_PER_LIANG = 0.0375
KG_PER_CATTY = 0.5


def convert_weight_to_kg(value: float, from_unit: str) -> float:
    # Konversi weight value ke kilogram.
    if not from_unit:
        return value

    unit = from_unit.upper().strip()

    if unit in ("KG", "KGM", "KILOGRAM", "KILOGRAMS"):
        return value
    elif unit in ("LB", "LBS", "POUND", "POUNDS"):
        return value * KG_PER_LB
    elif unit in ("TON", "TONNE", "TONNES", "TNE", "MT"):
        return value * KG_PER_TON
    elif unit in ("LIANG", "TAEL"):
        return value * KG_PER_LIANG
    elif unit in ("CATTY", "KIN"):
        return value * KG_PER_CATTY
    elif unit in ("G", "GR", "GRAM", "GRAMS"):
        return value / 1000.0

    return value  # assume already kg


# CONTAINER PARSING

CONTAINER_NUMBER_RE = re.compile(
    r"\b([A-Z]{3,4})[Uu]?(\d{6,7})\b"
)
CONTAINER_SIZE_RE = re.compile(
    r"\b(\d{1,2})[FTQHQ]\b"
)


def parse_container_number(container_str: str) -> Optional[Tuple[str, str]]:
    # Parse nomor kontainer.
    if not container_str:
        return None

    match = CONTAINER_NUMBER_RE.search(container_str.upper())
    if match:
        return (match.group(1), match.group(2))
    return None


def parse_container_size(container_str: str) -> str:
    # Parse ukuran kontainer.
    if not container_str:
        return "20"

    s = container_str.upper().strip()

    if "20" in s and "FT" in s:
        return "20"
    elif "40" in s and "HQ" in s:
        return "40HQ"
    elif "40" in s and "HC" in s:
        return "40HQ"
    elif "40" in s:
        return "40"
    elif "45" in s:
        return "45"
    elif s in ("LCL", "BULK"):
        return "LCL"

    # Try regex
    match = CONTAINER_SIZE_RE.search(s)
    if match:
        size = match.group(1)
        return f"{size}FT"

    return "20"


# DATE PARSING

DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d.%m.%Y",
]


def parse_date(date_str: str) -> Optional[str]:
    # Parse date string ke DD/MM/YYYY.
    from datetime import datetime

    if not date_str:
        return None

    s = str(date_str).strip()

    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass

    # Try fuzzy matching
    try:
        dt = datetime.strptime(s, "%d %b %y")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        pass

    return None


# SHIPMENT ID GENERATION

def generate_shipment_id(
    bl_number: Optional[str] = None,
    invoice_number: Optional[str] = None,
    date_str: Optional[str] = None,
) -> str:
    # Generate shipment ID.
    from datetime import datetime

    base = "SHP"

    if bl_number:
        # Use last 6 chars of BL number, stripped of letters
        cleaned = re.sub(r"[^0-9]", "", bl_number)
        if cleaned:
            base = f"BL{cleaned[-6:]}"
        else:
            base = f"BL{bl_number[-6:]}"
    elif invoice_number:
        cleaned = re.sub(r"[^0-9]", "", invoice_number)
        if cleaned:
            base = f"CI{cleaned[-6:]}"

    if date_str:
        parsed = parse_date(date_str)
        if parsed:
            dt = datetime.strptime(parsed, "%d/%m/%Y")
            suffix = dt.strftime("%m%d")
        else:
            suffix = date_str[-4:]
        return f"{base}-{suffix}"

    return base
