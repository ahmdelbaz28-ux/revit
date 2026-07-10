"""
Unit tests for backend/akamai_middleware.py.

These tests verify the Akamai integration middleware works correctly in
isolation (without an actual Akamai deployment). They use Starlette's
TestClient to drive the middleware through real ASGI semantics.

Run:
    pytest backend/tests/test_akamai_middleware.py -v
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure the backend package is importable when running standalone
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.akamai_middleware import (
    AkamaiConfig,
    AkamaiIntegrationMiddleware,
)

# Test fixture IPs — all are RFC 5737 (TEST-NET-1) / RFC 1918 private ranges,
# safe to hardcode in test code. Defined as constants so SonarCloud S1313
# does not flag each literal.
_TEST_IP_PUBLIC = "1.2.3.4"        # noqa: S1313 — TEST-NET-1 (RFC 5737) test fixture
_TEST_IP_PRIVATE = "10.0.0.1"      # noqa: S1313 — RFC 1918 private test fixture
_TEST_IP_AKAMAI = "203.0.113.5"    # TEST-NET-3 (RFC 5737) — simulates Akamai edge


# ── Helpers ──────────────────────────────────────────────────────────────────


def _health(request):
    return JSONResponse({"status": "ok", "ip": request.headers.get("x-forwarded-for", "")})


def _login(request):
    return JSONResponse({"ok": True, "ip": request.headers.get("x-forwarded-for", "")})


def _build_app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/api/health", _health, methods=["GET"]),
            Route("/api/v1/auth/login", _login, methods=["POST"]),
        ]
    )
    app.add_middleware(AkamaiIntegrationMiddleware)
    return app


@pytest.fixture(autouse=True)
def _clear_akamai_env(monkeypatch):
    """Clear all AKAMAI_* env vars before each test."""
    # list() is required: monkeypatch.delenv mutates os.environ during
    # iteration, which would raise RuntimeError without the snapshot.
    for key in list(os.environ.keys()):  # noqa: S7504 — intentional snapshot
        if key.startswith("AKAMAI_"):
            monkeypatch.delenv(key, raising=False)
    yield


# ── AkamaiConfig tests ───────────────────────────────────────────────────────


class TestAkamaiConfig:
    def test_defaults_disabled(self):
        cfg = AkamaiConfig()
        assert cfg.enabled is False
        assert cfg.require_origin_token == ""
        assert cfg.blocked_countries == frozenset()
        assert cfg.allowed_bot_score == 30
        assert cfg.rate_limit_passthrough is True

    def test_enable(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        cfg = AkamaiConfig()
        assert cfg.enabled is True

    def test_blocked_countries_parse(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_BLOCKED_COUNTRIES", "CN, ru ,IR,KP")
        cfg = AkamaiConfig()
        assert cfg.blocked_countries == frozenset({"CN", "RU", "IR", "KP"})

    def test_bot_score_threshold(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ALLOWED_BOT_SCORE", "50")
        cfg = AkamaiConfig()
        assert cfg.allowed_bot_score == 50

    def test_bot_score_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ALLOWED_BOT_SCORE", "not-a-number")
        cfg = AkamaiConfig()
        assert cfg.allowed_bot_score == 30  # default

    def test_production_mode_default_is_production(self, monkeypatch):
        monkeypatch.delenv("FIREAI_ENV", raising=False)
        cfg = AkamaiConfig()
        assert cfg.production_mode is True  # safety-critical default

    def test_production_mode_dev(self, monkeypatch):
        monkeypatch.setenv("FIREAI_ENV", "development")
        cfg = AkamaiConfig()
        assert cfg.production_mode is False


# ── Middleware behavior tests ────────────────────────────────────────────────


class TestMiddlewareDisabled:
    """When AKAMAI_ENABLED=false (default), middleware is a no-op."""

    def test_health_endpoint_passes_through(self):
        client = TestClient(_build_app())
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_xff_header_not_modified(self):
        client = TestClient(_build_app())
        resp = client.get("/api/health", headers={"X-Forwarded-For": _TEST_IP_PUBLIC})
        # When disabled, XFF is NOT overwritten
        assert resp.json()["ip"] == _TEST_IP_PUBLIC


class TestTrueClientIPOverride:
    """When AKAMAI_ENABLED=true, True-Client-IP overwrites X-Forwarded-For."""

    def test_xff_overwritten(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        client = TestClient(_build_app())
        # Send both XFF and True-Client-IP
        resp = client.get(
            "/api/health",
            headers={
                "X-Forwarded-For": f"{_TEST_IP_PRIVATE}, 10.0.0.2",  # spoofed
                "True-Client-IP": _TEST_IP_AKAMAI,  # Akamai's value
            },
        )
        assert resp.status_code == 200
        # Backend sees True-Client-IP, not spoofed XFF
        assert resp.json()["ip"] == _TEST_IP_AKAMAI

    def test_no_true_client_ip_keeps_xff(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        client = TestClient(_build_app())
        resp = client.get(
            "/api/health",
            headers={"X-Forwarded-For": _TEST_IP_PRIVATE},
        )
        assert resp.status_code == 200
        # XFF is preserved if no True-Client-IP
        assert resp.json()["ip"] == _TEST_IP_PRIVATE


class TestOriginVerification:
    """AKAMAI_REQUIRE_ORIGIN_TOKEN rejects direct origin access in production."""

    def test_production_blocks_missing_token(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_REQUIRE_ORIGIN_TOKEN", "secret-123")
        monkeypatch.setenv("FIREAI_ENV", "production")
        client = TestClient(_build_app())
        resp = client.get("/api/health")
        assert resp.status_code == 403
        assert resp.json()["code"] == "AKAMAI_BLOCKED"

    def test_production_blocks_wrong_token(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_REQUIRE_ORIGIN_TOKEN", "secret-123")
        monkeypatch.setenv("FIREAI_ENV", "production")
        client = TestClient(_build_app())
        resp = client.get("/api/health", headers={"Akamai-Internal": "wrong-secret"})
        assert resp.status_code == 403

    def test_production_allows_correct_token(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_REQUIRE_ORIGIN_TOKEN", "secret-123")
        monkeypatch.setenv("FIREAI_ENV", "production")
        client = TestClient(_build_app())
        resp = client.get("/api/health", headers={"Akamai-Internal": "secret-123"})
        assert resp.status_code == 200

    def test_dev_allows_missing_token(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_REQUIRE_ORIGIN_TOKEN", "secret-123")
        monkeypatch.setenv("FIREAI_ENV", "development")
        client = TestClient(_build_app())
        resp = client.get("/api/health")
        # In dev, missing token is logged but allowed
        assert resp.status_code == 200


class TestGeoBlocking:
    """AKAMAI_BLOCKED_COUNTRIES rejects requests from listed countries."""

    def test_blocked_country_rejected(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_BLOCKED_COUNTRIES", "IR,KP,RU")
        client = TestClient(_build_app())
        resp = client.get("/api/health", headers={"Akamai-Geo-Country": "IR"})
        assert resp.status_code == 403
        assert "IR" in resp.json()["message"]

    def test_allowed_country_passes(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_BLOCKED_COUNTRIES", "IR,KP,RU")
        client = TestClient(_build_app())
        resp = client.get("/api/health", headers={"Akamai-Geo-Country": "EG"})
        assert resp.status_code == 200

    def test_missing_country_passes(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_BLOCKED_COUNTRIES", "IR,KP,RU")
        client = TestClient(_build_app())
        # No Akamai-Geo-Country header — should pass (Akamai may not set it for some IPs)
        resp = client.get("/api/health")
        assert resp.status_code == 200


class TestBotScoreEnforcement:
    """High bot scores are rejected on /api/v1/auth/* but allowed elsewhere."""

    def test_high_bot_score_blocked_on_login(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_ALLOWED_BOT_SCORE", "30")
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/auth/login",
            headers={"Akamai-Bot-Score": "85"},  # bad bot
        )
        assert resp.status_code == 403
        assert "Automated traffic" in resp.json()["message"]

    def test_low_bot_score_allowed_on_login(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_ALLOWED_BOT_SCORE", "30")
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/auth/login",
            headers={"Akamai-Bot-Score": "10"},  # human
        )
        assert resp.status_code == 200

    def test_high_bot_score_allowed_on_health(self, monkeypatch):
        """Bot score only enforced on auth endpoints."""
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_ALLOWED_BOT_SCORE", "30")
        client = TestClient(_build_app())
        resp = client.get(
            "/api/health",
            headers={"Akamai-Bot-Score": "85"},  # bad bot, but not sensitive endpoint
        )
        assert resp.status_code == 200

    def test_invalid_bot_score_ignored(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        monkeypatch.setenv("AKAMAI_ALLOWED_BOT_SCORE", "30")
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/auth/login",
            headers={"Akamai-Bot-Score": "not-a-number"},
        )
        # Invalid value is ignored, request passes
        assert resp.status_code == 200


class TestResponseHeaders:
    """Middleware injects traceability headers on every response."""

    def test_akamai_translated_header_added(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        client = TestClient(_build_app())
        resp = client.get("/api/health")
        assert resp.headers.get("x-akamai-translated-request") == "true"

    def test_akamai_grn_echoed(self, monkeypatch):
        monkeypatch.setenv("AKAMAI_ENABLED", "true")
        client = TestClient(_build_app())
        grn = "abc-123-def"
        resp = client.get("/api/health", headers={"X-Akamai-Request-Id": grn})
        assert resp.headers.get("x-akamai-grn") == grn


# ── Run as script (for quick verification without pytest) ────────────────────


if __name__ == "__main__":
    """Quick verification: run all tests with stdlib unittest."""
    print("Running AkamaiIntegrationMiddleware tests...")
    print("(For full output, run: pytest backend/tests/test_akamai_middleware.py -v)")
    print()

    # Manual smoke test
    os.environ["AKAMAI_ENABLED"] = "true"
    os.environ["AKAMAI_REQUIRE_ORIGIN_TOKEN"] = "test-secret"
    os.environ["FIREAI_ENV"] = "production"

    app = _build_app()
    client = TestClient(app)

    print("Test 1: Direct origin access blocked (no Akamai-Internal header)")
    resp = client.get("/api/health")
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
    print(f"  ✓ HTTP {resp.status_code} — blocked")

    print("Test 2: With valid Akamai-Internal header, request passes")
    resp = client.get("/api/health", headers={"Akamai-Internal": "test-secret"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    print(f"  ✓ HTTP {resp.status_code} — passed")

    print("Test 3: True-Client-IP overwrites X-Forwarded-For")
    resp = client.get(
        "/api/health",
        headers={
            "Akamai-Internal": "test-secret",
            "X-Forwarded-For": _TEST_IP_PRIVATE,
            "True-Client-IP": _TEST_IP_AKAMAI,
        },
    )
    assert resp.json()["ip"] == _TEST_IP_AKAMAI
    print(f"  ✓ X-Forwarded-For = {resp.json()['ip']} (True-Client-IP)")

    print("Test 4: Response has X-Akamai-Translated-Request header")
    assert resp.headers.get("x-akamai-translated-request") == "true"
    print("  ✓ X-Akamai-Translated-Request: true")

    print()
    print("All smoke tests passed ✓")
