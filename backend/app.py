"""
backend/app.py — FastAPI Application Entry Point
===============================================

Core FastAPI application with all CAD/BIM integration routes.
Implements the complete backend for AutoCAD/Revit/Digital Twin system.

ARCHITECTURE:
- FastAPI app with CORS middleware
- Rate limiting with SlowAPI
- All CAD/BIM integration routes
- Health check endpoints
- Error handlers for CAD connection issues
- Security headers middleware (V129: defense-in-depth)
- Correlation ID middleware (V129: end-to-end tracing)

USAGE:
    uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000

V129 INFRASTRUCTURE SECURITY HARDENING (2026-06-18):
  - Added SecurityHeadersMiddleware (X-Frame-Options, X-Content-Type-Options,
    HSTS, CSP, Referrer-Policy, Permissions-Policy, X-XSS-Protection)
  - Added CorrelationIdMiddleware (X-Correlation-ID for audit trail)
  - Mounted health_router under /api prefix (was missing — tests expected
    /api/health but only /api/v1/health existed)
  - Applied V127 CORS hardening pattern: production without explicit
    CORS_ORIGINS now fails safe (RuntimeError)
  - Added Depends(require_permission(SYSTEM_CONFIG)) to cache management
    endpoints (was public — anonymous cache invalidation DoS vector)
  - Changed __main__ bind from 0.0.0.0 to 127.0.0.1 (loopback only;
    production deployments MUST use a reverse proxy: nginx, traefik, AWS ALB)
"""

import os
import time
import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Import our CAD/BIM integration routers
from backend.routers import autocad, revit, digital_twin
from backend.routers import health as health_router_module

# Import rate limiter from centralized module (avoids circular import)
from backend.limiter import limiter

# V129: Security middleware — SecurityHeadersMiddleware adds X-Frame-Options,
# X-Content-Type-Options, HSTS, CSP, Referrer-Policy, Permissions-Policy to
# every HTTP response. CorrelationIdMiddleware adds X-Correlation-ID for
# end-to-end audit tracing (NFPA 72 §14.2.4 compliance).
from backend.security_middleware import (
    CorrelationIdMiddleware,
    SecurityHeadersMiddleware,
)

# V129: Auth dependency for cache management endpoints (was public).
from backend.auth import require_permission
from backend.rbac import Permission

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Reduce noise from third-party libraries
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


# ============================================================================
# CONTENT SECURITY POLICY (CSP) BUILDER
# ============================================================================
# V119 FIX (Finding #4): Production default for CSP_UNSAFE_EVAL is now
# "false" (secure-by-default). Development default remains "true" for DX.
# SAFETY: A safety-critical fire alarm engineering UI must not be vulnerable
# to XSS amplification via 'unsafe-eval'. Modern frontend libraries
# (recharts >=2.x, three.js >=0.150) work without it in production builds.

def _build_csp() -> str:
    """Build a Content-Security-Policy header value.

    Environment-aware:
      - FIREAI_ENV=production (default): 'unsafe-eval' is OFF unless explicitly enabled.
      - FIREAI_ENV=development:           'unsafe-eval' is ON  unless explicitly disabled.

    Operators may override either default by setting CSP_UNSAFE_EVAL=true|false.

    Production + unsafe-eval=on is logged at ERROR level (V119 escalation)
    so the misconfiguration cannot hide in log noise.
    """
    # Truthy values that enable unsafe-eval (backward compatible with pre-V119).
    # Defined INSIDE the function so the function is fully self-contained and
    # can be exec'd in isolation by tests/test_csp_security.py.
    _truthy = {"true", "1", "yes"}

    env = os.getenv("FIREAI_ENV", "production").lower()
    is_dev = env == "development"

    # Resolve CSP_UNSAFE_EVAL with environment-aware default.
    unsafe_eval_raw = os.getenv("CSP_UNSAFE_EVAL")
    if unsafe_eval_raw is not None:
        unsafe_eval = unsafe_eval_raw.strip().lower() in _truthy
    else:
        unsafe_eval = is_dev  # dev: True, prod: False

    # V119: escalate to ERROR when production keeps unsafe-eval on.
    if unsafe_eval and not is_dev:
        logger.error(
            "CSP 'unsafe-eval' ENABLED in production (FIREAI_ENV=%s). "
            "This is a security risk for a safety-critical UI - "
            "set CSP_UNSAFE_EVAL=false to disable.",
            env,
        )

    script_src = "'self' 'unsafe-inline'" + (" 'unsafe-eval'" if unsafe_eval else "")
    style_src = "'self' 'unsafe-inline'"
    img_src = "'self' data: blob:"

    # connect-src: development allows localhost (Vite HMR / websockets);
    # production uses CSP_CONNECT_SRC env var if provided, else 'self'.
    if is_dev:
        connect_src = "'self' http://localhost:* ws://localhost:* http://127.0.0.1:* ws://127.0.0.1:*"
        custom_connect = os.getenv("CSP_CONNECT_SRC")
        if custom_connect:
            connect_src += f" {custom_connect}"
    else:
        custom_connect = os.getenv("CSP_CONNECT_SRC")
        connect_src = "'self'" + (f" {custom_connect}" if custom_connect else "")

    parts = [
        "default-src 'self'",
        f"script-src {script_src}",
        f"style-src {style_src}",
        f"img-src {img_src}",
        f"connect-src {connect_src}",
        "font-src 'self' data:",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
    ]
    return "; ".join(parts)

