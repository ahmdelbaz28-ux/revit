"""backend/limiter.py — Rate Limiter Configuration
===============================================

Centralized rate limiter configuration to avoid circular imports.
Import this module directly instead of importing from backend.app.

Usage:
    from backend.limiter import limiter, get_remote_address
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)

__all__ = ["get_remote_address", "limiter"]
