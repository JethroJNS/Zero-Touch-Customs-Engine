FROM python:3.11-slim-bookworm

LABEL maintainer="adaCODE"
LABEL description="Document OCR CEISA 4.0 Extraction Web Application"

WORKDIR /app

# Install system dependencies
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

# Copy requirements first
COPY requirements.txt /app/requirements.txt

# Install core scientific packages FIRST with numpy 2.x support
# shapely 2.0+ is required for numpy 2.x compatibility
RUN pip install --no-cache-dir \
    "numpy>=2.0.0" \
    "scipy>=1.14.0" \
    "scikit-image>=0.24.0" \
    "shapely>=2.0.0"

# Install PyTorch CPU
RUN pip install --no-cache-dir \
    torch==2.1.0 \
    torchvision==0.16.0 \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-multipart \
    aiofiles \
    httpx \
    sqlalchemy[asyncio] \
    asyncpg \
    psycopg2-binary \
    "transformers>=4.40,<4.50" \
    accelerate \
    scikit-learn \
    openpyxl \
    pymupdf \
    regex \
    seqeval \
    tqdm \
    Pillow

# Install opencv-python-headless (compatible with numpy 2.x)
RUN pip install --no-cache-dir opencv-python-headless>=4.10.0

# Install paddlepaddle
RUN pip install --no-cache-dir paddlepaddle==3.0.0

# Install paddleocr
RUN pip install --no-cache-dir "paddleocr>=2.7,<3.0"

# Copy application files
COPY src/ /app/src/
COPY ml/ /app/ml/
COPY training/ /app/training/
COPY training_dataset/ /app/training_dataset/
COPY download_model.py /app/download_model.py
COPY download_model_hf.py /app/download_model_hf.py
COPY finetune_v4.py /app/finetune_v4.py

# Set environment variables
ENV PYTHONPATH=/app/src:/app
ENV PYTHONUNBUFFERED=1

# Download model if MODEL_REPO is set
ARG MODEL_REPO
ENV MODEL_REPO=${MODEL_REPO}
RUN if [ -n "${MODEL_REPO}" ]; then \
    pip install --no-cache-dir huggingface_hub && \
    python /app/download_model_hf.py --repo "${MODEL_REPO}" --target-dir /app/ml/models/layoutlmv3-v4/best_model; \
    fi

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
