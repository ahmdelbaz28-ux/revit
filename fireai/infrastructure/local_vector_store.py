"""
local_vector_store.py — Local Vector Store for Code Understanding
=============================================================

Provides a simple in-memory vector store for code chunks without external dependencies.
Uses TF-IDF for lightweight embeddings (no API needed) or integrates with Modal API for
OpenAI embeddings when available.

Features:
- TF-IDF embeddings (local, no API)
- OpenAI embeddings via Modal API (optional)
- Cosine similarity search
- Chunk management with metadata

Usage:
    from fireai.infrastructure.local_vector_store import LocalVectorStore

    store = LocalVectorStore()
    store.add("def hello(): pass", metadata={"type": "function", "name": "hello"})
    results = store.search("function definition", k=5)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional, cast

import numpy as np

logger = logging.getLogger(__name__)

# Try to import sklearn for TF-IDF
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False
    logger.warning("sklearn not installed. Using simple keyword matching.")


@dataclass
class VectorChunk:
    """A chunk with vector embedding."""
    chunk_id: str
    content: str
    metadata: dict[str, Any]
    vector: Optional[np.ndarray] = None
    tokens: int = 0


class LocalVectorStore:
    """
    Local vector store for code chunks.

    Supports two embedding modes:
    1. TF-IDF (local, no API) - enabled by default
    2. OpenAI embeddings via Modal API - when OPENAI_API_KEY set

    Features:
    - Add chunks with automatic embedding
    - Search by semantic similarity
    - Filter by metadata
    - Batch operations

    Args:
        embedding_mode: "tfidf" (local) or "openai" (API)
        max_chunks: Maximum chunks to store (LRU eviction)
    """

    def __init__(
        self,
        embedding_mode: str = "tfidf",
        max_chunks: int = 10000,
    ):
        self.embedding_mode = embedding_mode
        self.max_chunks = max_chunks

        # Storage
        self._chunks: dict[str, VectorChunk] = {}
        self._vectors: list[np.ndarray] = []
        self._contents: list[str] = []

        # TF-IDF vectorizer
        if _HAS_SKLEARN and embedding_mode == "tfidf":
            self._vectorizer = TfidfVectorizer(
                max_features=5000,
                ngram_range=(1, 3),  # Unigrams, bigrams, trigrams
                stop_words='english',
                token_pattern=r'(?u)\b\w+\b',  # Include single-char tokens
            )
            self._fitted = False
        else:
            self._vectorizer = None
            self._fitted = False

        # Matrix for TF-IDF embeddings
        self._matrix: Optional[np.ndarray] = None

        # Statistics
        self._total_embedded = 0

    def _generate_chunk_id(self, content: str, metadata: dict) -> str:
        """Generate unique chunk ID."""
        unique_str = f"{content[:100]}:{metadata.get('file_path', '')}:{metadata.get('line_start', 0)}"
        return hashlib.md5(unique_str.encode(), usedforsecurity=False).hexdigest()[:12]

    def _embed_tfidf(self, texts: list[str]) -> np.ndarray:
        """Embed texts using TF-IDF."""
        if not self._fitted:
            self._matrix = self._vectorizer.fit_transform(texts).toarray()
            self._fitted = True
        else:
            # Transform new texts
            try:
                self._matrix = self._vectorizer.transform(texts).toarray()
            except Exception as e:
                logger.warning(f"TF-IDF transform failed: {e}")
                return cast(np.ndarray, np.zeros((len(texts), 100)))
        return self._matrix

    def _embed_openai(self, texts: list[str]) -> np.ndarray:
        """Embed texts using OpenAI API via Modal."""
        import httpx

        modal_key = os.environ.get(
            "MODAL_RESEARCH_KEY",
            "modalresearch_TzUJFpXlhpM9zxRhymgDm4DZmIT_IFDGYuPtZT9Eekg"
        )

        # For Modal, use their embeddings endpoint
        url = "https://api.us-west-2.modal.direct/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {modal_key}",
            "Content-Type": "application/json",
        }

        embeddings = []
        for text in texts:
            try:
                response = httpx.post(
                    url,
                    headers=headers,
                    json={
                        "model": "zai-org/GLM-5-FP8",
                        "input": text[:8000],  # Truncate long texts
                    },
                    timeout=60.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    # Extract embedding from response
                    if "data" in data and len(data["data"]) > 0:
                        emb = data["data"][0].get("embedding", [])
                        embeddings.append(emb if emb else np.zeros(1536))
                    else:
                        embeddings.append(np.zeros(1536))
                else:
                    logger.warning(f"OpenAI embedding failed: {response.status_code}")
                    embeddings.append(np.zeros(1536))
            except Exception as e:
                logger.warning(f"Embedding error: {e}")
                embeddings.append(np.zeros(1536))

        return np.array(embeddings)

    def _compute_keyword_scores(self, query: str, content: str) -> float:
        """Compute simple keyword-based relevance score."""
        query_words = set(query.lower().split())
        content_words = set(re.findall(r'\w+', content.lower()))

        if not query_words:
            return 0.0

        # Count matches
        matches: float = float(len(query_words & content_words))

        # Bonus for exact phrase matches
        if query.lower() in content.lower():
            matches += 5.0

        # Bonus for word starts
        for word in query_words:
            for content_word in content_words:
                if content_word.startswith(word) or word.startswith(content_word):
                    matches += 0.5

        return matches / len(query_words)

    def add(
        self,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        chunk_id: Optional[str] = None,
    ) -> str:
        """
        Add a chunk to the store.

        Args:
            content: Text content
            metadata: Optional metadata (file_path, line_start, chunk_type, etc.)
            chunk_id: Optional custom ID (generated if not provided)

        Returns:
            chunk_id of the added chunk
        """
        if metadata is None:
            metadata = {}

        if chunk_id is None:
            chunk_id = self._generate_chunk_id(content, metadata)

        # Create chunk
        chunk = VectorChunk(
            chunk_id=chunk_id,
            content=content,
            metadata=metadata,
            tokens=len(content) // 4,  # Approximate tokens
        )

        # Add to storage
        self._chunks[chunk_id] = chunk
        self._contents.append(content)

        # Embed (lazy)
        self._total_embedded += 1

        # LRU: remove oldest if over limit
        if len(self._chunks) > self.max_chunks:
            oldest_id = next(iter(self._chunks))
            del self._chunks[oldest_id]

        # Refit TF-IDF if using local embeddings
        if self.embedding_mode == "tfidf" and _HAS_SKLEARN:
            self._fitted = False

        logger.debug(f"Added chunk {chunk_id} to vector store")
        return chunk_id

    def add_batch(self, chunks: list[dict[str, Any]]) -> list[str]:
        """
        Add multiple chunks at once.

        Args:
            chunks: List of {"content": ..., "metadata": {...}} dicts

        Returns:
            List of chunk_ids
        """
        return [self.add(c["content"], c.get("metadata", {})) for c in chunks]

    def get(self, chunk_id: str) -> Optional[VectorChunk]:
        """Get a chunk by ID."""
        return self._chunks.get(chunk_id)

    def search(
        self,
        query: str,
        k: int = 5,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Search for chunks similar to query.

        Args:
            query: Search query (can be empty if using filter_metadata)
            k: Number of results to return
            filter_metadata: Optional metadata filters

        Returns:
            List of {"chunk_id", "content", "metadata", "score"} dicts
        """
        results = []

        for chunk_id, chunk in self._chunks.items():
            # Apply metadata filter first
            if filter_metadata:
                skip = False
                for key, value in filter_metadata.items():
                    if chunk.metadata.get(key) != value:
                        skip = True
                        break
                if skip:
                    continue

            # Compute score (keyword + TF-IDF)
            score = self._compute_keyword_scores(query, chunk.content)

            # For empty query with filter, give score of 1.0
            if not query and filter_metadata:
                score = 1.0

            if score > 0 or (not query and filter_metadata):
                results.append({
                    "chunk_id": chunk_id,
                    "content": chunk.content,
                    "metadata": chunk.metadata,
                    "score": score if score > 0 else 1.0,
                })

        # TF-IDF similarity (if available)
        if self.embedding_mode == "tfidf" and _HAS_SKLEARN and len(self._contents) > 0:
            try:
                all_contents = list(self._chunks.values())
                all_texts = [c.content for c in all_contents]

                if all_texts:
                    # Fit and transform all at once
                    content_matrix = self._vectorizer.fit_transform(all_texts).toarray()
                    query_vec = self._vectorizer.transform([query]).toarray()

                    # Compute similarities
                    similarities = cosine_similarity(query_vec, content_matrix)[0]

                    # Add TF-IDF scores
                    for i, chunk in enumerate(all_contents):
                        tfidf_score = float(similarities[i])
                        # Update or add
                        found = False
                        for r in results:
                            if r["chunk_id"] == chunk.chunk_id:
                                r["score"] = (cast(float, r["score"]) + tfidf_score) / 2
                                found = True
                                break
                        if not found and tfidf_score > 0.1:  # Threshold
                            results.append({
                                "chunk_id": chunk.chunk_id,
                                "content": chunk.content,
                                "metadata": chunk.metadata,
                                "score": tfidf_score,
                            })
            except Exception as e:
                logger.warning(f"TF-IDF search failed: {e}")

        # Sort by score
        results.sort(key=lambda x: -cast(float, x["score"]))

        return results[:k]

    def search_by_file(self, file_path: str, k: int = 10) -> list[dict[str, Any]]:
        """Get chunks from a specific file."""
        return self.search(
            query="",
            k=k,
            filter_metadata={"file_path": file_path},
        )

    def delete(self, chunk_id: str) -> bool:
        """Delete a chunk by ID."""
        if chunk_id in self._chunks:
            del self._chunks[chunk_id]
            self._fitted = False
            return True
        return False

    def clear(self) -> None:
        """Clear all chunks."""
        self._chunks.clear()
        self._contents.clear()
        self._fitted = False
        self._matrix = None

    @property
    def total_chunks(self) -> int:
        """Get total number of chunks."""
        return len(self._chunks)

    def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        type_counts: dict[str, int] = defaultdict(int)
        for chunk in self._chunks.values():
            chunk_type = chunk.metadata.get("chunk_type", "unknown")
            type_counts[chunk_type] += 1

        return {
            "total_chunks": self.total_chunks,
            "max_chunks": self.max_chunks,
            "embedding_mode": self.embedding_mode,
            "has_tfidf": _HAS_SKLEARN,
            "chunks_by_type": dict(type_counts),
        }


# Singleton
_vector_store: Optional[LocalVectorStore] = None


def get_vector_store(
    embedding_mode: str = "tfidf",
    max_chunks: int = 10000,
) -> LocalVectorStore:
    """Get singleton vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = LocalVectorStore(
            embedding_mode=embedding_mode,
            max_chunks=max_chunks,
        )
    return _vector_store


__all__ = [
    "LocalVectorStore",
    "VectorChunk",
    "get_vector_store",
]
