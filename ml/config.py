from pathlib import Path

# PROJECT ROOT
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DATASET_DIR = PROJECT_ROOT / "dataset"
MODEL_DIR = PROJECT_ROOT / "models"
OUTPUT_DIR = PROJECT_ROOT / "output"

# DOCUMENT TYPES
DOC_TYPE_CI = "CI"
DOC_TYPE_PL = "PL"
DOC_TYPE_BL = "BL"
DOC_TYPE_FE = "FE"
DOC_TYPES = [DOC_TYPE_CI, DOC_TYPE_PL, DOC_TYPE_BL, DOC_TYPE_FE]


class NERLabel(str):
    # NER label untuk CEISA entity.
    def __new__(cls, value, ceisa_sheet=None, ceisa_col=None, description=""):
        inst = super().__new__(cls, value)
        inst.ceisa_sheet = ceisa_sheet
        inst.ceisa_col = ceisa_col
        inst.description = description
        return inst


# CI ENTITY TYPES
CI_ENTITIES = [
    # Header
    "invoice_number",
    "invoice_date",
    "seller_name",
    "seller_address",
    "buyer_name",
    "buyer_address",
    "currency",
    "incoterms",
    "country_of_origin",
    "country_of_destination",
    "item_description",
    "item_code",
    "item_quantity",
    "item_unit",
    "item_unit_price",
    "item_amount",
    "item_hs_code",
    "item_dimensions",
    "total_amount",
    "total_quantity",
    "total_net_weight",
    "total_gross_weight",
    "payment_terms",
    "port_of_loading",
    "port_of_discharge",
    "bl_number",
    "container_number",
    "seal_number",
]

# PL ENTITY TYPES
PL_ENTITIES = [
    "item_code",
    "item_description",
    "item_quantity",
    "item_unit",
    "item_dimensions",
    "number_of_cartons",
    "cbm",
    "net_weight_per_item",
    "gross_weight_per_item",
    "total_net_weight",
    "total_gross_weight",
    "total_cartons",
    "total_cbm",
]

# BL ENTITY TYPES
BL_ENTITIES = [
    "bl_number",
    "bl_date",
    "shipper_name",
    "shipper_address",
    "consignee_name",
    "consignee_address",
    "notify_party_name",
    "notify_party_address",
    "vessel_name",
    "voyage_number",
    "port_of_loading",
    "port_of_discharge",
    "place_of_receipt",
    "place_of_delivery",
    "container_number",
    "seal_number",
    "number_of_packages",
    "gross_weight",
    "measurement",
    "kind_of_packages",
    "description_of_goods",
    "freight_term",
    "issue_date",
    "country_of_origin",
]

ALL_ENTITIES = list(set(CI_ENTITIES + PL_ENTITIES + BL_ENTITIES))


