FROM python:3.10-slim AS builder
WORKDIR /app
COPY fire-alarm-db/database-design/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    tesseract-ocr \
    tesseract-ocr-ara \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
WORKDIR /app
COPY fire-alarm-db/ .
RUN mkdir -p /app/outputs /app/temp /app/models

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD curl -f http://localhost:8000/healthz || exit 1
EXPOSE 8000
USER 1000:1000
CMD ["python", "database-design/main.py"]