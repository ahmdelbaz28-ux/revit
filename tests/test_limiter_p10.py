"""
tests/test_limiter_p10.py — P1.10 regression tests for backend/limiter.py

Verifies the trusted-proxy-aware rate-limiter key function:
  - Direct connections return the client IP
  - Behind a trusted proxy, X-Forwarded-For is respected (first IP)
  - Untrusted sources cannot forge X-Forwarded-For to bypass rate limiting
  - Missing client info returns a sentinel
  - Whitespace in X-Forwarded-For is handled

Per agent.md Rule 10 — these tests are NEVER modified; only production
code is modified.
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import MagicMock

import pytest


def _reload_limiter(trusted_proxies: str | None):
    """Reload backend.limiter with a specific FIREAI_TRUSTED_PROXIES env.

    The module caches the trusted-proxy set at import time, so we must
    reload it after changing the env var.
    """
    if trusted_proxies is None:
        os.environ.pop("FIREAI_TRUSTED_PROXIES", None)
    else:
        os.environ["FIREAI_TRUSTED_PROXIES"] = trusted_proxies
    import backend.limiter
    importlib.reload(backend.limiter)
    return backend.limiter


def _make_request(client_host: str | None, xff: str | None = None):
    """Build a mock Request with the given client.host and X-Forwarded-For."""
    r = MagicMock()
    if client_host:
        r.client = MagicMock()
        r.client.host = client_host
    else:
        r.client = None
    r.headers = {}
    if xff:
        r.headers["X-Forwarded-For"] = xff
    return r


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Ensure FIREAI_TRUSTED_PROXIES is unset before each test."""
    monkeypatch.delenv("FIREAI_TRUSTED_PROXIES", raising=False)
    yield
    monkeypatch.delenv("FIREAI_TRUSTED_PROXIES", raising=False)


class TestGetClientIp:
    """P1.10: trusted-proxy-aware rate-limiter key function."""

    def test_direct_connection_returns_client_ip(self):
        """When no trusted proxies are configured, return the direct IP."""
        mod = _reload_limiter(trusted_proxies=None)
        r = _make_request("203.0.113.5")
        assert mod.get_client_ip(r) == "203.0.113.5"

    def test_trusted_proxy_with_xff_returns_first_ip(self):
        """Behind a trusted proxy, X-Forwarded-For's first IP is used."""
        mod = _reload_limiter(trusted_proxies="127.0.0.1,10.0.0.1")
        r = _make_request("127.0.0.1", xff="203.0.113.5, 10.0.0.1")
        assert mod.get_client_ip(r) == "203.0.113.5"

    def test_untrusted_source_ignores_xff(self):
        """CRITICAL SECURITY TEST: an untrusted source cannot forge XFF.

        Without this check, any client could send X-Forwarded-For with
        a different value per request and bypass rate limiting entirely.
        """
        mod = _reload_limiter(trusted_proxies="127.0.0.1")
        r = _make_request("198.51.100.7", xff="1.2.3.4")
        # Must return the DIRECT IP, NOT the forged XFF value.
        assert mod.get_client_ip(r) == "198.51.100.7"

    def test_trusted_proxy_without_xff_returns_direct_ip(self):
        """If XFF is missing even behind a trusted proxy, fall back to direct IP."""
        mod = _reload_limiter(trusted_proxies="127.0.0.1")
        r = _make_request("127.0.0.1", xff=None)
        assert mod.get_client_ip(r) == "127.0.0.1"

    def test_no_client_returns_sentinel(self):
        """No client info → return '0.0.0.0' sentinel (shared bucket)."""
        mod = _reload_limiter(trusted_proxies=None)
        r = _make_request(None)
        assert mod.get_client_ip(r) == "0.0.0.0"

    def test_xff_whitespace_is_stripped(self):
        """Proxies sometimes add spaces after commas — must handle gracefully."""
        mod = _reload_limiter(trusted_proxies="127.0.0.1")
        r = _make_request("127.0.0.1", xff="  203.0.113.5  , 10.0.0.1")
        assert mod.get_client_ip(r) == "203.0.113.5"

    def test_empty_xff_behind_trusted_proxy_falls_back(self):
        """Empty XFF header → fall back to direct IP."""
        mod = _reload_limiter(trusted_proxies="127.0.0.1")
        r = _make_request("127.0.0.1", xff="")
        assert mod.get_client_ip(r) == "127.0.0.1"

    def test_multiple_trusted_proxies(self):
        """Multiple proxies in FIREAI_TRUSTED_PROXIES are all respected."""
        mod = _reload_limiter(trusted_proxies="127.0.0.1,10.0.0.1,172.16.0.1")
        # From 10.0.0.1 (trusted)
        r1 = _make_request("10.0.0.1", xff="203.0.113.5")
        assert mod.get_client_ip(r1) == "203.0.113.5"
        # From 172.16.0.1 (trusted)
        r2 = _make_request("172.16.0.1", xff="198.51.100.7")
        assert mod.get_client_ip(r2) == "198.51.100.7"

    def test_ipv6_loopback_as_trusted_proxy(self):
        """IPv6 ::1 loopback is a common proxy address in dev."""
        mod = _reload_limiter(trusted_proxies="::1")
        r = _make_request("::1", xff="203.0.113.5")
        assert mod.get_client_ip(r) == "203.0.113.5"


class TestLimiterInstance:
    """The limiter instance uses the trusted-proxy-aware key function."""

    def test_limiter_uses_get_client_ip(self):
        """Limiter's internal key_func should be our get_client_ip."""
        mod = _reload_limiter(trusted_proxies=None)
        # slowapi Limiter stores the key_func as _key_func (private)
        assert mod.limiter._key_func is mod.get_client_ip
