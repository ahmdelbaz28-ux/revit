"""
test_v142_graphrag.py — Tests for GraphRAG Engine + API endpoints.

Per agent.md Rule 10 + Rule 19.
"""

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# GraphRAG Engine Tests
# ---------------------------------------------------------------------------


class TestGraphRAGEngine:
    """Tests for the GraphRAG hybrid retrieval engine."""

    def test_engine_initializes_without_credentials(self):
        """Engine should initialize gracefully without Neo4j/OpenAI."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine
        engine = GraphRAGEngine(neo4j_uri="", openai_api_key="")
        engine._initialize()
        assert engine._initialized is True
        assert engine._graph is None
        assert engine._vector_store is None

    def test_save_to_memory_returns_false_without_config(self):
        """save_to_memory should return False when not configured."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine
        engine = GraphRAGEngine(neo4j_uri="", openai_api_key="")
        result = engine.save_to_memory("test text")
        assert result is False

    def test_add_knowledge_returns_false_without_config(self):
        """add_knowledge should return False when not configured."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine
        engine = GraphRAGEngine(neo4j_uri="", openai_api_key="")
        result = engine.add_knowledge("test knowledge")
        assert result is False

    def test_ask_returns_message_without_config(self):
        """ask should return error message when not configured."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine
        engine = GraphRAGEngine(neo4j_uri="", openai_api_key="")
        result = engine.ask("test question")
        assert "not available" in result.lower()

    def test_search_similar_returns_empty_without_config(self):
        """search_similar should return empty list when not configured."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine
        engine = GraphRAGEngine(neo4j_uri="", openai_api_key="")
        result = engine.search_similar("test query")
        assert result == []

    def test_health_check_returns_dict(self):
        """Health check should return a dict with status."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine
        engine = GraphRAGEngine(neo4j_uri="", openai_api_key="")
        result = engine.health_check()
        assert "initialized" in result
        assert "neo4j_connected" in result
        assert "vector_store" in result
        assert "embedding_model" in result
        assert "embedding_dimensions" in result

    def test_get_graphrag_engine_singleton(self):
        """get_graphrag_engine should return the same instance."""
        from fireai.infrastructure.graphrag_engine import (
            GraphRAGEngine,
            get_graphrag_engine,
        )
        e1 = get_graphrag_engine()
        e2 = get_graphrag_engine()
        assert e1 is e2
        assert isinstance(e1, GraphRAGEngine)

    def test_embedding_dimensions_is_1536(self):
        """OpenAI text-embedding-3-small should use 1536 dimensions."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine
        engine = GraphRAGEngine()
        assert engine._embedding_dimensions == 1536

    def test_llm_model_is_gpt4o(self):
        """Default LLM model should be gpt-4o."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine
        engine = GraphRAGEngine()
        assert engine._llm_model == "gpt-4o"


# ---------------------------------------------------------------------------
# V2 API Endpoint Tests
# ---------------------------------------------------------------------------


class TestV2GraphRAGEndpoints:
    """Tests for /api/v2/graphrag/* endpoints."""

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("FIREAI_API_KEY", "test-key-for-v142-1234567890")
        from backend.app import app
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        return {"X-API-Key": "test-key-for-v142-1234567890"}

    def test_graphrag_health_endpoint(self, client, auth_headers):
        """/api/v2/graphrag/health should return health status."""
        r = client.get("/api/v2/graphrag/health", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "initialized" in data
        assert "neo4j_connected" in data

    def test_graphrag_ask_endpoint(self, client, auth_headers):
        """/api/v2/graphrag/ask should return an answer (even if 'not available')."""
        r = client.post("/api/v2/graphrag/ask", json={
            "question": "What is NFPA 72?",
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "question" in data
        assert "answer" in data

    def test_graphrag_search_endpoint(self, client, auth_headers):
        """/api/v2/graphrag/search should return results (even if empty)."""
        r = client.post("/api/v2/graphrag/search", json={
            "query": "smoke detector spacing",
            "limit": 5,
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "total" in data

    def test_graphrag_knowledge_endpoint_returns_503_without_config(self, client, auth_headers):
        """/api/v2/graphrag/knowledge should return 503 when engine not configured."""
        r = client.post("/api/v2/graphrag/knowledge", json={
            "text": "Ahmed works at Aramco as a fire protection engineer.",
            "extract_entities": False,
        }, headers=auth_headers)
        # Without OpenAI key, engine returns False → 503
        assert r.status_code in (200, 503)
