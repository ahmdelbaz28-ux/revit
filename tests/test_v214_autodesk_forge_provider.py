"""
test_v214_autodesk_forge_provider.py — V214 regression tests for
AutodeskForgeProvider real APS API implementation.

Verifies that the 5 methods are no longer STUBs:
  1. _get_auth_token() — real APS OAuth2 client_credentials flow
  2. extract_rooms() — real Model Derivative API calls
  3. read_devices() — real Model Derivative API calls
  4. write_devices() — real Design Automation API (no more NotImplementedError)
  5. health_check() — real authentication check (no more hardcoded healthy=False)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from fireai.bridges.bim_provider import AutodeskForgeProvider


class TestV214AutodeskForgeProviderRealImplementation:
    """V214: AutodeskForgeProvider must have real APS API implementation,
    not STUBs that return None / [] / NotImplementedError.
    """

    def test_get_auth_token_uses_real_aps_endpoint(self):
        """_get_auth_token must call the real APS authentication endpoint
        (not just return None as a STUB).
        """
        provider = AutodeskForgeProvider(
            client_id="test_id",
            client_secret="test_secret",
        )

        # Mock httpx.post to simulate a successful APS response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "fake_token_abc123",
            "expires_in": 3600,
        }

        with patch("httpx.post", return_value=mock_response) as mock_post:
            token = provider._get_auth_token()

        assert token == "fake_token_abc123"
        # Verify the real APS endpoint was called
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "developer.api.autodesk.com/authentication/v1/authenticate" in call_args[0][0]
        # Verify client_credentials grant type
        data = call_args[1].get("data") or call_args[0][1]
        assert data["client_id"] == "test_id"
        assert data["client_secret"] == "test_secret"
        assert data["grant_type"] == "client_credentials"

    def test_get_auth_token_returns_none_without_credentials(self):
        """_get_auth_token must return None when credentials are missing."""
        provider = AutodeskForgeProvider(client_id=None, client_secret=None)
        token = provider._get_auth_token()
        assert token is None

    def test_get_auth_token_caches_token_until_expiry(self):
        """_get_auth_token must cache the token and not re-authenticate
        on every call (until expiry).
        """
        provider = AutodeskForgeProvider(
            client_id="test_id",
            client_secret="test_secret",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "cached_token",
            "expires_in": 3600,
        }

        with patch("httpx.post", return_value=mock_response) as mock_post:
            token1 = provider._get_auth_token()
            token2 = provider._get_auth_token()  # Should use cache

        assert token1 == "cached_token"
        assert token2 == "cached_token"
        # httpx.post should only be called once (cache hit on second call)
        assert mock_post.call_count == 1

    def test_extract_rooms_calls_real_model_derivative_api(self):
        """extract_rooms must call the real Model Derivative API endpoints
        (not just return [] as a STUB).
        """
        provider = AutodeskForgeProvider(
            client_id="test_id",
            client_secret="test_secret",
        )

        # Mock _get_auth_token to return a fake token
        with patch.object(provider, "_get_auth_token", return_value="fake_token"):
            # Mock httpx.get for the two API calls (metadata + object tree)
            mock_metadata_resp = MagicMock()
            mock_metadata_resp.status_code = 200
            mock_metadata_resp.json.return_value = {
                "data": {"metadata": [{"guid": "test_guid"}]}
            }

            mock_tree_resp = MagicMock()
            mock_tree_resp.status_code = 200
            mock_tree_resp.json.return_value = {
                "data": {
                    "objects": [
                        {"name": "Revit.Room_001", "objectid": 100},
                        {"name": "Revit.Room_002", "objectid": 101},
                        {"name": "Revit.Wall_001", "objectid": 200},  # not a room
                    ]
                }
            }

            with patch("httpx.get", side_effect=[mock_metadata_resp, mock_tree_resp]) as mock_get:
                rooms = provider.extract_rooms(source="test_urn")

        assert len(rooms) == 2
        assert rooms[0].name == "Revit.Room_001"
        assert rooms[1].name == "Revit.Room_002"
        # Verify real APS endpoint was called
        assert mock_get.call_count == 2
        assert "modelderivative/v2/designdata" in mock_get.call_args_list[0][0][0]

    def test_read_devices_calls_real_model_derivative_api(self):
        """read_devices must call the real Model Derivative API and filter
        for fire alarm device keywords.
        """
        provider = AutodeskForgeProvider(
            client_id="test_id",
            client_secret="test_secret",
        )

        with patch.object(provider, "_get_auth_token", return_value="fake_token"):
            mock_metadata_resp = MagicMock()
            mock_metadata_resp.status_code = 200
            mock_metadata_resp.json.return_value = {
                "data": {"metadata": [{"guid": "test_guid"}]}
            }

            mock_tree_resp = MagicMock()
            mock_tree_resp.status_code = 200
            mock_tree_resp.json.return_value = {
                "data": {
                    "objects": [
                        {"name": "Smoke Detector SD-01", "objectid": 100},
                        {"name": "Horn Strobe HS-01", "objectid": 101},
                        {"name": "Wall_001", "objectid": 200},  # not a device
                    ]
                }
            }

            with patch("httpx.get", side_effect=[mock_metadata_resp, mock_tree_resp]):
                devices = provider.read_devices(source="test_urn")

        assert len(devices) == 2
        assert devices[0]["name"] == "Smoke Detector SD-01"
        assert devices[1]["name"] == "Horn Strobe HS-01"

    def test_write_devices_does_not_raise_not_implemented(self):
        """write_devices must NOT raise NotImplementedError.
        Previously it always raised. Now it returns 0 on failure (missing
        params) or the device count on success.
        """
        provider = AutodeskForgeProvider(
            client_id="test_id",
            client_secret="test_secret",
        )

        with patch.object(provider, "_get_auth_token", return_value="fake_token"):
            # Without app_bundle/activity_id/input_rvt_urn, should return 0
            # (NOT raise NotImplementedError)
            result = provider.write_devices(
                devices=[{"id": "d1", "name": "Smoke Detector"}],
                target=None,
            )
            assert result == 0

    def test_write_devices_calls_real_design_automation_api(self):
        """write_devices must call the real Design Automation API
        (POST /daus/v2/workitems) when all parameters are provided.
        """
        provider = AutodeskForgeProvider(
            client_id="test_id",
            client_secret="test_secret",
        )

        with patch.object(provider, "_get_auth_token", return_value="fake_token"):
            mock_create_resp = MagicMock()
            mock_create_resp.status_code = 201
            mock_create_resp.json.return_value = {"id": "workitem_123"}

            mock_poll_resp = MagicMock()
            mock_poll_resp.status_code = 200
            mock_poll_resp.json.return_value = {"status": "success"}

            with patch("httpx.post", return_value=mock_create_resp) as mock_post, \
                 patch("httpx.get", return_value=mock_poll_resp):
                result = provider.write_devices(
                    devices=[{"id": "d1", "name": "Smoke Detector"}],
                    target="oss://bucket/output.rvt",
                    app_bundle="FireAI_Revit_Plugin",
                    activity_id="FireAI_CreateDevices",
                    input_rvt_urn="oss://bucket/input.rvt",
                )

            assert result == 1  # 1 device written
            # Verify real Design Automation endpoint was called
            mock_post.assert_called_once()
            assert "daus/v2/workitems" in mock_post.call_args[0][0]

    def test_health_check_performs_real_authentication(self):
        """health_check must call _get_auth_token() and return healthy=True
        when authentication succeeds (not hardcoded healthy=False).
        """
        provider = AutodeskForgeProvider(
            client_id="test_id",
            client_secret="test_secret",
        )

        with patch.object(provider, "_get_auth_token", return_value="fake_token"):
            result = provider.health_check()

        assert result["healthy"] is True
        assert "latency_ms" in result
        assert "token_expires_at" in result

    def test_health_check_returns_false_when_auth_fails(self):
        """health_check must return healthy=False when authentication fails."""
        provider = AutodeskForgeProvider(
            client_id="bad_id",
            client_secret="bad_secret",
        )

        with patch.object(provider, "_get_auth_token", return_value=None):
            result = provider.health_check()

        assert result["healthy"] is False
        # Accept either regular dash or em dash
        assert "Authentication failed" in result["details"] or "authentication failed" in result["details"].lower()

    def test_no_stub_markers_in_source(self):
        """The source file must NOT contain actual STUB return patterns
        (return None # STUB, return [] # STUB) as code.
        STUB mentions in docstrings/comments are allowed (historical notes).
        """
        import re
        src_path = "fireai/bridges/bim_provider.py"
        with open(src_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for actual STUB return patterns as CODE (not in comments)
        # Lines that have 'return None' or 'return []' followed by STUB comment
        stub_code_pattern = re.compile(r'^[^#]*return\s+(None|\[\])\s*.*STUB', re.MULTILINE | re.IGNORECASE)
        matches = stub_code_pattern.findall(content)
        assert matches == [], (
            f"Found STUB return patterns as code in {src_path}: {matches}"
        )

        # Also verify no NotImplementedError with STUB in the message
        notimpl_stub_pattern = re.compile(r'NotImplementedError\([^)]*STUB[^)]*\)', re.IGNORECASE)
        notimpl_matches = notimpl_stub_pattern.findall(content)
        assert notimpl_matches == [], (
            f"Found NotImplementedError with STUB in {src_path}: {notimpl_matches}"
        )
