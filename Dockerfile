# Document OCR Web Application
# Optimized build: dependencies cached unless requirements.txt changes

FROM python:3.11-slim-bookworm

LABEL maintainer="adaCODE"
LABEL description="Document OCR CEISA 4.0 Extraction Web Application"

WORKDIR /app

# ── Install system dependencies for OpenCV, PyMuPDF, PIL, OCR, and PostgreSQL ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libfontconfig1 \
    fonts-dejavu-core \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# ── Copy and install Python dependencies FIRST (cached unless requirements.txt changes) ──
COPY requirements.txt /app/requirements.txt

# Install PyTorch CPU first (separate due to custom index)
RUN pip install --no-cache-dir \
    torch==2.1.0 \
    torchvision==0.16.0 \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Install all other dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-multipart \
    aiofiles \
    sqlalchemy[asyncio] \
    asyncpg \
    psycopg2-binary \
    paddlepaddle \
    "paddleocr>=2.7,<3.0" \
    "transformers>=4.40,<4.50" \
    accelerate \
    scikit-learn \
    openpyxl \
    pymupdf \
    Pillow \
    numpy \
    regex

# ── Copy application code ──────────────────────────────────────────────────────
COPY src/ /app/src/
COPY ml/ /app/ml/
COPY download_model.py /app/download_model.py

# ── Environment variables ─────────────────────────────────────────────────────
ENV PYTHONPATH=/app:${PYTHONPATH}
ENV PYTHONUNBUFFERED=1

# ── Download ML model (optional) ────────────────────────────────────────────
ARG MODEL_REPO=
RUN if [ -n "$MODEL_REPO" ]; then \
    pip install --no-cache-dir huggingface_hub && \
    python /app/download_model.py --huggingface-repo "$MODEL_REPO"; \
    fi

# ── Expose port ─────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Run the web server ──────────────────────────────────────────────────────
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
