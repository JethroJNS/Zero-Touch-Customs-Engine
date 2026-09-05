# Zero-Touch Customs Engine

Aplikasi web untuk mengekstrak data dari dokumen customs Indonesia (CEISA 4.0). Unggah dokumen Commercial Invoice, Packing List, dan Bill of Lading untuk otomatis mengekstrak entitas dan menghasilkan paket declaration Excel.


## Daftar Isi

1. [Fitur](#fitur)
2. [Tech Stack](#tech-stack)
3. [Requirements](#requirements)
4. [Struktur Proyek](#struktur-proyek)
5. [Arsitektur](#arsitektur)
6. [Cara Menjalankan dengan Docker](#cara-menjalankan-dengan-docker)
7. [Deployment ke Hostinger VPS](#deployment-ke-hostinger-vps)
8. [Cara Training Ulang Model (Local)](#cara-training-ulang-model-local)
9. [Variabel Environment](#variabel-environment)
10. [Endpoint API](#endpoint-api)
11. [CEISA 4.0 Host-to-Host Integration](#ceisa-40-host-to-host-integration)
---


## Fitur

- **Dashboard**: Overview data shipment, status CEISA, dan aktivitas operasional
- **Smart Upload**: Unggah dan ekstraksi infromasi dari dokumen CI, PL, BL, dan FE (PDF, PNG, JPG, JPEG, TIFF)
- **Declarations**: Simpan, lihat, kirim, dan hapus record shipment
- **Activity (Audit Log)**: Lacak semua aktivitas sistem secara real-time

## Tech Stack

- **Backend**: FastAPI + Uvicorn
- **Database**: PostgreSQL
- **OCR**: PaddleOCR
- **ML Model**: LayoutLMv3 (fine-tuned)
- **Deployment**: Docker + VPS


## Requirements

**Runtime:**
- Docker & Docker Compose
- PostgreSQL
- ~2 GB disk + ~500MB model
- RAM 2+ GB

**Local Development (tanpa Docker):**
```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
```


## Struktur Proyek

```
Zero-Touch-Customs-Engine/
├── src/
│   ├── main.py              # FastAPI entry point
│   ├── routes/              # API endpoints
│   │   ├── shipments.py     # Shipment CRUD + extract endpoint
│   │   ├── activities.py    # Activity log
│   │   └── dashboard.py     # Dashboard stats
│   ├── models/             # SQLAlchemy models
│   ├── services/            # Business logic
│   ├── templates/          # HTML templates
│   └── static/             # Frontend assets
├── ml/
│   ├── config.py           # ML configuration
│   ├── src/
│   │   ├── ocr/            # PaddleOCR wrapper
│   │   │   └── engine.py   # OCR engine
│   │   ├── extraction/     # Entity extraction
│   │   │   └── hybrid_engine.py
│   │   ├── excel/          # CEISA Excel export
│   │   └── postprocessing/ # Text normalization
│   └── models/
│       └── layoutlmv3-v4/
│           └── best_model/ # Model downloaded from HuggingFace
├── training/
│   ├── render_pages.py     # PDF → PNG rendering
│   ├── run_ocr.py          # PaddleOCR inference
│   └── prepare_data.py     # Dataset generation
├── training_dataset/       # Training data (61 shipments)
├── download_model_hf.py   # HuggingFace model download script
├── finetune_v4.py          # Model fine-tuning script
├── Dockerfile              # Docker image definition
├── docker-compose.yml      # Local development compose
├── requirements.txt        # Python dependencies
├── .env.example           # Template environment variables
└── README.md
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


## Cara Menjalankan dengan Docker

### 1. Setup Environment Variables

```bash
# Salin .env.example menjadi .env
cp .env.example .env
```

**Penting:** File `.env` WAJIB dibuat sebelum menjalankan Docker Compose. File ini berisi:
- `DATABASE_URL` - Connection string PostgreSQL
- `MODEL_REPO` - Repository ID untuk download model ML
- `CEISA_*` - Konfigurasi CEISA (opsional)

Tanpa `.env`, aplikasi tidak akan bisa connect ke database dan download model.

### 2. Nyalakan Docker dan Jalankan Aplikasi

```bash
# Build dan jalankan aplikasi
docker compose up --build

# Buka di browser
open http://localhost:8000
```


## Deployment ke Hostinger VPS

### Prasyarat
- VPS Hostinger dengan OS Ubuntu 22.04
- Docker & Docker Compose terinstall
- Domain (opsional)

### 1. Login ke VPS

```bash
ssh root@your-vps-ip
```

### 2. Install Docker

```bash
# Update sistem
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose
apt install docker-compose -y

# Enable dan start Docker
systemctl enable docker
systemctl start docker
```

### 3. Upload Project ke VPS

```bash
# Di lokal, archive project
cd /path/to/Zero-Touch-Customs-Engine
tar -czvf zero-touch-customs.tar.gz .

# Upload ke VPS
scp zero-touch-customs.tar.gz root@your-vps-ip:/root/

# Di VPS, extract
cd /root
tar -xzvf zero-touch-customs.tar.gz
```

### 4. Setup PostgreSQL

```bash
cd Zero-Touch-Customs-Engine

# Jalankan PostgreSQL saja dulu
docker compose up -d db

# Tunggu sampai ready
sleep 5

# Cek logs
docker compose logs db
```

### 5. Set Environment Variables

Buat file `.env`:

```bash
cat > .env << 'EOF'
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ocr_engine
POSTGRES_DB=ocr_engine
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
MODEL_REPO=iDelthea/zero-touch-customs-model
EOF
```

### 6. Build dan Jalankan Aplikasi

```bash
# Build Docker image
docker compose build

# Jalankan semua service
docker compose up -d

# Cek status
docker compose ps

# Cek logs
docker compose logs -f
```

### 7. Verifikasi Deployment

```bash
# Test apakah app running
curl http://localhost:8000

# Cek logs
docker compose logs app
```

### 8. Setup Domain (Opsional)

1. Di Hostinger hPanel, buka **Domain** → **DNS Zone**
2. Tambahkan A record pointing ke IP VPS
3. Tunggu propagasi DNS (~24 jam)

### 9. Setup Nginx Reverse Proxy (Recommended)

```bash
# Install Nginx
apt install nginx -y

# Buat config
cat > /etc/nginx/sites-available/zero-touch << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Enable site
ln -s /etc/nginx/sites-available/zero-touch /etc/nginx/sites-enabled/

# Test config
nginx -t

# Reload Nginx
systemctl reload nginx
```

### 10. Setup SSL (Let's Encrypt)

```bash
# Install Certbot
apt install certbot python3-certbot-nginx -y

# Generate SSL
certbot --nginx -d your-domain.com

# Auto-renew setup
systemctl enable certbot.timer
systemctl start certbot.timer
```

### Troubleshooting

```bash
# Lihat semua logs
docker compose logs -f

# Lihat logs app saja
docker compose logs -f app

# Restart service
docker compose restart app

# Rebuild tanpa cache
docker compose build --no-cache
docker compose up -d

# Hapus dan mulai ulang
docker compose down -v
docker compose up -d
```


## Cara Training Ulang Model (Local)

Pipeline training: **Dokumen PDF → Render PNG → OCR → Generate Label → Train → Eval**

### Prasyarat

**Dependencies:**
```bash
# Install dependencies
pip install -r requirements.txt
```

**Dataset Training:**

- Letakkan dataset training di folder `training_dataset/` di root project
- Setiap shipment dalam folder terpisah:
  - `{No_Aju}_CI.pdf` - Commercial Invoice (opsional)
  - `{No_Aju}_PL.pdf` - Packing List (opsional)
  - `{No_Aju}_BL.pdf` - Bill of Lading (opsional)
  - `{No_Aju}.xlsx` - Ground Truth CEISA Excel
- Minimum: 1 folder dengan minimal 1 PDF dan 1 Excel

**Contoh struktur folder:**
```
training_dataset/
├── shipment_001/
│   ├── shipment_001_CI.pdf
│   ├── shipment_001_PL.pdf
│   ├── shipment_001_BL.pdf
│   └── shipment_001.xlsx
├── shipment_002/
│   └── ...
```

### Step 1: Render PDF ke Gambar

Konversi semua halaman PDF shipment ke PNG dengan zoom 2x untuk kualitas OCR.

```bash
# Jalankan dari root project
python training/render_pages.py
```

**Output:** `data/rendered/{shipment_id}/{filename}_p{n}.png`

**Contoh output:**
```
data/rendered/shipment_001/
├── shipment_001_CI_p1.png
├── shipment_001_CI_p2.png
├── shipment_001_PL_p1.png
└── shipment_001_BL_p1.png
```

**Hardware:** CPU, ~50 halaman/detik

---

### Step 2: Ekstraksi Teks dengan OCR

Jalankan PaddleOCR pada semua gambar yang sudah dirender untuk mendapatkan teks dan bounding box.

```bash
# GPU (lebih cepat, ~2 menit)
python training/run_ocr.py --use-gpu

# CPU (lebih lambat, ~15 menit)
python training/run_ocr.py
```

**Output:** `data/ocr_results.json`

**Format output:**
```json
{
  "path/to/image.png": {
    "width": 1653,
    "height": 2340,
    "words": [
      {"text": "INVOICE", "bbox": [100, 50, 200, 80], "confidence": 0.99},
      {"text": "No:", "bbox": [100, 100, 150, 120], "confidence": 0.95}
    ]
  }
}
```

**Hardware:** GPU ~2 menit, CPU ~15 menit

---

### Step 3: Generate Dataset Labeled

Match ground truth dari Excel ke hasil OCR menggunakan fuzzy matching, generate label BIO untuk setiap kata.

```bash
# Generate dataset training dan validation
python -m src.training.dataset
```

**Atau dengan shortcut:**

```bash
python -m training.prepare_data
```

**Output:**
```
data/
├── train.jsonl          # 80% data training
├── val.jsonl            # 20% data validation
├── label_map.json       # 81 label (O + 40 entity × B-/I-)
└── stats.json           # Statistik dataset
```

**Format label_map.json:**
```json
{
  "O": 0,
  "B-invoice_number": 1,
  "I-invoice_number": 2,
  "B-invoice_date": 3,
  ...
}
```

---

### Step 4: Fine-Tune LayoutLMv3

Train model pada dataset yang sudah di-label.

```bash
# GPU
python finetune_v4.py --data-dir ./data --epochs 40

# CPU (sangat lambat)
python finetune_v4.py --data-dir ./data --epochs 40 --cpu
```

**Output:**
```
ml/models/layoutlmv3-v4/
├── best_model/          # Model dengan F1 tertinggi (GUNAKAN INI)
│   ├── config.json
│   ├── model.safetensors
│   ├── tokenizer.json
│   ├── tokenizer_config.json
│   └── label_map.json
├── final_model/         # Model epoch terakhir
│   └── ...
└── history.json         # Log training (loss, F1 per epoch)
```

**Hardware:**
- GPU (recommended): CUDA otomatis aktif, ~30-60 menit untuk 40 epoch
- CPU: ~10x lebih lambat, hanya untuk testing

**Penjelasan parameter training:**

| Parameter | Default | Keterangan |
|-----------|---------|-------------|
| `--data-dir` | `./data` | Direktori dataset |
| `--train-file` | `train.jsonl` | File training |
| `--val-file` | `val.jsonl` | File validation |
| `--output-dir` | `./ml/models/layoutlmv3-v4` | Direktori output model |
| `--model-name` | `microsoft/layoutlmv3-base` | Base model HuggingFace |
| `--epochs` | `40` | Maksimum epoch |
| `--batch-size` | `4` | Batch size per step |
| `--grad-accum` | `4` | Effective batch = batch×accum = 16 |
| `--base-lr` | `2e-5` | Learning rate |
| `--entity-weight` | `5.0` | Bobot entity tokens (mencegah all-O) |
| `--o-weight` | `0.1` | Bobot O tokens |
| `--warmup-ratio` | `0.1` | Rasio warmup steps |
| `--patience` | `10` | Early stop jika F1 tidak improve |
| `--seed` | `42` | Random seed |
| `--max-length` | `512` | Max token length |
| `--cpu` | - | Force CPU mode |

---

### Step 5: Evaluasi Model

Evaluasi model trained pada data validation.

```bash
python training/evaluate.py \
  --model ml/models/layoutlmv3-v4/best_model \
  --data-dir ./data
```

**Output:** Precision, Recall, F1-Score per entity

---

### Step 6: Upload Model ke HuggingFace

Setelah training selesai, upload model ke HuggingFace untuk digunakan di deployment.

```bash
# Install huggingface_hub
pip install huggingface_hub

# Login
hf auth login

# Buat repository baru (jika belum ada)
hf repos create zero-touch-customs-model --type model

# Upload folder best_model
hf upload zero-touch-customs-model ml/models/layoutlmv3-v4/best_model/

# Atau upload seluruh folder output
hf upload zero-touch-customs-model ml/models/layoutlmv3-v4/ --repo-type model
```

**Repository:** https://huggingface.co/iDelthea/zero-touch-customs-model

### Upload ke Repository Baru

Jika model diupload ke repository atau akun HuggingFace yang baru, perlu modifikasi file `.env` sebagai berikut:

Ubah `MODEL_REPO` sesuai repository baru:

```bash
# Sebelum
MODEL_REPO=iDelthea/zero-touch-customs-model

# Sesudah (contoh: akun lain)
MODEL_REPO=username/model-name-yang-berbeda
```

---

### Struktur Folder Setelah Training

```
Zero-Touch-Customs-Engine/
├── data/
│   ├── rendered/                 # Output Step 1 (PNG)
│   │   └── {shipment_id}/
│   │       └── {id}_CI_p{n}.png
│   ├── ocr_results.json         # Output Step 2 (OCR)
│   ├── train.jsonl              # Output Step 3 (training)
│   ├── val.jsonl                # Output Step 3 (validation)
│   ├── label_map.json           # Output Step 3 (labels)
│   └── stats.json               # Output Step 3 (stats)
├── ml/
│   └── models/
│       └── layoutlmv3-v4/
│           ├── base_model/       # Base model LayoutLMv3
│           └── best_model/      # Output Step 4 (trained model)
│               ├── config.json
│               ├── model.safetensors
│               └── ...
└── training_dataset/            # Input dataset (61 shipments)
    └── {shipment_id}/
        ├── {id}_CI.pdf
        ├── {id}_PL.pdf
        ├── {id}_BL.pdf
        └── {id}.xlsx
```


## Variabel Environment

Salin `.env.example` menjadi `.env` dan konfigurasi sesuai kebutuhan:

```bash
cp .env.example .env
```

### Untuk Docker Compose (Lokal)

Gunakan nilai default dari `.env.example`:

```bash
DATABASE_URL=postgresql://postgres:postgres@db:5432/ocr_engine
MODEL_REPO=iDelthea/zero-touch-customs-model
```

### Untuk VPS Hostinger

Jika PostgreSQL berjalan di host yang sama:

```bash
# PostgreSQL di VPS
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/ocr_engine
MODEL_REPO=iDelthea/zero-touch-customs-model
CEISA_ENV=dev
CEISA_USERNAME=your_username
CEISA_PASSWORD=your_password
```

Jika menggunakan PostgreSQL Hosting Hostinger (managed database):

```bash
# Gunakan connection string dari Hostinger
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@YOUR_HOST:5432/ocr_engine
```

| Variabel | Deskripsi | Required |
|----------|------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `MODEL_REPO` | HuggingFace repo ID untuk model | No |
| `MODEL_PATH` | Path lokal ke model | No |
| `CEISA_ENV` | `dev` atau `prod` | No |
| `CEISA_USERNAME` | Username CEISA portal | No |
| `CEISA_PASSWORD` | Password CEISA portal | No |


## Endpoint API

### Ekstraksi & Shipments

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| `POST` | `/api/extract` | Upload dokumen, ekstrak entitas |
| `POST` | `/api/shipments` | Simpan hasil ekstraksi |
| `GET` | `/api/shipments` | Daftar shipment |
| `GET` | `/api/shipments/{id}` | Detail shipment |
| `GET` | `/api/shipments/{id}/download` | Download Excel |
| `POST` | `/api/shipments/{id}/send` | Kirim ke CEISA |
| `PATCH` | `/api/shipments/{id}/status` | Update status |
| `DELETE` | `/api/shipments/{id}` | Hapus shipment |

### Dashboard & Activity

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| `GET` | `/api/dashboard` | Statistik dashboard |
| `GET` | `/api/activities` | Daftar aktivitas |
| `GET` | `/api/activities/stats` | Statistik aktivitas |

### Development

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| `POST` | `/api/seed` | Seed sample data |
| `POST` | `/api/seed/activities` | Seed activity log |

## CEISA 4.0 Host-to-Host Integration

`TODO:` Integrasi dengan sistem CEISA 4.0 Bea Cukai Indonesia.

### Prasyarat

1. Daftar di Portal CEISA: https://portal.beacukai.go.id
2. Set variabel environment:

```bash
CEISA_ENV=dev
CEISA_USERNAME=your_username
CEISA_PASSWORD=your_password
```

### CEISA Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| `GET` | `/api/ceisa/config` | Cek konfigurasi |
| `POST` | `/api/ceisa/submit/{id}` | Submit ke CEISA |
| `GET` | `/api/ceisa/status/{id}` | Cek status |
| `GET` | `/api/ceisa/preview/{id}` | Preview declaration |
| `POST` | `/api/ceisa/validate/{id}` | Validasi data |
