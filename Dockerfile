# ═══════════════════════════════════════════════════════════════════════════
# FireAI — Safety-Critical Fire Protection Digital Twin
# Multi-stage Docker build: Frontend (Node) + Python deps + Runtime
# ═══════════════════════════════════════════════════════════════════════════

# ─── Stage 1: Build the React frontend (Vite) ─────────────────────────────
# V206 FIX: The frontend MUST be built and served by the FastAPI app on
# HuggingFace Spaces. Without this stage, the HF Space URL returns 404 for /
# because there is no static file server — only the FastAPI backend runs.
FROM node:20-slim AS frontend-builder

WORKDIR /build

# Copy package files first to leverage Docker layer caching
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --prefer-offline 2>&1 | tail -5

# Copy the rest of the frontend source and build
COPY frontend/ ./
# Set the production API URL — same-origin since backend serves frontend
ENV VITE_API_URL=/api/v1
ENV VITE_APP_VERSION=8.1.0
RUN npm run build

# Verify the build output exists
RUN ls -la dist/ && test -f dist/index.html


# ─── Stage 2: Python Dependencies ─────────────────────────────────────────
FROM python:3.12-slim AS python-builder

WORKDIR /build

# V140 FIX: Install setuptools + wheel BEFORE pip install — required by
# pyproject.toml build-system (setuptools.build_meta backend). Without this,
# pip fails with "Cannot import 'setuptools.build_meta'" when installing
# packages that use PEP 517 builds.
RUN pip install --no-cache-dir --upgrade pip setuptools>=68 wheel

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 3: Runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="FireAI Engineering Team"
LABEL description="Safety-Critical Fire Protection Digital Twin — NFPA 72-2022"
LABEL version="1.0.0"

# V214: Install LibreDWG (dwg2dxf binary) for real DWG→DXF conversion.
# Without this, dwg_converter.py falls back to a mock that writes an
# entity-empty DXF file (with an explicit warning). Installing libredwg-tools
# enables real DWG parsing in Docker/Linux deployments without AutoCAD.
# apt-get clean + rm -rf /var/lib/apt/lists/* keeps the image small.
RUN apt-get update && \
    apt-get install -y --no-install-recommends libredwg-tools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    dwg2dxf --version 2>&1 | head -1 || echo "dwg2dxf installed (version check non-fatal)"

RUN groupadd -r fireai && \
    useradd -r -g fireai -d /app -s /sbin/nologin -c "FireAI Service" fireai

WORKDIR /app

# Copy installed Python packages
COPY --from=python-builder /install /usr/local

# Copy application code (only what's needed for production)
COPY --chown=fireai:fireai backend/ backend/
COPY --chown=fireai:fireai fireai/ fireai/
COPY --chown=fireai:fireai parsers/ parsers/
COPY --chown=fireai:fireai integration/ integration/
COPY --chown=fireai:fireai pyproject.toml ./
COPY --chown=fireai:fireai qomn_conduit/ qomn_conduit/
COPY --chown=fireai:fireai qomn_fire/ qomn_fire/
COPY --chown=fireai:fireai facp_system/ facp_system/
COPY --chown=fireai:fireai core/ core/
COPY --chown=fireai:fireai marine/ marine/
COPY --chown=fireai:fireai adapters/ adapters/

# V206: Copy the built frontend (from Stage 1) — served at / by FastAPI StaticFiles
# when BAZSPARK_FRONTEND_DIST is set (see backend/app.py).
COPY --chown=fireai:fireai --from=frontend-builder /build/dist /app/frontend_dist

# Create data, logs, and db directories.
# V174 FIX: /app/db MUST be pre-created and owned by fireai. backend/api_keys.py
# line 648 calls _ensure_default_admin_key() at MODULE LOAD TIME; when
# FIREAI_API_KEY is set (production + CI Gate 6), this calls add_api_key() →
# _save_keys() → path.parent.mkdir(parents=True, exist_ok=True) on the
# KEYS_FILE directory (default "db/api_keys.json" → /app/db). Without this
# pre-created directory, the fireai user (non-root) cannot mkdir under /app
# (owned by root) and the container crashes with:
#   PermissionError: [Errno 13] Permission denied: 'db'
# This was the root cause of CI Gate 6 failures (runs #741–#748+).
# Pre-creating /app/db aligns with the existing pattern for /app/data and
# /app/logs, and requires NO application code change.
RUN mkdir -p /app/data /app/logs /app/db && \
    chown -R fireai:fireai /app/data /app/logs /app/db /app/frontend_dist

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIREAI_ENV=production \
    LOG_LEVEL=WARNING \
    UDM_DB_PATH=/app/data/udm_elements.db \
    BAZSPARK_FRONTEND_DIST=/app/frontend_dist
# DATABASE_URL is intentionally NOT set here — it comes from the Hugging Face Space secret.
# This allows the container to use the Supabase PostgreSQL instance.
# Fallback: if no secret is provided, the app uses the DIGITAL_TWIN_DB_PATH SQLite file.
# CRITICAL-3: Unified DB path — DATABASE_URL is now the single source of truth.
# Removed DIGITAL_TWIN_DB_PATH (was unused, caused confusion).
# V206: BAZSPARK_FRONTEND_DIST points to the built frontend so backend/app.py
# mounts StaticFiles and serves the SPA at / (see _spa_fallback in app.py).

USER fireai

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/api/health')" || exit 1

# C-2 FIX: Default to 1 worker for SQLite (WAL mode allows concurrent reads
# but concurrent writes from multiple processes risk SQLITE_BUSY/data corruption).
# For multi-worker deployments, use PostgreSQL via deploy/docker/docker-compose.yml
#
# H-3 FIX: Bind to 0.0.0.0 for external routing (required by cloud hosting like HF Spaces).
CMD uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-7860} --workers ${UVICORN_WORKERS:-1}  # NOSONAR — S7019: dockerfile acceptable
