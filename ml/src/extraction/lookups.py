"""
Lookup Tables for CEISA 4.0 Export.

Maps raw extracted values → CEISA standardized codes.
These are the external/third-party data sources that NER cannot provide.

Coverage:
  - HS Chapter → BM (Bea Materai) tariff rates
  - Port names → UN/LOCODE
  - Country names → ISO 2-letter codes
  - Currency names → ISO 4217 codes
  - Incoterms → CEISA incoterm codes
  - Packaging types → CEISA packaging codes
  - Port codes → CEISA port codes
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# HS TARIFF RATES (Bea Masuk / BM)
# Based on PMK Nomor 172 Tahun 2023 and BKF regulations.
# Format: chapter_range → (tariff_pct, facility_code)
# ═══════════════════════════════════════════════════════════════════════════════

HS_TARIFF_RATES: Dict[str, Tuple[float, str]] = {
    # Textile and textile articles (HS 50-63)
    "50": (5.0, "3"),   # Silk
    "51": (5.0, "3"),   # Wool, fine hair
    "52": (5.0, "3"),   # Cotton
    "53": (5.0, "3"),   # Vegetable fibres
    "54": (5.0, "3"),   # Man-made filaments
    "55": (5.0, "3"),   # Man-made staple fibres
    "56": (5.0, "3"),   # Wadding, felt, special yarns
    "57": (5.0, "3"),   # Carpets
    "58": (5.0, "3"),   # Special woven fabrics
    "59": (5.0, "3"),   # Impregnated textile fabrics
    "60": (5.0, "3"),   # Knitted fabrics
    "61": (10.0, "3"),  # Apparel, knitted
    "62": (10.0, "3"),  # Apparel, not knitted
    "63": (10.0, "3"),  # Other textile articles

    # Rubber and articles (HS 40)
    "40": (5.0, "3"),   # Rubber and articles thereof

    # Machinery and mechanical appliances (HS 84)
    "84": (0.0, "3"),   # Nuclear reactors, machinery
    "85": (0.0, "3"),   # Electrical machinery

    # Vehicles (HS 87)
    "87": (0.0, "3"),   # Vehicles, parts and accessories

    # Base metals (HS 72-83)
    "72": (5.0, "3"),   # Iron and steel
    "73": (5.0, "3"),   # Articles of iron/steel
    "74": (5.0, "3"),   # Copper and articles
    "75": (5.0, "3"),   # Nickel and articles
    "76": (5.0, "3"),   # Aluminium and articles
    "78": (5.0, "3"),   # Lead and articles
    "79": (5.0, "3"),   # Zinc and articles
    "80": (5.0, "3"),   # Tin and articles
    "81": (5.0, "3"),   # Other base metals
    "83": (5.0, "3"),   # Miscellaneous articles of base metal

    # Chemical products (HS 28-38)
    "28": (5.0, "3"),   # Inorganic chemicals
    "29": (5.0, "3"),   # Organic chemicals
    "30": (5.0, "3"),   # Pharmaceutical products
    "31": (5.0, "3"),   # Fertilizers
    "32": (5.0, "3"),   # Tanning extracts, dyes
    "33": (5.0, "3"),   # Essential oils, cosmetics
    "34": (5.0, "3"),   # Soap, lubricants
    "35": (5.0, "3"),   # Albumin, starch
    "36": (5.0, "3"),   # Explosives, pyrotechnics
    "37": (5.0, "3"),   # Photographic goods
    "38": (5.0, "3"),   # Miscellaneous chemical products

    # Plastics (HS 39)
    "39": (5.0, "3"),   # Plastics and articles thereof

    # Paper and paperboard (HS 47-49)
    "47": (5.0, "3"),   # Pulp, paper
    "48": (5.0, "3"),   # Paper articles
    "49": (5.0, "3"),   # Books, printed matter

    # Leather (HS 41-43)
    "41": (5.0, "3"),   # Raw hides and skins
    "42": (10.0, "3"),  # Leather articles
    "43": (5.0, "3"),   # Furskins, artificial fur

    # Wood and articles (HS 44-46)
    "44": (5.0, "3"),   # Wood and articles
    "45": (5.0, "3"),   # Cork
    "46": (5.0, "3"),   # Manufactures of straw

    # Footwear, headgear (HS 64-67)
    "64": (10.0, "3"),  # Footwear
    "65": (10.0, "3"),  # Headgear
    "66": (10.0, "3"),  # Umbrellas
    "67": (10.0, "3"),  # Feathers, artificial flowers

    # Stone, ceramics, glass (HS 68-70)
    "68": (5.0, "3"),   # Stone articles
    "69": (5.0, "3"),   # Ceramic products
    "70": (5.0, "3"),   # Glass and articles

    # Natural/cultured pearls (HS 71)
    "71": (5.0, "3"),   # Pearls, precious stones, metals

    # Optical/photographic (HS 90-92)
    "90": (0.0, "3"),   # Optical instruments
    "91": (5.0, "3"),   # Clocks and watches
    "92": (5.0, "3"),   # Musical instruments

    # Arms and ammunition (HS 93)
    "93": (5.0, "3"),   # Arms and ammunition

    # Furniture, toys (HS 94-96)
    "94": (10.0, "3"),  # Furniture, bedding
    "95": (10.0, "3"),  # Toys, games
    "96": (10.0, "3"),  # Miscellaneous manufactured articles

    # Works of art (HS 97)
    "97": (0.0, "3"),   # Works of art, antiques

    # Default for unlisted chapters
    "_default": (5.0, "3"),
}


def get_hs_tariff(hs_code: str) -> Tuple[float, str]:
    """
    Get BM tariff rate and facility code for an HS code.

    Args:
        hs_code: HS code (e.g., "59022020", "40112000")

    Returns:
        Tuple of (tariff_pct, facility_code)
        e.g., (5.0, "3") for standard rate with facility
    """
    if not hs_code:
        return (5.0, "3")

    # Extract chapter (first 2 digits)
    cleaned = re.sub(r"[^0-9]", "", hs_code)
    if len(cleaned) < 2:
        return (5.0, "3")

    chapter = cleaned[:2]
    if chapter in HS_TARIFF_RATES:
        return HS_TARIFF_RATES[chapter]

    return HS_TARIFF_RATES["_default"]


# ═══════════════════════════════════════════════════════════════════════════════
# PORT NAMES → UN/LOCODE
# Indonesian customs uses UN/LOCODE for all ports.
# ═══════════════════════════════════════════════════════════════════════════════

PORT_TO_LOCODE: Dict[str, str] = {
    # China - Major ports
    "YANGZHOU": "CNYZH",
    "YANGZHOU, CHINA": "CNYZH",
    "ZHANGJIAGANG": "CNZJG",
    "ZHANGJIAGANG, CHINA": "CNZJG",
    "SHEKOU": "CNSHE",
    "DALIAN": "CNDLC",
    "DALIAN, CHINA": "CNDLC",
    "XIAMEN": "CNXMN",
    "XIAMEN, CHINA": "CNXMN",
    "YANTIAN": "CNYTN",
    "YANTIAN, CHINA": "CNYTN",
    "NANSHA": "CNNSA",
    "NANSHA, CHINA": "CNNSA",
    "HONG KONG": "HKHKG",
    "HONGKONG": "HKHKG",
    "NINGBO": "CNNBO",
    "NINGBO-ZHOUSHAN": "CNNBO",
    "SHANGHAI": "CNSHA",
    "SHANGHAI, CHINA": "CNSHA",
    "QINGDAO": "CNTAO",
    "QINGDAO, CHINA": "CNTAO",
    "TIANJIN": "CNTJN",
    "TIANJIN, CHINA": "CNTJN",
    "GUANGZHOU": "CNCAN",
    "GUANGZHOU, CHINA": "CNCAN",
    "HUANGPU": "CNCAN",
    "HUANGPU, CHINA": "CNCAN",
    "HUIZHOU": "CNHUI",
    "ZHONGSHAN": "CNZSN",

    # Taiwan
    "KEELUNG": "TWKEL",
    "KAOHSIUNG": "TWKHH",
    "TAIPEI": "TWTPE",

    # Japan
    "TOKYO": "JPTYO",
    "YOKOHAMA": "JPYOK",
    "OSAKA": "JPOSA",
    "NAGOYA": "JPNGO",
    "KOBE": "JPUBE",
    "HAKATA": "JPHKT",

    # Korea
    "BUSAN": "KRPUS",
    "BUSAN, KOREA": "KRPUS",
    "PUSAN": "KRPUS",
    "SEOUL": "KRINC",
    "INCHEON": "KRINC",

    # Southeast Asia
    "SINGAPORE": "SGSIN",
    "SINGAPORE, SINGAPORE": "SGSIN",
    "PORT KLANG": "MYPKG",
    "PENANG": "MYPEN",
    "LAHAD DATU": "MYLDU",
    "BINTULU": "MYBTU",
    "PASIR GUDANG": "MYPGU",
    "TANJUNG PELEPAS": "MYTPP",
    "HO CHI MINH": "VNSGN",
    "HO CHI MINH CITY": "VNSGN",
    "HOCHIMINH": "VNSGN",
    "SAIGON": "VNSGN",
    "HAIPHONG": "VNHPH",
    "HANOI": "VNHAN",
    "CANG CAT LAI": "VNSGN",
    "CANG TIEN SA": "VNUTH",
    "BANGKOK": "THBKK",
    "LAEM CHABANG": "THLCH",
    "PENANG": "MYPEN",
    "KOTA KINABALU": "MYBKI",
    "KUCHING": "MYKCH",
    "BELAWAN": "IDBLW",
    "MEDAN": "IDBLW",
    "PANGKAL BALAM": "IDPBL",
    "PANGKAL PINANG": "IDPGK",

    # Indonesia - Export ports (Pelabuhan Muat)
    "TANJUNG PRIOK": "IDTPP",
    "JAKARTA": "IDTPP",
    "JAKARTA, INDONESIA": "IDTPP",
    "SURABAYA": "IDSUB",
    "SURABAYA, INDONESIA": "IDSUB",
    "SEMARANG": "IDSEM",
    "BELAWAN": "IDBLW",
    "MAKASSAR": "IDUPA",
    "PANGKAL PINANG": "IDPGK",
    "CIKARANG": "IDCGK",
    "TANJUNG PERAK": "IDSUB",
    "JOMBANG": "IDSUB",

    # Australia
    "SYDNEY": "AUSYD",
    "MELBOURNE": "AUMEL",
    "BRISBANE": "AUBNE",
    "FREMANTLE": "AUFRE",

    # Europe
    "ROTTERDAM": "NLRTM",
    "ROTTERDAM, NETHERLANDS": "NLRTM",
    "ANTWERP": "BEANR",
    "HAMBURG": "DEHAM",
    "FELIXSTOWE": "GBFXT",
    "LE HAVRE": "FRLEH",
    "BARCELONA": "ESBCN",
    "PIRAEUS": "GRPIR",

    # Americas
    "LOS ANGELES": "USLAX",
    "LONG BEACH": "USLGB",
    "NEW YORK": "USNYC",
    "HOUSTON": "USHOU",
    "SAVANNAH": "USSAV",
    "VANCOUVER": "CAVAN",
    "MONTREAL": "CAMTQ",
    "SANTOS": "BRSSZ",
    "BUENOS AIRES": "ARBUE",
    "CALLAO": "PECLL",

    # Middle East
    "DUBAI": "AEJEA",
    "SHARJAH": "AESHC",
    "JEBEL ALI": "AEJEA",
    "SALALAH": "OMSLL",
    "KUWAIT": "KUKWI",

    # Africa
    "DURBAN": "ZADUR",
    "CAPE TOWN": "ZACPT",
    "PORT ELIZABETH": "ZAPLZ",
    "MOMBASA": "KEMOM",
}

# Reverse lookup
LOCODE_TO_PORT: Dict[str, str] = {v: k for k, v in PORT_TO_LOCODE.items()}


def get_port_locode(port_name: str) -> Optional[str]:
    """
    Map a port name to UN/LOCODE.

    Args:
        port_name: Port name (e.g., "NINGBO", "Shanghai, China")

    Returns:
        UN/LOCODE (e.g., "CNNBO") or None if not found
    """
    if not port_name:
        return None

    name_upper = port_name.upper().strip()

    # Direct match
    if name_upper in PORT_TO_LOCODE:
        return PORT_TO_LOCODE[name_upper]

    # Partial match
    for port_key, locode in PORT_TO_LOCODE.items():
        if port_key in name_upper or name_upper in port_key:
            return locode

    # Try extracting city name (remove common suffixes)
    cleaned = re.sub(r"[,\-\s]*(CHINA|INDONESIA|KOREA|JAPAN|SINGAPORE|THAILAND|MALAYSIA|VIETNAM).*$", "", name_upper)
    if cleaned and cleaned != name_upper:
        if cleaned in PORT_TO_LOCODE:
            return PORT_TO_LOCODE[cleaned]

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# COUNTRY NAMES → ISO 3166-1 alpha-2
# ═══════════════════════════════════════════════════════════════════════════════

COUNTRY_TO_ISO2: Dict[str, str] = {
    # East Asia
    "CHINA": "CN",
    "PEOPLES REPUBLIC OF CHINA": "CN",
    "PRC": "CN",
    "HONG KONG": "HK",
    "HONGKONG": "HK",
    "TAIWAN": "TW",
    "REPUBLIC OF CHINA": "TW",
    "JAPAN": "JP",
    "JAPAN, JAPAN": "JP",
    "SOUTH KOREA": "KR",
    "KOREA": "KR",
    "KOREA, REPUBLIC OF": "KR",
    "REPUBLIC OF KOREA": "KR",
    "DPRK": "KP",
    "NORTH KOREA": "KP",

    # Southeast Asia
    "INDONESIA": "ID",
    "SINGAPORE": "SG",
    "MALAYSIA": "MY",
    "THAILAND": "TH",
    "VIETNAM": "VN",
    "VIET NAM": "VN",
    "PHILIPPINES": "PH",
    "CAMBODIA": "KH",
    "MYANMAR": "MM",
    "LAOS": "LA",
    "BRUNEI": "BN",
    "TIMOR LESTE": "TL",

    # South Asia
    "INDIA": "IN",
    "PAKISTAN": "PK",
    "BANGLADESH": "BD",
    "SRI LANKA": "LK",
    "NEPAL": "NP",
    "BHUTAN": "BT",
    "MALDIVES": "MV",

    # Middle East
    "UNITED ARAB EMIRATES": "AE",
    "UAE": "AE",
    "SAUDI ARABIA": "SA",
    "QATAR": "QA",
    "KUWAIT": "KW",
    "BAHRAIN": "BH",
    "OMAN": "OM",
    "IRAN": "IR",
    "IRAQ": "IQ",
    "TURKEY": "TR",
    "ISRAEL": "IL",
    "LEBANON": "LB",
    "JORDAN": "JO",

    # Europe
    "GERMANY": "DE",
    "FRANCE": "FR",
    "UNITED KINGDOM": "GB",
    "UK": "GB",
    "ENGLAND": "GB",
    "ITALY": "IT",
    "SPAIN": "ES",
    "NETHERLANDS": "NL",
    "HOLLAND": "NL",
    "BELGIUM": "BE",
    "SWITZERLAND": "CH",
    "AUSTRIA": "AT",
    "SWEDEN": "SE",
    "NORWAY": "NO",
    "DENMARK": "DK",
    "FINLAND": "FI",
    "POLAND": "PL",
    "CZECH REPUBLIC": "CZ",
    "HUNGARY": "HU",
    "ROMANIA": "RO",
    "BULGARIA": "BG",
    "GREECE": "GR",
    "PORTUGAL": "PT",
    "IRELAND": "IE",
    "RUSSIA": "RU",
    "RUSSIAN FEDERATION": "RU",
    "UKRAINE": "UA",
    "BELARUS": "BY",

    # Americas
    "UNITED STATES": "US",
    "USA": "US",
    "UNITED STATES OF AMERICA": "US",
    "CANADA": "CA",
    "MEXICO": "MX",
    "BRAZIL": "BR",
    "ARGENTINA": "AR",
    "CHILE": "CL",
    "PERU": "PE",
    "COLOMBIA": "CO",
    "VENEZUELA": "VE",
    "ECUADOR": "EC",

    # Africa
    "SOUTH AFRICA": "ZA",
    "EGYPT": "EG",
    "MOROCCO": "MA",
    "TUNISIA": "TN",
    "ALGERIA": "DZ",
    "NIGERIA": "NG",
    "KENYA": "KE",
    "ETHIOPIA": "ET",
    "GHANA": "GH",
    "TANZANIA": "TZ",
    "UGANDA": "UG",
    "ANGOLA": "AO",
    "MOZAMBIQUE": "MZ",
    "ZAMBIA": "ZM",
    "ZIMBABWE": "ZW",
    "BOTSWANA": "BW",
    "NAMIBIA": "NA",
    "MAURITIUS": "MU",
    "MADAGASCAR": "MG",

    # Oceania
    "AUSTRALIA": "AU",
    "NEW ZEALAND": "NZ",
    "PAPUA NEW GUINEA": "PG",
    "FIJI": "FJ",

    # Default
    "UNKNOWN": "CN",
}

ISO2_TO_COUNTRY: Dict[str, str] = {v: k for k, v in COUNTRY_TO_ISO2.items()}


def get_country_code(country_name: str) -> str:
    """
    Map a country name to ISO 3166-1 alpha-2 code.

    Args:
        country_name: Country name (e.g., "CHINA", "Indonesia") or ISO 2-letter code

    Returns:
        ISO 2-letter code (e.g., "CN", "ID")
    """
    if not country_name:
        return "CN"  # Default to China

    name_upper = country_name.upper().strip()

    # If already a valid ISO 2-letter code, return as-is
    if len(name_upper) == 2 and name_upper.isalpha():
        return name_upper

    if name_upper in COUNTRY_TO_ISO2:
        return COUNTRY_TO_ISO2[name_upper]

    # Partial match — check if country_key is a word-bounded substring of name_upper
    # or if name_upper is a word-bounded substring of country_key.
    # Use word boundaries to avoid "ID" matching inside "INDONESIA" or "KR" in "UKRAINE".
    for country_key, code in COUNTRY_TO_ISO2.items():
        # Word-bounded: country_key inside name_upper
        if country_key in name_upper:
            # Make sure it's a word boundary match (prevents 'ID' in 'INDONESIA')
            start = name_upper.find(country_key)
            before_ok = start == 0 or not name_upper[start - 1].isalpha()
            after_ok = (start + len(country_key) >= len(name_upper) or
                        not name_upper[start + len(country_key)].isalpha())
            if before_ok and after_ok:
                return code
        # name_upper inside country_key
        if name_upper in country_key:
            start = country_key.find(name_upper)
            before_ok = start == 0 or not country_key[start - 1].isalpha()
            after_ok = (start + len(name_upper) >= len(country_key) or
                        not country_key[start + len(name_upper)].isalpha())
            if before_ok and after_ok:
                return code

    return "CN"  # Default fallback


# ═══════════════════════════════════════════════════════════════════════════════
# CURRENCY CODES
# ISO 4217 currency codes
# ═══════════════════════════════════════════════════════════════════════════════

CURRENCY_TO_ISO4217: Dict[str, str] = {
    # Clean currency codes
    "USD": "USD",
    "US$": "USD",
    "US DOLLAR": "USD",
    "DOLLAR": "USD",
    "US DOLLAR PER KG": "USD",
    "USD/KG": "USD",
    "US$ /KG": "USD",
    "USD/KG": "USD",
    "CNY": "CNY",
    "RMB": "CNY",
    "YEN": "CNY",
    "YUAN": "CNY",
    "EURO": "EUR",
    "EUR": "EUR",
    "GBP": "GBP",
    "POUND": "GBP",
    "STERLING": "GBP",
    "JPY": "JPY",
    "YEN": "JPY",
    "SGD": "SGD",
    "SINGAPORE DOLLAR": "SGD",
    "MYR": "MYR",
    "MALAYSIAN RINGGIT": "MYR",
    "IDR": "IDR",
    "RUPIAH": "IDR",
    "THB": "THB",
    "BAHT": "THB",
    "KRW": "KRW",
    "WON": "KRW",
    "HKD": "HKD",
    "HONG KONG DOLLAR": "HKD",
    "AUD": "AUD",
    "AUSTRALIAN DOLLAR": "AUD",
    "NZD": "NZD",
    "INR": "INR",
    "RUPEE": "INR",
    "PHP": "PHP",
    "PESO": "PHP",
    "VND": "VND",
    "DONG": "VND",
}


def get_currency_code(currency_name: str) -> str:
    """Map currency name to ISO 4217 code."""
    if not currency_name:
        return "USD"

    name_upper = currency_name.upper().strip()

    # Remove unit suffixes (common in OCR: "USD/KG", "USD/KGS", "USD PER KG")
    name_clean = re.sub(r"[\/\s]*(?:PER|KG|KGS|LB|LBS|KGS?)\s*$", "", name_upper)
    if name_clean != name_upper:
        name_upper = name_clean

    if name_upper in CURRENCY_TO_ISO4217:
        return CURRENCY_TO_ISO4217[name_upper]

    # Partial match
    for curr_key, code in CURRENCY_TO_ISO4217.items():
        if curr_key in name_upper or name_upper in curr_key:
            return code

    return "USD"


# ═══════════════════════════════════════════════════════════════════════════════
# INCOTERMS
# ═══════════════════════════════════════════════════════════════════════════════

INCOTERM_TO_CODE: Dict[str, str] = {
    "EXW": "EXW",  # Ex Works
    "FCA": "FCA",  # Free Carrier
    "FAS": "FAS",  # Free Alongside Ship
    "FOB": "FOB",  # Free On Board
    "CFR": "CFR",  # Cost and Freight
    "CIF": "CIF",  # Cost, Insurance and Freight
    "CPT": "CPT",  # Carriage Paid To
    "CIP": "CIP",   # Carriage and Insurance Paid To
    "DAP": "DAP",  # Delivered At Place
    "DPU": "DPU",  # Delivered at Place Unloaded
    "DDP": "DDP",  # Delivered Duty Paid
    "DAT": "DAT",  # Delivered At Terminal
}

# Incoterms that determine CIF calculation
CIF_INCOTERMS = {"CIF", "CIP", "CFR", "CPT"}
FOB_INCOTERMS = {"FOB", "FCA", "EXW", "FAS"}


def get_incoterm_code(incoterm_name: str) -> Optional[str]:
    """Map incoterm name to CEISA incoterm code."""
    if not incoterm_name:
        return None

    name_upper = incoterm_name.upper().strip()

    if name_upper in INCOTERM_TO_CODE:
        return INCOTERM_TO_CODE[name_upper]

    for inc_key, code in INCOTERM_TO_CODE.items():
        if inc_key in name_upper:
            return code

    return None


def is_cif_based(incoterm: str) -> bool:
    """Check if incoterm is CIF-based (freight/insurance already included)."""
    if not incoterm:
        return False
    return incoterm.upper() in CIF_INCOTERMS


# ═══════════════════════════════════════════════════════════════════════════════
# PACKAGING CODES
# Kode Kemasan berdasarkan BC 2.0 / CEISA 4.0
# ═══════════════════════════════════════════════════════════════════════════════

PACKAGING_TO_CODE: Dict[str, str] = {
    # Piece counts
    "PIECE": "PCE",
    "PIECES": "PCE",
    "PC": "PCE",
    "PCS": "PCE",
    "UNIT": "PCE",
    "UNITS": "PCE",
    "EACH": "PCE",

    # Sets
    "SET": "SET",
    "SETS": "SET",

    # Length measures
    "METER": "MTR",
    "METERS": "MTR",
    "MTR": "MTR",
    "MT": "MTR",

    # Weight measures
    "KILOGRAM": "KGM",
    "KILOGRAMS": "KGM",
    "KG": "KGM",
    "KGS": "KGM",

    # Tons
    "TONNE": "TNE",
    "TONNES": "TNE",
    "TON": "TNE",
    "MT": "TNE",

    # Liters
    "LITER": "LTR",
    "LITERS": "LTR",
    "LITRE": "LTR",
    "LITRES": "LTR",
    "LT": "LTR",

    # Volume
    "CUBIC METER": "MTQ",
    "CUBIC METERS": "MTQ",
    "M3": "MTQ",
    "CBM": "MTQ",

    # Rolls / spools
    "ROLL": "ROL",
    "ROLLS": "ROL",
    "SPOOL": "ROL",
    "SPOOLS": "ROL",
    "REEL": "ROL",
    "REELS": "ROL",

    # Cartons / boxes
    "CARTON": "CT",
    "CARTONS": "CT",
    "CTN": "CT",
    "BOX": "CT",
    "BOXES": "CT",
    "PACK": "CT",
    "PACKS": "CT",

    # Pallets
    "PALLET": "TDP",
    "PALLETS": "TDP",
    "FLAT PALLET": "TDP",

    # Drums / barrels
    "DRUM": "DRM",
    "DRUMS": "DRM",
    "BARREL": "DRM",
    "BARRELS": "DRM",
    "STEEL DRUM": "DRM",

    # Bags / sacks
    "BAG": "BAG",
    "BAGS": "BAG",
    "SACK": "BAG",
    "SACKS": "BAG",
    "BIG BAG": "BAG",
    "BIGBAG": "BAG",
    "JUMBO BAG": "BAG",

    # Crates
    "CRATE": "CRD",
    "CRATES": "CRD",

    # Container types (for KONTAINER sheet)
    "20FT": "20",
    "40FT": "40",
    "40HQ": "40",
    "45FT": "45",
    "ISO TANK": "TANK",
}


def get_packaging_code(packaging_name: str) -> str:
    """
    Map packaging name to CEISA packaging code.

    Args:
        packaging_name: Packaging description (e.g., "Cartons", "KG", "Rolls")

    Returns:
        CEISA packaging code (e.g., "CT", "KGM", "ROL")
    """
    if not packaging_name:
        return "PCE"

    name_upper = packaging_name.upper().strip()

    if name_upper in PACKAGING_TO_CODE:
        return PACKAGING_TO_CODE[name_upper]

    for pkg_key, code in PACKAGING_TO_CODE.items():
        if pkg_key in name_upper:
            return code

    return "PCE"  # Default to pieces


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY TYPES → CEISA Entity Codes
# KODE ENTITAS for ENTITAS sheet
# ═══════════════════════════════════════════════════════════════════════════════

ENTITY_TYPE_CODES: Dict[str, int] = {
    # Importir / Buyer
    "buyer": 1,
    "importer": 1,
    "penerima": 1,

    # Eksportir / Seller
    "seller": 9,
    "exporter": 9,
    "pengirim": 9,

    # Produsen / Manufacturer
    "manufacturer": 10,
    "produsen": 10,
    "pabrik": 10,

    # Shipper / Pengirim Barang
    "shipper": 7,
    "pengirim_barang": 7,

    # Notify Party
    "notify": 4,
    "notify_party": 4,
    "notifyparty": 4,

    # Consignee
    "consignee": 11,
    "tujuan_kirim": 11,
}


def get_entity_type_code(entity_type: str) -> int:
    """Map entity type to CEISA KODE ENTITAS."""
    if not entity_type:
        return 1  # Default to importer

    name_upper = entity_type.lower().strip()

    for key, code in ENTITY_TYPE_CODES.items():
        if key in name_upper:
            return code

    return 1  # Default to importer
