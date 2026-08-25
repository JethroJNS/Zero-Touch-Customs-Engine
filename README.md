# Zero-Touch Customs Engine

Aplikasi web untuk mengekstrak data dari dokumen customs Indonesia (CEISA 4.0). Unggah dokumen Commercial Invoice, Packing List, dan Bill of Lading untuk otomatis mengekstrak entitas dan menghasilkan paket declaration Excel.

## Cara Menjalankan

```bash
# Build dan jalankan aplikasi
docker compose up --build

# Buka di browser
open http://localhost:8000

# Halaman:
# - Dashboard   → http://localhost:8000/
# - Smart Upload → http://localhost:8000/smart-upload
# - Declarations → http://localhost:8000/declarations
# - Activity    → http://localhost:8000/activity
```

## Fitur

- **Smart Upload**: Unggah dokumen CI, PL, dan/atau BL (PDF, PNG, JPG, JPEG, TIFF)
- **Ekstraksi Hybrid**: Kombinasi ML (LayoutLMv3) + Pattern-based extraction
- **Ekspor CEISA 4.0**: Menghasilkan paket declaration Excel lengkap
- **Kelola Declarations**: Simpan, lihat, kirim, dan hapus record shipment
- **Audit Log (Activity)**: Lacak semua aktivitas sistem secara real-time
- **Dashboard**: Overview data shipment, status CEISA, dan aktivitas operasional
- **CPU-Only**: Tidak memerlukan GPU untuk inferensi

## Struktur Proyek

```
website/
├── src/
│   ├── main.py               # Entry point FastAPI + semua endpoint
│   ├── dashboard.html        # Halaman dashboard
│   ├── smart_upload.html     # Halaman upload dokumen
│   ├── declarations.html     # Kelola declarations
│   ├── activity.html         # Audit log aktivitas
│   ├── training/             # Modul dataset untuk training
│   │   └── dataset.py       # GroundTruthReader, EntityMatcher, LabeledDatasetBuilder
│   └── static/               # Aset frontend
│       ├── style.css
│       └── images/
├── ml/
│   ├── config.py             # Konfigurasi ML
│   ├── src/
│   │   ├── ocr/              # PaddleOCR wrapper (inference)
│   │   ├── extraction/        # Ekstraksi entitas (inference pipeline)
│   │   ├── excel/            # Ekspor Excel CEISA 4.0
│   │   └── postprocessing/   # Normalisasi teks
│   └── models/
│       └── layoutlmv3-v4/
│           └── best_model/   # Bobot model LayoutLMv3 (inference)
├── training/                 # Pipeline training end-to-end
│   ├── render_pages.py       # Step 1: Render PDF → PNG
│   ├── run_ocr.py             # Step 2: PaddleOCR on images
│   ├── prepare_data.py       # Step 3: Ground-truth matching → JSONL
│   ├── finetune_v4.py        # Step 4: LayoutLMv3 fine-tuning
│   └── evaluate.py           # Step 5: Evaluasi model
├── training_dataset/          # Dataset mentah (61 shipments)
│   └── {shipment_id}/        # 1 folder per shipment
│       ├── {id}_CI.pdf       # Commercial Invoice
│       ├── {id}_PL.pdf       # Packing List
│       ├── {id}_BL.pdf       # Bill of Lading
│       └── {id}.xlsx         # Ground truth CEISA Excel
├── data/                     # Output & dataset training
│   ├── rendered/              # Output Step 1 (PNG images)
│   ├── ocr_results.json      # Output Step 2 (OCR words + bboxes)
│   ├── train.jsonl           # Output Step 3 (80% split)
│   ├── val.jsonl             # Output Step 3 (20% split)
│   ├── label_map.json        # Output Step 3 (81 labels)
│   ├── stats.json            # Output Step 3 (dataset statistics)
│   ├── train_v2.jsonl        # Pre-built training set
│   └── val_v2.jsonl          # Pre-built validation set
├── finetune_v4.py            # Shortcut: langsung ke Step 4
├── label_map_v2.json         # Label map v2 (81 labels)
├── .env                      # Konfigurasi environment
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Training Ulang Model ML

Pipeline end-to-end: **Dokumen Mentah (CI/PL/BL PDF + GT Excel) → Render → OCR → Label → Train**

Pipeline otomatis mengekstrak ground truth dari Excel, mencocokkan dengan teks hasil OCR menggunakan fuzzy matching, dan men-generate label BIO untuk setiap kata. Tidak perlu labeling manual.

### Prasyarat

- Python 3.11+
- PyMuPDF (`pip install pymupdf`)
- PaddleOCR (`pip install paddleocr paddlepaddle`)
- PyTorch + transformers + seqeval
- (Opsional) CUDA GPU

### Step 1 — Render PDF ke Gambar

Konversi semua halaman PDF shipment ke PNG (2× zoom untuk kualitas OCR):

```bash
cd "C:\Users\Acer\Documents\Kuliah\Kerja Praktik\website"
python training/render_pages.py
```

**Output:** `data/rendered/{shipment_id}/{filename}_p{n}.png`
**Hardware:** CPU, ~50 halaman/detik

### Step 2 — Ekstraksi Teks dengan OCR

Jalankan PaddleOCR pada semua gambar yang sudah dirender:

```bash
# GPU (lebih cepat)
python training/run_ocr.py --rendered-dir ./data/rendered --output ./data/ocr_results.json --use-gpu

