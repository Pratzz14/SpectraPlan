FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 STORAGE_BACKEND=supabase BACKGROUND_ASSESSMENTS=true \
    CLOUD_CACHE_DIR=/tmp/spectraplan/cache KNOWLEDGE_WORK_DIR=/tmp/spectraplan/work \
    SOURCE_DIR=/tmp/spectraplan/sources CORPUS_DIR=/tmp/spectraplan/corpus \
    WEB_CORPUS_DIR=/tmp/spectraplan/website EMBEDDING_CACHE_DIR=/opt/embedding-model \
    STATIC_FRONTEND_DIR=/app/frontend/dist DATABASE_SSL_ROOT_CERT=/app/deploy/supabase-ca.crt \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 INGEST_CONCURRENCY=1 KNOWLEDGE_OCR_TESSDATA=/usr/share/tesseract-ocr/5/tessdata
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY deploy/ deploy/
RUN python deploy/prepare_model.py
RUN python -m deploy.memory_probe
COPY --from=frontend /build/dist frontend/dist
RUN useradd --create-home app && mkdir -p /tmp/spectraplan && chown app:app /tmp/spectraplan
USER app
CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