# CEISA SCHEMA MAPPING
ENTITY_TO_EXCEL: dict = {
    "NOMOR AJU":                    {"sheet": "HEADER",        "col": "NOMOR AJU"},
    "KODE VALUTA":                  {"sheet": "HEADER",        "col": "KODE VALUTA"},
    "KODE INCOTERM":                {"sheet": "HEADER",        "col": "KODE INCOTERM"},
    "ASURANSI":                     {"sheet": "HEADER",        "col": "ASURANSI"},
    "FREIGHT":                      {"sheet": "HEADER",        "col": "FREIGHT"},
    "FOB":                          {"sheet": "HEADER",        "col": "FOB"},
    "CIF":                          {"sheet": "HEADER",        "col": "CIF"},
    "NILAI BARANG":                 {"sheet": "HEADER",        "col": "NILAI BARANG"},
    "KOTA PERNYATAAN":              {"sheet": "HEADER",        "col": "KOTA PERNYATAAN"},
    "TANGGAL PERNYATAAN":           {"sheet": "HEADER",        "col": "TANGGAL PERNYATAAN"},
    "NAMA PERNYATAAN":              {"sheet": "HEADER",        "col": "NAMA PERNYATAAN"},
    "JABATAN PERNYATAAN":           {"sheet": "HEADER",        "col": "JABATAN PERNYATAAN"},
    "BRUTO":                        {"sheet": "HEADER",        "col": "BRUTO"},
    "NETTO":                        {"sheet": "HEADER",        "col": "NETTO"},
    "KODE PELABUHAN MUAT":         {"sheet": "HEADER",        "col": "KODE PELABUHAN MUAT"},
    "KODE PELABUHAN BONGKAR":      {"sheet": "HEADER",        "col": "KODE PELABUHAN BONGKAR"},
    "KODE NEGARA TUJUAN":           {"sheet": "HEADER",        "col": "KODE NEGARA TUJUAN"},
    "TANGGAL TIBA":                 {"sheet": "HEADER",        "col": "TANGGAL TIBA"},
    "TANGGAL BERANGKAT":            {"sheet": "HEADER",        "col": "TANGGAL BERANGKAT"},
    "KODE GUNA BARANG":             {"sheet": "HEADER",        "col": "KODE GUNA BARANG"},
    "KODE ASAL BARANG":             {"sheet": "HEADER",        "col": "KODE ASAL BARANG"},

    "SELLER/NAMA ENTITAS":          {"sheet": "ENTITAS",      "col": "NAMA ENTITAS"},
    "SELLER/ALAMAT ENTITAS":        {"sheet": "ENTITAS",      "col": "ALAMAT ENTITAS"},
    "SELLER/KODE NEGARA":           {"sheet": "ENTITAS",      "col": "KODE NEGARA"},
    "BUYER/NAMA ENTITAS":           {"sheet": "ENTITAS",      "col": "NAMA ENTITAS"},
    "BUYER/ALAMAT ENTITAS":         {"sheet": "ENTITAS",      "col": "ALAMAT ENTITAS"},
    "BUYER/KODE NEGARA":            {"sheet": "ENTITAS",      "col": "KODE NEGARA"},
    "SHIPPER/NAMA ENTITAS":         {"sheet": "ENTITAS",      "col": "NAMA ENTITAS"},
    "SHIPPER/ALAMAT ENTITAS":       {"sheet": "ENTITAS",      "col": "ALAMAT ENTITAS"},
    "SHIPPER/KODE NEGARA":          {"sheet": "ENTITAS",      "col": "KODE NEGARA"},
    "CONSIGNEE/NAMA ENTITAS":       {"sheet": "ENTITAS",      "col": "NAMA ENTITAS"},
    "CONSIGNEE/ALAMAT ENTITAS":     {"sheet": "ENTITAS",      "col": "ALAMAT ENTITAS"},
    "CONSIGNEE/KODE NEGARA":        {"sheet": "ENTITAS",      "col": "KODE NEGARA"},
    "NOTIFY/NAMA ENTITAS":          {"sheet": "ENTITAS",      "col": "NAMA ENTITAS"},
    "NOTIFY/ALAMAT ENTITAS":        {"sheet": "ENTITAS",      "col": "ALAMAT ENTITAS"},
    "NOTIFY/KODE NEGARA":           {"sheet": "ENTITAS",      "col": "KODE NEGARA"},

    "NOMOR DOKUMEN CI":             {"sheet": "DOKUMEN",      "col": "NOMOR DOKUMEN"},
    "TANGGAL DOKUMEN CI":           {"sheet": "DOKUMEN",      "col": "TANGGAL DOKUMEN"},
    "NOMOR DOKUMEN BL":             {"sheet": "DOKUMEN",      "col": "NOMOR DOKUMEN"},
    "TANGGAL DOKUMEN BL":           {"sheet": "DOKUMEN",      "col": "TANGGAL DOKUMEN"},

    "NAMA PENGANGKUT":              {"sheet": "PENGANGKUT",   "col": "NAMA PENGANGKUT"},
    "NOMOR PENGANGKUT":             {"sheet": "PENGANGKUT",   "col": "NOMOR PENGANGKUT"},
    "KODE BENDERA":                 {"sheet": "PENGANGKUT",   "col": "KODE BENDERA"},
    "VESSEL NAME":                  {"sheet": "PENGANGKUT",   "col": "NAMA PENGANGKUT"},
    "VOYAGE NUMBER":                {"sheet": "PENGANGKUT",   "col": "NOMOR PENGANGKUT"},

    "JUMLAH KEMASAN":               {"sheet": "KEMASAN",      "col": "JUMLAH KEMASAN"},
    "KODE KEMASAN":                 {"sheet": "KEMASAN",      "col": "KODE KEMASAN"},
    "TOTAL CARTONS":                {"sheet": "KEMASAN",      "col": "JUMLAH KEMASAN"},

    "NOMOR KONTINER":               {"sheet": "KONTAINER",    "col": "NOMOR KONTINER"},
    "CONTAINER NUMBER":             {"sheet": "KONTAINER",    "col": "NOMOR KONTINER"},
    "SEAL NUMBER":                  {"sheet": "KONTAINER",    "col": "NOMOR SEGEL"},

    "HS":                           {"sheet": "BARANG",        "col": "HS"},
    "KODE BARANG":                  {"sheet": "BARANG",        "col": "KODE BARANG"},
    "URAIAN":                       {"sheet": "BARANG",        "col": "URAIAN"},
    "MEREK":                        {"sheet": "BARANG",        "col": "MEREK"},
    "TIPE":                         {"sheet": "BARANG",        "col": "TIPE"},
    "UKURAN":                       {"sheet": "BARANG",        "col": "UKURAN"},
    "KODE SATUAN":                  {"sheet": "BARANG",        "col": "KODE SATUAN"},
    "JUMLAH SATUAN":                {"sheet": "BARANG",        "col": "JUMLAH SATUAN"},
    "NETTO_ITEM":                   {"sheet": "BARANG",        "col": "NETTO"},
    "BRUTO_ITEM":                   {"sheet": "BARANG",        "col": "BRUTO"},
    "KODE NEGARA ASAL":             {"sheet": "BARANG",        "col": "KODE NEGARA ASAL"},
    "KODE ASAL BARANG":             {"sheet": "BARANG",        "col": "KODE ASAL BARANG"},
    "KODE GUNA BARANG":             {"sheet": "BARANG",        "col": "KODE GUNA BARANG"},
    "CIF_ITEM":                     {"sheet": "BARANG",        "col": "CIF"},
    "FOB_ITEM":                     {"sheet": "BARANG",        "col": "FOB"},
    "HARGA SATUAN":                 {"sheet": "BARANG",        "col": "HARGA SATUAN"},

    "HARGA INVOICE":                {"sheet": "KOMPONENBIAYA","col": "HARGA INVOICE"},
    "BIAYA TRANSPORTASI":           {"sheet": "KOMPONENBIAYA","col": "BIAYA TRANSPORTASI"},
    "ASURANSI_ITEM":                {"sheet": "KOMPONENBIAYA","col": "ASURANSI"},
    "FREIGHT_ITEM":                 {"sheet": "KOMPONENBIAYA","col": "FREIGHT"},
}