# CPU
python training/run_ocr.py --rendered-dir ./data/rendered --output ./data/ocr_results.json
```

**Output:** `data/ocr_results.json` — berisi semua kata, bounding box, dan confidence score
**Hardware:** GPU ~2 menit, CPU ~15 menit

### Step 3 — Generate Dataset Labeled

MATCHING GROUND TRUTH ke hasil OCR, generate label BIO untuk setiap kata:

```bash
python -m training.prepare_data
```

**Output:**
- `data/train.jsonl` — 80% halaman (training)
- `data/val.jsonl` — 20% halaman (validasi)
- `data/label_map.json` — 81 label (O + 40 entity × B-/I-)
- `data/stats.json` — statistik dataset

**Catatan:** Jika `ocr_results.json` ditemukan, pipeline langsung gunakan hasil tersebut. Jika tidak ada, akan coba PyMuPDF text extraction, fallback ke PaddleOCR live.

### Step 4 — Fine-Tune LayoutLMv3

Train model pada dataset yang sudah di-label:

```bash
# GPU (recommended)
python finetune_v4.py --data-dir ./data --train-file train.jsonl --val-file val.jsonl --output-dir ml/models/layoutlmv3-customs --epochs 40 --batch-size 4 --grad-accum 4 --base-lr 2e-5 --entity-weight 5.0 --o-weight 0.1 --warmup-ratio 0.1 --patience 10

