from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_cache: Dict[int, Tuple[float, float, float]] = {}
_cache_loaded = False


def _default_rates() -> Dict[str, float]:
    return {"bm": 0.0, "ppn": 12.0, "pph": 2.5, "hs_code": None, "found": False}


def _ensure_master_loaded() -> None:
    global _cache_loaded
    if _cache_loaded:
        return
    _load_master()
    _cache_loaded = True


def _load_master() -> None:
    # Load hs_code_tax_mapping.json into the module cache.
    try:
        import json

        search_paths = [
            Path(__file__).parent / "data" / "hs_code_tax_mapping.json",
            Path(__file__).parent.parent.parent / "data" / "hs_code_tax_mapping.json",
        ]

        path = None
        for p in search_paths:
            if p.exists():
                path = p
                break

        if path is None:
            logger.warning(
                f"hs_code_tax_mapping.json not found in {search_paths}. "
                "HS lookup will return zeros."
            )
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        entries = 0
        for hs_str, rates in data.items():
            try:
                code_int = int(hs_str)

                def parse_pct(val):
                    if isinstance(val, str) and val.endswith("%"):
                        return float(val.rstrip("%"))
                    return float(val) if val else 0.0

                bm = parse_pct(rates.get("BM", "0%"))
                ppn = parse_pct(rates.get("PPN", "0%"))
                pph = parse_pct(rates.get("PPH", "0%"))

                _cache[code_int] = (bm, ppn, pph)
                entries += 1
            except (ValueError, TypeError):
                continue

        logger.info(f"HS master loaded: {entries} entries from {path.name}")
    except Exception as e:
        logger.warning(f"Failed to load HS master: {e}. HS lookup will return zeros.")


def get_hs_tariff(hs_code: int | str) -> Dict[str, float]:
    _ensure_master_loaded()

    try:
        if isinstance(hs_code, str):
            code_int = int(str(hs_code).strip()[:8].ljust(8, "0"))
        else:
            code_int = int(hs_code)
    except (ValueError, TypeError):
        return _default_rates()

    # Exact 8-digit match
    if code_int in _cache:
        bm, ppn, pph = _cache[code_int]
        return {
            "bm": bm, "ppn": ppn, "pph": pph,
            "hs_code": str(code_int).zfill(8),
            "found": True,
        }

    # 4-digit prefix match
    prefix4 = code_int // 10000
    for cached_code, (bm, ppn, pph) in _cache.items():
        if cached_code // 10000 == prefix4:
            logger.info(f"HS {code_int}: using 4-digit prefix match {cached_code}")
            return {
                "bm": bm, "ppn": ppn, "pph": pph,
                "hs_code": str(code_int).zfill(8),
                "found": False,
            }

    # Default rates
    return _default_rates()


def clear_cache() -> None:
    global _cache_loaded
    _cache.clear()
    _cache_loaded = False
