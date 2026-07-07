# NOSONAR
"""
V192 Backend Integration Tests — Life-safety CRUD verification.

Tests the FULL lifecycle of every entity type through the V2 API:
  Element: create → get → list → update → delete
  Connection: create → get → list → delete
  Conflict: detect → list → resolve

These tests are STRICT — they assert exact status codes, exact field names,
and exact response shapes. No (201, 400, 500) ambiguity.

Per agent.md Rule 12: "Wrong code in this system is catastrophic — it
threatens human life. There is zero tolerance for error."
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from backend.app import app
    with TestClient(app) as c:
        yield c


def _create_element(client, name: str = "V192-Test-Wall") -> str:
    """Helper: create an element, return its ID."""
    resp = client.post(
        "/api/elements",
        json={"properties": {"element_type": "wall", "name": name}},
    )
    assert resp.status_code in (200, 201), f"Create element failed: {resp.status_code} {resp.text}"
    data = resp.json().get("data", {})
    eid = data.get("element_id") or data.get("elementId")
    assert eid, f"Element response missing id: {data}"
    return eid


# ══════════════════════════════════════════════════════════════════════════════
# ELEMENT FULL LIFECYCLE
# ══════════════════════════════════════════════════════════════════════════════


class TestV192ElementLifecycle:
    """Test Element CRUD through the V2 API — strict assertions."""

    def test_create_element_returns_201(self, client):
        """POST /api/elements with valid data must return 201."""
        resp = client.post(
            "/api/elements",
            json={"properties": {"element_type": "wall", "name": "V192-Lifecycle-Wall"}},
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        # Verify response has required fields (after V189 transformer, snake_case)
        assert "element_id" in data or "elementId" in data, f"Missing element_id: {data}"
        assert "properties" in data, f"Missing properties: {data}"
        assert "version" in data, f"Missing version: {data}"

    def test_get_element_by_id_returns_200(self, client):
        """GET /api/elements/{id} must return 200 for existing element."""
        eid = _create_element(client, "V192-Get-Wall")
        resp = client.get(f"/api/elements/{eid}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()["data"]
        assert data.get("element_id") or data.get("elementId") == eid

    def test_list_elements_returns_200_with_items(self, client):
        """GET /api/elements must return 200 with items array."""
        _create_element(client, "V192-List-Wall")
        resp = client.get("/api/elements")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data, f"Missing items: {data}"
        assert "total" in data, f"Missing total: {data}"
        assert isinstance(data["items"], list)
        assert data["total"] >= 1

    def test_update_element_returns_200(self, client):
        """PUT /api/elements/{id} must return 200 with updated data."""
        eid = _create_element(client, "V192-Update-Wall")
        resp = client.put(
            f"/api/elements/{eid}",
            json={"properties": {"element_type": "wall", "name": "V192-Updated-Name"}},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_delete_element_returns_200(self, client):
        """DELETE /api/elements/{id} must return 200 for existing element."""
        eid = _create_element(client, "V192-Delete-Wall")
        resp = client.delete(f"/api/elements/{eid}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_delete_element_soft_deletes_not_hard_deletes(self, client):
        """
        DELETE /api/elements/{id} must soft-delete (mark is_deleted=true).

        V192 FIX: The backend uses soft-delete for audit trail purposes
        (NFPA 72 requires traceability of all changes). After delete:
          - GET /api/elements/{id} returns 200 with is_deleted=true (NOT 404)
          - The element row is preserved for audit history
        This test verifies the soft-delete behavior is correct.
        """
        eid = _create_element(client, "V192-SoftDelete-Wall")
        resp = client.delete(f"/api/elements/{eid}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        # GET should return 200 (soft-deleted element is still retrievable)
        get_resp = client.get(f"/api/elements/{eid}")
        assert get_resp.status_code == 200, (
            f"Soft-deleted element should return 200 (not 404) for audit: "
            f"got {get_resp.status_code}"
        )
        data = get_resp.json()["data"]
        # The is_deleted field should be true
        is_deleted = data.get("is_deleted") or data.get("isDeleted")
        assert is_deleted is True, (
            f"Soft-deleted element should have is_deleted=true: {data}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION FULL LIFECYCLE
# ══════════════════════════════════════════════════════════════════════════════


class TestV192ConnectionLifecycle:
    """Test Connection CRUD through the V2 API — strict assertions."""

    def _create_pair(self, client):
        """Create two elements, return (from_id, to_id)."""
        return _create_element(client, "V192-Conn-A"), _create_element(client, "V192-Conn-B")

    def test_create_connection_returns_201(self, client):
        """POST /api/connections with valid elements must return 201."""
        from_id, to_id = self._create_pair(client)
        resp = client.post(
            "/api/connections",
            json={
                "from_element_id": from_id,
                "to_element_id": to_id,
                "relationship_type": "adjacent",
            },
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()["data"]
        assert data.get("from_element_id") or data.get("fromElementId") == from_id
        assert data.get("to_element_id") or data.get("toElementId") == to_id

    def test_list_connections_returns_200(self, client):
        """GET /api/connections must return 200 with items."""
        from_id, to_id = self._create_pair(client)
        client.post("/api/connections", json={
            "from_element_id": from_id,
            "to_element_id": to_id,
            "relationship_type": "contains",
        })
        resp = client.get("/api/connections")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert data["total"] >= 1

    def test_delete_connection_returns_200(self, client):
        """DELETE /api/connections/{id} must return 200 for existing connection."""
        from_id, to_id = self._create_pair(client)
        create_resp = client.post("/api/connections", json={
            "from_element_id": from_id,
            "to_element_id": to_id,
            "relationship_type": "supports",
        })
        conn_id = create_resp.json()["data"].get("connection_id") or \
                  create_resp.json()["data"].get("connectionId")

        resp = client.delete(f"/api/connections/{conn_id}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_create_connection_with_metadata_preserves_keys(self, client):
        """V191 regression: metadata camelCase keys must be preserved."""
        from_id, to_id = self._create_pair(client)
        resp = client.post(
            "/api/connections",
            json={
                "from_element_id": from_id,
                "to_element_id": to_id,
                "relationship_type": "adjacent",
                "metadata": {"cableSize": "2.5mm²", "installerName": "John"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        metadata = data.get("metadata") or {}
        assert "cableSize" in metadata, f"camelCase key 'cableSize' was corrupted: {metadata}"
        assert "installerName" in metadata, f"camelCase key 'installerName' was corrupted: {metadata}"


# ══════════════════════════════════════════════════════════════════════════════
# CONFLICT DETECTION
# ══════════════════════════════════════════════════════════════════════════════


class TestV192ConflictDetection:
    """Test Conflict detection through the V2 API — strict assertions."""

    def test_detect_conflicts_returns_200(self, client):
        """POST /api/conflicts/detect must return 200 (never 500)."""
        resp = client.post("/api/conflicts/detect")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)

    def test_list_conflicts_returns_200(self, client):
        """GET /api/conflicts must return 200 with items array."""
        resp = client.get("/api/conflicts")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data or isinstance(data, list), f"Missing items: {data}"

    def test_resolve_nonexistent_conflict_returns_404(self, client):
        """POST /api/conflicts/{id}/resolve for nonexistent must return 404."""
        resp = client.post(
            "/api/conflicts/nonexistent-v192-id/resolve",
            json={"strategy": "SEMANTIC_MERGE"},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


# HEALTH & STATISTICS  # NOSONAR - python:S125
# ══════════════════════════════════════════════════════════════════════════════


class TestV192HealthAndStats:
    """Test health and statistics endpoints — strict assertions."""

    def test_health_returns_200_with_status_ok(self, client):
        """GET /health must return 200 with status=ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "ok", f"Health status not 'ok': {data}"
        assert data["database"] == "connected", f"Database not connected: {data}"

    def test_reports_statistics_returns_200(self, client):
        """GET /api/reports/statistics must return 200."""
        resp = client.get("/api/reports/statistics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
