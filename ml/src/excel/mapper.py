from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# FIELD METADATA

@dataclass(frozen=True)
class FieldMeta:
    """Metadata untuk satu field CEISA."""
    entity_name: str
    sheet: str
    excel_col: str
    required: bool = False
    default: Optional[str] = None
    data_type: str = "text"  # text | number | date | code | currency
    validators: Tuple[str, ...] = ()
    ceisa_code: Optional[str] = None  # contoh "KODE PELABUHAN MUAT"


FIELD_METADATA: Dict[str, FieldMeta] = {
    # HEADER
    "nomor_aju":              FieldMeta("shipment_id",     "HEADER",         "NOMOR AJU",               required=True,  data_type="text"),
    "kode_kantor":            FieldMeta("kode_kantor",    "HEADER",         "KODE KANTOR",             default="040300"),
    "kode_dokumen":           FieldMeta("kode_dokumen",   "HEADER",         "KODE DOKUMEN",            default="20"),
    "kode_jenis_impor":       FieldMeta("kode_impor",     "HEADER",         "KODE JENIS IMPOR",        default="1"),
    "kode_jenis_prosedur":    FieldMeta("kode_prosedur",  "HEADER",         "KODE JENIS PROSEDUR",     default="1"),
    "kode_cara_bayar":        FieldMeta("kode_bayar",     "HEADER",         "KODE CARA BAYAR",         default="1"),
    "kode_tutup_pu":          FieldMeta("kode_tutup",     "HEADER",         "KODE TUTUP PU",           default="11"),
    "kode_valuta":            FieldMeta("currency",        "HEADER",         "KODE VALUTA",             required=False),
    "kode_incoterm":          FieldMeta("incoterms",       "HEADER",         "KODE INCOTERM"),
    "kode_pelabuhan_muat":    FieldMeta("port_of_loading", "HEADER",        "KODE PELABUHAN MUAT"),
    "kode_pelabuhan_bongkar": FieldMeta("port_of_discharge","HEADER",       "KODE PELABUHAN BONGKAR"),
    "kode_pelabuhan_transit": FieldMeta("port_of_loading", "HEADER",        "KODE PELABUHAN TRANSIT"),
    "kode_pelabuhan_tujuan": FieldMeta("port_of_destination","HEADER",     "KODE PELABUHAN TUJUAN"),
    "fob":                    FieldMeta("total_amount",    "HEADER",         "FOB",                     data_type="currency"),
    "cif":                    FieldMeta("total_amount",    "HEADER",         "CIF",                     data_type="currency"),
    "freight":                FieldMeta("freight",         "HEADER",         "FREIGHT",                 data_type="currency"),
    "bruto":                  FieldMeta("total_gross_weight","HEADER",      "BRUTO",                   data_type="number"),
    "netto":                  FieldMeta("total_net_weight", "HEADER",        "NETTO",                   data_type="number"),
    "ndpbm":                  FieldMeta("ndpbm",            "HEADER",         "NDPBM",                   default="2640.37", data_type="currency"),
    "kode_asuransi":          FieldMeta("asuransi",        "HEADER",        "KODE ASURANSI",           default="DN"),
    "asuransi":               FieldMeta("asuransi",         "HEADER",        "ASURANSI",                default="0.0", data_type="currency"),
    "kota_pernyataan":        FieldMeta("kota_pernyataan", "HEADER",       "KOTA PERNYATAAN",         default="CIKARANG"),
    "nama_pernyataan":        FieldMeta("nama_pernyataan", "HEADER",       "NAMA PERNYATAAN",         default="ADE LENY"),
    "jabatan_pernyataan":     FieldMeta("jabatan_pernyataan","HEADER",     "JABATAN PERNYATAAN",      default="MANAGER"),
    "kode_guna_barang":       FieldMeta("guna_barang",     "HEADER",        "KODE GUNA BARANG",        default="KMD"),
    "kode_asal_barang":       FieldMeta("country_of_origin","HEADER",       "KODE ASAL BARANG",        default="1"),
    "flag_proporsional_netto":FieldMeta("prop_netto",      "HEADER",        "FLAG PROPORSIONAL NETTO", default="T"),
    # ENTITAS
    "entitas_nomor_aju":      FieldMeta("shipment_id",     "ENTITAS",       "NOMOR AJU"),
    "entitas_seri":          FieldMeta("seri_entitas",     "ENTITAS",       "SERI"),
    "entitas_kode":          FieldMeta("kode_entitas",     "ENTITAS",       "KODE ENTITAS"),
    "entitas_nama":          FieldMeta("nama_entitas",     "ENTITAS",       "NAMA ENTITAS"),
    "entitas_alamat":        FieldMeta("alamat_entitas",   "ENTITAS",       "ALAMAT ENTITAS"),
    "entitas_negara":        FieldMeta("negara_entitas",   "ENTITAS",       "KODE NEGARA"),
    "entitas_nomor_identitas":FieldMeta("npwp",            "ENTITAS",       "NOMOR IDENTITAS"),
    "entitas_nib":           FieldMeta("nib",              "ENTITAS",       "NIB ENTITAS"),
    "entitas_api":           FieldMeta("kode_api",         "ENTITAS",       "KODE JENIS API"),
    # DOKUMEN
    "dokumen_nomor_aju":     FieldMeta("shipment_id",     "DOKUMEN",       "NOMOR AJU"),
    "dokumen_seri":         FieldMeta("seri_dokumen",     "DOKUMEN",       "SERI"),
    "dokumen_kode":         FieldMeta("kode_dokumen",     "DOKUMEN",       "KODE DOKUMEN"),
    "dokumen_nomor":        FieldMeta("nomor_dokumen",    "DOKUMEN",       "NOMOR DOKUMEN"),
    "dokumen_tanggal":      FieldMeta("tanggal_dokumen",  "DOKUMEN",       "TANGGAL DOKUMEN"),
    # PENGANGKUT
    "angkut_nomor_aju":      FieldMeta("shipment_id",     "PENGANGKUT",    "NOMOR AJU"),
    "angkut_seri":          FieldMeta("seri_angkut",     "PENGANGKUT",    "SERI"),
    "angkut_cara":          FieldMeta("cara_angkut",     "PENGANGKUT",    "KODE CARA ANGKUT",       default="1"),
    "angkut_nama":          FieldMeta("vessel_name",     "PENGANGKUT",    "NAMA PENGANGKUT"),
    "angkut_nomor":        FieldMeta("voyage_number",   "PENGANGKUT",    "NOMOR PENGANGKUT"),
    # KEMASAN
    "kemasan_nomor_aju":     FieldMeta("shipment_id",     "KEMASAN",       "NOMOR AJU"),
    "kemasan_seri":         FieldMeta("seri_kemasan",    "KEMASAN",       "SERI"),
    "kemasan_kode":         FieldMeta("packaging_type",  "KEMASAN",       "KODE KEMASAN"),
    "kemasan_jumlah":       FieldMeta("number_of_packages","KEMASAN",     "JUMLAH KEMASAN",         data_type="number"),
    # KONTAINER
    "kontainer_nomor_aju":   FieldMeta("shipment_id",     "KONTAINER",     "NOMOR AJU"),
    "kontainer_seri":       FieldMeta("seri_kontainer",  "KONTAINER",     "SERI"),
    "kontainer_nomor":      FieldMeta("container_numbers","KONTAINER",     "NOMOR KONTINER"),
    "kontainer_ukuran":     FieldMeta("container_size",   "KONTAINER",     "KODE UKURAN KONTAINER",   default="40"),
    "kontainer_jenis":      FieldMeta("container_type",  "KONTAINER",     "KODE JENIS KONTAINER",    default="8"),
    "kontainer_tipe":       FieldMeta("container_tipe",  "KONTAINER",     "KODE TIPE KONTAINER",     default="1"),
    "kontainer_segel":      FieldMeta("seal_numbers",    "KONTAINER",     "NOMOR SEGEL"),
    # KOMPONENBIAYA
    "biaya_nomor_aju":      FieldMeta("shipment_id",     "KOMPONENBIAYA", "NOMOR AJU"),
    "biaya_jenis":         FieldMeta("jenis_nilai",     "KOMPONENBIAYA", "JENIS NILAI",            default="1"),
    "biaya_invoice":       FieldMeta("total_amount",    "KOMPONENBIAYA", "HARGA INVOICE",          data_type="currency"),
    "biaya_transport":     FieldMeta("freight",         "KOMPONENBIAYA", "BIAYA TRANSPORTASI",     data_type="currency"),
    # BARANG
    "barang_nomor_aju":     FieldMeta("shipment_id",     "BARANG",        "NOMOR AJU"),
    "barang_seri":         FieldMeta("seri_barang",     "BARANG",        "SERI BARANG"),
    "barang_hs":           FieldMeta("item_hs_code",    "BARANG",        "HS"),
    "barang_kode":         FieldMeta("item_code",       "BARANG",        "KODE BARANG"),
    "barang_uraian":       FieldMeta("item_description","BARANG",        "URAIAN"),
    "barang_merek":        FieldMeta("item_brand",      "BARANG",        "MEREK",                   default="TANPA MEREK"),
    "barang_tipe":         FieldMeta("item_type",       "BARANG",        "TIPE",                    default="TANPA TIPE"),
    "barang_ukuran":       FieldMeta("item_dimensions", "BARANG",        "UKURAN"),
    "barang_spesifikasi":  FieldMeta("item_spesifikasi","BARANG",       "SPESIFIKASI LAIN",        default="-"),
    "barang_satuan":       FieldMeta("item_unit",       "BARANG",        "KODE SATUAN"),
    "barang_jumlah_satuan":FieldMeta("item_quantity",   "BARANG",        "JUMLAH SATUAN",          data_type="number"),
    "barang_kemasan_kode": FieldMeta("item_packaging",  "BARANG",        "KODE KEMASAN",           default="CT"),
    "barang_jumlah_kemasan":FieldMeta("item_cartons",   "BARANG",        "JUMLAH KEMASAN",         data_type="number"),
    "barang_netto":        FieldMeta("item_net_weight", "BARANG",        "NETTO",                  data_type="number"),
    "barang_bruto":        FieldMeta("item_gross_weight","BARANG",       "BRUTO",                  data_type="number",  default="0.0"),
    "barang_fob":          FieldMeta("item_amount",      "BARANG",        "FOB",                    data_type="currency"),
    "barang_cif":          FieldMeta("item_amount",      "BARANG",        "CIF",                    data_type="currency"),
    "barang_cif_rupiah":   FieldMeta("item_cif_rupiah", "BARANG",        "CIF RUPIAH",             data_type="currency"),
    "barang_ndpbm":        FieldMeta("ndpbm",           "BARANG",        "NDPBM",                  data_type="currency"),
    "barang_harga_satuan": FieldMeta("item_unit_price", "BARANG",        "HARGA SATUAN",           data_type="currency"),
    "barang_guna":         FieldMeta("guna_barang",     "BARANG",        "KODE GUNA BARANG",       default="KMD"),
    "barang_asal":         FieldMeta("country_of_origin","BARANG",        "KODE ASAL BARANG",       default="1"),
    "barang_negara_asal":  FieldMeta("country_of_origin","BARANG",        "KODE NEGARA ASAL"),
    "barang_lartas":       FieldMeta("lartas",          "BARANG",        "PERNYATAAN LARTAS",      default="T"),
    "barang_4tahun":       FieldMeta("flag_4tahun",     "BARANG",        "FLAG 4 TAHUN",           default="T"),
    "barang_kondisi":      FieldMeta("kondisi_barang",  "BARANG",        "KODE KONDISI BARANG",    default="1"),
    "barang_metode":       FieldMeta("metode_nilai",    "BARANG",        "METODE PENENTUAN NILAI", default="Metode 1"),
    "barang_statement":    FieldMeta("statement_harga","BARANG",         "STATEMENT PERBEDAAN HARGA", default="T"),
    # PUNGUTAN
    "pungutan_nomor_aju":   FieldMeta("shipment_id",     "PUNGUTAN",      "NOMOR AJU"),
    "pungutan_fasilitas":   FieldMeta("fasilitas_tarif", "PUNGUTAN",      "KODE FASILITAS TARIF",   default="1"),
    "pungutan_jenis":       FieldMeta("jenis_pungutan",  "PUNGUTAN",      "KODE JENIS PUNGUTAN",    default="PPN"),
    # VERSI
    "versi_nomor_aju":      FieldMeta("shipment_id",     "VERSI",         "NOMOR AJU"),
    "versi_value":          FieldMeta("versi",            "VERSI",         "VERSION",                 default="1.3"),
}


