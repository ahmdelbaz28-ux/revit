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

    # PostgreSQL Configuration (Primary Database)
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "sqlite:///./db/digital_twin.db"  # Default fallback
    )

    # Digital Twin Database Path (for the existing system)
    DIGITAL_TWIN_DB_PATH: str = os.environ.get(
        "DIGITAL_TWIN_DB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "digital_twin.db")
    )

    # Qdrant Configuration (Vector Database)
    QDRANT_HOST: Optional[str] = os.environ.get("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.environ.get("QDRANT_PORT", 6333))
    QDRANT_API_KEY: Optional[str] = os.environ.get("QDRANT_API_KEY")
    QDRANT_URL: Optional[str] = os.environ.get("QDRANT_URL")  # For cloud instances

    # Neo4j Configuration (Graph Database)
    NEO4J_URI: str = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USERNAME: str = os.environ.get("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD: str = os.environ.get("NEO4J_PASSWORD", "")
    NEO4J_DATABASE: str = os.environ.get("NEO4J_DATABASE", "neo4j")

    # Redis Configuration (Cache/Temporary Storage)
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379")
    REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
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
    ENVIRONMENT: str = os.environ.get("FIREAI_ENV", "development")
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