# ── In-memory cache with expiration support ────────────────────────────────
_cache: dict[str, dict] = {}


def get_cache():
    """Get cache instance. Returns in-memory dict if Redis unavailable."""
    return _cache


async def cache_get(key: str):
    """Get value from cache. Returns None if expired or missing."""
    entry = _cache.get(key)
    if entry is None:
        return None
    if time.time() > entry.get("expire", 0):
        _cache.pop(key, None)  # Remove expired entry
        return None
    return entry["value"]


async def cache_set(key: str, value: str, expire: int = 300):
    """Set value in cache with expiration in seconds."""
    _cache[key] = {"value": value, "expire": time.time() + expire}


async def cache_delete(key: str):
    """Delete key from cache."""
    _cache.pop(key, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    Used for startup and shutdown tasks.
    """
    logger.info("Starting CAD/BIM Integration Platform...")
    yield
    logger.info("Shutting down CAD/BIM Integration Platform...")

# Create FastAPI app with lifespan
app = FastAPI(
    title="CAD/BIM Integration Platform",
    description="""
## API Overview

Complete platform for **AutoCAD** and **Revit** integration with **Digital Twin** capabilities.

### Features

- **AutoCAD Integration**: Connect to AutoCAD, read/write DWG files, create/draw entities
- **Revit Integration**: Connect to Revit, read/write RVT files, create/modify elements
- **Bidirectional Conversion**: Convert between AutoCAD and Revit formats
- **Digital Twin Engine**: Central conversion hub with semantic mapping
- **Version Management**: Track and rollback conversion history

### Authentication

All endpoints require API key authentication via `X-API-Key` header.

### Rate Limiting

| Endpoint Type | Limit |
|---------------|-------|
| Health/Read | 1000/minute |
| Standard | 100/minute |
| Write/Upload | 50/minute |
| Heavy Operations | 10/minute |
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add rate limiter state
app.state.limiter = limiter

# Add rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS middleware — V127 / V129 hardening ───────────────────────────────
# V127 precedent (from backend_app.py): production MUST set CORS_ORIGINS
# explicitly. Wildcard '*' is FORBIDDEN. Missing env var → RuntimeError
# (fail-safe). Development defaults to localhost-only (safe default).
#
# Per CORS Fetch Standard §3.2: allow_origins=["*"] + allow_credentials=True
# is FORBIDDEN. We do not enable credentials here because the API uses
# X-API-Key header auth (not cookies).
#
# SECURITY: This is a safety-critical fire protection engineering API.
# Allowing arbitrary origins to read API responses would permit any website
# to exfiltrate engineering data (building layouts, fire alarm designs).
_env_mode = os.getenv("FIREAI_ENV", "development").lower()
if _env_mode in ("production", "prod"):
    _cors_raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if not _cors_raw:
        # Production without explicit CORS_ORIGINS — fail safe.
        # The platform operator MUST declare trusted origins.
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS environment variable is REQUIRED in production. "
            "Set it to a comma-separated list of trusted origins, e.g. "
            "'https://app.example.com,https://admin.example.com'. "
            "Wildcards are forbidden in production for life-safety audit reasons."
        )
    ALLOWED_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    if "*" in ALLOWED_ORIGINS:
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS='*' is forbidden in production. List explicit origins."
        )
else:
    # Development / testing — safe defaults (localhost only).
    ALLOWED_ORIGINS = [
        o.strip()
        for o in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:5173,http://localhost:8000",
        ).split(",")
        if o.strip()
    ]

# V129: Add SecurityHeadersMiddleware FIRST (outermost), so it runs AFTER
# CORS middleware on the response path and can append headers to the final
# response. Starlette executes middleware in LIFO order: the LAST added
# middleware is the OUTERMOST (runs first on request, last on response).
# We want SecurityHeadersMiddleware to be outermost so it always adds
# headers regardless of which inner middleware handled the request.
app.add_middleware(SecurityHeadersMiddleware)

# V129: CorrelationIdMiddleware — adds X-Correlation-ID to every request
# for end-to-end audit tracing. Pure ASGI (no body buffering).
app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # NEVER enable allow_credentials=True with this design — API uses
    # X-API-Key header auth (not cookies), so cross-origin credentialed
    # requests are unnecessary and would expand the attack surface.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "X-Correlation-ID"],
)