# CPU (sangat lambat, hanya untuk testing)
python finetune_v4.py --data-dir ./data --train-file train.jsonl --val-file val.jsonl --output-dir ml/models/layoutlmv3-customs --epochs 5 --batch-size 2 --cpu
```

### Step 5 — Evaluasi (opsional)

Evaluasi model trained pada data validasi:

```bash
python training/evaluate.py --model ml/models/layoutlmv3-customs/best_model --data-dir ./data
```

### One-Line Command (Langsung ke Step 4, Sudah Punya JSONL)

Jika dataset sudah siap di `data/train.jsonl` dan `data/val.jsonl`:

```bash
cd "C:\Users\Acer\Documents\Kuliah\Kerja Praktik\website" && python finetune_v4.py --data-dir ./data --train-file train.jsonl --val-file val.jsonl --output-dir ./ml/models/layoutlmv3-v4 --model-name microsoft/layoutlmv3-base --epochs 40 --batch-size 4 --grad-accum 4 --base-lr 2e-5 --entity-weight 5.0 --o-weight 0.1 --warmup-ratio 0.1 --patience 10
```

### Penjelasan Parameter Training

| Parameter | Nilai Default | Keterangan |
|-----------|-------------|------------|
| `--data-dir` | `./data` | Direktori dataset |
| `--train-file` | `train.jsonl` | File training |
| `--val-file` | `val.jsonl` | File validasi |
| `--output-dir` | `./ml/models/layoutlmv3-v4` | Direktori output model |
| `--model-name` | `microsoft/layoutlmv3-base` | Base model HuggingFace |
| `--epochs` | `40` | Maksimum epoch |
| `--batch-size` | `4` | Batch size per step |
| `--grad-accum` | `4` | Effective batch = 4×4=16 |
| `--base-lr` | `2e-5` | Learning rate |
| `--entity-weight` | `5.0` | Bobot entity tokens (mencegah all-O collapse) |
| `--o-weight` | `0.1` | Bobot O tokens |
| `--warmup-ratio` | `0.1` | Rasio warmup steps |
| `--patience` | `10` | Early stop jika F1 tidak improve |
| `--seed` | `42` | Random seed |
| `--max-length` | `512` | Max token length |

### Hardware

- **GPU (recommended):** CUDA otomatis aktif. Tambah `--batch-size 8` jika VRAM cukup (≥8GB).
- **CPU only:** Tambahkan `--cpu --batch-size 2`. Training ~10× lebih lambat.

### Output Training

Setelah training selesai:

- `ml/models/layoutlmv3-v4/best_model/` — checkpoint dengan F1 tertinggi **(gunakan ini untuk inference)**
- `ml/models/layoutlmv3-v4/final_model/` — model epoch terakhir
- `ml/models/layoutlmv3-v4/history.json` — log history training

Untuk menggunakan model baru, pastikan `MODEL_PATH` di `.env` menunjuk ke direktori `best_model/`:

```
MODEL_PATH=ml/models/layoutlmv3-v4/best_model
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

> Semua aksi (OCR, Create, Send, Approve, dll) secara otomatis logged ke Activity page.

## Requirements

**Runtime (Docker):**
- Docker & Docker Compose
- ~2 GB disk (base) + ~500MB (dengan model)
- RAM 4+ GB direkomendasikan

**Training ulang model:**
- Python 3.11+
- torch, transformers, seqeval, tqdm, numpy
- GPU dengan CUDA (recommended) atau CPU

## Endpoint API

### Ekstraksi & Shipments

### `POST /api/extract`
Unggah dokumen dan dapat hasil ekstraksi.

**Form fields:** `ci`, `pl`, `bl` (minimal satu diperlukan), `shipment_id` (opsional)

### `POST /api/shipments`
Simpan hasil ekstraksi ke database.

### `GET /api/shipments`
Daftar semua shipment. Query params: `status`, `search`, `limit`, `offset`

### `GET /api/shipments/{id}`
Detail shipment.

### `GET /api/shipments/{id}/download`
Download file Excel shipment.

### `POST /api/shipments/{id}/send`
Tandai shipment sebagai terkirim.

### `PATCH /api/shipments/{id}/status`
Update status shipment.

### `DELETE /api/shipments/{id}`
Hapus shipment.

### Dashboard

### `GET /api/dashboard`
Statistik dashboard: Saved Records, CEISA Ready, Needs Review, CEISA Approved, Operational Overview.

### Activity / Audit Log

### `GET /api/activities`
Daftar aktivitas dengan pagination. Query params: `action`, `status`, `search`, `page`, `per_page`

### `GET /api/activities/stats`
Summary statistik: Total Events, OCR Runs, CEISA Submissions, Last Activity.

### Development

### `POST /api/seed`
Seed sample shipment records ke database.

### `POST /api/seed/activities`
Seed sample activity records ke database (selalu replace data lama).

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

## Jalankan Tanpa Docker

```bash
pip install -r requirements.txt
cd src && python main.py
```
