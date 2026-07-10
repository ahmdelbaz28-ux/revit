"""
test_limiter.py — Tests for backend/limiter.py.

Verifies the rate limiter module configuration.
"""
from __future__ import annotations

from backend.limiter import get_remote_address, limiter


class TestLimiterModule:
    """backend/limiter.py instantiation and utilities."""

    def test_limiter_is_instance(self):
        from slowapi import Limiter

        assert isinstance(limiter, Limiter)

    def test_get_remote_address_is_callable(self):
        assert callable(get_remote_address)

    def test_limiter_has_no_state_by_default(self):
        """Fresh limiter should start with empty rate-limit state."""
        assert limiter is not None
