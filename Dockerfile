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

# Install PyTorch CPU
RUN pip install --no-cache-dir \
    torch==2.1.0 \
    torchvision==0.16.0 \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Install core dependencies FIRST (without conflicting libs)
RUN pip install --no-cache-dir \
    "numpy>=1.24.0,<2.0"

# Install main dependencies
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
    tqdm

# Install paddle dependencies with specific numpy (IMPORTANT: order matters)
RUN pip install --no-cache-dir \
    paddlepaddle==3.0.0

# Force numpy after paddlepaddle
RUN pip install --no-cache-dir --force-reinstall "numpy>=1.24.0,<2.0"

# Install paddleocr
RUN pip install --no-cache-dir "paddleocr>=2.7,<3.0"

# Force numpy again after paddleocr
RUN pip install --no-cache-dir --force-reinstall "numpy>=1.24.0,<2.0"

# Install Pillow last with numpy pinned
RUN pip install --no-cache-dir "Pillow>=10.0.0,<11.0.0"

# Install opencv-python-headless (tanpa GUI, compatible dengan numpy 1.x)
RUN pip install --no-cache-dir opencv-python-headless==4.8.1.78

# Install shapely versi lama yang kompatibel dengan numpy 1.x
RUN pip install --no-cache-dir shapely==1.8.5

# Force numpy final time
RUN pip install --no-cache-dir --force-reinstall "numpy>=1.24.0,<2.0"

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
