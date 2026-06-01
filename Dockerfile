# ═══════════════════════════════════════════════════════════════════════════
# FireAI — Safety-Critical Fire Protection Digital Twin
# Multi-stage Docker build for reproducible, secure deployment
# ═══════════════════════════════════════════════════════════════════════════
# SECURITY NOTES:
#   - Non-root user (fireai)
#   - No build tools in final image
#   - Health check built in
#   - Minimal attack surface
# ═══════════════════════════════════════════════════════════════════════════

# ─── Stage 1: Build ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 2: Runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="FireAI Engineering Team"
LABEL description="Safety-Critical Fire Protection Digital Twin — NFPA 72-2022"
LABEL version="1.0.0"

# Security: Create non-root user
RUN groupadd -r fireai && \
    useradd -r -g fireai -d /app -s /sbin/nologin -c "FireAI Service" fireai

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=fireai:fireai . .

# Create data and logs directories
RUN mkdir -p /app/data /app/logs && \
    chown -R fireai:fireai /app/data /app/logs

# Security: Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIREAI_ENV=production \
    LOG_LEVEL=WARNING

# Switch to non-root user
USER fireai

# Expose API port
EXPOSE 8000

# Health check — verify the API is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Start the FastAPI server
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
