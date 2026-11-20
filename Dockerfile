# TravelGenie — one container: FastAPI serves the API and the built React app.
# Built and run by Hugging Face Spaces (Docker SDK, port 7860).

# ---------- 1. Build the React frontend ----------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. Python app ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MODEL_CACHE_DIR=/app/models \
    COOKIE_SECURE=true \
    HOME=/home/user

# Hugging Face runs containers as uid 1000.
RUN useradd -m -u 1000 user
WORKDIR /app

# ChromaDB is only for local development (production uses Postgres + pgvector).
COPY requirements.txt .
RUN grep -v -i '^chromadb' requirements.txt > requirements.prod.txt \
    && pip install -r requirements.prod.txt

COPY backend ./backend
COPY data ./data

# Download the embedding + reranker models at build time so startup is fast.
RUN python -c "from backend.rag import models; models.warm_up()"

COPY --from=web /web/dist ./frontend/dist

RUN mkdir -p storage && chown -R user:user /app
USER user

EXPOSE 7860
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "7860", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
