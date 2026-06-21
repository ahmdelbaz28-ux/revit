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

# ─── Stage 2: Python Dependencies + Wheel Build ───────────────────────────
# P0.3 FIX: previously `pip install -r requirements.txt` — but
# requirements.txt had only 13 packages while pyproject.toml declares 36.
# This left the runtime image missing numpy, scipy, shapely, ezdxf, lxml,
# pandas, matplotlib, prometheus-client, psutil, click, aiohttp, etc.
# The single source of truth is pyproject.toml; install from it.
FROM python:3.12-slim AS python-builder

WORKDIR /build

# Install build deps (gcc for any C-extension wheels in the dependency tree)
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml + README.md (needed for metadata) + LICENSE for the wheel
COPY pyproject.toml README.md LICENSE ./

# Copy ALL application source so setuptools' find_packages() can discover
# the fireai, backend, parsers, qomn_fire, qomn_conduit, facp_system,
# facp_distributed, core, adapters, marine, integration top-level packages
# declared in [tool.setuptools.packages.find] of pyproject.toml.
COPY backend/ backend/
COPY fireai/ fireai/
COPY parsers/ parsers/
COPY integration/ integration/
COPY qomn_conduit/ qomn_conduit/
COPY qomn_fire/ qomn_fire/
COPY facp_system/ facp_system/
COPY facp_distributed/ facp_distributed/
COPY core/ core/
COPY adapters/ adapters/
COPY marine/ marine/

# Build the wheel + install it (and all dependencies) into /install prefix.
# The wheel is a real Python wheel with all source files; without copying
# the source above, find_packages() returns nothing and `pip install .`
# silently produces an EMPTY package (7KB dist-info only).
RUN pip install --no-cache-dir --prefix=/install .

# ─── Stage 3: Runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="FireAI" \
      org.opencontainers.image.description="Safety-Critical Fire Protection Digital Twin — NFPA 72-2022" \
      org.opencontainers.image.version="1.55.0" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/ahmdelbaz28-ux/revit" \
      maintainer="FireAI Engineering Team"

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r fireai \
    && useradd -r -g fireai -d /app -s /sbin/nologin -c "FireAI Service" fireai

WORKDIR /app

# Copy installed Python packages (deps + the fireai wheel itself)
COPY --from=python-builder /install /usr/local

# Copy application source code for runtime imports (e.g. uvicorn backend.app:app
# imports `backend` from CWD /app, not from site-packages).
COPY --chown=fireai:fireai backend/ backend/
COPY --chown=fireai:fireai fireai/ fireai/
COPY --chown=fireai:fireai parsers/ parsers/
COPY --chown=fireai:fireai integration/ integration/
COPY --chown=fireai:fireai pyproject.toml ./
COPY --chown=fireai:fireai qomn_conduit/ qomn_conduit/
COPY --chown=fireai:fireai qomn_fire/ qomn_fire/
COPY --chown=fireai:fireai facp_system/ facp_system/
COPY --chown=fireai:fireai facp_distributed/ facp_distributed/

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
    PYTHONPATH=/app

USER fireai

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# C-2 FIX: Default to 1 worker for SQLite (WAL mode allows concurrent reads
# but concurrent writes from multiple processes risk SQLITE_BUSY/data corruption).
# For multi-worker deployments, use PostgreSQL via deploy/docker/docker-compose.yml
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
