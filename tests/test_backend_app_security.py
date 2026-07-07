"""
tests/test_backend_app_security.py — V127 SAFETY: backend_app.py CORS hardening
================================================================================
V127 SAFETY FIX: backend_app.py must NOT use wildcard CORS origins in production.
The previous code defaulted to allow_origins=["*"] which allows any website
to read API responses. In production, CORS_ORIGINS must be explicitly set to
a comma-separated list of trusted origins.

Tests:
  1. Production with explicit origins — works
  2. Production without CORS_ORIGINS — raises RuntimeError (fail-safe)
  3. Production with CORS_ORIGINS="*" — raises RuntimeError (wildcard forbidden)
  4. Development default — localhost-only origins
  5. allow_credentials is always False (header auth, not cookies)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from starlette.middleware.cors import CORSMiddleware

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _get_cors_middleware_kwargs(app):
    """Extract CORS middleware kwargs from a FastAPI app."""
    for m in app.user_middleware:
        if m.cls is CORSMiddleware:
            return m.kwargs
    return None


def _reload_backend_app(env_overrides: dict) -> Any:
    """Reload backend_app with the given env vars set."""
    # Clear cached module so __init__ runs again with new env
    for mod_name in list(sys.modules):  # NOSONAR - python:S7504
        if mod_name == "backend_app" or mod_name.startswith("backend_app."):
            del sys.modules[mod_name]
    saved = {}
    for k, v in env_overrides.items():
        saved[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        return importlib.import_module("backend_app")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestV127CorsHardening:
    """V127: backend_app.py must enforce explicit CORS origins in production."""

    def test_production_requires_cors_origins_env_var(self):
        """Production + no CORS_ORIGINS → RuntimeError (fail-safe)."""
        with pytest.raises(RuntimeError, match="CORS_ORIGINS.*REQUIRED"):
            _reload_backend_app({
                "FIREAI_ENV": "production",
                "CORS_ORIGINS": None,
                "DIGITAL_TWIN_DB_PATH": ":memory:",
            })

    def test_production_rejects_wildcard_origin(self):
        """Production + CORS_ORIGINS='*' → RuntimeError (wildcard forbidden)."""
        with pytest.raises(RuntimeError, match=r"'\*'.*forbidden"):
            _reload_backend_app({
                "FIREAI_ENV": "production",
                "CORS_ORIGINS": "*",
                "DIGITAL_TWIN_DB_PATH": ":memory:",
            })

    def test_production_accepts_explicit_origins(self):
        """Production + explicit origins → CORS middleware configured correctly."""
        backend_app = _reload_backend_app({
            "FIREAI_ENV": "production",
            "CORS_ORIGINS": "https://app.example.com,https://admin.example.com",
            "DIGITAL_TWIN_DB_PATH": ":memory:",
        })
        kwargs = _get_cors_middleware_kwargs(backend_app.app)
        assert kwargs is not None, "CORS middleware must be present"
        assert "https://app.example.com" in kwargs["allow_origins"]
        assert "https://admin.example.com" in kwargs["allow_origins"]
        assert "*" not in kwargs["allow_origins"]

    def test_development_defaults_to_localhost_only(self):
        """Development mode → CORS defaults to localhost dev ports."""
        backend_app = _reload_backend_app({
            "FIREAI_ENV": "development",
            "CORS_ORIGINS": None,
            "DIGITAL_TWIN_DB_PATH": ":memory:",
        })
        kwargs = _get_cors_middleware_kwargs(backend_app.app)
        assert kwargs is not None
        origins = kwargs["allow_origins"]
        # All default origins must be localhost
        for o in origins:
            assert "localhost" in o or "127.0.0.1" in o, (
                f"Dev default origin {o!r} must be localhost-only"
            )
        assert "*" not in origins

    def test_allow_credentials_always_false(self):
        """
        API uses X-API-Key header auth (not cookies), so credentials must
        be False — prevents CORS-spec violation (wildcard + credentials).
        """
        for env in ("development", "testing"):
            backend_app = _reload_backend_app({
                "FIREAI_ENV": env,
                "CORS_ORIGINS": None,
                "DIGITAL_TWIN_DB_PATH": ":memory:",
            })
            kwargs = _get_cors_middleware_kwargs(backend_app.app)
            assert kwargs.get("allow_credentials") is False, (
                f"allow_credentials must be False in {env} mode (header auth, not cookies)"
            )

    def test_no_wildcard_in_production_when_using_explicit_list(self):
        """
        If a wildcard is mixed into a comma-separated list in production,
        the code MUST raise RuntimeError (defensive).
        """
        with pytest.raises(RuntimeError, match=r"'\*'.*forbidden"):
            _reload_backend_app({
                "FIREAI_ENV": "production",
                "CORS_ORIGINS": "https://a.com,*,https://b.com",
                "DIGITAL_TWIN_DB_PATH": ":memory:",
            })
