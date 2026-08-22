# Zero-Touch Customs Engine

Aplikasi web untuk mengekstrak data dari dokumen customs Indonesia (CEISA 4.0). Unggah dokumen Commercial Invoice, Packing List, dan Bill of Lading untuk otomatis mengekstrak entitas dan menghasilkan paket declaration Excel.

## Cara Menjalankan

```bash
# Build dan jalankan aplikasi
docker compose up --build

# Buka di browser
open http://localhost:8000
```

## Fitur

- **Smart Upload**: Unggah dokumen CI, PL, dan/atau BL (PDF, PNG, JPG, JPEG, TIFF)
- **Ekstraksi Hybrid**: Kombinasi ML (LayoutLMv3) + Pattern-based extraction
- **Ekspor CEISA 4.0**: Menghasilkan paket declaration Excel lengkap
- **Kelola Declarations**: Simpan, lihat, kirim, dan hapus record shipment
- **CPU-Only**: Tidak memerlukan GPU untuk inferensi

## Struktur Proyek

```
src/
├── main.py                  # Entry point FastAPI
├── templates/                # Halaman HTML
│   ├── dashboard.html       # Halaman dashboard
│   ├── smart_upload.html   # Halaman upload dokumen
│   ├── declarations.html   # Kelola declarations
│   └── activity.html       # Log aktivitas
├── static/                  # Aset frontend
│   ├── style.css
│   └── images/
├── models/                  # Model database (SQLAlchemy)
├── routes/                  # Route API
├── services/                # Seed data
├── ceisa/                   # Integrasi CEISA 4.0
ml/
├── config.py               # Konfigurasi ML
├── src/
│   ├── ocr/               # PaddleOCR wrapper
│   ├── extraction/         # Ekstraksi entitas (HybridExtractor, Layout, Pattern)
│   ├── excel/             # Ekspor Excel CEISA 4.0
│   └── postprocessing/    # Normalisasi teks
└── models/
    └── layoutlmv3-v4/
        └── best_model/    # Bobot model (481MB)
.env                      # Konfigurasi environment
Dockerfile
docker-compose.yml
requirements.txt
```

## Model ML

Model LayoutLMv3 (481MB) belum termasuk di repository ini. Train model dengan command berikut:

```bash
python train.py --config ml/config.py --output ml/models/layoutlmv3-v4
```

## Arsitektur

```
Browser → FastAPI → HybridExtractor → ExcelExporter → Download Excel
             (src/)      (ml/)
                          │
                          ├── OCR (PaddleOCR)
                          ├── LayoutXLM (LayoutLMv3) ── fallback ──► Pattern-based
                          └── Merger → CEISA Excel
```

## Requirements

- Docker & Docker Compose
- ~2 GB disk (base) + ~500MB (dengan model)
- RAM 4+ GB direkomendasikan

## Endpoint API

### `POST /api/extract`
Unggah dokumen dan dapat hasil ekstraksi.

**Form fields:** `ci`, `pl`, `bl` (minimal satu diperlukan)

### `POST /api/shipments`
Simpan hasil ekstraksi ke database.

### `GET /api/shipments`
Daftar semua shipment.

### `GET /api/shipments/{id}`
Detail shipment.

### `POST /api/shipments/{id}/send`
Tandai shipment sebagai terkirim.

### `DELETE /api/shipments/{id}`
Hapus shipment.

## Variabel Environment

Salin `.env` dari template dan konfigurasi:

| Variabel | Deskripsi | Default |
|----------|------------|---------|
| `DATABASE_URL` | Koneksi PostgreSQL | `postgresql://postgres:postgres@db:5432/ocr_engine` |
| `POSTGRES_DB` | Nama database | `ocr_engine` |
| `POSTGRES_USER` | User database | `postgres` |
| `POSTGRES_PASSWORD` | Password database | `postgres` |
| `MODEL_PATH` | Path model LayoutLMv3 | `ml/models/layoutlmv3-v4/best_model` |
| `APP_PORT` | Port aplikasi | `8000` |

## Development

```bash
# Jalankan tanpa Docker (Python 3.11+)
pip install -r requirements.txt
cd src && python main.py
```
