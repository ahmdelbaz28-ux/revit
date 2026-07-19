# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
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
            # V257: Skip if neither REDIS_URL nor REDIS_HOST is configured.
            # Previously defaulted to localhost, causing 3s timeout in production.
            if not config.REDIS_URL and not config.REDIS_HOST:
                logger.info("Redis not configured (REDIS_URL/REDIS_HOST not set) — skipping")
                return
            if config.REDIS_URL:
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

        # V257: Skip if Qdrant is not configured
        if not config.QDRANT_URL and not config.QDRANT_HOST:
            logger.info("Qdrant not configured (QDRANT_URL/QDRANT_HOST not set) — skipping")
            return

        try:
            if config.QDRANT_URL:
                self._qdrant_client = QdrantClient(
                    url=config.QDRANT_URL,
                    api_key=config.QDRANT_API_KEY,
                    prefer_grpc=True
                )
            else:
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

        # V257: Skip if Neo4j is not configured
        if not config.NEO4J_URI:
            logger.info("Neo4j not configured (NEO4J_URI not set) — skipping")
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

    # ─── V282 FIX: BIM-specific convenience methods ────────────────────────
    # These 6 methods were referenced by backend/routers/multi_db.py but
    # never defined on MultiDatabaseService — every endpoint would raise
    # AttributeError at runtime. Now implemented as thin wrappers over the
    # existing primitives (redis_set/redis_get, qdrant_upsert_vectors/
    # qdrant_search, neo4j_execute_query).
    #
    # All methods are fail-safe: return False/[] when the underlying client
    # is unavailable (e.g., dev environment without Redis/Qdrant/Neo4j).

    BIM_REDIS_PREFIX = "bim:element:"
    BIM_QDRANT_COLLECTION = "bim_elements"

    def cache_bim_element(self, element_id: str, element_data: dict) -> bool:
        """Cache BIM element data in Redis (JSON-serialized)."""
        if not element_id or not isinstance(element_data, dict):
            return False
        try:
            import json
            payload = json.dumps(element_data, default=str)
            return self.redis_set(f"{self.BIM_REDIS_PREFIX}{element_id}", payload, ex=86400)
        except Exception:
            logger.exception("cache_bim_element failed")
            return False

    def get_cached_bim_element(self, element_id: str) -> Optional[dict]:
        """Retrieve cached BIM element data from Redis."""
        if not element_id:
            return None
        try:
            import json
            payload = self.redis_get(f"{self.BIM_REDIS_PREFIX}{element_id}")
            if payload is None:
                return None
            return json.loads(payload)
        except Exception:
            logger.exception("get_cached_bim_element failed")
            return None

    def store_element_embeddings(self, element_id: str, embeddings: list) -> bool:
        """Store element embeddings in Qdrant for similarity search."""
        if not element_id or not isinstance(embeddings, list) or not embeddings:
            return False
        if not self._qdrant_client:
            logger.warning("store_element_embeddings: Qdrant not available")
            return False
        try:
            # Qdrant PointStruct: {"id": <str|uuid>, "vector": [...], "payload": {...}}
            points = [{"id": element_id, "vector": embeddings, "payload": {"element_id": element_id}}]
            return self.qdrant_upsert_vectors(self.BIM_QDRANT_COLLECTION, points)
        except Exception:
            logger.exception("store_element_embeddings failed")
            return False

    def find_similar_elements(self, query_embedding: list, limit: int = 5) -> list:
        """Find similar BIM elements using Qdrant vector search."""
        if not isinstance(query_embedding, list) or not query_embedding:
            return []
        if not self._qdrant_client:
            logger.warning("find_similar_elements: Qdrant not available")
            return []
        try:
            results = self.qdrant_search(self.BIM_QDRANT_COLLECTION, query_embedding, limit=limit)
            # Normalize Qdrant results to a plain dict list for JSON response.
            normalized = []
            for r in results:
                # Qdrant returns ScoredPoint objects — extract fields defensively.
                payload = getattr(r, "payload", None) or (r.get("payload") if isinstance(r, dict) else {}) or {}
                score = getattr(r, "score", None) if not isinstance(r, dict) else r.get("score")
                element_id = payload.get("element_id", "")
                normalized.append({"element_id": element_id, "score": score, "payload": payload})
            return normalized
        except Exception:
            logger.exception("find_similar_elements failed")
            return []

    def create_element_relationships(
        self, element_id: str, related_elements: list, relationship_type: str = "CONNECTED_TO"
    ) -> bool:
        """Create relationships between elements in Neo4j (graph database).

        Creates a MERGE pattern: (a:Element {id: $element_id})
        -[:relationship_type]-> (b:Element {id: $related_id})
        for each related_id in related_elements.
        """
        if not element_id or not isinstance(related_elements, list) or not related_elements:
            return False
        if not self._neo4j_driver:
            logger.warning("create_element_relationships: Neo4j not available")
            return False
        # V282 SECURITY: relationship_type must be a valid Cypher identifier
        # to prevent Cypher injection. Allow only [A-Z_]+ after uppercasing.
        import re
        if not re.match(r"^[A-Z][A-Z0-9_]*$", relationship_type.upper()):
            logger.error("create_element_relationships: invalid relationship_type %r", relationship_type)
            return False
        rel_type = relationship_type.upper()
        try:
            # MERGE ensures idempotency (no duplicate nodes/edges on retry).
            query = (
                f"MERGE (a:Element {{id: $element_id}}) "
                f"WITH a "
                f"UNWIND $related_elements AS related_id "
                f"MERGE (b:Element {{id: related_id}}) "
                f"MERGE (a)-[:{rel_type}]->(b)"
            )
            with self.neo4j_session() as session:
                session.run(query, {"element_id": element_id, "related_elements": related_elements})
            return True
        except Exception:
            logger.exception("create_element_relationships failed")
            return False

    def neo4j_find_related_elements(self, element_id: str, relationship_type: str = "CONNECTED_TO") -> list:
        """Find elements related to a specific element in Neo4j.

        Traverses outgoing relationships of the given type from the source
        element. Returns a list of {"element_id": ..., "relationship_type": ...}.
        """
        if not element_id:
            return []
        if not self._neo4j_driver:
            logger.warning("neo4j_find_related_elements: Neo4j not available")
            return []
        # V282 SECURITY: relationship_type must be a valid Cypher identifier.
        import re
        if not re.match(r"^[A-Z][A-Z0-9_]*$", relationship_type.upper()):
            logger.error("neo4j_find_related_elements: invalid relationship_type %r", relationship_type)
            return []
        rel_type = relationship_type.upper()
        try:
            query = (
                f"MATCH (a:Element {{id: $element_id}})-[:{rel_type}]->(b:Element) "
                f"RETURN b.id AS element_id"
            )
            with self.neo4j_session() as session:
                result = session.run(query, {"element_id": element_id})
                return [{"element_id": record["element_id"], "relationship_type": rel_type}
                        for record in result]
        except Exception:
            logger.exception("neo4j_find_related_elements failed")
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
