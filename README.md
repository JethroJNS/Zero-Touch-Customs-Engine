# Zero-Touch Customs Engine

A web-based OCR extraction system for Indonesian customs documents (CEISA 4.0). Upload Commercial Invoice, Packing List, and Bill of Lading files to automatically extract entities and generate declaration packages.

## Quick Start

```bash
# Build and start the application
docker compose up --build

# Open in browser
open http://localhost:8000
```

## Features

- **Smart Upload**: Upload CI, PL, and/or BL files (PDF, PNG, JPG, JPEG, TIFF)
- **Hybrid Extraction**: Combines ML (LayoutLMv3) + Pattern-based extraction
- **CEISA 4.0 Export**: Produces complete Excel declaration package
- **Declarations Management**: Save, view, send, and delete shipment records
- **CPU-Only**: No GPU required for inference

## Project Structure

```
website/
├── src/                       # FastAPI application
│   ├── main.py               # FastAPI backend
│   ├── smart_upload.html     # Smart Upload page
│   ├── declarations.html     # Declarations management page
│   └── static/               # Frontend assets
│       ├── style.css         # UI styles
│       └── images/
├── ml/                        # ML inference engine
│   ├── config.py            # Configuration
│   ├── src/
│   │   ├── ocr/            # PaddleOCR wrapper
│   │   ├── extraction/     # Entity extraction (HybridExtractor, Layout, Pattern)
│   │   ├── excel/          # CEISA 4.0 Excel exporter
│   │   └── postprocessing/ # Text normalization
│   └── models/
│       └── layoutlmv3-v4/
│           └── best_model/  # Model weights (481MB)
├── .env                       # Environment configuration
├── download_model.py         # Model download utility
├── Dockerfile
├── docker-compose.yml
└── requirements.txt

training/                     # Model training code (separate repository)
├── training/                 # Training scripts (finetune_v4.py, etc.)
├── dataset/                 # Training dataset
├── train.jsonl             # Training data
├── val.jsonl               # Validation data
└── label_map_v2.json      # Entity labels
```

## ML Model

The LayoutLMv3 model (481MB) is included in this repository. For larger deployments or version control, you can:

### Option 1: Download during Docker build
```bash
docker build --build-arg MODEL_REPO=your-username/layoutlmv3-v4 .
```

### Option 2: Download manually
```bash
pip install huggingface_hub
python download_model.py --huggingface-repo your-username/layoutlmv3-v4
```

### Option 3: Use text-based fallback (no model needed)
The application works without the model using text-based regex extraction (lower accuracy).

**To upload your trained model to HuggingFace:**
```bash
huggingface-cli login
# From your training environment:
from huggingface_hub import create_repo, upload_folder
create_repo("your-username/layoutlmv3-v4")
upload_folder(folder_path="best_model", repo_id="your-username/layoutlmv3-v4")
```

## Architecture

```
Browser → FastAPI → HybridExtractor → ExcelExporter → Excel Download
            (src/)        (ml/)
                           │
                           ├── OCR (PaddleOCR)
                           ├── LayoutXLM (LayoutLMv3) ── fallback ──► Pattern-based
                           └── Merger → CEISA Excel
```

## Requirements

- Docker & Docker Compose
- ~2 GB disk space (base) + ~500MB (with model)
- 4+ GB RAM recommended

## API Endpoints

### `POST /api/extract`
Upload documents and get extraction results.

**Form fields:** `ci`, `pl`, `bl` (at least one required)

### `POST /api/shipments`
Save extraction results to database.

### `GET /api/shipments`
List all saved shipments.

### `GET /api/shipments/{id}`
Get shipment details.

### `POST /api/shipments/{id}/send`
Mark shipment as sent.

### `DELETE /api/shipments/{id}`
Delete a shipment.

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@db:5432/ocr_engine` |
| `POSTGRES_DB` | Database name | `ocr_engine` |
| `POSTGRES_USER` | Database user | `postgres` |
| `POSTGRES_PASSWORD` | Database password | `postgres` |
| `MODEL_PATH` | Path to LayoutLMv3 model | `ml/models/layoutlmv3-v4/best_model` |
| `APP_PORT` | Application port | `8000` |

## Development

```bash
# Run without Docker (requires Python 3.11+)
pip install -r requirements.txt
cd src && python main.py

# Train new model (requires training/ directory)
cd ../training
python -m training.finetune_v4
```