# EXCEL COLUMN DEFINITIONS
EXCEL_COLUMNS: dict = {
    "HEADER": [
        "NOMOR AJU", "KODE DOKUMEN", "KODE KANTOR", "KODE KANTOR BONGKAR",
        "KODE KANTOR PERIKSA", "KODE KANTOR TUJUAN", "KODE KANTOR EKSPOR",
        "KODE JENIS IMPOR", "KODE JENIS EKSPOR", "KODE JENIS TPB", "KODE JENIS PLB",
        "KODE JENIS PROSEDUR", "KODE TUJUAN PEMASUKAN", "KODE TUJUAN PENGIRIMAN",
        "KODE TUJUAN TPB", "KODE CARA DAGANG", "KODE CARA BAYAR", "KODE CARA BAYAR LAINNYA",
        "KODE GUDANG ASAL", "KODE GUDANG TUJUAN", "KODE JENIS KIRIM", "KODE JENIS PENGIRIMAN",
        "KODE KATEGORI EKSPOR", "KODE KATEGORI MASUK FTZ", "KODE KATEGORI KELUAR FTZ",
        "KODE KATEGORI BARANG FTZ", "KODE LOKASI", "KODE LOKASI BAYAR", "LOKASI ASAL",
        "LOKASI TUJUAN", "KODE DAERAH ASAL", "KODE GUDANG ASAL", "KODE GUDANG TUJUAN",
        "KODE NEGARA TUJUAN", "KODE TUTUP PU", "NOMOR BC11", "TANGGAL BC11",
        "NOMOR POS", "NOMOR SUB POS", "KODE PELABUHAN BONGKAR", "KODE PELABUHAN MUAT",
        "KODE PELABUHAN MUAT AKHIR", "KODE PELABUHAN TRANSIT", "KODE PELABUHAN TUJUAN",
        "KODE PELABUHAN EKSPOR", "KODE TPS", "TANGGAL BERANGKAT", "TANGGAL EKSPOR",
        "TANGGAL MASUK", "TANGGAL MUAT", "TANGGAL TIBA", "TANGGAL PERIKSA",
        "TEMPAT STUFFING", "TANGGAL STUFFING", "KODE TANDA PENGAMAN", "JUMLAH TANDA PENGAMAN",
        "FLAG CURAH", "FLAG SDA", "FLAG VD", "FLAG AP BK", "FLAG MIGAS",
        "KODE ASURANSI", "ASURANSI", "NILAI BARANG", "NILAI INCOTERM", "NILAI MAKLON",
        "ASURANSI", "FREIGHT", "FOB", "BIAYA TAMBAHAN", "BIAYA PENGURANG",
        "VD", "CIF", "HARGA_PENYERAHAN", "NDPBM", "TOTAL DANA SAWIT",
        "DASAR PENGENAAN PAJAK", "NILAI JASA", "UANG MUKA", "BRUTO", "NETTO",
        "VOLUME", "KOTA PERNYATAAN", "TANGGAL PERNYATAAN", "NAMA PERNYATAAN",
        "JABATAN PERNYATAAN", "KODE VALUTA", "KODE INCOTERM", "KODE JASA KENA PAJAK",
        "NOMOR BUKTI BAYAR", "TANGGAL BUKTI BAYAR", "KODE JENIS NILAI", "KODE KANTOR MUAT",
        "NOMOR DAFTAR", "TANGGAL DAFTAR", "KODE ASAL BARANG FTZ", "KODE TUJUAN PENGELUARAN",
        "PPN PAJAK", "PPNBM PAJAK", "TARIF PPN PAJAK", "TARIF PPNBM PAJAK",
        "BARANG TIDAK BERWUJUD", "KODE JENIS PENGELUARAN", "BARANG KIRIMAN",
        "FLAG KONSOL", "KODE JENIS PENGANGKUTAN", "FLAG PROPORSIONAL NETTO",
    ],
    "ENTITAS": [
        "NOMOR AJU", "SERI", "KODE ENTITAS", "KODE JENIS IDENTITAS",
        "NOMOR IDENTITAS", "NAMA ENTITAS", "ALAMAT ENTITAS", "NIB ENTITAS",
        "KODE JENIS API", "KODE STATUS", "NOMOR IJIN ENTITAS", "TANGGAL IJIN ENTITAS",
        "KODE NEGARA", "NIPER ENTITAS", "KODE KATEGORI KONSOLIDATOR", "KODE AFILIASI",
    ],
    "DOKUMEN": [
        "NOMOR AJU", "SERI", "KODE DOKUMEN", "NOMOR DOKUMEN", "TANGGAL DOKUMEN",
        "KODE FASILITAS", "KODE IJIN",
    ],
    "PENGANGKUT": [
        "NOMOR AJU", "SERI", "KODE CARA ANGKUT", "NAMA PENGANGKUT", "NOMOR PENGANGKUT",
        "KODE BENDERA", "CALL SIGN", "FLAG ANGKUT PLB", "CARA PENGANGKUTAN LAINNYA",
    ],
    "KEMASAN": [
        "NOMOR AJU", "SERI", "KODE KEMASAN", "JUMLAH KEMASAN", "MEREK", "NOMOR SEGEL",
    ],
    "KONTAINER": [
        "NOMOR AJU", "SERI", "NOMOR KONTINER", "KODE UKURAN KONTAINER",
        "KODE JENIS KONTAINER", "KODE TIPE KONTAINER", "NOMOR SEGEL",
    ],
    "KOMPONENBIAYA": [
        "NOMOR AJU", "JENIS NILAI", "HARGA INVOICE", "PEMBAYARAN TIDAK LANGSUNG",
        "DISKON", "KOMISI PENJUALAN", "BIAYA PENGEMASAN", "BIAYA PENGEPAKAN",
        "ASSIST", "ROYALTI", "PROCEEDS", "BIAYA TRANSPORTASI", "BIAYA PEMUATAN",
        "ASURANSI", "GARANSI", "BIAYA KEPENTINGAN SENDIRI", "BIAYA PASCA IMPOR",
        "BIAYA PAJAK INTERNAL", "BUNGA", "DEVIDEN",
    ],
    "BARANG": [
        "NOMOR AJU", "SERI BARANG", "HS", "KODE BARANG", "URAIAN", "MEREK", "TIPE",
        "UKURAN", "SPESIFIKASI LAIN", "KODE SATUAN", "JUMLAH SATUAN", "KODE KEMASAN",
        "JUMLAH KEMASAN", "KODE DOKUMEN ASAL", "KODE KANTOR ASAL", "NOMOR DAFTAR ASAL",
        "TANGGAL DAFTAR ASAL", "NOMOR AJU ASAL", "SERI BARANG ASAL", "NETTO", "BRUTO",
        "VOLUME", "SALDO AWAL", "SALDO AKHIR", "JUMLAH REALISASI", "CIF", "CIF RUPIAH",
        "NDPBM", "FOB", "ASURANSI", "FREIGHT", "NILAI TAMBAH", "DISKON", "HARGA PENYERAHAN",
        "HARGA PEROLEHAN", "HARGA SATUAN", "HARGA EKSPOR", "HARGA PATOKAN", "NILAI BARANG",
        "NILAI JASA", "NILAI DANA SAWIT", "NILAI DEVISA", "PERSENTASE IMPOR",
        "KODE ASAL BARANG", "KODE DAERAH ASAL", "KODE GUNA BARANG", "KODE JENIS NILAI",
        "JATUH TEMPO ROYALTI", "KODE KATEGORI BARANG", "KODE KONDISI BARANG",
        "KODE NEGARA ASAL", "KODE PERHITUNGAN", "PERNYATAAN LARTAS", "FLAG 4 TAHUN",
        "SERI IJIN", "TAHUN PEMBUATAN", "KAPASITAS SILINDER", "KODE BKC",
        "KODE KOMODITI BKC", "KODE SUB KOMODITI BKC", "FLAG TIS", "ISI PER KEMASAN",
        "JUMLAH DILEKATKAN", "JUMLAH PITA CUKAI", "HJE CUKAI", "TARIF CUKAI",
        "KODE JENIS EKSPOR", "METODE PENENTUAN NILAI", "ALASAN METODE PENENTUAN NILAI",
        "STATEMENT PERBEDAAN HARGA",
    ],
    "PUNGUTAN": [
        "NOMOR AJU", "KODE FASILITAS TARIF", "KODE JENIS PUNGUTAN",
        "NILAI PUNGUTAN", "NPWP BILLING",
    ],
    "VERSI": ["VERSI"],
    "RESPON": ["NOMOR AJU", "KODE RESPON", "NOMOR RESPON", "TANGGAL RESPON"],
}

