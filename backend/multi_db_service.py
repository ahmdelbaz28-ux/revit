# NOSONAR
"""
backend/multi_db_service.py — Multi-Database Service Layer
==========================================================

Unified service layer for managing multiple database backends:
- PostgreSQL (primary relational data)
- Qdrant (vector database for embeddings/RAG)
- Neo4j (graph database for relationships/topology)
- Redis (cache and temporary storage)

This service provides abstraction over multiple database technologies
while maintaining thread safety and proper resource management.
"""

from __future__ import annotations

import importlib.util
import logging
import threading
from contextlib import contextmanager
from typing import Any, Optional

import redis

from backend.config import config

# Optional imports with graceful degradation
try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False
    QdrantClient = None
    models = None

try:
    from neo4j import GraphDatabase
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False
    GraphDatabase = None

try:
    HAS_POSTGRES = importlib.util.find_spec("psycopg2") is not None
    if HAS_POSTGRES:
        from psycopg2 import pool as pg_pool  # type: ignore[import-untyped]
    else:
        pg_pool = None  # type: ignore[assignment]
except ImportError:
    HAS_POSTGRES = False
    pg_pool = None

logger = logging.getLogger(__name__)


class MultiDatabaseService:
    """
    Service layer managing connections to multiple database types.

    Handles initialization, connection pooling, and resource cleanup
    for PostgreSQL, Qdrant, Neo4j, and Redis databases.
    """

    def __init__(self):
        self._initialized = False
        self._lock = threading.Lock()

        # Database connections/pools
        self._redis_client: Optional[redis.Redis] = None
        self._qdrant_client: Optional[Any] = None
        self._neo4j_driver: Optional[Any] = None
        self._postgres_pool: Optional[Any] = None

        self.initialize()

    def initialize(self):
        """Initialize all available database connections."""
        with self._lock:
            if self._initialized:
                return

            # Initialize Redis
            self._setup_redis()

            # Initialize Qdrant (vector database)
            self._setup_qdrant()

            # Initialize Neo4j (graph database)
            self._setup_neo4j()

            # Initialize PostgreSQL (if using PostgreSQL backend)
            if config.DATABASE_URL.startswith(("postgres://", "postgresql://")):
                self._setup_postgres()

            self._initialized = True
            logger.info("Multi-database service initialized successfully")

    def _setup_redis(self):
        """Initialize Redis connection."""
        try:
            if config.REDIS_URL and config.REDIS_URL != "redis://localhost:6379":
                self._redis_client = redis.from_url(
                    config.REDIS_URL,
                    decode_responses=True,
                    password=config.REDIS_PASSWORD
                )
            else:
                self._redis_client = redis.Redis(
                    host=config.REDIS_HOST,
                    port=config.REDIS_PORT,
                    db=config.REDIS_DB,
                    password=config.REDIS_PASSWORD,
                    decode_responses=True
                )

            # Test connection
            self._redis_client.ping()
            logger.info("Redis connection established")
        except Exception:
            logger.exception("Failed to connect to Redis")
            self._redis_client = None

    def _setup_qdrant(self):
        """Initialize Qdrant client."""
        if not HAS_QDRANT:
            logger.warning("Qdrant client not installed. Install with: pip install qdrant-client")
            return

        try:
            if config.QDRANT_URL:
                # Cloud instance
                self._qdrant_client = QdrantClient(
                    url=config.QDRANT_URL,
                    api_key=config.QDRANT_API_KEY,
                    prefer_grpc=True
                )
            else:
                # Local instance
                self._qdrant_client = QdrantClient(
                    host=config.QDRANT_HOST,
                    port=config.QDRANT_PORT,
                    api_key=config.QDRANT_API_KEY
                )

            # Test connection
            self._qdrant_client.get_collections()
            logger.info("Qdrant connection established")
        except Exception:
            logger.exception("Failed to connect to Qdrant")
            self._qdrant_client = None

    def _setup_neo4j(self):
        """Initialize Neo4j driver."""
        if not HAS_NEO4J:
            logger.warning("Neo4j driver not installed. Install with: pip install neo4j")
            return

        try:
            self._neo4j_driver = GraphDatabase.driver(
                config.NEO4J_URI,
                auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD)
            )

            # Test connection
            with self._neo4j_driver.session(database=config.NEO4J_DATABASE) as session:
                session.run("RETURN 1")

            logger.info("Neo4j connection established")
        except Exception:
            logger.exception("Failed to connect to Neo4j")
            self._neo4j_driver = None

    def _setup_postgres(self):
        """Initialize PostgreSQL connection pool."""
        if not HAS_POSTGRES:
            logger.warning("PostgreSQL adapter not installed. Install with: pip install psycopg2-binary")
            return

        try:
            self._postgres_pool = pg_pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=20,
                dsn=config.DATABASE_URL,
            )
            logger.info("PostgreSQL connection pool established")
        except Exception:
            logger.exception("Failed to create PostgreSQL pool")
            self._postgres_pool = None

    # Redis methods
    def get_redis(self) -> Optional[redis.Redis]:
        """Get Redis client if available."""
        return self._redis_client

    def redis_set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set a value in Redis."""
        if not self._redis_client:
            return False
        try:
            self._redis_client.set(key, value, ex=ex)
            return True
        except Exception:
            logger.exception("Redis set error")
            return False

    def redis_get(self, key: str) -> Optional[str]:
        """Get a value from Redis."""
        if not self._redis_client:
            return None
        try:
            return self._redis_client.get(key)
        except Exception:
            logger.exception("Redis get error")
            return None

    def redis_delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        if not self._redis_client:
            return False
        try:
            return bool(self._redis_client.delete(key))
        except Exception:
            logger.exception("Redis delete error")
            return False

    # Qdrant methods
    def get_qdrant(self) -> Optional[Any]:
        """Get Qdrant client if available."""
        return self._qdrant_client

    def qdrant_upsert_vectors(self, collection_name: str, points: list) -> bool:
        """Upsert vectors to Qdrant collection."""
        if not self._qdrant_client:
            return False
        try:
            self._qdrant_client.upsert(collection_name=collection_name, points=points)
            return True
        except Exception:
            logger.exception("Qdrant upsert error")
            return False

    def qdrant_search(self, collection_name: str, query_vector: list, limit: int = 10) -> list:
        """Search vectors in Qdrant collection."""
        if not self._qdrant_client:
            return []
        try:
            results = self._qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit
            )
            return results
        except Exception:
            logger.exception("Qdrant search error")
            return []

    # Neo4j methods
    def get_neo4j(self) -> Optional[Any]:
        """Get Neo4j driver if available."""
        return self._neo4j_driver

    @contextmanager
    def neo4j_session(self, database: Optional[str] = None):
        """Context manager for Neo4j sessions."""
        if not self._neo4j_driver:
            raise RuntimeError("Neo4j driver not available")

        session = self._neo4j_driver.session(database=database or config.NEO4J_DATABASE)
        try:
            yield session
        finally:
            session.close()

    def neo4j_execute_query(self, query: str, parameters: dict = None, database: Optional[str] = None) -> list:
        """Execute a Cypher query against Neo4j."""
        if not self._neo4j_driver:
            return []

        try:
            with self.neo4j_session(database) as session:
                result = session.run(query, parameters or {})
                return [record.data() for record in result]
        except Exception:
            logger.exception("Neo4j query error")
            return []

    # PostgreSQL methods (when using PostgreSQL as primary DB)
    def get_postgres_pool(self) -> Optional[Any]:
        """Get PostgreSQL connection pool if available."""
        return self._postgres_pool

    @contextmanager
    def postgres_connection(self):
        """Context manager for PostgreSQL connections."""
        if not self._postgres_pool:
            raise RuntimeError("PostgreSQL pool not available")

        conn = self._postgres_pool.getconn()
        try:
            yield conn
        finally:
            self._postgres_pool.putconn(conn)

    def postgres_execute(self, query: str, parameters: tuple = None) -> list:
        """Execute a query against PostgreSQL."""
        if not self._postgres_pool:
            return []

        try:
            with self.postgres_connection() as conn:
                cur = conn.cursor()
                cur.execute(query, parameters or ())
                if query.strip().upper().startswith("SELECT"):
                    results = cur.fetchall()
                    cur.close()
                    return results
                else:
                    conn.commit()
                    cur.close()
                    return []
        except Exception:
            logger.exception("PostgreSQL query error")
            return []

    def health_check(self) -> dict:
        """Perform health check on all database connections."""
        return {
            "redis": self._redis_client is not None,
            "qdrant": self._qdrant_client is not None,
            "neo4j": self._neo4j_driver is not None,
            "postgres": self._postgres_pool is not None,
        }

    def close(self):
        """
        Close all database connections.

        V201 (SonarCloud S8572/S2148): All exception handlers in this method
        previously used bare `except Exception: pass`, silently swallowing
        errors during shutdown — making connection-leak debugging impossible.
        Each handler now logs the exception with full traceback via
        `logger.exception()` (which automatically includes the exception
        info from `sys.exc_info()`). The cleanup still proceeds (the
        client is set to None regardless) because the goal of close()
        is best-effort teardown.
        """
        with self._lock:
            # Close Redis
            if self._redis_client:
                try:
                    self._redis_client.close()
                except Exception:
                    logger.exception("Failed to close Redis client")
                self._redis_client = None

            # Close Qdrant
            if self._qdrant_client:
                try:
                    self._qdrant_client.close()
                except Exception:
                    logger.exception("Failed to close Qdrant client")
                self._qdrant_client = None

            # Close Neo4j
            if self._neo4j_driver:
                try:
                    self._neo4j_driver.close()
                except Exception:
                    logger.exception("Failed to close Neo4j driver")
                self._neo4j_driver = None

            # Close PostgreSQL pool
            if self._postgres_pool:
                try:
                    self._postgres_pool.closeall()
                except Exception:
                    logger.exception("Failed to close PostgreSQL pool")
                self._postgres_pool = None

            self._initialized = False
            logger.info("Multi-database service connections closed")


# Global instance
_multi_db_service: Optional[MultiDatabaseService] = None
_multi_db_lock = threading.Lock()


def get_multi_db_service() -> MultiDatabaseService:
    """Get or create the singleton MultiDatabaseService instance."""
    global _multi_db_service
    if _multi_db_service is None:
        with _multi_db_lock:
            if _multi_db_service is None:
                _multi_db_service = MultiDatabaseService()
    return _multi_db_service


def close_multi_db_service():
    """Close the global MultiDatabaseService instance."""
    global _multi_db_service
    if _multi_db_service:
        _multi_db_service.close()
        _multi_db_service = None
