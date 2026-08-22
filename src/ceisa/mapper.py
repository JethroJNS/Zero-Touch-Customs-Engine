import re
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ceisa")


class CeisaMapper:
    # Maps OCR extraction result ke CEISA PIB/PEB JSON.

    # Kode kantor pabean
    KODE_KANTOR = "051000"

    # Kode dokumen pabean
    DOKUMEN_PIB = "20"      # PIB - Pemberitahuan Impor Barang
    DOKUMEN_PEB = "30"      # PEB - Pemberitahuan Ekspor Barang

    # Incoterms codes
    INCOTERM_CODES = {
        "FOB": "FOB", "CIF": "CIF", "CFR": "CFR",
        "CPT": "CPT", "CIP": "CIP", "DAP": "DAP",
        "DDP": "DDP", "FCA": "FCA", "EXW": "EXW",
        "FAS": "FAS", "DAT": "DAT",
    }

    # Cara bayar codes
    CARA_BAYAR = {
        "T/T": "1",    # Telegraphic Transfer
        "L/C": "2",    # Letter of Credit
        "D/P": "3",    # Documents against Payment
        "D/A": "4",    # Documents against Acceptance
        "CASH": "5",   # Cash
        "CREDIT": "6", # Credit
        "OTHER": "9",  # Lainnya
    }

    # Jenis nilai codes
    JENIS_NILAI = {
        "KMD": "KMD",  # Cost, Insurance, Freight
        "NM": "NM",    # Net Money
        "BL": "BL",    # Harga Jual Eceran
    }

    def __init__(self, entities=None):
        self.entities = entities

    def map_header(self, entities) -> Dict[str, Any]:
        # Build the CEISA header document from extracted entities.
        e = entities

        # Parse dates
        invoice_date = self._parse_date(getattr(e, "invoice_date", None))
        aju_date = invoice_date.strftime("%Y-%m-%d") if invoice_date else datetime.now().strftime("%Y-%m-%d")

        # Currency and amount
        currency = getattr(e, "currency", "USD") or "USD"
        total_amount = self._parse_amount(getattr(e, "total_amount", None))

        # Incoterms
        incoterms = getattr(e, "incoterms", None)
        incoterm_code = self.INCOTERM_CODES.get(str(incoterms).upper(), "FOB") if incoterms else "FOB"

        # Payment method
        cara_bayar = self.CARA_BAYAR.get(
            str(getattr(e, "payment_method", "T/T")).upper(), "1"
        )

        # Port codes dari lookups
        port_loading = getattr(e, "port_of_loading", None)
        port_discharge = getattr(e, "port_of_discharge", None)

        # Company info
        buyer_name = getattr(e, "buyer_name", None) or ""
        seller_name = getattr(e, "seller_name", None) or ""

        # nomorAju: generate dari NPWP + date + sequence
        nomor_aju = self._generate_nomor_aju(
            kode_kantor=self.KODE_KANTOR,
            kode_dokumen=self.DOKUMEN_PIB,
            tanggal=aju_date,
        )

        # NDPBM (Nilai Pabean) — exchange rate
        ndpbm = getattr(e, "ndpbm", None) or "15000.0"
        ndpbm_val = self._parse_amount(ndpbm)

        # Total weights
        gross_weight = self._parse_amount(getattr(e, "total_gross_weight", None))
        net_weight = self._parse_amount(getattr(e, "total_net_weight", None))

        # Freight / insurance
        freight = self._parse_amount(getattr(e, "freight", None))
        insurance = self._parse_amount(getattr(e, "insurance", None))

        # FOB = CIF - freight - insurance
        fob_amount = total_amount
        if incoterm_code in ("CIF", "CIP", "CFR", "CPT"):
            fob_amount = max(0, total_amount - freight - insurance)

        header = {
            # Identitas Dokumen
            "nomorAju": nomor_aju,
            "tanggalAju": aju_date,
            "kodeKantor": self.KODE_KANTOR,
            "kodeDokumen": self.DOKUMEN_PIB,
            "kodeJenisProsedur": "1",         # Impor Biasa / Manual
            "kodeJenisImpor": "1",             # Biasa / TKB / PKB
            "kodeCaraBayar": cara_bayar,
            "kodeIncoterm": incoterm_code,
            "nilaiIncoterm": total_amount,
            "ndpbm": ndpbm_val,
            "valuta": currency,
            "fob": fob_amount,
            "asuransi": insurance,
            "freight": freight,
            "nilaiBarang": fob_amount,          # FOB for CIF calculation base
            "nilaiMaklon": 0,

            # Pelabuhan & Transportasi
            "kodePelMuat": port_loading or "CN",
            "kodePelTransit": "",
            "kodePelTujuan": port_discharge or "ID",

            # Identitas Perusahaan
            "npwpPerusahaan": getattr(e, "company_npwp", "") or "000000000000000",
            "namaPerusahaan": buyer_name or seller_name or "UNKNOWN",
            "alamatPerusahaan": getattr(e, "company_address", "") or "",

            # Data PIB Header
            "kodeJenisNilai": "KMD",
            "hargaPenyerahan": 0,
            "jumlahKontainer": self._parse_int(getattr(e, "container_count", None), default=1),
            "jumlahTandaPengaman": 0,
            "kodeAsuransi": "LN",               # Lokal / LN

            # BC 2.5 / BC 1.1 Reference
            "nomorBc11": getattr(e, "bc11_number", "") or "",
            "tanggalBc11": getattr(e, "bc11_date", "") or "",
            "posBc11": "0001",
            "subPosBc11": "00000000",

            # Identitas Pabean
            "idPengguna": getattr(e, "user_id", "") or "",
            "namaTtd": getattr(e, "signatory_name", "") or "",
            "jabatanTtd": getattr(e, "signatory_title", "") or "MANAGER",

            # Tambahan
            "seri": 0,
            "netto": net_weight or 0,
            "bruto": gross_weight or 0,
            "invoiceNumber": getattr(e, "invoice_number", "") or "",
            "invoiceDate": getattr(e, "invoice_date", "") or "",
        }

        return header

    def map_items(self, entities) -> List[Dict[str, Any]]:
        # Build per-item CEISA barang list from extracted items.
        items = getattr(entities, "items", []) or []
        if not items:
            logger.warning("No items to map — CEISA requires at least one item")
            return []

        ndpbm = self._parse_amount(getattr(entities, "ndpbm", None)) or 15000.0
        currency = getattr(entities, "currency", "USD") or "USD"
        incoterms = str(getattr(entities, "incoterms", "")).upper() or "FOB"
        incoterm_code = self.INCOTERM_CODES.get(incoterms, "FOB")

        total_amount = self._parse_amount(getattr(entities, "total_amount", None)) or 0
        freight = self._parse_amount(getattr(entities, "freight", None)) or 0
        insurance = self._parse_amount(getattr(entities, "insurance", None)) or 0
        cif_amount = total_amount if incoterm_code in ("CIF", "CIP", "CFR", "CPT") else total_amount + freight + insurance

        mapped_items = []
        for idx, item in enumerate(items):
            hs_code = self._normalize_hs(getattr(item, "hs_code", None))
            qty = self._parse_amount(getattr(item, "quantity", None)) or 1
            unit_price = self._parse_amount(getattr(item, "unit_price", None)) or 0
            amount = self._parse_amount(getattr(item, "amount", None)) or (qty * unit_price)
            cif_item = amount  # simplified — full CIF per item needs freight allocation
            cif_rupiah = cif_item * ndpbm
            fob_rupiah = amount * ndpbm

            barang = {
                "seri": idx + 1,
                "hsCode": hs_code or "00000000",
                "uraianBarang": getattr(item, "description", "") or "",
                "kodeNegaraAsal": getattr(item, "country_of_origin", "") or "CN",
                "jumlahSatuan": qty,
                "kodeSatuan": getattr(item, "unit", "") or "NMP",
                "hargaSatuan": unit_price,
                "hargaPerolehan": amount,
                "fob": amount,
                "cif": cif_item,
                "cifRupiah": cif_rupiah,
                "netto": self._parse_amount(getattr(item, "net_weight", None)) or 0,
                "bruto": self._parse_amount(getattr(item, "gross_weight", None)) or 0,
                "kodeKemasan": getattr(item, "packaging", "") or "PK",
                "jumlahKemasan": self._parse_int(getattr(item, "cartons", None), default=1),
                "kodeGuna": "01",
            }
            mapped_items.append(barang)

        return mapped_items

    def map_document(self, entities) -> Dict[str, Any]:
        # Build complete CEISA PIB document JSON.
        header = self.map_header(entities)
        items = self.map_items(entities)

        document = {
            **header,
            "barang": items,
        }

        return document

    # Helpers

    def _generate_nomor_aju(
        self,
        kode_kantor: str,
        kode_dokumen: str,
        tanggal: str,
        npwp: str = "000000000000000",
        sequence: int = 1,
    ) -> str:
        # Clean date: YYYY-MM-DD → YYYYMMDD
        date_part = tanggal.replace("-", "").replace("/", "")
        if len(date_part) != 8:
            date_part = datetime.now().strftime("%Y%m%d")

        # Clean NPWP: hanya digit
        npwp_clean = re.sub(r"\D", "", npwp)[:6].ljust(6, "0")

        # Sequence: 6 digit, zero-padded
        seq_str = str(sequence).zfill(6)

        nomor_aju = f"{kode_kantor}{kode_dokumen}{npwp_clean}{date_part}{seq_str}"
        return nomor_aju

    def _normalize_hs(self, hs: Optional[str]) -> str:
        if not hs:
            return ""
        # Remove non-digit
        digits = re.sub(r"\D", "", str(hs))
        if len(digits) >= 6:
            return digits[:8].ljust(8, "0")
        return digits.zfill(8)

    def _parse_date(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%b %d, %Y", "%d %b %Y"):
            try:
                return datetime.strptime(str(value).strip(), fmt)
            except ValueError:
                pass
        return None

    def _parse_amount(self, value: Any) -> Optional[float]:
        # Parse numeric amount from string or number.
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        s = re.sub(r"[A-Z$€£¥]", "", s)
        s = s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None

    def _parse_int(self, value: Any, *, default: int = 0) -> int:
        # Parse integer from string or number.
        if value is None:
            return default
        if isinstance(value, int):
            return value
        s = re.sub(r"\D", "", str(value))
        return int(s) if s else default