EXCEL_SHEET_ORDER = [
    "HEADER", "ENTITAS", "DOKUMEN", "PENGANGKUT", "KEMASAN", "KONTAINER",
    "KOMPONENBIAYA", "BARANG", "BARANGTARIF", "BARANGDOKUMEN", "BARANGENTITAS",
    "BARANGSPEKKHUSUS", "BARANGVD", "BAHANBAKU", "BAHANBAKUTARIF", "BAHANBAKUDOKUMEN",
    "PUNGUTAN", "JAMINAN", "BANKDEVISA", "VERSI", "RESPON",
]

# CEISA 4.0 Excel column definitions.
EXCEL_COLUMNS: dict = {
    "HEADER": [
        "NOMOR AJU", "KODE KANTOR", "KODE DOKUMEN", "KODE JENIS IMPOR",
        "KODE JENIS PROSEDUR", "KODE CARA BAYAR", "KODE TUTUP PU",
        "KODE VALUTA", "KODE INCOTERM", "FOB", "CIF", "FREIGHT",
        "BRUTO", "NETTO", "NDPBM", "KODE ASURANSI", "ASURANSI",
        "KODE PELABUHAN MUAT", "KODE PELABUHAN BONGKAR",
        "KODE PELABUHAN TRANSIT", "KODE PELABUHAN TUJUAN",
        "KOTA PERNYATAAN", "NAMA PERNYATAAN", "JABATAN PERNYATAAN",
        "KODE GUNA BARANG", "KODE ASAL BARANG", "FLAG PROPORSIONAL NETTO",
    ],
    "ENTITAS": [
        "NOMOR AJU", "SERI", "KODE ENTITAS", "NAMA ENTITAS",
        "ALAMAT ENTITAS", "KODE NEGARA", "NOMOR IDENTITAS",
        "NIB ENTITAS", "KODE JENIS API", "KODE STATUS",
    ],
    "DOKUMEN": [
        "NOMOR AJU", "SERI", "KODE DOKUMEN", "NOMOR DOKUMEN",
        "TANGGAL DOKUMEN", "SERI BRAND", "KODE ASAL DOKUMEN",
    ],
    "PENGANGKUT": [
        "NOMOR AJU", "SERI", "KODE CARA ANGKUT",
        "NAMA PENGANGKUT", "NOMOR PENGANGKUT",
        "KODE FLAG", "NOMOR VOYAGE", "KODE BENDERA",
    ],
    "KEMASAN": [
        "NOMOR AJU", "SERI", "KODE KEMASAN", "JUMLAH KEMASAN",
        "MEREK KEMASAN", "KODE GUNA BARANG",
    ],
    "KONTAINER": [
        "NOMOR AJU", "SERI", "NOMOR KONTINER",
        "KODE UKURAN KONTAINER", "KODE JENIS KONTAINER",
        "KODE TIPE KONTAINER", "NOMOR SEGEL",
    ],
    "KOMPONENBIAYA": [
        "NOMOR AJU", "JENIS NILAI", "HARGA INVOICE",
        "BIAYA TRANSPORTASI", "BIAYA ASURANSI", "BIAYA KRIMER",
        "BIAYA LAIN", "CIF", "CIF RUPIAH", "NDPBM",
    ],
    "BARANG": [
        "NOMOR AJU", "SERI BARANG", "HS", "KODE BARANG",
        "URAIAN", "MEREK", "TIPE", "UKURAN", "SPESIFIKASI LAIN",
        "KODE SATUAN", "JUMLAH SATUAN", "KODE KEMASAN", "JUMLAH KEMASAN",
        "NETTO", "BRUTO", "FOB", "CIF", "CIF RUPIAH", "NDPBM",
        "HARGA SATUAN", "KODE GUNA BARANG", "KODE ASAL BARANG",
        "KODE NEGARA ASAL", "PERNYATAAN LARTAS", "FLAG 4 TAHUN",
        "KODE KONDISI BARANG", "METODE PENENTUAN NILAI",
        "STATEMENT PERBEDAAN HARGA",
    ],
    "PUNGUTAN": [
        "NOMOR AJU", "KODE FASILITAS TARIF", "KODE JENIS PUNGUTAN",
        "JUMLAH PUNGUTAN", "KODE TARIF",
    ],
    "VERSI": ["VERSION"],
    "RESPON": ["NOMOR AJU", "TIMESTAMP", "KODE RESPON", "DESKRIPSI"],

    "BARANGTARIF": [
        "NOMOR AJU", "SERI BARANG", "KODE PUNGUTAN", "KODE TARIF", "TARIF",
        "KODE FASILITAS", "TARIF FASILITAS", "NILAI BAYAR", "NILAI FASILITAS",
        "NILAI SUDAH DILUNASI", "KODE SATUAN", "JUMLAH SATUAN",
        "FLAG BMT SEMENTARA", "KODE KOMODITI CUKAI", "KODE SUB KOMODITI CUKAI",
        "FLAG TIS", "FLAG PELEKATAN", "KODE KEMASAN", "JUMLAH KEMASAN",
    ],
    "BARANGDOKUMEN": ["NOMOR AJU", "SERI BARANG", "SERI DOKUMEN", "KODE DOKUMEN"],
    "BARANGENTITAS": ["NOMOR AJU", "SERI BARANG", "SERI ENTITAS", "KODE ENTITAS"],
    "BARANGSPEKKHUSUS": ["NOMOR AJU", "SERI BARANG", "KODE SPEK", "URAIAN SPEK"],
    "BARANGVD": ["NOMOR AJU", "SERI BARANG", "SERI VD", "KODE VD"],
    "BAHANBAKU": ["NOMOR AJU", "SERI BB", "KODE BB", "HS BB", "URAIAN BB", "NETTO BB"],
    "BAHANBAKUTARIF": ["NOMOR AJU", "SERI BB", "KODE TARIF", "TARIF"],
    "BAHANBAKUDOKUMEN": ["NOMOR AJU", "SERI BB", "SERI DOKUMEN"],
    "JAMINAN": ["NOMOR AJU", "SERI JAMINAN", "KODE JENIS JAMINAN", "NOMINAL"],
    "BANKDEVISA": ["NOMOR AJU", "SERI BANK", "KODE BANK", "NAMA BANK"],
}


