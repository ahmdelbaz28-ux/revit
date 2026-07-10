# Multi-Database Setup Guide

This guide explains how to configure and use the multi-database system in the Revit project, supporting PostgreSQL, Qdrant, Neo4j, and Redis.

## Overview

The application supports four types of databases:

1. **PostgreSQL** - Primary relational database (via Supabase)
2. **Qdrant** - Vector database for embeddings and RAG (Retrieval Augmented Generation)
3. **Neo4j** - Graph database for relationship modeling and topology
4. **Redis** - In-memory cache and temporary storage

## Configuration

### Automatic Setup

Run the interactive setup script to configure all databases:

```bash
python setup_databases.py
```

This will generate a `.env` file with all the necessary environment variables.

### Manual Configuration

Create a `.env` file in the project root with the following variables:

```bash
# PostgreSQL (Supabase)
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@aws-0-us-west-1.pooler.supabase.com:5432/postgres
DIGITAL_TWIN_DB_PATH=./db/digital_twin.db

# Qdrant (Vector Database)
QDRANT_URL=https://your-cluster-url.gcp.qdrant.tech:6333  # For cloud
# Or for local:
# QDRANT_HOST=localhost
# QDRANT_PORT=6333
QDRANT_API_KEY=your-qdrant-api-key

# Neo4j (Graph Database)
NEO4J_URI=bolt+s://your-instance.databases.neo4j.io:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-neo4j-password
NEO4J_DATABASE=neo4j

# Redis (Cache/Storage)
REDIS_URL=redis://your-upstash-url.upstash.io:37463
# Or for local:
# REDIS_HOST=localhost
# REDIS_PORT=6379
# REDIS_PASSWORD=your-redis-password
# REDIS_DB=0

# Application
FIREAI_API_KEY=your-api-key
FIREAI_ENV=development
```

## Database Providers

### 1. PostgreSQL (Supabase) - Free Tier Available

- Visit [https://supabase.com](https://supabase.com) to create an account
- Create a new project
- Find your connection string in Project Settings → Database
- The free tier includes 500MB storage and 10M monthly active users

### 2. Qdrant (Vector Database) - Free Tier Available

- Visit [https://cloud.qdrant.io](https://cloud.qdrant.io) to create an account
- Create a new cluster
- Get your cluster URL and API key
- The free tier includes 1M vectors and 1GB storage

### 3. Neo4j (Graph Database) - AuraDB Free Tier

- Visit [https://neo4j.com/cloud/platform/aura-graph-database/](https://neo4j.com/cloud/platform/aura-graph-database/) to create an account
- Create a new AuraDB instance
- Get your connection URI, username, and password
- The free tier includes 5GB storage and 100M ops/month

### 4. Redis (Cache) - Upstash Free Tier

- Visit [https://upstash.com](https://upstash.com) to create an account
- Create a new Redis database
- Get your connection URL
- The free tier includes 100MB storage and 10k ops/day

## Usage in Code

The multi-database service is available throughout the application:

```python
from backend.multi_db_service import get_multi_db_service

# Get the service instance
db_service = get_multi_db_service()

# Access individual databases:
redis_client = db_service.get_redis()
qdrant_client = db_service.get_qdrant()
neo4j_driver = db_service.get_neo4j()
postgres_pool = db_service.get_postgres_pool()

# Example usage:
# Redis
db_service.redis_set("key", "value", ex=3600)  # Expires in 1 hour
value = db_service.redis_get("key")

# Qdrant
db_service.qdrant_upsert_vectors("collection_name", points=[...])

# Neo4j
result = db_service.neo4j_execute_query("MATCH (n) RETURN n LIMIT 10")

# PostgreSQL
result = db_service.postgres_execute("SELECT * FROM projects LIMIT 10")
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `DIGITAL_TWIN_DB_PATH` | Path to SQLite fallback DB | ./db/digital_twin.db |
| `QDRANT_URL` | Qdrant cloud instance URL | - |
| `QDRANT_HOST` | Qdrant host (local) | localhost |
| `QDRANT_PORT` | Qdrant port | 6333 |
| `QDRANT_API_KEY` | Qdrant authentication key | - |
| `NEO4J_URI` | Neo4j connection URI | bolt://localhost:7687 |
| `NEO4J_USERNAME` | Neo4j username | neo4j |
| `NEO4J_PASSWORD` | Neo4j password | - |
| `NEO4J_DATABASE` | Neo4j database name | neo4j |
| `REDIS_URL` | Redis connection URL | - |
| `REDIS_HOST` | Redis host | localhost |
| `REDIS_PORT` | Redis port | 6379 |
| `REDIS_PASSWORD` | Redis password | - |
| `REDIS_DB` | Redis database number | 0 |
| `FIREAI_ENV` | Environment (development/production) | development |

## Dependencies

Install the required dependencies:

```bash
pip install psycopg2-binary qdrant-client neo4j redis
```

Or with the project:

```bash
pip install -e ".[dev]"
```

## Health Check

The application provides a health check endpoint at `/api/database-health` to verify all database connections are working.