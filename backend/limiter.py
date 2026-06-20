"""
backend/limiter.py — Rate Limiter Configuration
===============================================

Centralized rate limiter configuration to avoid circular imports.
Import this module directly instead of importing from backend.app.

P1.10 FIX (2026-06-20): replaced slowapi.util.get_remote_address
(which returns request.client.host directly) with a trusted-proxy-
aware key function. The previous setup had TWO failure modes:

  1. Behind a reverse proxy (nginx/traefik/AWS ALB),
     request.client.host is ALWAYS the proxy's IP (e.g. 127.0.0.1).
     All users appear to share one IP → the rate limit becomes a
     global limit applied across ALL users. A single abuser hits
     the limit and every legitimate user is blocked.

  2. Naively trusting X-Forwarded-For without an allow-list lets
     any client forge the header and bypass rate limiting entirely.
     The attacker sends a different X-Forwarded-For value per
     request and gets unlimited requests.

The fix uses the operator-suggested trusted-proxy pattern:
  - If the direct client IP is in FIREAI_TRUSTED_PROXIES (comma-
    separated env var), trust X-Forwarded-For and use the first
    address in the list.
  - Otherwise, use the direct client IP (no header trust).

This is safe because:
  - An attacker CANNOT forge X-Forwarded-For unless they connect
    from a trusted proxy IP (which they can't, by definition).
  - Legitimate users behind the proxy get per-IP rate limiting
    based on their real client IP (from X-Forwarded-For).
  - Direct connections (dev mode, no proxy) work as before.

Usage:
    from backend.limiter import limiter, get_client_ip
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from slowapi import Limiter
from starlette.requests import Request

logger = logging.getLogger(__name__)


def _parse_trusted_proxies() -> set[str]:
    """Parse FIREAI_TRUSTED_PROXIES env var into a set of IPs.

    Returns a set of strings (IPs). Empty set if the env var is not
    set or empty. Whitespace-only entries are stripped.
    """
    raw = os.getenv("FIREAI_TRUSTED_PROXIES", "")
    proxies: set[str] = set()
    for entry in raw.split(","):
        entry = entry.strip()
        if entry:
            proxies.add(entry)
    return proxies


# Cache the trusted-proxy set at module load. If the env var changes
# at runtime (e.g. via .env reload), the process must be restarted.
# This is intentional — runtime mutation of security config is dangerous.
_TRUSTED_PROXIES: set[str] = _parse_trusted_proxies()

if _TRUSTED_PROXIES:
    logger.info(
        "Rate limiter: trusting X-Forwarded-For from %d proxy IP(s): %s",
        len(_TRUSTED_PROXIES),
        sorted(_TRUSTED_PROXIES),
    )
else:
    logger.info(
        "Rate limiter: FIREAI_TRUSTED_PROXIES not set — using direct "
        "client IP only (X-Forwarded-For will be IGNORED). Set this "
        "env var to the proxy IP(s) when running behind nginx/traefik/ALB."
    )


def get_client_ip(request: Request) -> str:
    """Get client IP for rate-limit keying.

    P1.10 FIX: respects X-Forwarded-For ONLY when the direct connection
    comes from a trusted proxy. This prevents both failure modes:
      - Proxy-mode global rate limit (all users share one IP)
      - X-Forwarded-For forgery (attacker bypasses rate limit)

    Args:
        request: Starlette/FastAPI Request object.

    Returns:
        Client IP string. Falls back to '0.0.0.0' if no client info
        is available (should not happen in normal HTTP traffic).
    """
    client_host: Optional[str] = None
    if request.client is not None:
        client_host = request.client.host

    # No client info — cannot rate-limit meaningfully. Return a sentinel
    # so all such requests share one bucket (safer than spreading them
    # across random keys).
    if not client_host:
        return "0.0.0.0"

    # Only trust X-Forwarded-For if the direct connection is from a
    # configured trusted proxy. This is the security-critical check.
    if client_host in _TRUSTED_PROXIES:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            # X-Forwarded-For format: "client, proxy1, proxy2, ..."
            # The FIRST address is the original client. Take it.
            # Strip whitespace to be lenient with proxies that add
            # spaces after commas.
            first_ip = xff.split(",")[0].strip()
            if first_ip:
                return first_ip

    # Either not behind a trusted proxy, or X-Forwarded-For missing.
    # Use the direct client IP.
    return client_host


# Configure rate limiter with the trusted-proxy-aware key function.
limiter = Limiter(key_func=get_client_ip)

__all__ = ["limiter", "get_client_ip"]
