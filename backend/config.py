"""
backend/config.py — Centralized Configuration for Multi-Database Setup
========================================================

Configuration management for:
- PostgreSQL (primary database)
- Qdrant (vector database)
- Neo4j (graph database)
- Redis (cache/database)
"""

from __future__ import annotations

import os
from typing import Optional

# Load .env file before reading any configuration values.
# This ensures environment variables from .env are available to os.environ.get()
# throughout the Config class and any module that imports config.
# Falls back gracefully if python-dotenv is not installed.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # Never override real environment variables
except ImportError:
    pass


class Config:
    """Centralized configuration for all database connections."""

    # V254 FIX: Unified database paths. Previously DATABASE_URL defaulted to
    # relative "sqlite:///./db/digital_twin.db" (CWD-dependent, outside /app/data
    # volume) while DIGITAL_TWIN_DB_PATH defaulted to an absolute path. This
    # caused data loss on container restart. Now both default to /app/data/.
    _DEFAULT_DB_DIR = os.environ.get("FIREAI_DATA_DIR", "/app/data")
    _DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "digital_twin.db")

    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{_DEFAULT_DB_PATH}"  # Default: absolute path inside /app/data
    )

    # Digital Twin Database Path (for the existing system)
    DIGITAL_TWIN_DB_PATH: str = os.environ.get(
        "DIGITAL_TWIN_DB_PATH",
        _DEFAULT_DB_PATH  # Same path as DATABASE_URL — no more divergence
    )

    # Qdrant Configuration (Vector Database)
    QDRANT_HOST: Optional[str] = os.environ.get("QDRANT_HOST")  # V257: was 'localhost'
    QDRANT_PORT: int = int(os.environ.get("QDRANT_PORT", 6333))
    QDRANT_API_KEY: Optional[str] = os.environ.get("QDRANT_API_KEY")
    QDRANT_URL: Optional[str] = os.environ.get("QDRANT_URL")  # For cloud instances

    # Neo4j Configuration (Graph Database)
    NEO4J_URI: Optional[str] = os.environ.get("NEO4J_URI")  # V257: was 'bolt://localhost:7687'
    NEO4J_USERNAME: str = os.environ.get("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD: str = os.environ.get("NEO4J_PASSWORD", "")
    NEO4J_DATABASE: str = os.environ.get("NEO4J_DATABASE", "neo4j")

    # Redis Configuration (Cache/Temporary Storage)
    REDIS_URL: Optional[str] = os.environ.get("REDIS_URL")  # V257: was 'redis://localhost:6379'
    REDIS_HOST: Optional[str] = os.environ.get("REDIS_HOST")  # V257: was 'localhost'
    REDIS_PORT: int = int(os.environ.get("REDIS_PORT", 6379))
    REDIS_PASSWORD: Optional[str] = os.environ.get("REDIS_PASSWORD")
    REDIS_DB: int = int(os.environ.get("REDIS_DB", 0))

    # ── Akamai Edge Integration ────────────────────────────────────────────
    # When AKAMAI_ENABLED=true, the backend trusts Akamai headers
    # (True-Client-IP, Akamai-Internal, Akamai-Bot-Score, Akamai-Geo-Country)
    # and rejects direct origin access in production.
    # See backend/akamai_middleware.py for the full integration.
    AKAMAI_ENABLED: bool = os.environ.get("AKAMAI_ENABLED", "false").lower() in (
        "true", "1", "yes", "on",
    )
    # Shared secret injected by Akamai EdgeWorker / Property Manager.
    # When set, requests without this header are rejected in production.
    AKAMAI_REQUIRE_ORIGIN_TOKEN: str = os.environ.get(
        "AKAMAI_REQUIRE_ORIGIN_TOKEN", ""
    ).strip()
    # Comma-separated ISO 3166-1 alpha-2 country codes to block (e.g. "CN,RU,IR,KP")
    AKAMAI_BLOCKED_COUNTRIES: str = os.environ.get("AKAMAI_BLOCKED_COUNTRIES", "")
    # Bot score threshold (0-100, 0=human, 100=bot) for sensitive endpoints.
    # Requests above this score on /api/v1/auth/* are rejected.
    AKAMAI_ALLOWED_BOT_SCORE: int = int(os.environ.get("AKAMAI_ALLOWED_BOT_SCORE", "30"))
    # Forward Akamai's X-RateLimit-* response headers to the client
    AKAMAI_RATE_LIMIT_HEADER: bool = os.environ.get(
        "AKAMAI_RATE_LIMIT_HEADER", "true"
    ).lower() in ("true", "1", "yes", "on")

    # Additional settings
    ENVIRONMENT: str = os.environ.get("FIREAI_ENV", "production")
    DEBUG: bool = ENVIRONMENT.lower() == "development"

    @classmethod
    def validate_config(cls) -> list[str]:
        """Validate configuration and return list of warnings/errors."""
        issues = []

        # Check if PostgreSQL connection string format is valid (if using PostgreSQL)
        if cls.DATABASE_URL.startswith(("postgres://", "postgresql://")):
            if not all(part in cls.DATABASE_URL for part in ["//", "@"]):
                issues.append("DATABASE_URL may have invalid PostgreSQL format")

        # Check if Neo4j has credentials when using remote server
        if not cls.NEO4J_URI.startswith("bolt://localhost") and not cls.NEO4J_PASSWORD:
            issues.append("Neo4j remote connection detected without password")

        return issues


# Singleton instance
config = Config()
