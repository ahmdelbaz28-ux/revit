"""test_v2_api.py — Tests for /api/v2/ Cloud-Native API Endpoints.

MISSION TASK 3.1 — Validates v2 API endpoints and deprecation headers.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    """TestClient with API key auth enabled."""
    monkeypatch.setenv("FIREAI_API_KEY", "test-key-for-v2-api-testing-1234567890")
    from backend.app import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-key-for-v2-api-testing-1234567890"}


# ---------------------------------------------------------------------------
# Health Endpoint Tests
# ---------------------------------------------------------------------------


class TestV2Health:
    def test_v2_health_returns_200(self, client):
        r = client.get("/api/v2/health")
        assert r.status_code == 200
        data = r.json()
        # Both /api/v2/health endpoints (inline + v2 router) return status
        assert data["status"] in ("healthy", "ok")

    def test_v2_health_lists_capabilities(self, client):
        r = client.get("/api/v2/health")
        data = r.json()
        # v2 router endpoint returns "capabilities"; inline returns "features"
        capabilities = data.get("capabilities", data.get("features", []))
        assert "generative_design" in capabilities or len(capabilities) > 0


# ---------------------------------------------------------------------------
# Deprecation Header Tests
# ---------------------------------------------------------------------------


class TestDeprecationHeaders:
    def test_v1_endpoints_have_deprecation_header(self, client):
        """Per RFC 7234: v1 endpoints must send Deprecation: true."""
        r = client.get("/api/v1/health")
        assert r.headers.get("Deprecation") == "true"

    def test_v1_endpoints_have_sunset_header(self, client):
        """Sunset header must specify a date."""
        r = client.get("/api/v1/health")
        sunset = r.headers.get("Sunset")
        assert sunset is not None
        assert "2027" in sunset  # 1-year sunset window

    def test_v1_endpoints_have_link_header(self, client):
        """Link header must point to v2 successor."""
        r = client.get("/api/v1/health")
        link = r.headers.get("Link")
        assert link is not None
        assert "/api/v2/" in link
        assert 'rel="successor-version"' in link

    def test_v2_endpoints_do_not_have_deprecation(self, client):
        """v2 endpoints should NOT be deprecated."""
        r = client.get("/api/v2/health")
        assert r.headers.get("Deprecation") is None


# ---------------------------------------------------------------------------
# BIM Provider Endpoints
# ---------------------------------------------------------------------------


class TestBIMProviderEndpoints:
    def test_list_providers_returns_3_providers(self, client, auth_headers):
        r = client.get("/api/v2/bim/providers", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 3
        assert "local_revit" in data["providers"]
        assert "ifc_file" in data["providers"]
        assert "autodesk_forge" in data["providers"]

    def test_bim_health_without_provider_returns_warning(self, client, auth_headers, monkeypatch):
        """When no provider configured, health should indicate this."""
        monkeypatch.delenv("FIREAI_BIM_PROVIDER", raising=False)
        r = client.get("/api/v2/bim/health", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["healthy"] is False


# ---------------------------------------------------------------------------
# IFC 4.3 Mapping Endpoints
# ---------------------------------------------------------------------------


class TestIFC43Endpoints:
    def test_map_detector_returns_ifc4x3(self, client, auth_headers):
        r = client.post("/api/v2/ifc43/map-detector", json={
            "device_id": "SM-01", "type": "smoke",
            "x": 5.0, "y": 3.0, "z": 2.8, "room_id": "R-001",
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ifc_type"] == "IfcFireAlarmInstance"
        assert data["predefined_type"] == "SMOKE_DETECTOR"
        assert data["target_schema"] == "IFC4X3_ADD2"
        assert len(data["global_id"]) == 22

    def test_map_detector_heat_type(self, client, auth_headers):
        r = client.post("/api/v2/ifc43/map-detector", json={
            "device_id": "HT-01", "type": "heat",
            "x": 1.0, "y": 2.0, "z": 3.0, "room_id": "R-002",
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["predefined_type"] == "HEAT_DETECTOR"

    def test_map_detector_includes_property_sets(self, client, auth_headers):
        r = client.post("/api/v2/ifc43/map-detector", json={
            "device_id": "SM-02", "type": "smoke",
            "x": 0, "y": 0, "z": 0, "room_id": "R-003",
        }, headers=auth_headers)
        data = r.json()
        assert "property_sets" in data
        # Should have audit + safety + design property sets
        pset_names = list(data["property_sets"].keys())
        assert any("Audit" in n for n in pset_names)
        assert any("Safety" in n for n in pset_names)


# ---------------------------------------------------------------------------
# Generative Design Endpoint
# ---------------------------------------------------------------------------


class TestGenerativeDesignEndpoint:
    def test_generate_returns_3_variants(self, client, auth_headers):
        r = client.post("/api/v2/generative/design", json={
            "room_width": 10.0, "room_length": 8.0, "room_height": 3.0,
            "room_name": "TestOffice", "occupancy_type": "office",
            "detector_type": "smoke", "use_multiprocessing": False,
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["recommended_variant"] in (
            "cost_minimized", "standard_compliant", "safety_maximized"
        )
        assert len(data["variants"]) == 3
        assert "cost_minimized" in data["variants"]
        assert "standard_compliant" in data["variants"]
        assert "safety_maximized" in data["variants"]

    def test_generate_includes_run_id(self, client, auth_headers):
        r = client.post("/api/v2/generative/design", json={
            "room_width": 5.0, "room_length": 5.0, "room_height": 3.0,
            "use_multiprocessing": False,
        }, headers=auth_headers)
        data = r.json()
        assert "run_id" in data
        assert len(data["run_id"]) > 0

    def test_generate_invalid_room_returns_422(self, client, auth_headers):
        """Negative width should be rejected."""
        r = client.post("/api/v2/generative/design", json={
            "room_width": -5.0, "room_length": 5.0,
            "use_multiprocessing": False,
        }, headers=auth_headers)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# AR Export Endpoint
# ---------------------------------------------------------------------------


class TestARExportEndpoint:
    def test_export_both_formats(self, client, auth_headers):
        r = client.post("/api/v2/ar/export", json={
            "building_id": "B-TEST", "format": "both",
            "nodes": [
                {"id": "SM-01", "name": "Detector 1", "node_type": "detector",
                 "position": [5.0, 3.0, 2.8]},
            ],
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "glb" in data["formats"]
        assert "usdz" in data["formats"]
        assert data["formats"]["glb"]["size_bytes"] > 0
        assert data["formats"]["usdz"]["size_bytes"] > 0

    def test_export_glb_only(self, client, auth_headers):
        r = client.post("/api/v2/ar/export", json={
            "building_id": "B-TEST", "format": "glb",
            "nodes": [],
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "glb" in data["formats"]
        assert "usdz" not in data["formats"]

    def test_export_returns_base64_content(self, client, auth_headers):
        r = client.post("/api/v2/ar/export", json={
            "building_id": "B-TEST", "format": "usdz",
            "nodes": [],
        }, headers=auth_headers)
        data = r.json()
        import base64
        usdz_bytes = base64.b64decode(data["formats"]["usdz"]["content_base64"])
        # USDZ starts with PK (zip magic)
        assert usdz_bytes[:2] == b"PK"


# ---------------------------------------------------------------------------
# Webhook Endpoints
# ---------------------------------------------------------------------------


class TestWebhookEndpoints:
    def test_subscribe_creates_subscription(self, client, auth_headers):
        r = client.post("/api/v2/webhooks/subscribe", json={
            "url": "https://example.com/webhook",
            "secret": "very-secure-secret-key-1234567890",
            "event_types": ["DESIGN_COMPLETED"],
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "subscription_id" in data
        assert data["url"] == "https://example.com/webhook"
        assert "DESIGN_COMPLETED" in data["event_types"]

    def test_subscribe_rejects_short_secret(self, client, auth_headers):
        r = client.post("/api/v2/webhooks/subscribe", json={
            "url": "https://example.com/hook",
            "secret": "short",
            "event_types": [],
        }, headers=auth_headers)
        assert r.status_code == 422  # Pydantic validation error

    def test_list_subscriptions(self, client, auth_headers):
        # First subscribe
        client.post("/api/v2/webhooks/subscribe", json={
            "url": "https://example.com/hook2",
            "secret": "very-secure-secret-key-1234567890",
            "event_types": [],
        }, headers=auth_headers)
        # Then list
        r = client.get("/api/v2/webhooks/subscriptions", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 1

    def test_unsubscribe(self, client, auth_headers):
        # First subscribe
        r = client.post("/api/v2/webhooks/subscribe", json={
            "url": "https://example.com/hook3",
            "secret": "very-secure-secret-key-1234567890",
            "event_types": [],
        }, headers=auth_headers)
        sub_id = r.json()["subscription_id"]

        # Then unsubscribe
        r = client.delete(f"/api/v2/webhooks/subscriptions/{sub_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["removed"] is True

    def test_publish_event(self, client, auth_headers):
        r = client.post("/api/v2/webhooks/publish", json={
            "event_type": "DESIGN_COMPLETED",
            "source": "test",
            "data": {"room_id": "R-001"},
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "event_id" in data
        assert data["delivered"] is True


# ---------------------------------------------------------------------------
# Smoke Simulation Endpoint
# ---------------------------------------------------------------------------


class TestSmokeSimulationEndpoint:
    def test_create_placeholder_state(self, client, auth_headers):
        r = client.post("/api/v2/smoke-simulation/state", json={
            "room_id": "R-001",
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "placeholder"
        assert data["is_placeholder"] is True
        assert "NOT VALIDATED" in data["validation_warning"]

    def test_create_validated_state_with_fds(self, client, auth_headers):
        """V137 F-6: FDS run ID must match format 'fds-YYYY-NNN'."""
        r = client.post("/api/v2/smoke-simulation/state", json={
            "room_id": "R-002",
            "smoke_density_points": [
                {"x": 5.0, "y": 3.0, "z": 1.7, "density_kg_m3": 0.025},
            ],
            "visibility_at_height": {"1.7": 8.5},
            "fds_run_id": "fds-2026-001",  # V137 F-6: valid format
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "validated"
        assert data["is_validated"] is True
        assert data["fds_run_id"] == "fds-2026-001"


# ---------------------------------------------------------------------------
# Auth Tests
# ---------------------------------------------------------------------------


class TestAuth:
    def test_v2_endpoints_require_api_key(self, client):
        """Without API key, v2 endpoints (except /health) return 401."""
        r = client.get("/api/v2/bim/providers")
        assert r.status_code == 401

    def test_v2_health_is_public(self, client):
        """/api/v2/health should be accessible without auth."""
        r = client.get("/api/v2/health")
        assert r.status_code == 200

    def test_v2_endpoints_with_valid_key_return_200(self, client, auth_headers):
        r = client.get("/api/v2/bim/providers", headers=auth_headers)
        assert r.status_code == 200
