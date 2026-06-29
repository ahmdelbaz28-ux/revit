# FireAI Platform Deployment Guide

## Table of Contents
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Configuration Guide](#configuration-guide)
- [Troubleshooting](#troubleshooting)

## Overview

This guide provides step-by-step instructions for deploying the FireAI platform in various environments. The platform consists of multiple services including API servers, workers, databases, and cache systems.

## Prerequisites

### System Requirements
- **CPU**: Minimum 4 cores (8+ recommended)
- **RAM**: Minimum 8GB (16GB+ recommended)
- **Storage**: Minimum 50GB free space
- **OS**: Linux, Windows, or macOS
- **Docker**: Version 20.10 or higher
- **Docker Compose**: Version 2.0 or higher

### Software Dependencies
- Docker Engine
- Docker Compose
- Git
- Python 3.12+ (for local development)

## Environment Setup

### 1. Clone the Repository
```bash
git clone https://github.com/ahmdelbaz28-ux/revit.git
cd revit
```

### 2. Copy Environment Template
```bash
cp .env.sample .env
```

### 3. Configure Environment Variables
Edit the `.env` file with appropriate values:

```bash
# Database Configuration
DB_USER=fireai
DB_PASSWORD=your_secure_password
DB_NAME=fireai

# Redis Configuration
REDIS_PASSWORD=your_redis_password

# API Key Configuration
FIREAI_API_KEY=your_api_key_here
FIREAI_EVIDENCE_HMAC_KEY=your_hmac_key_here

# Gemini API (Optional)
GEMINI_API_KEY=your_gemini_key_here

# Logging Level
LOG_LEVEL=INFO

# Version Tag
FIREAI_VERSION=1.55.0
```

## Docker Deployment

### 1. Navigate to Docker Directory
```bash
cd deploy/docker
```

### 2. Build and Start Services
```bash
docker-compose up --build -d
```

### 3. Check Service Status
```bash
docker-compose ps
```

### 4. View Logs
```bash
docker-compose logs -f api
```

### 5. Stop Services
```bash
docker-compose down
```

## Kubernetes Deployment

### 1. Navigate to Kubernetes Directory
```bash
cd deploy/k8s
```

### 2. Apply Kubernetes Manifests
```bash
kubectl apply -f namespace.yaml
kubectl apply -f secrets.yaml
kubectl apply -f postgres-pvc.yaml
kubectl apply -f redis-pvc.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f redis-deployment.yaml
kubectl apply -f api-deployment.yaml
kubectl apply -f worker-deployment.yaml
kubectl apply -f nginx-deployment.yaml
kubectl apply -f services.yaml
kubectl apply -f ingress.yaml
```

## Configuration Guide

### Environment Variables

#### Database Configuration
- `DB_USER`: PostgreSQL username (default: fireai)
- `DB_PASSWORD`: PostgreSQL password (required)
- `DB_NAME`: PostgreSQL database name (default: fireai)

#### Redis Configuration
- `REDIS_PASSWORD`: Redis password (required)

#### API Configuration
- `FIREAI_API_KEY`: Main API key for authentication (required)
- `FIREAI_EVIDENCE_HMAC_KEY`: HMAC key for evidence signing (required)

#### External Services
- `GEMINI_API_KEY`: Google Gemini API key (optional)
- `FIREAI_MEMORY_LLM_PROVIDER`: LLM provider (default: gemini)
- `FIREAI_MEMORY_LLM_MODEL`: LLM model (default: gemini-2.0-flash)

#### Logging
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

### Security Settings

#### API Key Security
API keys are stored as bcrypt hashes with positive validation caching to prevent timing attacks. Always use strong, randomly generated API keys.

#### Network Security
Services communicate internally via the `fireai-net` Docker network. External access is provided through nginx reverse proxy.

## Troubleshooting

### Common Issues

#### 1. Database Connection Issues
**Symptoms**: API service fails to start with database connection errors
**Solution**: 
- Verify PostgreSQL service is running
- Check database credentials in .env file
- Confirm database service is healthy: `docker-compose exec db pg_isready`

#### 2. Redis Connection Issues
**Symptoms**: Authentication errors or cache misses
**Solution**:
- Verify Redis service is running
- Check Redis password in .env file
- Confirm Redis service is healthy: `docker-compose exec redis redis-cli ping`

#### 3. API Health Check Failures
**Symptoms**: API service reports unhealthy status
**Solution**:
- Check API logs: `docker-compose logs api`
- Verify database and Redis connectivity
- Confirm required environment variables are set

#### 4. Worker Service Issues
**Symptoms**: Background jobs not executing
**Solution**:
- Check worker logs: `docker-compose logs worker`
- Verify API connectivity from worker
- Confirm shared volume access

### Diagnostic Commands

#### Check Overall System Health
```bash
docker-compose ps
docker-compose logs --tail=50 api
docker-compose logs --tail=50 worker
docker-compose logs --tail=50 db
docker-compose logs --tail=50 redis
```

#### Test API Connectivity
```bash
curl -H "X-API-Key: YOUR_API_KEY" http://localhost/api/v1/health
```

#### Check Database Schema
```bash
docker-compose exec db psql -U fireai -d fireai -c "\dt"
```

#### Monitor Resource Usage
```bash
docker stats
```

### Recovery Procedures

#### Database Backup and Restore
```bash
# Backup
docker-compose exec db pg_dump -U fireai fireai > backup.sql

# Restore
cat backup.sql | docker-compose exec -T db psql -U fireai fireai
```

#### Rollback Deployment
```bash
# Using specific version tags
docker-compose pull api:PREVIOUS_VERSION
docker-compose pull worker:PREVIOUS_VERSION
docker-compose pull nginx:PREVIOUS_VERSION
docker-compose up -d
```

## Production Considerations

### Scaling Recommendations
- **API Service**: Scale to 2+ replicas for high availability
- **Worker Service**: Adjust replica count based on workload
- **Database**: Consider read replicas for heavy read workloads
- **Redis**: Consider cluster mode for high availability

### Security Best Practices
- Rotate API keys regularly
- Use strong, unique passwords for all services
- Implement network segmentation
- Regular security audits and updates
- Enable SSL/TLS for all external communications

### Monitoring and Alerting
- Monitor service health and resource usage
- Set up alerts for failed health checks
- Log aggregation and analysis
- Performance monitoring