# POSTPROCESSING CONFIG
POSTPROC_CONFIG: dict = {
    # Format tanggal
    "date_formats": [
        "%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y",
        "%Y-%m-%d", "%d.%m.%Y", "%b %d, %Y", "%Y%m%d",
    ],
    "default_date_format": "%Y-%m-%d",

    # Kode mata uang
    "currency_codes": ["USD", "CNY", "EUR", "GBP", "JPY", "SGD", "IDR", "AUD", "KRW"],

    # Kode incoterms
    "incoterms_codes": ["FOB", "CIF", "CFR", "EXW", "DAP", "DDP", "FCA", "CPT", "CIP", "FAS", "DAT"],

    # Kode pelabuhan (nama -> LOCODE)
    "port_codes": {
        "SHANGHAI": "CNSHA", "NINGBO": "CNNBO", "YANTIAN": "CNYTN",
        "GUANGZHOU": "CNCAN", "HONGKONG": "HKHKG", "SINGAPORE": "SGSIN",
        "NANSHA": "CNNSA", "KAOHSIUNG": "TWKHH", "BUSAN": "KRPUS",
        "QINGDAO": "CNTAO", "TIANJIN": "CNTJN", "DALIAN": "CNDLC",
        "XIAMEN": "CNXMN", "YANTIAN": "CNYTN", "SHENZHEN": "CNSZN",
        "JAKARTA": "IDTPP", "SEMARANG": "IDSUB", "SURABAYA": "IDSUB",
        "BELAWAN": "IDBLW", "TANJUNG PRIOK": "IDTPP",
        "CIKARANG": "IDCGK",
    },

    # Kode negara (nama -> ISO 2-letter)
    "country_codes": {
        "CHINA": "CN", "INDONESIA": "ID", "SINGAPORE": "SG",
        "MALAYSIA": "MY", "THAILAND": "TH", "JAPAN": "JP",
        "KOREA": "KR", "HONG KONG": "HK", "TAIWAN": "TW",
        "VIETNAM": "VN", "INDIA": "IN", "USA": "US", "U.S.A.": "US",
        "GERMANY": "DE", "UNITED KINGDOM": "GB", "AUSTRALIA": "AU",
    },

    # Kode satuan (nama -> kode bea cukai)
    "unit_codes": {
        "PCS": "PCE", "PC": "PCE", "PIECES": "PCE", "PIECE": "PCE",
        "SET": "SET", "SETS": "SET",
        "MTR": "MTR", "METER": "MTR", "METERS": "MTR",
        "KG": "KGM", "KILOGRAM": "KGM", "KILOGRAMS": "KGM",
        "MT": "TNE", "TON": "TNE", "TONNE": "TNE",
        "CTN": "CT", "CARTON": "CT", "CARTONS": "CT",
        "PK": "PK", "PACK": "PK", "PACKAGE": "PK",
    },

    # Kode kemasan
    "packaging_codes": {
        "CTN": "CT", "CARTON": "CT", "CARTONS": "CT",
        "PK": "PK", "PACKAGE": "PK", "PALLET": "PLT",
        "CASE": "CS", "CRATE": "CR", "DRUM": "DM",
        "BAG": "BG", "BARREL": "BR", "BOX": "BX",
    },

    # Kode bendera kapal
    "vessel_flag_codes": {
        "SG": "SG", "SINGAPORE": "SG",
        "HK": "HK", "HONG KONG": "HK",
        "CN": "CN", "CHINA": "CN",
        "ID": "ID", "INDONESIA": "ID",
        "PA": "PA", "PANAMA": "PA",
        "LR": "LR", "LIBERIA": "LR",
        "MT": "MT", "MALTA": "MT",
        "BS": "BS", "BAHAMAS": "BS",
    },
}