# REVERSE MAPPING

def get_sheet_fields(sheet: str) -> List[Tuple[str, FieldMeta]]:
    return [
        (key, meta) for key, meta in FIELD_METADATA.items()
        if meta.sheet == sheet
    ]


def get_entity_fields(entity_name: str) -> List[Tuple[str, FieldMeta]]:
    return [
        (key, meta) for key, meta in FIELD_METADATA.items()
        if meta.entity_name == entity_name
    ]


def get_sheet_names() -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for meta in FIELD_METADATA.values():
        if meta.sheet not in seen:
            seen.add(meta.sheet)
            result.append(meta.sheet)
    return result


def get_required_fields() -> List[str]:
    return [k for k, m in FIELD_METADATA.items() if m.required]


# VALIDATION RULES

HS_CODE_REGEX = r"^\d{8,13}$"
DATE_REGEX = r"^\d{4}-\d{2}-\d{2}$"
PORT_CODE_REGEX = r"^[A-Z]{5}$"
COUNTRY_CODE_REGEX = r"^[A-Z]{2}$"
CONTAINER_REGEX = r"^[A-Z]{4}\d{7}$"
WEIGHT_REGEX = r"^\d+\.?\d*$"
AMOUNT_REGEX = r"^\d+\.?\d*$"

VALIDATION_RULES: Dict[str, str] = {
    "barang_hs":           HS_CODE_REGEX,
    "dokumen_tanggal":     DATE_REGEX,
    "kode_pelabuhan_muat":PORT_CODE_REGEX,
    "kode_pelabuhan_bongkar": PORT_CODE_REGEX,
    "kontainer_nomor":    CONTAINER_REGEX,
    "barang_netto":        WEIGHT_REGEX,
    "barang_bruto":        WEIGHT_REGEX,
    "barang_fob":          AMOUNT_REGEX,
    "barang_cif":          AMOUNT_REGEX,
}
