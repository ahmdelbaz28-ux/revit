"""
tests/test_speckle_integration.py — Integration tests for Speckle service and agent commands.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.services.speckle_service import get_speckle_service, SpeckleService
from scripts.local_agent import _dispatch_autocad, _dispatch_revit


class TestSpeckleService:
    """Verifies backend/services/speckle_service.py behaviors."""

    def test_singleton_get_instance(self):
        """get_speckle_service must return the same singleton instance."""
        svc1 = get_speckle_service()
        svc2 = get_speckle_service()
        assert svc1 is svc2
        assert isinstance(svc1, SpeckleService)

    def test_push_to_speckle_simulation_mode(self):
        """push_to_speckle must succeed and return a commit ID in simulation mode."""
        svc = SpeckleService()
        svc.simulation_mode = True

        elements = [
            {"id": "100", "type": "FireAlarmDetector", "x": 12.5, "y": 45.3},
            {"id": "101", "type": "FACP", "x": 10.0, "y": 10.0}
        ]

        res = svc.push_to_speckle(
            stream_id="test_stream",
            server_url="https://speckle.xyz",
            token="test_token",
            elements=elements
        )

        assert res["success"] is True
        assert "commit_id" in res
        assert res["simulation_mode"] is True

    def test_receive_from_speckle_simulation_mode(self):
        """receive_from_speckle must return mock objects in simulation mode."""
        svc = SpeckleService()
        svc.simulation_mode = True

        res = svc.receive_from_speckle(
            stream_id="test_stream",
            server_url="https://speckle.xyz",
            token="test_token"
        )

        assert res["success"] is True
        assert len(res["elements"]) > 0
        assert res["elements"][0]["type"] == "Wall"
        assert res["simulation_mode"] is True


class TestAgentSpeckleRouting:
    """Verifies local_agent.py dispatches speckle actions through Named Pipe or fallbacks."""

    def test_autocad_speckle_push_routing_fallback(self):
        """Autocad speckle_push falls back to error if C# named pipe is not active."""
        args = {
            "stream_id": "test_stream",
            "server_url": "https://speckle.xyz",
            "token": "test_token"
        }
        res = _dispatch_autocad("speckle_push", args)
        assert res["success"] is False
        assert "only supported when BazSparkAutoCADBridge" in res["error"]

    def test_revit_speckle_pull_routing_fallback(self):
        """Revit speckle_pull falls back to error if C# named pipe is not active."""
        args = {
            "stream_id": "test_stream",
            "server_url": "https://speckle.xyz",
            "token": "test_token"
        }
        res = _dispatch_revit("speckle_pull", args)
        assert res["success"] is False
        assert "only supported when BazSparkRevitBridge" in res["error"]
