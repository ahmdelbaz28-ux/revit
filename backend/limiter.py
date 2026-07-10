"""
backend/limiter.py — Rate Limiter Configuration.
===============================================

Centralized rate limiter configuration to avoid circular imports.
Import this module directly instead of importing from backend.app.

Usage:
    from backend.limiter import limiter, get_remote_address

Akamai integration (added 2026-07-09):
    When the request transits Akamai Edge, the canonical client IP is the
    True-Client-IP header (set by Akamai AFTER authenticating the request).
    The legacy X-Forwarded-For chain is untrusted because:
      - It can be spoofed by the client (just set the header)
      - It contains multiple hops (comma-separated) that complicate parsing
      - Akamai overwrites it with True-Client-IP at the edge

    The key_func below reads True-Client-IP first, falling back to
    X-Forwarded-For (first hop) and finally request.client.host. This
    makes rate limiting accurate behind Akamai while still working in
    local dev (where True-Client-IP is absent).

    backend/akamai_middleware.py also overwrites X-Forwarded-For with
    True-Client-IP at the ASGI scope level, so downstream code that reads
    X-Forwarded-For directly also gets the correct IP.
"""

from __future__ import annotations

from starlette.requests import Request
from slowapi import Limiter


def get_remote_address(request: Request) -> str:
    """Get the client IP address for rate limiting.

    Priority:
      1. CF-Connecting-IP (Cloudflare — set after edge authentication)
      2. True-Client-IP (Akamai — set after edge authentication)
      3. X-Forwarded-For (first hop — for other proxies)
      4. request.client.host (direct connection — local dev)

    Returns "0.0.0.0" if no IP can be determined (should never happen
    in practice, but prevents a None key_func crash if it does).
    """
    # 1. Cloudflare CF-Connecting-IP — canonical client IP behind Cloudflare
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        ip = cf_ip.strip().split(",")[0].strip()
        if ip:
            return ip

    # 2. Akamai True-Client-IP — canonical client IP behind Akamai
    true_client_ip = request.headers.get("True-Client-IP")
    if true_client_ip:
        ip = true_client_ip.strip().split(",")[0].strip()
        if ip:
            return ip

    # 3. X-Forwarded-For — first hop (set by other proxies / load balancers)
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        ip = xff.split(",")[0].strip()
        if ip:
            return ip

    # 4. Direct connection (local dev, or no proxy in front)
    if request.client and request.client.host:
        return request.client.host

    # Fallback — prevents None key_func crash
    return "0.0.0.0"


# Configure rate limiter with the Akamai-aware key function
limiter = Limiter(key_func=get_remote_address)

__all__ = ["get_remote_address", "limiter"]
