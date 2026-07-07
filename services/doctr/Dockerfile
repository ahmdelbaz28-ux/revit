# services/doctr/Dockerfile — DocTR OCR Service for FireAI
# Provides OCR with bounding boxes for scanned floor plans.
# Runs as a separate Docker container — no AGPL contamination.
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for OpenCV + DocTR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .  # NOSONAR: S6470 .dockerignore filters sensitive files
# Create non-root user for security (S6471)
RUN useradd -m -u 1000 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
