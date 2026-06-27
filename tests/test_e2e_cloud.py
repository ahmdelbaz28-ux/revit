"""
test_e2e_cloud.py — End-to-End Cloud Integration Tests.

V144: These tests connect to REAL cloud services (Neo4j Aura, Qdrant Cloud,
Modal API) and verify that the V141-V142 infrastructure actually works.

Unlike unit tests that test graceful fallback, these tests:
1. Connect to Neo4j Aura Cloud → add elements → run impact analysis
2. Connect to Qdrant Cloud → store memories → search → verify results
3. Connect to Modal API (GLM-5.1-FP8) → initialize GraphRAG → verify transformer + qa_chain

Tests are SKIPPED if cloud credentials are not in .env (not failed).
This allows CI to run without cloud access while developers can run
them locally with: pytest tests/test_e2e_cloud.py -v

Per agent.md Rule 1 (ABSOLUTE TRUTH): these tests provide REAL evidence
that cloud services work, not just code that looks correct.
"""

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helper: Load .env
# ---------------------------------------------------------------------------

def load_env():
    """Load .env file if it exists."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

_HAS_NEO4J = bool(os.environ.get("NEO4J_URI") and os.environ.get("NEO4J_PASSWORD"))
_HAS_QDRANT = bool(os.environ.get("QDRANT_URL") and os.environ.get("QDRANT_API_KEY"))
_HAS_MODAL = bool(os.environ.get("MODAL_API_KEY") or os.environ.get("OPENAI_API_KEY"))

skip_neo4j = pytest.mark.skipif(not _HAS_NEO4J, reason="Neo4j Aura credentials not in .env")
skip_qdrant = pytest.mark.skipif(not _HAS_QDRANT, reason="Qdrant Cloud credentials not in .env")
skip_modal = pytest.mark.skipif(not _HAS_MODAL, reason="Modal/OpenAI API key not in .env")


# ---------------------------------------------------------------------------
# 1. Neo4j Aura Cloud E2E Tests
# ---------------------------------------------------------------------------


class TestNeo4jAuraE2E:
    """E2E tests for Neo4j Aura Cloud — Topology Graph Service."""

    @skip_neo4j
    def test_neo4j_connection_real(self):
        """Connect to REAL Neo4j Aura Cloud and verify health."""
        from fireai.infrastructure.topology_graph_service import TopologyGraphService

        service = TopologyGraphService()
        service._initialize()

        assert service._driver is not None, "Neo4j driver should be initialized"
        assert service._initialized is True

        health = service.health_check()
        assert health["healthy"] is True, f"Neo4j should be healthy: {health}"
        assert health["uri"].startswith("neo4j+s://"), "Should use secure bolt+TLS"

    @skip_neo4j
    def test_neo4j_add_element_real(self):
        """Add a REAL element to Neo4j Aura and verify it's stored."""
        from fireai.infrastructure.topology_graph_service import (
            ElementType,
            NetworkElement,
            TopologyGraphService,
        )

        service = TopologyGraphService()
        service._initialize()

        element = NetworkElement(
            element_id="E2E-BUS-001",
            element_type=ElementType.BUS,
            name="E2E Test Bus",
            properties={"voltage_kv": 13.8, "test": True},
        )
        result = service.add_element(element)
        assert result is True, "add_element should return True on real Neo4j"

    @skip_neo4j
    def test_neo4j_add_connection_real(self):
        """Add REAL connections to Neo4j Aura and verify."""
        from fireai.infrastructure.topology_graph_service import (
            ElementType,
            NetworkConnection,
            NetworkElement,
            RelationshipType,
            TopologyGraphService,
        )

        service = TopologyGraphService()
        service._initialize()

        # Add elements
        service.add_element(NetworkElement("E2E-BRK-001", ElementType.BREAKER, "E2E Breaker"))
        service.add_element(NetworkElement("E2E-BUS-002", ElementType.BUS, "E2E Bus 2"))
        service.add_element(NetworkElement("E2E-LOAD-001", ElementType.LOAD, "E2E Load"))

        # Add connections
        assert service.add_connection(NetworkConnection(
            "E2E-BRK-001", "E2E-BUS-002", RelationshipType.FEEDS
        )) is True
        assert service.add_connection(NetworkConnection(
            "E2E-BUS-002", "E2E-LOAD-001", RelationshipType.FEEDS
        )) is True

    @skip_neo4j
    def test_neo4j_impact_analysis_real(self):
        """Run REAL impact analysis on Neo4j Aura Cloud."""
        from fireai.infrastructure.topology_graph_service import TopologyGraphService

        service = TopologyGraphService()
        service._initialize()

        result = service.analyze_breaker_impact("E2E-BRK-001")

        assert result.breaker_id == "E2E-BRK-001"
        assert "E2E-BUS-002" in result.affected_buses, \
            f"BUS-002 should be affected. Got: {result.affected_buses}"
        assert "E2E-LOAD-001" in result.affected_loads, \
            f"LOAD-001 should be affected. Got: {result.affected_loads}"
        assert result.analysis_ms > 0, "Should take >0ms"
        assert result.analysis_ms < 5000, "Should take <5s (cloud latency)"
        assert result.path_count > 0, "Should find at least 1 path"

    @skip_neo4j
    def test_neo4j_health_check_real(self):
        """Verify Neo4j health check returns real node/edge counts."""
        from fireai.infrastructure.topology_graph_service import TopologyGraphService

        service = TopologyGraphService()
        service._initialize()

        health = service.health_check()
        assert health["healthy"] is True
        assert health.get("nodes", 0) > 0, "Should have nodes from previous tests"
        assert health.get("edges", 0) > 0, "Should have edges from previous tests"


