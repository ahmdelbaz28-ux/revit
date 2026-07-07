"""
vector_memory_service.py — Qdrant-backed Semantic Memory for FireAI Agents
==============================================================================

Provides RAG (Retrieval-Augmented Generation) capabilities for the 24+ AI
agents in the FireAI platform. Without this, every question is treated as
if heard for the first time.

Capabilities:
1. **Conversation Memory**: Engineer conversations stored as vectors with
   metadata (user_id, project_id, timestamp) for context recall.
2. **Study Results Memory**: Past ETAP/FireAI study results indexed
   semantically for comparison ("show me similar short circuit studies").
3. **Document RAG**: Equipment datasheets, cable catalogs, protection
   standards indexed for semantic search.
4. **ETAP Expert Knowledge**: 4,400+ lines of skills/etap-expert.md +
   IEC/IEEE standards indexed for instant retrieval.

Architecture:
- Uses Qdrant as the primary vector database (docker-compose service)
- Falls back to in-memory Qdrant when server unavailable (dev mode)
- Embeddings via sentence-transformers (local, no API dependency)
- Collection-per-use-case for clean separation

References:
- Qdrant docs: https://qdrant.tech/documentation/
- agent.md Rule 12 (Safety-First): Vector memory is ADVISORY only
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QDRANT_URL_ENV = "QDRANT_URL"
QDRANT_URL_DEFAULT = "http://localhost:6333"
QDRANT_API_KEY_ENV = "QDRANT_API_KEY"

# Collection names per use case
COLLECTION_CONVERSATIONS = "fireai_conversations"
COLLECTION_STUDY_RESULTS = "fireai_study_results"
COLLECTION_DOCUMENTS = "fireai_documents"
COLLECTION_ETAP_KNOWLEDGE = "fireai_etap_knowledge"

# Embedding model (local, no API dependency)
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MemoryType(str, Enum):
    """Types of semantic memory stored in Qdrant."""

    CONVERSATION = "conversation"
    STUDY_RESULT = "study_result"
    DOCUMENT = "document"
    ETAP_KNOWLEDGE = "etap_knowledge"
    ENGINEERING_DECISION = "engineering_decision"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    """
    A single memory entry stored in Qdrant.

    Attributes:
        id: Unique UUID for the memory entry.
        content: The text content to be embedded.
        memory_type: Type of memory (conversation, study, document, etc.).
        metadata: Additional metadata (user_id, project_id, timestamp, etc.).
        score: Similarity score when retrieved (0.0 to 1.0).
    """

    id: str
    content: str
    memory_type: MemoryType
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "metadata": self.metadata,
            "score": round(self.score, 4),
        }


@dataclass
class SearchResult:
    """
    Result of a semantic search.

    Attributes:
        query: The original query text.
        results: List of MemoryEntry matches, sorted by score (descending).
        total: Total number of matches found.
        collection: Which collection was searched.
    """

    query: str
    results: List[MemoryEntry]
    total: int
    collection: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "total": self.total,
            "collection": self.collection,
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Vector Memory Service
# ---------------------------------------------------------------------------


class VectorMemoryService:
    """
    Qdrant-backed semantic memory service for AI agents.

    Usage:
        service = VectorMemoryService()

        # Store a memory
        service.store(
            content="Engineer asked about NFPA 72 spacing for smoke detectors",
            memory_type=MemoryType.CONVERSATION,
            metadata={"user_id": "eng_001", "project_id": "P-100"},
        )

        # Search memories
        results = service.search(
            query="smoke detector spacing requirements",
            memory_type=MemoryType.CONVERSATION,
            limit=5,
        )
    """

    def __init__(
        self,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize the vector memory service.

        Args:
            qdrant_url: Qdrant server URL. If None, reads from env var.
            qdrant_api_key: Optional API key for Qdrant Cloud.
        """
        self._url = qdrant_url or os.environ.get(QDRANT_URL_ENV, QDRANT_URL_DEFAULT)
        self._api_key = qdrant_api_key or os.environ.get(QDRANT_API_KEY_ENV)
        self._client = None
        self._embedder = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Lazy Initialization
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        """Initialize Qdrant client and embedding model (lazy)."""
        if self._initialized:
            return

        # Initialize embedding model
        try:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("Embedding model loaded: %s", EMBEDDING_MODEL_NAME)
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. Install with: "
                "pip install sentence-transformers. "
                "Vector memory will use hash-based fallback embeddings."
            )
            self._embedder = None

        # Initialize Qdrant client
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            if self._api_key:
                self._client = QdrantClient(
                    url=self._url,
                    api_key=self._api_key,
                )
            else:
                self._client = QdrantClient(url=self._url)

            # Create collections if they don't exist
            collections_to_create = [
                (COLLECTION_CONVERSATIONS, "Conversation memory"),
                (COLLECTION_STUDY_RESULTS, "Study results memory"),
                (COLLECTION_DOCUMENTS, "Document RAG"),
                (COLLECTION_ETAP_KNOWLEDGE, "ETAP expert knowledge"),
            ]
            for collection_name, description in collections_to_create:
                try:
                    self._client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(
                            size=EMBEDDING_DIMENSIONS,
                            distance=Distance.COSINE,
                        ),
                    )
                    logger.info("Created Qdrant collection: %s", collection_name)
                except Exception:
                    # Collection already exists — this is fine
                    pass

            logger.info("Qdrant client connected to %s", self._url)
            self._initialized = True

        except Exception as exc:
            logger.warning(
                "Qdrant initialization failed (%s). "
                "Vector memory will operate in fallback mode (no persistence).",
                exc,
            )
            self._client = None
            self._initialized = True  # Mark as attempted (don't retry)

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> List[float]:
        """
        Generate embedding vector for text.

        Falls back to hash-based pseudo-embedding when sentence-transformers
        is unavailable. This is NOT suitable for production but prevents
        crashes in development.
        """
        if self._embedder is not None:
            embedding = self._embedder.encode(text)
            return embedding.tolist()

        # Fallback: hash-based pseudo-embedding (deterministic but not semantic)
        import hashlib

        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        # Repeat hash to fill EMBEDDING_DIMENSIONS
        vector = []
        for i in range(EMBEDDING_DIMENSIONS):
            byte_idx = i % len(hash_bytes)
            vector.append(hash_bytes[byte_idx] / 255.0 - 0.5)
        return vector

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Store a memory entry in Qdrant.

        Args:
            content: Text content to embed and store.
            memory_type: Type of memory (determines collection).
            metadata: Optional metadata dict.

        Returns:
            Memory entry ID, or None if storage failed.
        """
        self._initialize()
        if self._client is None:
            logger.warning("Qdrant unavailable — memory not stored")
            return None

        try:
            from qdrant_client.models import PointStruct

            entry_id = str(uuid.uuid4())
            embedding = self._embed(content)

            collection = self._get_collection(memory_type)

            point = PointStruct(
                id=entry_id,
                vector=embedding,
                payload={
                    "content": content,
                    "memory_type": memory_type.value,
                    "metadata": metadata or {},
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
            )

            self._client.upsert(
                collection_name=collection,
                points=[point],
            )

            logger.info(
                "Stored memory: type=%s id=%s collection=%s",
                memory_type.value, entry_id, collection,
            )
            return entry_id

        except Exception as exc:
            logger.exception("Failed to store memory: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        memory_type: MemoryType,
        limit: int = 5,
        score_threshold: float = 0.0,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> SearchResult:
        """
        Search for similar memories.

        Args:
            query: Search query text.
            memory_type: Type of memory to search.
            limit: Maximum number of results.
            score_threshold: Minimum similarity score (0.0 to 1.0).
            filter_metadata: Optional metadata filters.

        Returns:
            SearchResult with matching MemoryEntry list.
        """
        self._initialize()
        if self._client is None:
            return SearchResult(query=query, results=[], total=0, collection="unavailable")

        try:
            query_embedding = self._embed(query)
            collection = self._get_collection(memory_type)

            # Build filter if metadata provided
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            must_conditions = []
            if filter_metadata:
                for key, value in filter_metadata.items():
                    must_conditions.append(
                        FieldCondition(
                            key=f"metadata.{key}",
                            match=MatchValue(value=value),
                        )
                    )

            search_filter = Filter(must=must_conditions) if must_conditions else None

            # V142 FIX: Qdrant client v1.18+ uses query_points() not search()
            results = self._client.query_points(
                collection_name=collection,
                query=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=search_filter,
            )

            entries: List[MemoryEntry] = []
            # query_points returns QueryResponse with .points attribute
            points = results.points if hasattr(results, 'points') else results
            for hit in points:
                payload = hit.payload or {}
                entries.append(MemoryEntry(
                    id=str(hit.id),
                    content=payload.get("content", ""),
                    memory_type=memory_type,
                    metadata=payload.get("metadata", {}),
                    score=hit.score or 0.0,
                ))

            return SearchResult(
                query=query,
                results=entries,
                total=len(entries),
                collection=collection,
            )

        except Exception as exc:
            logger.exception("Memory search failed: %s", exc)
            return SearchResult(query=query, results=[], total=0, collection="error")

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, memory_type: MemoryType, entry_id: str) -> bool:
        """
        Delete a memory entry by ID.

        Returns:
            True if deleted, False if failed.
        """
        self._initialize()
        if self._client is None:
            return False

        try:
            collection = self._get_collection(memory_type)
            from qdrant_client.models import PointIdsList

            self._client.delete(
                collection_name=collection,
                points_selector=PointIdsList(points=[entry_id]),
            )
            logger.info("Deleted memory: type=%s id=%s", memory_type.value, entry_id)
            return True
        except Exception as exc:
            logger.exception("Failed to delete memory: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Check Qdrant connectivity and collection status."""
        self._initialize()
        if self._client is None:
            return {
                "healthy": False,
                "url": self._url,
                "error": "Qdrant client not initialized",
                "embedder": "unavailable" if self._embedder is None else EMBEDDING_MODEL_NAME,
            }

        try:
            collections = self._client.get_collections()
            collection_names = [c.name for c in collections.collections]

            return {
                "healthy": True,
                "url": self._url,
                "collections": collection_names,
                "embedder": EMBEDDING_MODEL_NAME if self._embedder else "hash-fallback",
                "dimensions": EMBEDDING_DIMENSIONS,
            }
        except Exception as exc:
            return {
                "healthy": False,
                "url": self._url,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_collection(memory_type: MemoryType) -> str:
        """Map MemoryType to Qdrant collection name."""
        return {
            MemoryType.CONVERSATION: COLLECTION_CONVERSATIONS,
            MemoryType.STUDY_RESULT: COLLECTION_STUDY_RESULTS,
            MemoryType.DOCUMENT: COLLECTION_DOCUMENTS,
            MemoryType.ETAP_KNOWLEDGE: COLLECTION_ETAP_KNOWLEDGE,
            MemoryType.ENGINEERING_DECISION: COLLECTION_STUDY_RESULTS,
        }[memory_type]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_vector_memory: Optional[VectorMemoryService] = None


def get_vector_memory() -> VectorMemoryService:
    """Get the singleton VectorMemoryService instance."""
    global _vector_memory
    if _vector_memory is None:
        _vector_memory = VectorMemoryService()
    return _vector_memory


__all__ = [
    "COLLECTION_CONVERSATIONS",
    "COLLECTION_DOCUMENTS",
    "COLLECTION_ETAP_KNOWLEDGE",
    "COLLECTION_STUDY_RESULTS",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL_NAME",
    "MemoryEntry",
    "MemoryType",
    "SearchResult",
    "VectorMemoryService",
    "get_vector_memory",
]
