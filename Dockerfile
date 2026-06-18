# ═══════════════════════════════════════════════════════════════════════════
# FireAI — Safety-Critical Fire Protection Digital Twin
# Multi-stage Docker build: Frontend (Node) + Python deps + Runtime
# ═══════════════════════════════════════════════════════════════════════════

# ─── Stage 1: Frontend Build ──────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ─── Stage 2: Python Dependencies ─────────────────────────────────────────
FROM python:3.12-slim AS python-builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 3: Runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="FireAI Engineering Team"
LABEL description="Safety-Critical Fire Protection Digital Twin — NFPA 72-2022"
LABEL version="1.0.0"

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r fireai \
    && useradd -r -g fireai -d /app -s /sbin/nologin -c "FireAI Service" fireai

WORKDIR /app

# Copy installed Python packages
COPY --from=python-builder /install /usr/local

# Copy application code (only what's needed for production)
COPY --chown=fireai:fireai backend/ backend/
COPY --chown=fireai:fireai fireai/ fireai/
COPY --chown=fireai:fireai parsers/ parsers/
COPY --chown=fireai:fireai integration/ integration/
COPY --chown=fireai:fireai pyproject.toml setup.py ./
COPY --chown=fireai:fireai qomn_conduit/ qomn_conduit/
COPY --chown=fireai:fireai qomn_fire/ qomn_fire/
COPY --chown=fireai:fireai facp_system/ facp_system/

# Copy built frontend from stage 1
COPY --from=frontend-builder --chown=fireai:fireai /build/frontend/dist/ frontend/dist/

# Create data and logs directories
RUN mkdir -p /app/data /app/logs && \
    chown -R fireai:fireai /app/data /app/logs

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIREAI_ENV=production \
    LOG_LEVEL=WARNING \
    DIGITAL_TWIN_DB_PATH=/app/data/digital_twin.db \
    UDM_DB_PATH=/app/data/udm_elements.db \
    UVICORN_LIMIT_MAX_REQUESTS=1000 \
    UVICORN_TIMEOUT_KEEP_ALIVE=5

USER fireai

EXPOSE 8000

# v2: use curl instead of `python -c "import urllib..."` — lighter on CPU
# and memory, and gives a clearer exit code on connection failure.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

# C-2 FIX: Default to 1 worker for SQLite (WAL mode allows concurrent reads
# but concurrent writes from multiple processes risk SQLITE_BUSY/data corruption).
# For multi-worker deployments, use PostgreSQL via deploy/docker/docker-compose.yml
#
# v2: --limit-max-requests recycles each worker after N requests, mitigating
# memory leaks in long-running processes (FastAPI/SQLAlchemy). Default 1000.
# --timeout-keep-alive=5 closes idle connections promptly.
CMD uvicorn backend.app:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers ${UVICORN_WORKERS:-1} \
    --limit-max-requests ${UVICORN_LIMIT_MAX_REQUESTS:-1000} \
    --timeout-keep-alive ${UVICORN_TIMEOUT_KEEP_ALIVE:-5}
