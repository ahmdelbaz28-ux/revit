# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
test_v141_vector_topology.py — Tests for Qdrant Vector Memory + Neo4j Topology.

Per agent.md Rule 10 + Rule 19.
"""

# No __future__ annotations — needed for Pydantic forward ref resolution

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Vector Memory Service Tests
# ---------------------------------------------------------------------------


class TestVectorMemoryService:
    """Tests for Qdrant-backed vector memory."""

    def test_service_initializes_without_qdrant(self):
        """Service should initialize gracefully when Qdrant is unavailable."""
        from fireai.infrastructure.vector_memory_service import VectorMemoryService
        service = VectorMemoryService(qdrant_url="http://nonexistent:6333")  # NOSONAR: HTTP/WS in test  # NOSONAR — S7632: test function documented via class name / module path
        service._initialize()
        # Should not crash — falls back to no-op mode
        assert service._initialized is True

    def test_store_returns_none_when_qdrant_unavailable(self):
        """Store should return None when Qdrant is unavailable."""
        from fireai.infrastructure.vector_memory_service import (
            MemoryType,
            VectorMemoryService,
        )
        service = VectorMemoryService(qdrant_url="http://nonexistent:6333")  # NOSONAR: HTTP/WS in test  # NOSONAR — S7632: test function documented via class name / module path
        result = service.store(
            content="test memory",
            memory_type=MemoryType.CONVERSATION,
        )
        assert result is None

    def test_search_returns_empty_when_qdrant_unavailable(self):
        """Search should return empty results when Qdrant is unavailable."""
        from fireai.infrastructure.vector_memory_service import (
            MemoryType,
            VectorMemoryService,
        )
        service = VectorMemoryService(qdrant_url="http://nonexistent:6333")  # NOSONAR: HTTP/WS in test  # NOSONAR — S7632: test function documented via class name / module path
        result = service.search(
            query="test query",
            memory_type=MemoryType.CONVERSATION,
        )
        assert result.total == 0
        assert len(result.results) == 0

    def test_health_check_returns_dict(self):
        """Health check should return a dict with healthy status."""
        from fireai.infrastructure.vector_memory_service import VectorMemoryService
        service = VectorMemoryService(qdrant_url="http://nonexistent:6333")  # NOSONAR: HTTP/WS in test  # NOSONAR — S7632: test function documented via class name / module path
        result = service.health_check()
        assert "healthy" in result
        assert isinstance(result["healthy"], bool)

    def test_memory_type_enum_has_all_types(self):
        """MemoryType should have all expected types."""
        from fireai.infrastructure.vector_memory_service import MemoryType
        assert MemoryType.CONVERSATION.value == "conversation"
        assert MemoryType.STUDY_RESULT.value == "study_result"
        assert MemoryType.DOCUMENT.value == "document"
        assert MemoryType.ETAP_KNOWLEDGE.value == "etap_knowledge"

    def test_memory_entry_to_dict(self):
        """MemoryEntry should serialize to dict correctly."""
        from fireai.infrastructure.vector_memory_service import (
            MemoryEntry,
            MemoryType,
        )
        entry = MemoryEntry(
            id="test-001",
            content="test content",
            memory_type=MemoryType.CONVERSATION,
            metadata={"user_id": "u1"},
            score=0.95,
        )
        d = entry.to_dict()
        assert d["id"] == "test-001"
        assert d["content"] == "test content"
        assert d["memory_type"] == "conversation"
        assert d["score"] == pytest.approx(0.95)

    def test_get_vector_memory_singleton(self):
        """get_vector_memory should return the same instance."""
        from fireai.infrastructure.vector_memory_service import (
            VectorMemoryService,
            get_vector_memory,
        )
        s1 = get_vector_memory()
        s2 = get_vector_memory()
        assert s1 is s2
        assert isinstance(s1, VectorMemoryService)


# ---------------------------------------------------------------------------
# Topology Graph Service Tests
# ---------------------------------------------------------------------------


class TestTopologyGraphService:
    """Tests for Neo4j-backed topology graph."""

    def test_service_initializes_without_neo4j(self):
        """Service should initialize gracefully when Neo4j is unavailable."""
        from fireai.infrastructure.topology_graph_service import TopologyGraphService
        service = TopologyGraphService(uri="bolt://nonexistent:7687")
        service._initialize()
        assert service._initialized is True

    def test_add_element_in_memory_fallback(self):
        """Add element should work with in-memory fallback."""
        from fireai.infrastructure.topology_graph_service import (
            ElementType,
            NetworkElement,
            TopologyGraphService,
        )
        service = TopologyGraphService(uri="bolt://nonexistent:7687")
        service._initialize()
        element = NetworkElement(
            element_id="BUS-001",
            element_type=ElementType.BUS,
            name="Main Bus",
            properties={"voltage_kv": 13.8},
        )
        assert service.add_element(element) is True

    def test_add_connection_in_memory_fallback(self):
        """Add connection should work with in-memory fallback."""
        from fireai.infrastructure.topology_graph_service import (
            ElementType,
            NetworkConnection,
            NetworkElement,
            RelationshipType,
            TopologyGraphService,
        )
        service = TopologyGraphService(uri="bolt://nonexistent:7687")
        service._initialize()

        # Add two elements first
        service.add_element(NetworkElement(
            element_id="BUS-001", element_type=ElementType.BUS, name="Bus 1"))
        service.add_element(NetworkElement(
            element_id="BUS-002", element_type=ElementType.BUS, name="Bus 2"))

        conn = NetworkConnection(
            from_element="BUS-001",
            to_element="BUS-002",
            relationship_type=RelationshipType.FEEDS,
        )
        assert service.add_connection(conn) is True

    def test_impact_analysis_in_memory(self):
        """Impact analysis should work with in-memory fallback."""
        from fireai.infrastructure.topology_graph_service import (
            ElementType,
            NetworkConnection,
            NetworkElement,
            RelationshipType,
            TopologyGraphService,
        )
        service = TopologyGraphService(uri="bolt://nonexistent:7687")
        service._initialize()

        # Build a simple topology: BRK-001 → BUS-001 → LOAD-001
        service.add_element(NetworkElement(
            element_id="BRK-001", element_type=ElementType.BREAKER, name="Main Breaker"))
        service.add_element(NetworkElement(
            element_id="BUS-001", element_type=ElementType.BUS, name="Main Bus"))
        service.add_element(NetworkElement(
            element_id="LOAD-001", element_type=ElementType.LOAD, name="Building Load"))

        service.add_connection(NetworkConnection(
            from_element="BRK-001", to_element="BUS-001",
            relationship_type=RelationshipType.FEEDS))
        service.add_connection(NetworkConnection(
            from_element="BUS-001", to_element="LOAD-001",
            relationship_type=RelationshipType.FEEDS))

        result = service.analyze_breaker_impact("BRK-001")
        assert result.breaker_id == "BRK-001"
        assert "BUS-001" in result.affected_buses
        assert "LOAD-001" in result.affected_loads
        assert result.analysis_ms > 0

    def test_health_check_returns_dict(self):
        """Health check should return a dict."""
        from fireai.infrastructure.topology_graph_service import TopologyGraphService
        service = TopologyGraphService(uri="bolt://nonexistent:7687")
        result = service.health_check()
        assert "healthy" in result
        assert isinstance(result["healthy"], bool)

    def test_element_type_enum_has_all_types(self):
        """ElementType should have all expected types."""
        from fireai.infrastructure.topology_graph_service import ElementType
        assert ElementType.BUS.value == "Bus"
        assert ElementType.LINE.value == "Line"
        assert ElementType.TRANSFORMER.value == "Transformer"
        assert ElementType.LOAD.value == "Load"
        assert ElementType.BREAKER.value == "Breaker"
        assert ElementType.GENERATOR.value == "Generator"

    def test_get_topology_service_singleton(self):
        """get_topology_service should return the same instance."""
        from fireai.infrastructure.topology_graph_service import (
            TopologyGraphService,
            get_topology_service,
        )
        s1 = get_topology_service()
        s2 = get_topology_service()
        assert s1 is s2
        assert isinstance(s1, TopologyGraphService)

    def test_impact_analysis_result_to_dict(self):
        """ImpactAnalysisResult should serialize correctly."""
        from fireai.infrastructure.topology_graph_service import ImpactAnalysisResult
        result = ImpactAnalysisResult(
            breaker_id="BRK-001",
            affected_loads=["LOAD-001", "LOAD-002"],
            affected_buses=["BUS-001"],
            path_count=3,
            analysis_ms=5.2,
        )
        d = result.to_dict()
        assert d["breaker_id"] == "BRK-001"
        assert d["affected_count"] == 3
        assert d["path_count"] == 3


# ---------------------------------------------------------------------------
# V2 API Endpoint Tests
# ---------------------------------------------------------------------------


class TestV2MemoryTopologyEndpoints:
    """Tests for /api/v2/memory/* and /api/v2/topology/* endpoints."""

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("FIREAI_API_KEY", "test-key-for-v141-1234567890")
        from backend.app import app
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        return {"X-API-Key": "test-key-for-v141-1234567890"}

    def test_memory_health_endpoint(self, client, auth_headers):
        """/api/v2/memory/health should return health status."""
        r = client.get("/api/v2/memory/health", headers=auth_headers)
        assert r.status_code == 200
        assert "healthy" in r.json()

    def test_topology_health_endpoint(self, client, auth_headers):
        """/api/v2/topology/health should return health status."""
        r = client.get("/api/v2/topology/health", headers=auth_headers)
        assert r.status_code == 200
        assert "healthy" in r.json()

    def test_topology_add_element(self, client, auth_headers):
        """Add element endpoint should work (in-memory fallback)."""
        r = client.post("/api/v2/topology/element", json={
            "element_id": "BUS-TEST",
            "element_type": "Bus",
            "name": "Test Bus",
            "properties": {"voltage_kv": 13.8},
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["added"] is True

    def test_topology_add_connection(self, client, auth_headers):
        """Add connection endpoint should work."""
        # First add two elements
        client.post("/api/v2/topology/element", json={
            "element_id": "BUS-A2", "element_type": "Bus", "name": "A",
        }, headers=auth_headers)
        client.post("/api/v2/topology/element", json={
            "element_id": "BUS-B2", "element_type": "Bus", "name": "B",
        }, headers=auth_headers)

        r = client.post("/api/v2/topology/connection", json={
            "from_element": "BUS-A2",
            "to_element": "BUS-B2",
            "relationship_type": "FEEDS",
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["added"] is True

    def test_topology_impact_analysis(self, client, auth_headers):
        """Impact analysis endpoint should return affected elements."""
        # Build topology: BRK → BUS → LOAD
        for eid, etype in [("BRK-I2", "Breaker"), ("BUS-I2", "Bus"), ("LOAD-I2", "Load")]:
            client.post("/api/v2/topology/element", json={
                "element_id": eid, "element_type": etype, "name": eid,
            }, headers=auth_headers)

        for frm, to in [("BRK-I2", "BUS-I2"), ("BUS-I2", "LOAD-I2")]:
            client.post("/api/v2/topology/connection", json={
                "from_element": frm, "to_element": to,
                "relationship_type": "FEEDS",
            }, headers=auth_headers)

        r = client.post("/api/v2/topology/impact", json={
            "breaker_id": "BRK-I2",
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["breaker_id"] == "BRK-I2"
        assert "LOAD-I2" in data["affected_loads"]
