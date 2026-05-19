# FireAI V5.1.2 - Complete Docker Image
# ================================
# Includes: Python, LibreDWG, FireAI dependencies

FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libredwg-tools \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Copy FireAI code
COPY . .

# Default command
CMD ["python", "-c", "print('FireAI V5.1.2 Ready')"]