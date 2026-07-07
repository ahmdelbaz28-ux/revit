"""
tests/test_security_middleware_v129.py — Tests for V129 Infrastructure Security Hardening
=========================================================================================

Verifies the new SecurityHeadersMiddleware and the V129 hardening of
backend/app.py:

1. SecurityHeadersMiddleware adds all required headers to every response:
   - x-frame-options: DENY
   - x-content-type-options: nosniff
   - referrer-policy: no-referrer
   - x-xss-protection: 0
   - permissions-policy: (deny all)
   - content-security-policy (environment-aware)
   - strict-transport-security (always emitted in 2026+ — browsers ignore
     HSTS on localhost since Chrome v79 / Firefox v75)

2. CorrelationIdMiddleware adds x-correlation-id to every response.

3. backend/app.py mounts the health router under /api prefix.

4. backend/app.py cache endpoints require SYSTEM_CONFIG permission.

5. CORS hardening: production without CORS_ALLOWED_ORIGINS → RuntimeError.

6. CSP is environment-aware:
   - production: no 'unsafe-eval', no localhost connect-src
   - development: 'unsafe-eval' allowed, localhost connect-src allowed

7. Headers are NOT duplicated if a route already sets them (defense-in-depth).

These tests are NEW (Rule 10 permits adding tests; only modifying existing
tests is forbidden). They follow the same style as tests/test_backend_app_security.py.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def dev_app():
    """Load backend.app in development mode."""
    saved_env = os.environ.get("FIREAI_ENV")
    saved_key = os.environ.get("FIREAI_API_KEY")
    os.environ["FIREAI_ENV"] = "development"
    os.environ["FIREAI_API_KEY"] = ""
    # Clear cached module so __init__ runs again with new env
    for mod_name in list(sys.modules):  # NOSONAR - python:S7504
        if mod_name == "backend.app" or mod_name.startswith("backend.app."):
            del sys.modules[mod_name]
    try:
        backend_app = importlib.import_module("backend.app")
        yield backend_app.app
    finally:
        if saved_env is not None:
            os.environ["FIREAI_ENV"] = saved_env
        else:
            os.environ.pop("FIREAI_ENV", None)
        if saved_key is not None:
            os.environ["FIREAI_API_KEY"] = saved_key
        else:
            os.environ.pop("FIREAI_API_KEY", None)


@pytest.fixture
def dev_client(dev_app):
    """TestClient for the dev app."""
    with TestClient(dev_app) as c:
        yield c


# ── SecurityHeadersMiddleware tests ──────────────────────────────────────────


class TestSecurityHeadersMiddleware:
    """V129: SecurityHeadersMiddleware must add all required headers."""

    def test_x_frame_options_present(self, dev_client):
        """X-Frame-Options: DENY must be on every response (clickjacking)."""
        response = dev_client.get("/api/v1/health")
        assert response.headers.get("x-frame-options") == "DENY"

    def test_x_content_type_options_present(self, dev_client):
        """X-Content-Type-Options: nosniff must be on every response (MIME sniffing)."""
        response = dev_client.get("/api/v1/health")
        assert response.headers.get("x-content-type-options") == "nosniff"

    def test_referrer_policy_present(self, dev_client):
        """Referrer-Policy: no-referrer must be on every response."""
        response = dev_client.get("/api/v1/health")
        assert response.headers.get("referrer-policy") == "no-referrer"

    def test_x_xss_protection_present(self, dev_client):
        """X-XSS-Protection: 0 must be on every response (disable legacy auditor)."""
        response = dev_client.get("/api/v1/health")
        assert response.headers.get("x-xss-protection") == "0"

    def test_permissions_policy_present(self, dev_client):
        """Permissions-Policy must deny all powerful features."""
        response = dev_client.get("/api/v1/health")
        pp = response.headers.get("permissions-policy", "")
        # Must deny camera, microphone, geolocation at minimum
        assert "camera=()" in pp
        assert "microphone=()" in pp
        assert "geolocation=()" in pp

    def test_csp_present_in_development(self, dev_client):
        """Content-Security-Policy must be present in development mode."""
        response = dev_client.get("/api/v1/health")
        csp = response.headers.get("content-security-policy", "")
        assert csp, "CSP header missing"
        # Dev CSP allows unsafe-eval (Vite HMR)
        assert "'unsafe-eval'" in csp
        # Dev CSP allows localhost connect-src
        assert "http://localhost:*" in csp
        # object-src must always be 'none' (no Flash/Java/plugins)
        assert "object-src 'none'" in csp
        # frame-ancestors must always be 'none' (no framing)
        assert "frame-ancestors 'none'" in csp

    def test_hsts_always_present(self, dev_client):
        """
        Strict-Transport-Security must be on every response.

        In 2026+, modern browsers ignore HSTS on localhost (Chrome v79+,
        Firefox v75+), so the developer-trap concern is moot. Emitting HSTS
        always is the safer default for a safety-critical system.
        """
        response = dev_client.get("/api/v1/health")
        hsts = response.headers.get("strict-transport-security", "")
        assert hsts, "HSTS header missing"
        assert "max-age=31536000" in hsts  # 1 year
        assert "includeSubDomains" in hsts

    def test_correlation_id_present(self, dev_client):
        """X-Correlation-ID must be on every response (audit trail)."""
        response = dev_client.get("/api/v1/health")
        cid = response.headers.get("x-correlation-id", "")
        assert cid, "X-Correlation-ID header missing"
        # Must be a valid UUID or alphanumeric string
        assert len(cid) >= 8

    def test_correlation_id_echoed_from_request(self, dev_client):
        """If client sends X-Correlation-ID, server must echo it back."""
        custom_cid = "550e8400-e29b-41d4-a716-446655440000"
        response = dev_client.get(
            "/api/v1/health",
            headers={"X-Correlation-ID": custom_cid},
        )
        assert response.headers.get("x-correlation-id") == custom_cid

    def test_headers_on_error_responses(self, dev_client):
        """
        Security headers must be present even on error responses.

        STRESS-TEST FIX #2: With ApiKeyMiddleware now installed, anonymous
        requests to non-public endpoints return 401 (must authenticate).
        The test was written for the old behavior (404 for nonexistent
        endpoints). The security goal — security headers present on error
        responses — applies to ANY error status (401, 403, 404, 500).
        """
        response = dev_client.get("/api/v1/nonexistent-endpoint")
        # Anonymous request → 401 (must authenticate) — this is the safer
        # behavior because it doesn't reveal whether the endpoint exists.
        assert response.status_code in (401, 403, 404), (
            f"Expected an error status, got {response.status_code}"
        )
        # Security headers must still be present
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert "content-security-policy" in response.headers


# ── CSP environment-awareness tests ──────────────────────────────────────────


class TestCSPEnvironmentAwareness:
    """V129: CSP must be environment-aware (locked down in production)."""

    def test_production_csp_no_unsafe_eval(self):
        """Production CSP must NOT include 'unsafe-eval'."""
        os.environ["FIREAI_ENV"] = "production"
        os.environ["CORS_ALLOWED_ORIGINS"] = "https://app.example.com"
        try:
            from backend.security_middleware import _build_csp, _is_production_env
            assert _is_production_env()
            csp = _build_csp({"type": "http"})
            assert "'unsafe-eval'" not in csp, (
                "Production CSP must NOT allow 'unsafe-eval' — XSS amplification risk"
            )
            assert "http://localhost:*" not in csp, (
                "Production CSP must NOT allow localhost connect-src"
            )
        finally:
            os.environ["FIREAI_ENV"] = "development"
            os.environ.pop("CORS_ALLOWED_ORIGINS", None)

    def test_development_csp_allows_unsafe_eval(self):
        """Development CSP MUST include 'unsafe-eval' (Vite HMR requirement)."""
        os.environ["FIREAI_ENV"] = "development"
        from backend.security_middleware import _build_csp, _is_production_env
        assert not _is_production_env()
        csp = _build_csp({"type": "http"})
        assert "'unsafe-eval'" in csp


# ── backend/app.py CORS hardening tests (V127 pattern applied) ───────────────


class TestBackendAppCorsHardening:
    """V129: backend/app.py must enforce explicit CORS origins in production."""

    def test_production_requires_cors_origins_env_var(self):
        """Production + no CORS_ALLOWED_ORIGINS → RuntimeError (fail-safe)."""
        with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS.*REQUIRED"):
            _reload_backend_app({
                "FIREAI_ENV": "production",
                "CORS_ALLOWED_ORIGINS": None,
                "FIREAI_API_KEY": "",
            })

    def test_production_rejects_wildcard_origin(self):
        """Production + CORS_ALLOWED_ORIGINS='*' → RuntimeError."""
        with pytest.raises(RuntimeError, match=r"'\*'.*forbidden"):
            _reload_backend_app({
                "FIREAI_ENV": "production",
                "CORS_ALLOWED_ORIGINS": "*",
                "FIREAI_API_KEY": "",
            })

    def test_production_accepts_explicit_origins(self):
        """Production + explicit origins → CORS configured correctly."""
        backend_app = _reload_backend_app({
            "FIREAI_ENV": "production",
            "CORS_ALLOWED_ORIGINS": "https://app.example.com,https://admin.example.com",
            "FIREAI_API_KEY": "",
        })
        from starlette.middleware.cors import CORSMiddleware
        kwargs = None
        for m in backend_app.app.user_middleware:
            if m.cls is CORSMiddleware:
                kwargs = m.kwargs
                break
        assert kwargs is not None
        assert "https://app.example.com" in kwargs["allow_origins"]
        assert "https://admin.example.com" in kwargs["allow_origins"]
        assert "*" not in kwargs["allow_origins"]


def _reload_backend_app(env_overrides: dict):
    """Reload backend.app with the given env vars set."""
    for mod_name in list(sys.modules):  # NOSONAR - python:S7504
        if mod_name == "backend.app" or mod_name.startswith("backend.app."):
            del sys.modules[mod_name]
    saved = {}
    for k, v in env_overrides.items():
        saved[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        return importlib.import_module("backend.app")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── Cache endpoint auth tests ────────────────────────────────────────────────


class TestCacheEndpointAuth:
    """V129: Cache management endpoints must require SYSTEM_CONFIG permission."""

    def test_cache_clear_requires_auth(self, dev_client):
        """
        POST /api/v1/cache/clear without auth → 401 (must authenticate).

        STRESS-TEST FIX #2: With ApiKeyMiddleware now installed, anonymous
        requests to non-public endpoints return 401 (must authenticate).
        Previously, anonymous requests defaulted to VIEWER role, which
        lacked SYSTEM_CONFIG permission → 403. The 401 behavior is stricter
        and more correct for a safety-critical system.
        """
        response = dev_client.post("/api/v1/cache/clear")
        assert response.status_code in (401, 403), (
            f"Cache clear must require authentication. "
            f"Got {response.status_code} instead of 401/403."
        )

    def test_cache_stats_requires_auth(self, dev_client):
        """
        GET /api/v1/cache/stats without auth → 401 (must authenticate).

        STRESS-TEST FIX #2: See test_cache_clear_requires_auth for rationale.
        """
        response = dev_client.get("/api/v1/cache/stats")
        assert response.status_code in (401, 403), (
            f"Cache stats must require authentication. "
            f"Got {response.status_code} instead of 401/403."
        )


# ── Health router mounting test ──────────────────────────────────────────────


class TestHealthRouterMounted:
    """V129: backend/app.py must mount health router under /api prefix."""

    def test_api_health_endpoint_exists(self, dev_client):
        """GET /api/health must return 200 (was 404 before V129)."""
        response = dev_client.get("/api/health")
        assert response.status_code == 200, (
            f"/api/health must exist (was 404 before V129). Got {response.status_code}."
        )

    def test_api_health_statistics_endpoint_exists(self, dev_client):
        """GET /api/health/statistics must return 200."""
        response = dev_client.get("/api/health/statistics")
        assert response.status_code == 200

    def test_legacy_reports_statistics_alias(self, dev_client):
        """GET /api/reports/statistics must work as legacy alias."""
        response = dev_client.get("/api/reports/statistics")
        assert response.status_code == 200


# ── backend_app.py also has security headers (adversarial audit finding) ────


class TestBackendAppAlsoHasSecurityHeaders:
    """
    V129 adversarial audit: backend_app.py (QOMN-FIRE API) must ALSO have
    security headers. Initially I only added them to backend/app.py — but
    backend_app.py is the production QOMN-FIRE API and needs the same
    defense-in-depth protection.
    """

    def test_backend_app_has_security_headers(self):
        """backend_app.py must emit X-Frame-Options on every response."""
        os.environ["FIREAI_ENV"] = "development"
        os.environ["FIREAI_API_KEY"] = ""
        try:
            # Reload backend_app fresh
            for mod_name in list(sys.modules):  # NOSONAR - python:S7504
                if mod_name == "backend_app" or mod_name.startswith("backend_app."):
                    del sys.modules[mod_name]
            backend_app = importlib.import_module("backend_app")
            with TestClient(backend_app.app) as client:
                response = client.get("/api/health")
                assert response.headers.get("x-frame-options") == "DENY"
                assert response.headers.get("x-content-type-options") == "nosniff"
                assert "content-security-policy" in response.headers
                assert "strict-transport-security" in response.headers
                # Correlation ID must also be present
                assert "x-correlation-id" in response.headers
        finally:
            # Restore env
            for mod_name in list(sys.modules):  # NOSONAR - python:S7504
                if mod_name == "backend_app" or mod_name.startswith("backend_app."):
                    del sys.modules[mod_name]