# HYBRID EXTRACTION CONFIG
class ExtractionStrategy:
    """
    Definisikan layer mana yang menangani entity category mana.
    LAYOUT: party names, addresses, vessel names, ports, dates.
    PATTERN: item codes, HS codes, numeric values.
    """

    # Entity untuk LayoutXLM
    LAYOUT_ENTITIES = {
        "invoice_number", "invoice_date",
        "bl_number", "bl_date", "issue_date",
        "seller_name", "seller_address",
        "buyer_name", "buyer_address",
        "shipper_name", "shipper_address",
        "consignee_name", "consignee_address",
        "notify_party_name", "notify_party_address",
        "vessel_name", "voyage_number",
        "port_of_loading", "port_of_discharge",
        "place_of_receipt", "place_of_delivery",
        "currency", "incoterms",
        "freight_term",
        "country_of_origin", "country_of_destination",
        "description_of_goods",
        "kind_of_packages",
    }

    # Entity untuk Pattern
    PATTERN_ENTITIES = {
        "item_code", "item_description",
        "item_quantity", "item_unit",
        "item_unit_price", "item_amount",
        "item_hs_code", "item_dimensions",
        "total_amount", "total_quantity",
        "total_net_weight", "total_gross_weight",
        "number_of_cartons", "cbm",
        "net_weight_per_item", "gross_weight_per_item",
        "total_cartons", "total_cbm",
        "container_number", "seal_number",
        "number_of_packages",
        "measurement",
        "payment_terms",
    }

    @classmethod
    def which(cls, entity_type: str) -> str:
        if entity_type in cls.LAYOUT_ENTITIES:
            return "layout"
        if entity_type in cls.PATTERN_ENTITIES:
            return "pattern"
        return "pattern"


# NER MODEL SETTINGS
NER_CONFIG: dict = {
    "layoutxlm_model": "microsoft/layoutxlm-base",
    "gliner_model": "urchade/gliner_multi_v2.1",
    "max_length": 512,
    "labels": ALL_ENTITIES,
    "threshold": 0.3,
    "batch_size": 4,
    "use_gpu": True,
    "confidence_threshold": 0.0,
}

# TRAINING SETTINGS
TRAIN_CONFIG: dict = {
    "epochs": 20,
    "batch_size": 8,
    "learning_rate": 5e-5,
    "warmup_steps": 100,
    "weight_decay": 0.01,
    "max_steps": 1000,
    "eval_steps": 100,
    "save_steps": 200,
    "gradient_accumulation_steps": 2,
}

# OCR SETTINGS
OCR_CONFIG: dict = {
    "use_angle_cls": True,
    "lang": "en",
    "det_db_thresh": 0.3,
    "det_db_box_thresh": 0.5,
    "det_db_unclip_ratio": 1.6,
    "rec_batch_num": 16,
    "use_gpu": False,   # OCR CPU untuk hindari GPU contention
}