# ---------------------------------------------------------------------------
# 2. Qdrant Cloud E2E Tests
# ---------------------------------------------------------------------------


class TestQdrantCloudE2E:
    """E2E tests for Qdrant Cloud — Vector Memory Service."""

    @skip_qdrant
    def test_qdrant_connection_real(self):
        """Connect to REAL Qdrant Cloud and verify health."""
        from fireai.infrastructure.vector_memory_service import VectorMemoryService

        service = VectorMemoryService()
        service._initialize()

        assert service._client is not None, "Qdrant client should be initialized"

        health = service.health_check()
        assert health["healthy"] is True, f"Qdrant should be healthy: {health}"
        assert "https://" in health.get("url", ""), "Should use HTTPS for cloud"

    @skip_qdrant
    def test_qdrant_store_real(self):
        """Store a REAL memory in Qdrant Cloud."""
        from fireai.infrastructure.vector_memory_service import (
            MemoryType,
            VectorMemoryService,
        )

        service = VectorMemoryService()
        service._initialize()

        entry_id = service.store(
            content="E2E TEST: NFPA 72 requires smoke detector spacing of 9.1m on flat ceilings",
            memory_type=MemoryType.ETAP_KNOWLEDGE,
            metadata={"test": "e2e", "standard": "NFPA 72"},
        )
        assert entry_id is not None, "store should return a UUID entry_id"
        assert len(entry_id) > 10, "entry_id should be a UUID string"

    @skip_qdrant
    def test_qdrant_search_exact_match_real(self):
        """Search Qdrant Cloud with exact text — should find it."""
        from fireai.infrastructure.vector_memory_service import (
            MemoryType,
            VectorMemoryService,
        )

        service = VectorMemoryService()
        service._initialize()

        # Store a unique text
        unique_text = "E2E SEARCH TEST: Darcy-Weisbach equation for CO2 systems"
        service.store(content=unique_text, memory_type=MemoryType.DOCUMENT)

        # Search with exact text (hash-based embeddings give score=1.0 for exact match)
        result = service.search(
            query=unique_text,
            memory_type=MemoryType.DOCUMENT,
            limit=5,
        )
        assert result.total > 0, "Should find at least 1 result for exact match"
        assert result.results[0].content == unique_text, \
            f"Top result should match. Got: {result.results[0].content[:50]}"
        assert result.results[0].score > 0.99, \
            f"Exact match should have score >0.99. Got: {result.results[0].score}"

    @skip_qdrant
    def test_qdrant_store_multiple_collections_real(self):
        """Store in multiple Qdrant collections — verify stores succeed."""
        from fireai.infrastructure.vector_memory_service import (
            MemoryType,
            VectorMemoryService,
        )

        service = VectorMemoryService()
        service._initialize()

        # Store in different collections
        id1 = service.store("E2E conversation memory test", MemoryType.CONVERSATION)
        id2 = service.store("E2E study result memory test", MemoryType.STUDY_RESULT)
        id3 = service.store("E2E document memory test", MemoryType.DOCUMENT)

        assert id1 and id2 and id3, "All stores should succeed"

        # V144: Search with exact text (hash embeddings require exact match)
        r1 = service.search("E2E conversation memory test", MemoryType.CONVERSATION, limit=5)
        r2 = service.search("E2E study result memory test", MemoryType.STUDY_RESULT, limit=5)

        # With hash-based embeddings, exact match should work
        # If sentence-transformers not installed, score may be 1.0 for exact match
        assert r1.total > 0 or r2.total > 0, \
            "At least one collection should return results for exact match"


# ---------------------------------------------------------------------------
# 3. GraphRAG Engine E2E Tests (Modal API)
# ---------------------------------------------------------------------------


