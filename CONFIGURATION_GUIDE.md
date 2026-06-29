# FireAI Platform Configuration Guide

## Table of Contents
- [Overview](#overview)
- [Core Configuration](#core-configuration)
- [Database Configuration](#database-configuration)
- [Cache Configuration](#cache-configuration)
- [API Configuration](#api-configuration)
- [Security Configuration](#security-configuration)
- [Logging Configuration](#logging-configuration)
- [External Service Integration](#external-service-integration)
- [Performance Tuning](#performance-tuning)

## Overview

This guide provides detailed information about all configurable aspects of the FireAI platform. The platform uses environment variables for configuration, allowing for flexible deployment across different environments.

## Core Configuration

### Environment Variables

The core configuration is managed through environment variables that control the application's behavior:

#### Basic Environment Settings
- `FIREAI_ENV`: Environment type (development, staging, production)
- `FIREAI_VERSION`: Current version of the application
- `FIREAI_DEBUG`: Enable debug mode (true/false)

#### Application Paths
- `FIREAI_DATA_DIR`: Directory for storing persistent data (default: /app/data)
- `FIREAI_LOGS_DIR`: Directory for storing logs (default: /app/logs)
- `FIREAI_TMP_DIR`: Directory for temporary files (default: /app/tmp)

## Database Configuration

### PostgreSQL Settings

The platform uses PostgreSQL as the primary database with asyncpg driver for asynchronous operations.

#### Connection Parameters
- `DATABASE_URL`: Complete database connection string
  - Format: `postgresql+asyncpg://user:password@host:port/database`
  - Example: `postgresql+asyncpg://fireai:mypassword@db:5432/fireai`

#### Migration Settings
- `FIREAI_DB_MIGRATE_ON_STARTUP`: Automatically run migrations on startup (true/false)
- `FIREAI_DB_POOL_SIZE`: Database connection pool size (default: 5)
- `FIREAI_DB_POOL_MAX_OVERFLOW`: Maximum pool overflow (default: 10)

#### Backup Settings
- `FIREAI_DB_BACKUP_ENABLED`: Enable automated backups (true/false)
- `FIREAI_DB_BACKUP_INTERVAL`: Backup interval in hours (default: 24)
- `FIREAI_DB_BACKUP_RETENTION_DAYS`: Days to retain backups (default: 30)

## Cache Configuration

### Redis Settings

Redis is used for caching, session storage, and task queue management.

#### Connection Parameters
- `REDIS_URL`: Redis connection string
  - Format: `redis://:password@host:port/db_index`
  - Example: `redis://:mypassword@redis:6379/0`

#### Cache Settings
- `FIREAI_CACHE_TTL`: Default cache TTL in seconds (default: 3600)
- `FIREAI_SESSION_TTL`: Session TTL in seconds (default: 7200)
- `FIREAI_RATE_LIMIT_STORAGE_URL`: Separate Redis instance for rate limiting (optional)

## API Configuration

### API Keys and Authentication

The platform implements a robust API key system with multiple security layers.

#### API Key Settings
- `FIREAI_API_KEY`: Primary API key for general access
- `FIREAI_EVIDENCE_HMAC_KEY`: HMAC key for evidence signing
- `FIREAI_ADMIN_API_KEY`: Administrative API key with elevated permissions

#### Rate Limiting
- `FIREAI_RATE_LIMIT_DEFAULT`: Default rate limit (requests per minute)
- `FIREAI_RATE_LIMIT_PROJECTS`: Rate limit for project operations
- `FIREAI_RATE_LIMIT_DEVICES`: Rate limit for device operations
- `FIREAI_RATE_LIMIT_CONNECTIONS`: Rate limit for connection operations

### API Versioning
- `FIREAI_API_V1_ENABLED`: Enable v1 API endpoints (true/false)
- `FIREAI_API_V2_ENABLED`: Enable v2 API endpoints (true/false)
- `FIREAI_API_DEPRECATION_WARNING`: Show deprecation warnings (true/false)

## Security Configuration

### Security Headers and Middleware

The platform implements multiple layers of security middleware.

#### Security Settings
- `FIREAI_CORS_ORIGINS`: Comma-separated list of allowed origins
- `FIREAI_CSRF_ENABLED`: Enable CSRF protection (true/false)
- `FIREAI_SECURITY_HEADERS_ENABLED`: Enable security headers (true/false)

#### Content Security Policy
- `FIREAI_CSP_DEFAULT_SRC`: Default CSP policy
- `FIREAI_CSP_SCRIPT_SRC`: Script CSP policy
- `FIREAI_CSP_STYLE_SRC`: Style CSP policy
- `FIREAI_CSP_IMG_SRC`: Image CSP policy

### Authentication Settings
- `FIREAI_AUTH_JWT_SECRET`: JWT secret key for token signing
- `FIREAI_AUTH_JWT_ALGORITHM`: JWT algorithm (default: HS256)
- `FIREAI_AUTH_JWT_EXPIRATION_MINUTES`: JWT expiration in minutes (default: 1440)

## Logging Configuration

### Log Levels and Output

The platform supports multiple log levels and output destinations.

#### Log Settings
- `LOG_LEVEL`: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `FIREAI_LOG_FORMAT`: Log format (json, text, default: json)
- `FIREAI_LOG_TO_CONSOLE`: Enable console logging (true/false)
- `FIREAI_LOG_TO_FILE`: Enable file logging (true/false)

#### Log Rotation
- `FIREAI_LOG_MAX_SIZE_MB`: Maximum log file size in MB (default: 100)
- `FIREAI_LOG_BACKUP_COUNT`: Number of backup log files (default: 5)
- `FIREAI_LOG_RETENTION_DAYS`: Days to retain log files (default: 30)

### Audit Logging
- `FIREAI_AUDIT_LOG_ENABLED`: Enable audit logging (true/false)
- `FIREAI_AUDIT_LOG_SENSITIVE`: Include sensitive data in audit logs (true/false)
- `FIREAI_AUDIT_LOG_RETENTION_DAYS`: Days to retain audit logs (default: 90)

## External Service Integration

### Third-Party Services

The platform can integrate with various external services for enhanced functionality.

#### Google Gemini AI
- `GEMINI_API_KEY`: Google Gemini API key
- `FIREAI_MEMORY_LLM_PROVIDER`: LLM provider (default: gemini)
- `FIREAI_MEMORY_LLM_MODEL`: LLM model to use (default: gemini-2.0-flash)

#### Database Connection Settings
- `FIREAI_DB_CONNECT_TIMEOUT`: Database connection timeout in seconds (default: 10)
- `FIREAI_DB_COMMAND_TIMEOUT`: Database command timeout in seconds (default: 30)
- `FIREAI_DB_IDLE_CONNECTION_TIMEOUT`: Idle connection timeout in seconds (default: 60)

## Performance Tuning

### Resource Limits

Configure resource usage to optimize performance for your environment.

#### Memory Settings
- `FIREAI_MEMORY_CACHE_SIZE`: Size of in-memory cache in MB (default: 128)
- `FIREAI_MEMORY_WORKER_CONCURRENCY`: Number of concurrent workers (default: 4)

#### Processing Settings
- `FIREAI_PROCESSING_TIMEOUT`: Processing timeout in seconds (default: 300)
- `FIREAI_BATCH_SIZE`: Batch processing size (default: 100)
- `FIREAI_PARALLEL_TASKS`: Number of parallel tasks (default: 8)

### Connection Pooling
- `FIREAI_HTTP_CLIENT_TIMEOUT`: HTTP client timeout (default: 30)
- `FIREAI_HTTP_POOL_LIMITS`: HTTP connection pool limits
  - Max connections: 100
  - Max keep-alive: 20

## Environment-Specific Configurations

### Development Environment
```
FIREAI_ENV=development
LOG_LEVEL=DEBUG
FIREAI_DB_MIGRATE_ON_STARTUP=true
FIREAI_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
FIREAI_RATE_LIMIT_DEFAULT=100/minute
```

### Production Environment
```
FIREAI_ENV=production
LOG_LEVEL=WARNING
FIREAI_DB_MIGRATE_ON_STARTUP=false
FIREAI_CORS_ORIGINS=https://yourdomain.com
FIREAI_RATE_LIMIT_DEFAULT=10/minute
FIREAI_SECURITY_HEADERS_ENABLED=true
FIREAI_CSRF_ENABLED=true
FIREAI_AUDIT_LOG_ENABLED=true
```

### Staging Environment
```
FIREAI_ENV=staging
LOG_LEVEL=INFO
FIREAI_DB_MIGRATE_ON_STARTUP=true
FIREAI_CORS_ORIGINS=https://staging.yourdomain.com
FIREAI_RATE_LIMIT_DEFAULT=50/minute
FIREAI_SECURITY_HEADERS_ENABLED=true
```

## Configuration Validation

### Required Variables
The following environment variables are required for the application to start:

1. `FIREAI_API_KEY`
2. `FIREAI_EVIDENCE_HMAC_KEY`
3. `DATABASE_URL`
4. `REDIS_URL`

### Optional Variables with Defaults
Many configuration variables have sensible defaults, but you may want to customize them based on your requirements.

## Configuration Examples

### Complete Production Configuration
```bash
# Environment
FIREAI_ENV=production
FIREAI_VERSION=1.55.0

# Database
DATABASE_URL=postgresql+asyncpg://fireai:prod_password@postgres:5432/fireai
FIREAI_DB_POOL_SIZE=10
FIREAI_DB_POOL_MAX_OVERFLOW=20

# Cache
REDIS_URL=redis://:prod_redis_password@redis:6379/0
FIREAI_CACHE_TTL=7200

# API
FIREAI_API_KEY=your_production_api_key
FIREAI_EVIDENCE_HMAC_KEY=your_production_hmac_key
FIREAI_RATE_LIMIT_DEFAULT=10/minute

# Security
FIREAI_CORS_ORIGINS=https://yourdomain.com
FIREAI_SECURITY_HEADERS_ENABLED=true
FIREAI_CSRF_ENABLED=true

# Logging
LOG_LEVEL=WARNING
FIREAI_AUDIT_LOG_ENABLED=true

# Performance
FIREAI_MEMORY_WORKER_CONCURRENCY=8
FIREAI_PROCESSING_TIMEOUT=600
```

### Configuration Best Practices

1. **Secure Storage**: Store sensitive configuration in secure vaults or encrypted environment variables
2. **Validation**: Always validate configuration values during deployment
3. **Documentation**: Document all custom configurations for team members
4. **Monitoring**: Monitor configuration changes and their impact on performance
5. **Backup**: Maintain backup copies of working configurations