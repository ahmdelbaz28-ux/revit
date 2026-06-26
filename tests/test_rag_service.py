"""tests/test_rag_service.py — RAG Service Tests"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.services.rag_service import RAGQuery, RAGResponse, RAGService


@pytest.fixture
def rag_svc():
    svc = RAGService()
    svc.seed_nfpa72()
    return svc


class TestRAGServiceInit:
    def test_creates_instance(self):
        svc = RAGService()
        assert svc is not None

    def test_empty_initially(self):
        svc = RAGService()
        stats = svc.get_stats()
        assert stats["total_documents"] == 0


class TestRAGSeeding:
    def test_seed_nfpa72(self, rag_svc):
        stats = rag_svc.get_stats()
        assert stats["total_documents"] == 8

    def test_seed_returns_count(self):
        svc = RAGService()
        count = svc.seed_nfpa72()
        assert count == 8

    def test_sources_after_seed(self, rag_svc):
        stats = rag_svc.get_stats()
        assert "NFPA 72-2022" in stats["sources"]
        assert "Egyptian Fire Code" in stats["sources"]


class TestRAGEmbedding:
    def test_embed_text(self):
        svc = RAGService()
        vec = svc.embed_text("smoke detector spacing")
        assert isinstance(vec, list)
        assert len(vec) > 0

    def test_embed_different_texts(self):
        svc = RAGService()
        v1 = svc.embed_text("smoke detector")
        v2 = svc.embed_text("heat detector")
        # Different texts should produce different embeddings
        assert v1 != v2


class TestRAGRetrieve:
    def test_retrieve_smoke_detector(self, rag_svc):
        results = rag_svc.retrieve("smoke detector spacing", top_k=3)
        assert len(results) >= 1
        assert any("NFPA 72" in r["source"] for r in results)

    def test_retrieve_heat_detector(self, rag_svc):
        results = rag_svc.retrieve("heat detector spacing", top_k=3)
        assert len(results) >= 1

    def test_retrieve_egyptian_code(self, rag_svc):
        results = rag_svc.retrieve("Egyptian building fire alarm requirements", top_k=3)
        assert any("Egyptian" in r["source"] for r in results)

    def test_retrieve_filter_by_source(self, rag_svc):
        results = rag_svc.retrieve("detector spacing", top_k=3, sources=["NFPA 72-2022"])
        for r in results:
            assert r["source"] == "NFPA 72-2022"

    def test_retrieve_scores_sorted(self, rag_svc):
        results = rag_svc.retrieve("smoke detector", top_k=5)
        if len(results) >= 2:
            assert results[0]["score"] >= results[1]["score"]


class TestRAGQuery:
    def test_query_smoke_detector(self, rag_svc):
        query = RAGQuery(question="What is the spacing for smoke detectors?")
        response = rag_svc.query(query)
        assert isinstance(response, RAGResponse)
        assert "NFPA 72" in response.answer or "smoke" in response.answer.lower()
        assert len(response.sources) >= 1
        assert response.disclaimer  # Must have disclaimer

    def test_query_with_correlation_id(self, rag_svc):
        query = RAGQuery(question="test", correlation_id="test-123")
        response = rag_svc.query(query)
        assert response.correlation_id == "test-123"

    def test_query_disclaimer_present(self, rag_svc):
        query = RAGQuery(question="test query")
        response = rag_svc.query(query)
        assert "ADVISORY ONLY" in response.disclaimer

    def test_query_empty_kb(self):
        svc = RAGService()  # No seed
        query = RAGQuery(question="test")
        response = svc.query(query)
        assert response.confidence == "low"

    def test_query_auto_correlation_id(self, rag_svc):
        query = RAGQuery(question="test")
        response = rag_svc.query(query)
        assert response.correlation_id.startswith("rag-")


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        sim = RAGService._cosine_similarity(v, v)
        assert abs(sim - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        sim = RAGService._cosine_similarity(v1, v2)
        assert abs(sim) < 0.001

    def test_empty_vectors(self):
        assert RAGService._cosine_similarity([], []) == 0.0
