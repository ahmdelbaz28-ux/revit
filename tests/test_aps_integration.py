"""
tests/test_aps_integration.py — Integration and Unit tests for Autodesk Platform Services.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app import app
from backend.services.aps_service import ApsService, get_aps_service


class TestApsService:
    """Verifies Autodesk Platform Services backend service logic."""

    def test_singleton_get_instance(self):
        """get_aps_service must return the same singleton instance."""
        svc1 = get_aps_service()
        svc2 = get_aps_service()
        assert svc1 is svc2
        assert isinstance(svc1, ApsService)

    def test_get_token_simulation(self):
        """get_token must return a mock token in simulation mode."""
        svc = ApsService()
        svc.simulation_mode = True
        res = svc.get_token()
        assert res["success"] is True
        assert "access_token" in res
        assert res["simulation_mode"] is True

    def test_create_bucket_simulation(self):
        """create_bucket must mock creation in simulation mode."""
        svc = ApsService()
        svc.simulation_mode = True
        res = svc.create_bucket("test_bucket", "mock_token")
        assert res["success"] is True
        assert res["bucketKey"] == "test_bucket"

    def test_upload_file_simulation(self):
        """upload_file must mock uploads in simulation mode."""
        svc = ApsService()
        svc.simulation_mode = True
        res = svc.upload_file("test_bucket", "test.dwg", "dummy_path", "mock_token")
        assert res["success"] is True
        assert "urn:adsk.objects" in res["objectId"]

    def test_execute_work_item_simulation(self):
        """execute_work_item must mock execution job creation in simulation mode."""
        svc = ApsService()
        svc.simulation_mode = True
        res = svc.execute_work_item("test_activity", "input_urn", "output_urn", {}, "mock_token")
        assert res["success"] is True
        assert "mock_work_item" in res["work_item_id"]

    def test_poll_work_item_simulation(self):
        """poll_work_item must mock successful execution in simulation mode."""
        svc = ApsService()
        svc.simulation_mode = True
        res = svc.poll_work_item("mock_work_item_id", "mock_token")
        assert res["success"] is True
        assert res["status"] == "success"
        assert res["progress"] == "100%"


class TestApsRouterEndpoints:
    """Verifies FastAPI API routes for Autodesk Platform Services Design Automation."""

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("FIREAI_API_KEY", "test-key-for-v2-api-testing-1234567890")
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        # The app uses API key auth middleware
        return {"X-API-Key": "test-key-for-v2-api-testing-1234567890"}

    def test_process_endpoint_simulation(self, client, auth_headers):
        """POST /api/v2/aps/process must successfully trigger WorkItem simulation."""
        # Enable simulation mode on the singleton service
        svc = get_aps_service()
        svc.simulation_mode = True

        payload = {
            "bucket_key": "bazspark_test_bucket",
            "object_key": "drawing.dwg",
            "activity_id": "BazSparkAutoCADBridge.DrawLayout",
            "params": {"NFPA72": "true", "detector_density": 0.8}
        }

        res = client.post("/api/v2/aps/process", json=payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "work_item_id" in data
        assert data["simulation_mode"] is True

    def test_status_endpoint_simulation(self, client, auth_headers):
        """GET /api/v2/aps/status/{work_item_id} must successfully poll progress simulation."""
        # Enable simulation mode on the singleton service
        svc = get_aps_service()
        svc.simulation_mode = True

        res = client.get("/api/v2/aps/status/mock_work_item_123", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["status"] == "success"
        assert data["progress"] == "100%"
        assert data["simulation_mode"] is True
