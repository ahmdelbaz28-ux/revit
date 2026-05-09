FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    fonts-liberation \
    libfontconfig1 \
    libfreetype6 \
    libxkbcommon0 \
    tesseract-ocr \
    tesseract-ocr-eng \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY fire-alarm-db/database-design/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY fire-alarm-db/ /app/fire-alarm-db/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "/app/fire-alarm-db/database-design/main.py"]