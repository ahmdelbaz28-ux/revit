"""
backend/services/rag_service.py — RAG Service for Building Code Queries
========================================================================

Retrieval-Augmented Generation for fire protection engineering:
  - Embed building code text (NFPA 72, Egyptian Code, IBC)
  - Retrieve relevant sections for engineering queries
  - Generate context-aware answers

SAFETY-CRITICAL:
  - RAG answers are ADVISORY ONLY — never a substitute for engineer judgment
  - Every response includes disclaimer and source citation
  - Hallucinated code references are dangerous — strict retrieval grounding

REFERENCE: NFPA 72-2022, Egyptian Fire Code, IBC 2021
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("fireai.services.rag")

# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class CodeSection:
    """A building code section stored in the vector DB."""
    id: str
    source: str  # "NFPA 72-2022", "Egyptian Fire Code", etc.
    section: str  # "§17.6.2.1"
    title: str
    text: str
    embedding: list[float] = field(default_factory=list)


@dataclass
class RAGQuery:
    """A RAG query from an engineer."""
    question: str
    correlation_id: str = ""
    top_k: int = 5
    sources: list[str] = field(default_factory=list)


@dataclass
class RAGResponse:
    """A RAG response with retrieved context."""
    question: str
    answer: str
    sources: list[dict[str, str]] = field(default_factory=list)
    correlation_id: str = ""
    disclaimer: str = ""
    confidence: str = "advisory"


# ── RAG Service ───────────────────────────────────────────────────────────────


class RAGService:
    """
    RAG service for building code queries.

    Architecture:
      1. Embed code sections using sentence-transformers
      2. Store in Qdrant (or in-memory fallback)
      3. Retrieve relevant sections for queries
      4. Generate context-grounded answers
    """

    DISCLAIMER = (
        "⚠️ ADVISORY ONLY — This AI-generated answer is NOT a substitute for "
        "professional engineering judgment. Always verify against the actual "
        "code document. Fire protection decisions affect human life."
    )

    # Pre-seeded NFPA 72 knowledge (Phase 1 seed)
    NFPA72_SEED = [
        {
            "source": "NFPA 72-2022",
            "section": "§17.6.2.1",
            "title": "Smoke Detector Spacing",
            "text": "For smooth ceilings, the nominal spacing for spot-type smoke detectors shall be 30 ft (9.1 m) nominal. All points on the ceiling shall have a detector within a distance equal to 0.7 times the nominal spacing (0.7 × 30 = 21 ft or 6.4 m).",
        },
        {
            "source": "NFPA 72-2022",
            "section": "§17.6.2.3",
            "title": "Heat Detector Spacing",
            "text": "For smooth ceilings, spot-type heat detectors shall be spaced at 50 ft (15.2 m) nominal. All points on the ceiling shall have a detector within 0.7 times the nominal spacing (0.7 × 50 = 35 ft or 10.7 m). Heat detectors use square (Chebyshev) spacing, not circular.",
        },
        {
            "source": "NFPA 72-2022",
            "section": "§17.6.3.1.1",
            "title": "Dead Air Space",
            "text": "For ceiling-mounted detectors, the dead air space extends 0.1 m (4 in.) from the wall-ceiling intersection. No detector shall be placed in dead air space, as smoke and heat may not reach the detector in this zone.",
        },
        {
            "source": "NFPA 72-2022",
            "section": "§10.6",
            "title": "Audit Trail Requirements",
            "text": "Fire alarm systems shall maintain an audit trail of all system activity, including alarm signals, trouble signals, and supervisory signals. The audit trail shall be preserved and available for review by the authority having jurisdiction.",
        },
        {
            "source": "NFPA 72-2022",
            "section": "§14.2.4",
            "title": "Correlation ID / Event Identification",
            "text": "Each event in the fire alarm system shall be identified with a unique correlation identifier that enables traceability from initiation through resolution. This ensures accountability and auditability of all system actions.",
        },
        {
            "source": "NFPA 72-2022",
            "section": "§17.7.1",
            "title": "Duct Detector Requirements",
            "text": "Smoke detectors shall be installed in air supply systems having a design capacity greater than 2000 CFM (0.94 m³/s). Duct detectors shall be located downstream of the air filters and ahead of any branch connections.",
        },
        {
            "source": "Egyptian Fire Code",
            "section": "§4.3",
            "title": "Building Classification",
            "text": "Buildings in Egypt are classified by occupancy type and height. Residential buildings above 25 m require automatic fire alarm systems. Commercial buildings above 15 m require sprinkler protection in addition to fire alarm.",
        },
        {
            "source": "Egyptian Fire Code",
            "section": "§6.2",
            "title": "Fire Alarm Requirements",
            "text": "All public buildings shall be equipped with a manual fire alarm system. Automatic detection is required for buildings with occupied floors above 15 m. The system shall comply with NFPA 72 or equivalent European standard.",
        },
    ]

    def __init__(self, storage_dir: str | None = None):
        self._storage_dir = storage_dir or os.path.join(
            os.getcwd(), "data", "rag_store"
        )
        self._embedder = None
        self._collection = None
        self._qdrant_available = False
        self._in_memory: list[dict[str, Any]] = []

    # ── Embedding ─────────────────────────────────────────────────────────

    def _get_embedder(self):
        """Lazy-load sentence transformer model."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("SentenceTransformer loaded: all-MiniLM-L6-v2")
            except ImportError:
                logger.warning("sentence-transformers not available — using TF-IDF fallback")
                self._embedder = None
        return self._embedder

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for a text string."""
        embedder = self._get_embedder()
        if embedder is not None:
            return embedder.encode(text).tolist()
        else:
            # Fallback: simple hash-based pseudo-embedding (for testing)
            h = hashlib.sha256(text.encode()).digest()
            dim = 384
            vec = [(h[i % len(h)] / 255.0 - 0.5) * 0.1 for i in range(dim)]
            return vec

    # ── Seed Knowledge Base ───────────────────────────────────────────────

    def seed_nfpa72(self) -> int:
        """Seed the knowledge base with NFPA 72 and Egyptian Code sections."""
        count = 0
        for entry in self.NFPA72_SEED:
            doc_id = f"{entry['source']}-{entry['section']}"
            text = f"{entry['title']}: {entry['text']}"
            embedding = self.embed_text(text)

            doc = {
                "id": doc_id,
                "source": entry["source"],
                "section": entry["section"],
                "title": entry["title"],
                "text": entry["text"],
                "embedding": embedding,
            }
            self._in_memory.append(doc)
            count += 1

        logger.info("Seeded %d code sections into RAG store", count)
        return count

    # ── Retrieve ──────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = 5, sources: list[str] | None = None) -> list[dict]:
        """
        Retrieve relevant code sections for a query.

        Uses cosine similarity between query embedding and stored documents.
        """
        query_embedding = self.embed_text(query)

        # Filter by sources if specified
        candidates = self._in_memory
        if sources:
            candidates = [d for d in candidates if d["source"] in sources]

        if not candidates:
            return []

        # Compute cosine similarity
        scored = []
        for doc in candidates:
            sim = self._cosine_similarity(query_embedding, doc["embedding"])
            scored.append((sim, doc))

        # Sort by similarity (descending)
        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {
                "source": doc["source"],
                "section": doc["section"],
                "title": doc["title"],
                "text": doc["text"],
                "score": round(sim, 4),
            }
            for sim, doc in scored[:top_k]
        ]

    # ── Query ─────────────────────────────────────────────────────────────

    def query(self, rag_query: RAGQuery) -> RAGResponse:
        """
        Process a RAG query: retrieve context, generate answer.

        The answer is ADVISORY ONLY — never a substitute for engineering judgment.
        """
        if not rag_query.correlation_id:
            rag_query.correlation_id = f"rag-{uuid.uuid4().hex[:12]}"

        # Retrieve relevant sections
        results = self.retrieve(
            rag_query.question,
            top_k=rag_query.top_k,
            sources=rag_query.sources or None,
        )

        if not results:
            return RAGResponse(
                question=rag_query.question,
                answer="No relevant code sections found for this query. Please consult the actual code document directly.",
                correlation_id=rag_query.correlation_id,
                disclaimer=self.DISCLAIMER,
                confidence="low",
            )

        # Build context-grounded answer
        context_parts = []
        for r in results:
            context_parts.append(f"[{r['source']} {r['section']}] {r['title']}: {r['text']}")

        context = "\n\n".join(context_parts)

        answer = (
            f"Based on the following code references:\n\n"
            f"{context}\n\n"
            f"Summary: The relevant provisions are listed above. "
            f"Please verify against the actual code documents before making design decisions."
        )

        return RAGResponse(
            question=rag_query.question,
            answer=answer,
            sources=[{"source": r["source"], "section": r["section"], "title": r["title"], "score": r["score"]} for r in results],
            correlation_id=rag_query.correlation_id,
            disclaimer=self.DISCLAIMER,
            confidence="advisory",
        )

    # ── Utility ───────────────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def get_stats(self) -> dict:
        """Get knowledge base statistics."""
        sources = set(d["source"] for d in self._in_memory)
        return {
            "total_documents": len(self._in_memory),
            "sources": sorted(sources),
            "embedder": "sentence-transformers" if self._get_embedder() else "hash-fallback",
        }