# Include our CAD/BIM integration routers
# FIX #35: Removed redundant prefix from app.include_router since each
# router already defines its own prefix (e.g., prefix="/autocad").
app.include_router(autocad.router, prefix="/api/v1", tags=["AutoCAD-v1"])
app.include_router(revit.router, prefix="/api/v1", tags=["Revit-v1"])
app.include_router(digital_twin.router, prefix="/api/v1", tags=["Digital-Twin-v1"])

# V129: Mount the health router under /api prefix so /api/health works.
# Previously only /api/v1/health existed (defined inline above), but tests
# and deployment probes expect /api/health. The health_router_module.router
# also provides /api/health/statistics and the legacy /api/reports/statistics
# alias — both required by backend/tests/test_routers.py.
app.include_router(health_router_module.router, prefix="/api", tags=["Health"])

# Health endpoints (no version prefix - always available)
@app.get("/api/v1/health", tags=["Health-v1"])
async def health_check_v1():
    """Health check endpoint for API v1."""
    return {
        "status": "healthy",
        "service": "CAD/BIM Integration Platform",
        "version": "1.0.0",
        "api_version": "v1"
    }

@app.get("/api/v2/health", tags=["Health-v2"])
async def health_check_v2():
    """Health check endpoint for API v2."""
    return {
        "status": "healthy",
        "service": "CAD/BIM Integration Platform",
        "version": "1.0.0",
        "api_version": "v2",
        "features": ["rate_limiting", "enhanced_caching", "streaming"]
    }

# Legacy health endpoint (deprecated)
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint (deprecated - use /api/v1/health)."""
    return {
        "status": "healthy",
        "service": "CAD/BIM Integration Platform",
        "version": "1.0.0",
        "deprecated": True,
        "suggestion": "Use /api/v1/health or /api/v2/health"
    }

# ── Error handlers ──────────────────────────────────────────────────────────
# FIX #2: Return JSONResponse (not HTTPException) and never expose str(exc)
# to the client. In a fire-safety system, internal exception messages can
# leak file paths, DB connection strings, and variable names.
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler — logs full traceback, returns safe message."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "success": False}
    )


# ═══════════════════════════════════════════════════════════════════════════
# CACHE MANAGEMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

# V129: Cache management endpoints now require SYSTEM_CONFIG permission.
# Previously these were public — an anonymous attacker could clear the cache
# (denial-of-service via cache invalidation) or read cache statistics
# (information disclosure: reveals internal operational metrics).
@app.post("/api/v1/cache/clear", tags=["Cache"])
async def clear_cache(
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """Clear all cached data. Requires SYSTEM_CONFIG permission (admin only).

    FIX #3: Count items BEFORE clearing so the response is accurate.
    Previously _cache.clear() ran before len(_cache), always returning 0.

    V129 FIX: This endpoint was public — anonymous cache invalidation is a
    DoS vector in a safety-critical system. Now requires admin permission.
    """
    count = len(_cache)
    _cache.clear()
    return {"message": "Cache cleared", "items_cleared": count}


@app.get("/api/v1/cache/stats", tags=["Cache"])
async def cache_stats(
    _role=Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """Get cache statistics. Requires SYSTEM_CONFIG permission (admin only).

    FIX #4: Also cleans up expired entries during stats check to prevent
    unbounded memory growth from expired-but-not-removed cache entries.

    V129 FIX: Cache statistics reveal internal operational metrics (cache
    hit rate, memory usage). This is sensitive information that should not
    be exposed anonymously. Now requires admin permission.
    """
    # Clean expired entries
    now = time.time()
    expired_keys = [k for k, v in _cache.items() if v.get("expire", 0) <= now]
    for k in expired_keys:
        _cache.pop(k, None)

    active_keys = sum(1 for v in _cache.values() if v.get("expire", 0) > now)
    return {
        "total_keys": len(_cache),
        "active_keys": active_keys,
        "expired_keys_cleaned": len(expired_keys),
        "cache_type": "in-memory"
    }


if __name__ == "__main__":
    import uvicorn
    # V129: Bind to 127.0.0.1 (loopback) by default. Production deployments
    # MUST use a reverse proxy (nginx, traefik, AWS ALB) to terminate TLS and
    # forward to this loopback address. Binding to 0.0.0.0 exposes the API
    # directly to the network, bypassing the proxy's rate limiting, TLS,
    # and request filtering.
    #
    # To bind to all interfaces (NOT recommended outside Docker), set
    # FIREAI_BIND_HOST=0.0.0.0 in the environment.
    _bind_host = os.getenv("FIREAI_BIND_HOST", "127.0.0.1")
    if _bind_host == "0.0.0.0":
        logger.warning(
            "Binding to 0.0.0.0 — API will be reachable from the network. "
            "Use a reverse proxy (nginx/traefik) in production. "
            "Set FIREAI_BIND_HOST=127.0.0.1 to restore loopback-only binding."
        )
    uvicorn.run(app, host=_bind_host, port=8000)
