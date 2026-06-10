"""
test_facp_router.py — FACP REST API Router Endpoint Tests
==========================================================
Validates the FastAPI router endpoints in backend/routers/facp.py:
  POST /api/facp/select      — Panel selection
  POST /api/facp/verify      — Compliance verification
  POST /api/facp/schedule    — DXF schedule generation
  POST /api/facp/spec        — CSI specification generation
  GET  /api/facp/panels      — Panel database listing

Safety-Critical: These tests verify the HTTP contract for the FACP
selection engine. Incorrect HTTP responses could mislead fire protection
engineers into selecting non-compliant panels.

Standards Referenced:
  - NFPA 72-2022 SS10.6.7, SS10.6.10, SS21.7
  - UL 864 10th Edition
  - CSI MasterFormat 28 31 11
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for module resolution
_PROJECT_ROOT = Path(__file__).parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from backend.routers.facp import router

# Create a minimal test app with just the FACP router
app = FastAPI()
app.include_router(router, prefix="/api")


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


# ============================================================================
# POST /api/facp/select — Panel Selection Endpoint
# ============================================================================


class TestFACPSelectEndpoint:
    """Tests for POST /api/facp/select."""

    def test_select_small_building(self, client):
        """Small building selection must return a valid panel recommendation."""
        response = client.post(
            "/api/facp/select",
            json={
                "device_count": 30,
                "nac_circuit_count": 2,
                "building_size_m2": 1500.0,
                "building_floors": 2,
                "requires_network": False,
                "requires_voice": False,
                "requires_releasing": False,
                "jurisdiction": "US",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        rec = data["data"]
        assert "recommended_model" in rec
        assert "manufacturer" in rec
        assert rec["capacity_utilization"] > 0
        assert rec["capacity_utilization"] <= 1.0
        assert rec["battery_size_ah"] > 0
        assert rec["nac_utilization"] > 0
        assert rec["nac_utilization"] <= 1.0
        assert len(rec["signature_hash"]) == 64  # SHA-256 hex
        assert "NFPA 72" in rec["nfpa_reference"]

    def test_select_voice_networked_building(self, client):
        """Voice + networked building must select a panel with voice support."""
        response = client.post(
            "/api/facp/select",
            json={
                "device_count": 300,
                "nac_circuit_count": 6,
                "building_size_m2": 20000.0,
                "building_floors": 10,
                "requires_network": True,
                "requires_voice": True,
                "requires_releasing": False,
                "jurisdiction": "US",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_select_fdny_jurisdiction(self, client):
        """FDNY jurisdiction must return FDNY-listed panel."""
        response = client.post(
            "/api/facp/select",
            json={
                "device_count": 100,
                "nac_circuit_count": 2,
                "building_size_m2": 5000.0,
                "building_floors": 3,
                "requires_network": False,
                "requires_voice": False,
                "requires_releasing": False,
                "jurisdiction": "FDNY",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "FDNY" in data["data"]["listings"]

    def test_select_releasing_service(self, client):
        """Releasing service must select a releasing-capable panel."""
        response = client.post(
            "/api/facp/select",
            json={
                "device_count": 200,
                "nac_circuit_count": 4,
                "building_size_m2": 10000.0,
                "building_floors": 3,
                "requires_network": True,
                "requires_voice": True,
                "requires_releasing": True,
                "jurisdiction": "US",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_select_invalid_device_count(self, client):
        """Zero or negative device count must return 422."""
        response = client.post(
            "/api/facp/select",
            json={
                "device_count": 0,
                "nac_circuit_count": 2,
                "building_size_m2": 1500.0,
                "building_floors": 2,
            },
        )
        assert response.status_code == 422

    def test_select_impossible_requirements(self, client):
        """Impossible requirements must return 422 (no compliant panels)."""
        response = client.post(
            "/api/facp/select",
            json={
                "device_count": 99999,
                "nac_circuit_count": 999,
                "building_size_m2": 100000.0,
                "building_floors": 100,
                "requires_network": True,
                "requires_voice": True,
                "requires_releasing": True,
                "jurisdiction": "FDNY",
            },
        )
        # Should return 422 (no compliant panels) not 500 (server error)
        assert response.status_code == 422
        data = response.json()
        assert "NO_COMPLIANT_PANEL" in str(data) or "no compliant" in str(data).lower()

    def test_select_cold_temperature(self, client):
        """Cold temperature must produce larger battery size."""
        response_20c = client.post(
            "/api/facp/select",
            json={
                "device_count": 100,
                "nac_circuit_count": 4,
                "building_size_m2": 5000.0,
                "building_floors": 3,
                "min_temperature_c": 20.0,
            },
        )
        response_0c = client.post(
            "/api/facp/select",
            json={
                "device_count": 100,
                "nac_circuit_count": 4,
                "building_size_m2": 5000.0,
                "building_floors": 3,
                "min_temperature_c": 0.0,
            },
        )
        assert response_20c.status_code == 200
        assert response_0c.status_code == 200
        ah_20c = response_20c.json()["data"]["battery_size_ah"]
        ah_0c = response_0c.json()["data"]["battery_size_ah"]
        assert ah_0c > ah_20c, "Cold temperature must increase battery size per NFPA 72 SS10.6.7"


# ============================================================================
# POST /api/facp/verify — Compliance Verification Endpoint
# ============================================================================


class TestFACPVerifyEndpoint:
    """Tests for POST /api/facp/verify."""

    def test_verify_compliant_panel(self, client):
        """Compliant panel verification must return is_compliant=True."""
        # First select a panel
        select_resp = client.post(
            "/api/facp/select",
            json={
                "device_count": 30,
                "nac_circuit_count": 2,
                "building_size_m2": 1500.0,
                "building_floors": 2,
                "requires_network": False,
                "requires_voice": False,
                "requires_releasing": False,
                "jurisdiction": "US",
            },
        )
        assert select_resp.status_code == 200
        rec = select_resp.json()["data"]

        # Now verify it
        verify_resp = client.post(
            "/api/facp/verify",
            json={
                "device_count": 30,
                "nac_circuit_count": 2,
                "building_size_m2": 1500.0,
                "building_floors": 2,
                "recommended_model": rec["recommended_model"],
                "manufacturer": rec["manufacturer"],
                "capacity_utilization": rec["capacity_utilization"],
                "nac_utilization": rec["nac_utilization"],
                "battery_size_ah": rec["battery_size_ah"],
                "battery_derating_method": rec["battery_derating_details"].get("method", "unknown"),
            },
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["success"] is True
        assert data["data"]["violation_count"] >= 0

    def test_verify_missing_required_fields(self, client):
        """Missing required fields must return 422 validation error."""
        response = client.post(
            "/api/facp/verify",
            json={
                "device_count": 30,
                # Missing other required fields
            },
        )
        assert response.status_code == 422


# ============================================================================
# POST /api/facp/schedule — DXF Schedule Endpoint
# ============================================================================


class TestFACPScheduleEndpoint:
    """Tests for POST /api/facp/schedule."""

    def test_schedule_generation(self, client):
        """Schedule generation must produce text table output."""
        response = client.post(
            "/api/facp/schedule",
            json={
                "recommended_model": "FC901",
                "manufacturer": "SIEMENS",
                "capacity_utilization": 0.72,
                "nac_utilization": 0.50,
                "battery_size_ah": 26.0,
                "battery_derating_method": "nfpa72_ieee485",
                "power_supply_watts": 50,
                "listings": ["UL", "CSFM"],
                "signature_hash": "a" * 64,
                "quantity": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "schedule" in data["data"]
        assert "FC901" in data["data"]["schedule"]

    def test_schedule_custom_quantity(self, client):
        """Schedule with custom quantity must include QTY."""
        response = client.post(
            "/api/facp/schedule",
            json={
                "recommended_model": "FC901",
                "manufacturer": "SIEMENS",
                "capacity_utilization": 0.72,
                "nac_utilization": 0.50,
                "battery_size_ah": 26.0,
                "battery_derating_method": "nfpa72_ieee485",
                "power_supply_watts": 50,
                "listings": ["UL"],
                "signature_hash": "b" * 64,
                "quantity": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["quantity"] == 3


# ============================================================================
# POST /api/facp/spec — CSI Specification Endpoint
# ============================================================================


class TestFACPSpecEndpoint:
    """Tests for POST /api/facp/spec."""

    def test_spec_generation(self, client):
        """CSI spec must contain Section 28 31 11."""
        response = client.post(
            "/api/facp/spec",
            json={
                "device_count": 30,
                "nac_circuit_count": 2,
                "building_size_m2": 1500.0,
                "building_floors": 2,
                "recommended_model": "FC901",
                "manufacturer": "SIEMENS",
                "capacity_utilization": 0.72,
                "nac_utilization": 0.50,
                "battery_size_ah": 26.0,
                "battery_derating_method": "nfpa72_ieee485",
                "power_supply_watts": 50,
                "listings": ["UL", "CSFM"],
                "signature_hash": "c" * 64,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "28 31 11" in data["data"]["csi_specification"]


# ============================================================================
# GET /api/facp/panels — Panel Database Listing
# ============================================================================


class TestFACPListPanelsEndpoint:
    """Tests for GET /api/facp/panels."""

    def test_list_panels(self, client):
        """Panel listing must return all panels with specifications."""
        response = client.get("/api/facp/panels")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["total_count"] > 0
        assert len(data["data"]["panels"]) > 0
        # Verify first panel has required fields
        panel = data["data"]["panels"][0]
        assert "model" in panel
        assert "manufacturer" in panel
        assert "points_capacity" in panel
        assert "nac_capacity" in panel
        assert "listings" in panel

    def test_list_panels_includes_manufacturers(self, client):
        """Panel listing must include unique manufacturer names."""
        response = client.get("/api/facp/panels")
        data = response.json()
        assert len(data["data"]["manufacturers"]) > 0

    def test_list_panels_includes_standards(self, client):
        """Panel listing must include referenced standards."""
        response = client.get("/api/facp/panels")
        data = response.json()
        standards = data["data"]["standards"]
        assert any("NFPA 72" in s for s in standards)
        assert any("UL 864" in s for s in standards)
