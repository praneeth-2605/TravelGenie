# TravelGenie — one container: FastAPI serves the API and the built React app.
# Runs on Google Cloud Run (or any Docker host). Listens on $PORT (default 8080).

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

# Run as an unprivileged user.
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

ENV PORT=8080
EXPOSE 8080
# Cloud Run injects $PORT; --proxy-headers so the app sees https and its public host.
CMD ["sh", "-c", "exec uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