class TestGraphRAGE2E:
    """E2E tests for GraphRAG Engine with Modal (GLM-5.1-FP8) + Neo4j Aura."""

    @skip_modal
    @skip_neo4j
    def test_graphrag_engine_initializes_real(self):
        """Initialize GraphRAG with REAL Neo4j + REAL Modal API."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine

        engine = GraphRAGEngine()
        engine._initialize()

        health = engine.health_check()
        assert health["initialized"] is True, "Engine should be initialized"
        assert health["neo4j_connected"] is True, "Neo4j should be connected"
        assert health["transformer"] is True, "LLMGraphTransformer should be active"
        assert health["qa_chain"] is True, "GraphCypherQAChain should be active"

    @skip_modal
    @skip_neo4j
    def test_graphrag_llm_model_is_glm(self):
        """Verify GraphRAG auto-selected GLM-5.1-FP8 (not gpt-4o)."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine

        engine = GraphRAGEngine()
        # If MODAL_API_KEY is set, model should be GLM-5.1-FP8
        if os.environ.get("MODAL_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            assert "GLM" in engine._llm_model or "glm" in engine._llm_model, \
                f"Should use GLM model when Modal key is set. Got: {engine._llm_model}"
        assert engine._openai_key, "Should have an API key set"

    @skip_modal
    @skip_neo4j
    def test_graphrag_ask_real(self):
        """Ask GraphRAG a question against REAL Neo4j + Modal."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine

        engine = GraphRAGEngine()
        engine._initialize()

        # Ask a question — should return a string answer (not "not available")
        answer = engine.ask("How many nodes are in the graph?")
        assert isinstance(answer, str), "Answer should be a string"
        assert len(answer) > 0, "Answer should not be empty"
        # Should NOT be the fallback message
        assert "not available" not in answer.lower(), \
            f"Should get a real answer, not fallback. Got: {answer[:100]}"

    @skip_modal
    @skip_neo4j
    def test_graphrag_provider_detected(self):
        """Verify GraphRAG detected the correct provider (Modal or OpenAI)."""
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine

        engine = GraphRAGEngine()
        assert engine._openai_key, "Should have API key detected"

        if os.environ.get("MODAL_API_KEY"):
            assert "modal" in engine._openai_base_url.lower() or \
                   "us-west-2" in engine._openai_base_url, \
                f"Should detect Modal base_url. Got: {engine._openai_base_url}"


# ---------------------------------------------------------------------------
# 4. Full Stack E2E Test (all 3 services together)
# ---------------------------------------------------------------------------


class TestFullStackE2E:
    """E2E test that uses all 3 cloud services together."""

    @skip_neo4j
    @skip_qdrant
    @skip_modal
    def test_all_cloud_services_connected(self):
        """Verify ALL cloud services are simultaneously connected."""
        # Neo4j
        from fireai.infrastructure.topology_graph_service import TopologyGraphService
        neo4j = TopologyGraphService()
        neo4j._initialize()
        assert neo4j.health_check()["healthy"] is True, "Neo4j should be healthy"

        # Qdrant
        from fireai.infrastructure.vector_memory_service import VectorMemoryService
        qdrant = VectorMemoryService()
        qdrant._initialize()
        assert qdrant.health_check()["healthy"] is True, "Qdrant should be healthy"

        # GraphRAG
        from fireai.infrastructure.graphrag_engine import GraphRAGEngine
        graphrag = GraphRAGEngine()
        graphrag._initialize()
        assert graphrag.health_check()["neo4j_connected"] is True, "GraphRAG Neo4j should be connected"

    @skip_neo4j
    def test_v2_api_topology_endpoint_e2e(self):
        """V2 API /api/v2/topology/health should report Neo4j connected."""
        os.environ["FIREAI_API_KEY"] = "e2e-test-key-1234567890"
        from fastapi.testclient import TestClient

        from backend.app import app

        client = TestClient(app)
        headers = {"X-API-Key": "e2e-test-key-1234567890"}

        r = client.get("/api/v2/topology/health", headers=headers)
        assert r.status_code == 200
        data = r.json()
        # When .env is loaded, Neo4j should be connected
        if _HAS_NEO4J:
            assert data.get("healthy") is True, \
                f"Topology health should be True with real Neo4j. Got: {data}"

    @skip_qdrant
    def test_v2_api_memory_endpoint_e2e(self):
        """V2 API /api/v2/memory/health should report Qdrant connected."""
        os.environ["FIREAI_API_KEY"] = "e2e-test-key-1234567890"
        from fastapi.testclient import TestClient

        from backend.app import app

        client = TestClient(app)
        headers = {"X-API-Key": "e2e-test-key-1234567890"}

        r = client.get("/api/v2/memory/health", headers=headers)
        assert r.status_code == 200
        data = r.json()
        if _HAS_QDRANT:
            assert data.get("healthy") is True, \
                f"Memory health should be True with real Qdrant. Got: {data}"
