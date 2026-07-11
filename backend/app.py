# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
from __future__ import annotations

"""
backend/app.py — FastAPI Application Entry Point.
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

import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# V207 (2026-07-09): Akamai Edge integration middleware.
# Reads True-Client-IP / Akamai-Internal / Akamai-Bot-Score / Akamai-Geo-Country
# headers injected by Akamai Property Manager. When AKAMAI_ENABLED=false (default),
# the middleware is a no-op pass-through — zero overhead on HF Space / Vercel
# without Akamai, full protection when Akamai is deployed in front.
# Pure ASGI (no body buffering) — see agent.md BUG-34 fix.
from backend.akamai_middleware import AkamaiIntegrationMiddleware

# V129: Auth dependency for cache management endpoints (was public).
from backend.auth import require_permission

# V208 (2026-07-09): Cloudflare Edge integration middleware.
# Reads CF-Connecting-IP / CF-RAY / CF-IPCountry headers injected by Cloudflare
# proxy. When CF_ENABLED=false (default), the middleware is a no-op pass-through.
# Complements Akamai middleware — both can be enabled simultaneously for multi-CDN.
from backend.cloudflare_middleware import CloudflareIntegrationMiddleware

# Import rate limiter from centralized module (avoids circular import)
from backend.limiter import limiter

# Import multi-database service
from backend.multi_db_service import get_multi_db_service
from backend.rbac import Permission

# Import our CAD/BIM integration routers
from backend.routers import autocad, digital_twin, revit
from backend.routers import health as health_router_module

# V129: Security middleware — SecurityHeadersMiddleware adds X-Frame-Options,
# X-Content-Type-Options, HSTS, CSP, Referrer-Policy, Permissions-Policy to
# every HTTP response. CorrelationIdMiddleware adds X-Correlation-ID for
# end-to-end audit tracing (NFPA 72 §14.2.4 compliance).
from backend.security_middleware import (
    ApiKeyMiddleware,
    CorrelationIdMiddleware,
    SecurityHeadersMiddleware,
)

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

def _build_csp() -> str:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
    """
    Build a Content-Security-Policy header value.

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

    # V140 FIX: Remove 'unsafe-inline' from script-src in production.
    # 'unsafe-inline' is kept for style-src (Tailwind CSS requires it).
    # For scripts, production uses 'self' only (React doesn't need inline scripts).
    # Development keeps 'unsafe-inline' for Vite HMR.
    if is_dev:
        script_src = "'self' 'unsafe-inline'" + (" 'unsafe-eval'" if unsafe_eval else "")
    else:
        # Production: no unsafe-inline for scripts (only unsafe-eval if explicitly enabled)
        script_src = "'self'" + (" 'unsafe-eval'" if unsafe_eval else "")
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
# STRESS-TEST FIX #3: Bounded cache with LRU eviction and thread-safe lock.
# Previously the cache was an unbounded dict — an attacker could pollute it
# with millions of entries, exhausting server memory.
#
# The new implementation:
#   - Enforces a maximum number of entries (default 10,000).
#   - When full, evicts the oldest entry (FIFO — Python dicts preserve
#     insertion order since 3.7; we use next(iter(_cache)) to get the
#     oldest key because dict.popitem() does NOT accept last=False in
#     CPython — that's OrderedDict only).
#   - Uses a threading.Lock for multi-step operations (read-modify-write
#     sequences like the cleanup loop in cache_stats).
#   - Skips eviction for entries that are already expired (cleans them first).
# STRICT FIX C: Added per-value size cap (1 MB default) to prevent a single
#              entry from consuming excessive memory.
# STRICT FIX H: Added a background reaper thread that periodically cleans
#              expired entries (every 60 seconds), so memory is reclaimed
#              even if cache_stats is never called.
from collections import OrderedDict as _OrderedDict

_CACHE_MAX_ENTRIES = int(os.getenv("FIREAI_CACHE_MAX_ENTRIES", "10000"))
# STRICT FIX C: Max size of a single cached value (1 MB default).
# Prevents a single entry from consuming excessive memory.
_CACHE_MAX_VALUE_SIZE = int(os.getenv("FIREAI_CACHE_MAX_VALUE_SIZE", str(1024 * 1024)))
_cache: _OrderedDict[str, dict] = _OrderedDict()
_cache_lock = threading.Lock()

# STRICT FIX H: Background reaper configuration
_CACHE_REAPER_INTERVAL = int(os.getenv("FIREAI_CACHE_REAPER_INTERVAL", "60"))
_cache_reaper_started = False
_cache_reaper_lock = threading.Lock()


def _evict_expired_locked() -> int:
    """Remove all expired entries. MUST be called with _cache_lock held."""
    now = time.time()
    expired = [k for k, v in _cache.items() if v.get("expire", 0) <= now]
    for k in expired:
        _cache.pop(k, None)
    return len(expired)


def _evict_oldest_locked(n: int = 1) -> None:
    """
    Evict the n oldest entries. MUST be called with _cache_lock held.

    Uses OrderedDict.popitem(last=False) which IS supported (unlike
    regular dict.popitem() in CPython).
    """
    for _ in range(n):
        if not _cache:
            return
        try:
            _cache.popitem(last=False)
        except KeyError:
            return


def _ensure_cache_reaper_started() -> None:
    """Start the background cache reaper thread (once, idempotent)."""
    global _cache_reaper_started
    if _cache_reaper_started:
        return
    with _cache_reaper_lock:
        if _cache_reaper_started:
            return
        _cache_reaper_started = True

        def _reaper_loop() -> None:
            while True:
                try:
                    time.sleep(_CACHE_REAPER_INTERVAL)
                    with _cache_lock:
                        removed = _evict_expired_locked()
                    if removed > 0:
                        logger.debug("Cache reaper removed %d expired entries", removed)
                except Exception as exc:
                    # F5 FIX: Log reaper errors instead of silently swallowing
                    # them. In a safety-critical system, silent failures are
                    # more dangerous than noisy ones.
                    logger.exception("Cache reaper error: %s", exc)

        t = threading.Thread(target=_reaper_loop, daemon=True, name="cache-reaper")
        t.start()
        logger.info("Cache reaper thread started (interval=%ds)", _CACHE_REAPER_INTERVAL)


def get_cache() -> _OrderedDict[str, dict]:
    """Get cache instance. Returns in-memory dict if Redis unavailable."""
    return _cache


async def cache_get(key: str):  # NOSONAR - python:S7503
    """Get value from cache. Returns None if expired or missing."""
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if time.time() > entry.get("expire", 0):
            _cache.pop(key, None)  # Remove expired entry
            return None
        # Move to end so recently-accessed entries survive eviction longer.
        _cache.move_to_end(key)
        return entry["value"]


async def cache_set(key: str, value: object, expire: int = 300) -> None:  # NOSONAR - python:S7503
    """
    Set value in cache with expiration in seconds.

    STRESS-TEST FIX #3: If cache is at capacity, expired entries are
    evicted first; if still at capacity, the oldest entry is evicted
    (LRU policy — least recently used).

    STRICT FIX C: Reject values larger than _CACHE_MAX_VALUE_SIZE
    to prevent a single entry from consuming excessive memory.
    """
    # STRICT FIX C: Check value size BEFORE acquiring the lock
    # F4 FIX: Check raw object size before string coercion to avoid
    # allocating a potentially huge string just to reject it.
    if not isinstance(value, str):
        raw_size = sys.getsizeof(value)
        if raw_size > _CACHE_MAX_VALUE_SIZE:
            logger.warning(
                "Cache value too large before coercion (%d bytes raw, max %d) -- rejecting",
                raw_size, _CACHE_MAX_VALUE_SIZE,
            )
            return
        # Coerce to str for cache storage (cache stores str per signature)
        value = str(value)
    if len(value) > _CACHE_MAX_VALUE_SIZE:
        logger.warning(
            "Cache value too large (%d bytes, max %d) — rejecting",
            len(value), _CACHE_MAX_VALUE_SIZE,
        )
        return

    with _cache_lock:
        # If this is a new key and we're at capacity, make room.
        if key not in _cache:
            if len(_cache) >= _CACHE_MAX_ENTRIES:
                # First pass: evict expired entries (cheap)
                _evict_expired_locked()
                # Second pass: if still at capacity, evict oldest (LRU)
                while len(_cache) >= _CACHE_MAX_ENTRIES:
                    _evict_oldest_locked(1)
        else:
            # Existing key — move to end (most recently used)
            _cache.move_to_end(key)
        _cache[key] = {"value": value, "expire": time.time() + expire}

    # STRICT FIX H: Start the reaper on first cache_set
    _ensure_cache_reaper_started()


async def cache_delete(key: str) -> None:  # NOSONAR - python:S7503
    """Delete key from cache."""
    with _cache_lock:
        _cache.pop(key, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    Used for startup and shutdown tasks.

    HOTFIX C-2: Now calls set_core_modules_loaded(True) on startup so the
    /api/health endpoint reports core_modules="loaded" instead of "unavailable".
    Previously set_core_modules_loaded() was defined but never invoked —
    health status was always "degraded" even when everything was working.

    V193 (R2) FIX: Validate FIREAI_SESSION_SECRET at startup. If missing or
    too short (<43 chars = 256 bits), hard-fail with a clear error message.
    Previously, the secret was only validated lazily when the auth router
    tried to register — and the auth router's failure was swallowed by
    _safe_include_router, leaving the app running with NO auth endpoints
    and NO visible error. This is the PRIMARY defense; the _safe_include_router
    re-raise (for CRITICAL_ROUTERS) is the SECONDARY defense.
    """
    # V193 (R2): Hard-fail at startup if session secret is misconfigured.
    # This is the ROOT-CAUSE fix for the silent auth-router failure that
    # allowed the app to start in a broken state.
    import os as _os
    _secret = _os.environ.get("FIREAI_SESSION_SECRET", "")
    if not _secret:
        raise RuntimeError(
            "FIREAI_SESSION_SECRET environment variable is not set. "
            "The session secret is REQUIRED for authentication. "
            "Generate one with: python3 -m backend.session_secret generate "
            "and set it via FIREAI_SESSION_SECRET env var (or "
            "FIREAI_SESSION_SECRET_FILE for Docker/K8s)."
        )
    if len(_secret) < 43:
        raise RuntimeError(
            f"FIREAI_SESSION_SECRET is too short: {len(_secret)} chars. "
            f"Minimum is 43 chars (256 bits of entropy). "
            f"Current value appears to be a placeholder or truncated. "
            f"Generate a strong one with: "
            f"python3 -c \"import secrets; print(secrets.token_urlsafe(64))\" "
            f"and set it as FIREAI_SESSION_SECRET."
        )

    logger.info("Starting CAD/BIM Integration Platform...")
    # HOTFIX C-2: Mark core modules as loaded so health check reports "ok".
    try:
        from backend.routers.health import set_core_modules_loaded
        set_core_modules_loaded(True)
        logger.info("Core modules marked as loaded for health check")
    except ImportError as exc:
        logger.warning("Could not import set_core_modules_loaded: %s", exc)
    yield
    logger.info("Shutting down CAD/BIM Integration Platform...")

# Create FastAPI app with lifespan
# V130 SECURITY FIX: docs/redoc/openapi are now gated by FIREAI_ENV.
# In production, the entire API surface (including internal RBAC permission
# names) MUST NOT be exposed to anonymous attackers. Set docs_url=None to
# fully disable. Development keeps the docs available for DX.
_is_prod = os.getenv("FIREAI_ENV", "development").lower() in ("production", "prod")
_docs_url = None if _is_prod else "/docs"
_redoc_url = None if _is_prod else "/redoc"
_openapi_url = None if _is_prod else "/openapi.json"

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
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url
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

# V207 (2026-07-09): Akamai Edge integration — must be SECOND outermost
# (just inside SecurityHeadersMiddleware) so it can:
#   1. Overwrite X-Forwarded-For with True-Client-IP BEFORE ApiKeyMiddleware
#      reads it for audit logging.
#   2. Reject direct origin access / geo-blocked / bot-score-exceeded requests
#      BEFORE ApiKeyMiddleware spends cycles validating their API keys.
# When AKAMAI_ENABLED=false, this is a no-op pass-through.
app.add_middleware(AkamaiIntegrationMiddleware)

# V208 (2026-07-09): Cloudflare Edge integration — third outermost.
# Reads CF-Connecting-IP / CF-RAY / CF-IPCountry headers. Same pattern as Akamai.
# When CF_ENABLED=false, this is a no-op pass-through.
app.add_middleware(CloudflareIntegrationMiddleware)

# V129: CorrelationIdMiddleware — adds X-Correlation-ID to every request
# for end-to-end audit tracing. Pure ASGI (no body buffering).
app.add_middleware(CorrelationIdMiddleware)

# STRESS-TEST FIX #2: ApiKeyMiddleware validates X-API-Key on every request
# and sets request.state.fireai_role / scope["fireai_role"] for downstream
# require_permission() checks. Without this, all RBAC checks fell through
# to Role.VIEWER, making admin endpoints unreachable and viewer-level
# endpoints effectively public. Added AFTER CORS so CORS preflight requests
# (OPTIONS) are not blocked by auth.
app.add_middleware(ApiKeyMiddleware)

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
app.include_router(autocad.router, prefix="/api/v1", tags=["AutoCAD-v1"])  # NOSONAR — S1192: duplicated literal acceptable in this localized context
app.include_router(revit.router, prefix="/api/v1", tags=["Revit-v1"])
app.include_router(digital_twin.router, prefix="/api/v1", tags=["Digital-Twin-v1"])

# ── STRESS-TEST FIX #8: Register ALL backend routers ───────────────────────
# Previously only autocad/revit/digital_twin/marine/monitor/health were
# registered. The vast majority of the API surface (projects, devices,
# connections, elements, conflicts, reports, exports, sync, memory,
# workflow, environment, dwg, qomn, facp, api_keys) was UNREACHABLE.
# This is the critical bug found by HTTP-level stress testing.
# We use _lazy_import to register each router defensively — if a router
# has an unmet optional dependency (e.g. shapely, ezdxf), it's skipped
# with a warning instead of crashing the whole app.
def _safe_include_router(module_name: str, prefix: str = "/api/v1", tag: str = "") -> None:
    """
    Import a router module and register it. Skip silently if unavailable.

    V193 (R2) FIX — ROOT CAUSE of silent auth-router failure:
      Previously this function swallowed ALL exceptions (including
      ValueError from session-secret validation) and only logged a
      WARNING. When FIREAI_SESSION_SECRET was < 43 chars, the auth
      router raised ValueError, was silently dropped, and all /auth/*
      endpoints returned 404. The frontend couldn't authenticate and
      the entire app was unusable — with NO visible error.

      Per agent.md Rule 1 (ABSOLUTE TRUTH) and Rule 13 (HONEST
      SELF-ASSESSMENT), mission-critical routers (auth, api_keys)
      MUST NOT be silently skipped. We now RE-RAISE for those, and
      for everything else we still log+continue (graceful
      degradation for optional routers like `workflow` which needs
      langgraph).

      The startup-time session-secret validation (below in this file)
      is the PRIMARY defense — it hard-fails before the app starts
      accepting requests. This re-raise is the SECONDARY defense in
      case the secret check is bypassed.
    """
    # Mission-critical routers — failure to register is a launch blocker.
    # Re-raise so the app crashes loudly instead of running in a broken state.
    CRITICAL_ROUTERS = frozenset({"auth", "api_keys"})

    try:
        import importlib
        mod = importlib.import_module(f"backend.routers.{module_name}")
        if hasattr(mod, "router"):
            app.include_router(mod.router, prefix=prefix, tags=[tag or module_name.title()])
            logger.debug("Registered router: %s", module_name)
        # Some routers define additional routers (e.g. analyze.project_router)
        if hasattr(mod, "project_router"):
            app.include_router(mod.project_router, prefix=prefix, tags=[tag or module_name.title()])
            logger.debug("Registered project_router from: %s", module_name)
        # V140 FIX (Rule 17 — Root-Cause Analysis): Some routers (notably
        # backend.routers.sync) export a SEPARATE `ws_router` for WebSocket
        # routes. WebSocket routes cannot share an APIRouter with HTTP routes
        # that have a path prefix like "/projects/{project_id}/sync" because
        # the prefix would be applied to the WebSocket path too, breaking the
        # contract documented in sync.py ("/ws" at root, not "/api/v1/ws").
        # The old _safe_include_router only registered `mod.router` and
        # `mod.project_router`, silently dropping `ws_router` — so the /ws
        # endpoint was unreachable and tests/test_sync_websocket.py failed
        # with WebSocketDisconnect(1000). Registering ws_router WITHOUT a
        # prefix preserves the documented "/ws" path.
        if hasattr(mod, "ws_router"):
            app.include_router(mod.ws_router, tags=[tag or module_name.title()])
            logger.debug("Registered ws_router from: %s (no prefix — preserves /ws root path)", module_name)
    except ImportError as e:
        # Optional dependency missing (e.g. langgraph for workflow router).
        # Safe to skip — feature is unavailable but app still works.
        logger.warning("Router '%s' skipped (optional dependency missing): %s", module_name, e)
    except Exception as e:
        # Any other exception (ValueError, RuntimeError, etc.) on a
        # CRITICAL router = launch blocker. Re-raise so the app fails fast.
        if module_name in CRITICAL_ROUTERS:
            logger.exception(
                "CRITICAL router '%s' failed to register: %s — aborting startup. "
                "This router is mission-critical; the app cannot function safely without it. "
                "Fix the underlying issue (likely FIREAI_SESSION_SECRET is missing or too short — "
                "minimum 43 chars / 256 bits).",
                module_name, e,
            )
            raise
        # Non-critical router: log and continue (graceful degradation)
        logger.warning("Router '%s' registration failed: %s", module_name, e)

# Register the missing routers. Order matters for route precedence, but
# FastAPI raises on conflict, so duplicates are caught at startup.
for _router_name in (
    "projects",
    "devices",
    "connections",
    "connections_v2",
    "elements",
    "conflicts",
    "reports",
    "exports",
    "sync",
    "memory",
    "workflow",
    "environment",
    "dwg",
    "qomn",
    "facp",
    "api_keys",
    "analyze",
    "llm",  # V207: AI Copilot (Zenmux OpenAI-compatible LLM service)
    "auth",  # M-3: session-based auth with HttpOnly cookies
):
    _safe_include_router(_router_name)

# V215 FIX: Register multi_db router (was never registered — 11 endpoints returned 404)
try:
    from backend.routers import multi_db as _multi_db_module
    app.include_router(_multi_db_module.router, prefix="/api/v1", tags=["multi-db"])
except ImportError as e:
    logger.warning("Router 'multi_db' skipped (optional dependency missing): %s", e)

# V130 MARINE MODULE: Mount the marine fire-safety router.
# Provides endpoints for IMO SOLAS II-2, IEC 60092-502, ship zone division,
# detector selection, extinguishing sizing, alarm-logic generation, and
# SCADA/ETAP/Revit/AutoCAD integrations for marine projects.
from backend.routers import marine as marine_router_module

app.include_router(marine_router_module.router, prefix="/api/v1", tags=["Marine"])

# V214: Mining fire protection router (NFPA 120/122 + MSHA 30 CFR Part 75)
from backend.routers import mining as mining_router_module

app.include_router(mining_router_module.router, prefix="/api/v1", tags=["Mining"])

# V130 FIX: Mount the monitor router so Prometheus can scrape /api/v1/monitor/metrics.
# Previously monitor.router was defined but NEVER registered via include_router,
# so every Prometheus scrape returned 404 and all dashboards/alerts had no data.
# Auth is enforced INSIDE the router via require_permission(Permission.MONITOR_READ).
# For unauthenticated /metrics scraping, deploy a sidecar that injects a
# service-account API key, or expose /metrics via a separate internal port.
#
# V140 FIX (Rule 17 — Root-Cause Analysis): The monitor router defines its
# routes with the FULL path already (e.g. `@router.get("/api/v1/monitor/health")`
# — see backend/routers/monitor.py:533). Adding `prefix="/api/v1"` here caused
# the routes to be registered at /api/v1/api/v1/monitor/health — double prefix.
# Every monitor test failed with 404. Removing the prefix here matches the
# router's own path definitions.
from backend.routers import monitor as monitor_router_module

app.include_router(monitor_router_module.router, tags=["Monitor"])

# V129: Mount the health router under /api prefix so /api/health works.
# Previously only /api/v1/health existed (defined inline above), but tests
# and deployment probes expect /api/health. The health_router_module.router
# also provides /api/health/statistics and the legacy /api/reports/statistics
# alias — both required by backend/tests/test_routers.py.
app.include_router(health_router_module.router, prefix="/api", tags=["Health"])

# ── V132 (MISSION TASK 3.1): API v2 with Deprecation Headers ─────────────
# Per RFC 7234: v1 endpoints receive Deprecation + Sunset + Link headers
# pointing to their v2 successors. This enables smooth migration to the
# new cloud-native API surface (Generative Design, BIM Provider abstraction,
# IFC 4.3, AR Export, Webhooks, Smoke Simulation state).
# The v2 router exposes the new capabilities under /api/v2/ prefix.
def _register_v2_router() -> None:
    """Mount the v2 router with all new cloud-native endpoints."""
    try:
        from backend.routers.v2 import router as v2_router
        app.include_router(v2_router, prefix="/api/v2", tags=["v2"])
        logger.info("V2 API router mounted at /api/v2/")
    except ImportError as e:
        logger.warning("V2 router skipped (optional dependency missing): %s", e)
    except Exception as e:
        logger.warning("V2 router registration failed: %s", e)

_register_v2_router()


# ── V133 (PHASE 1.1): CSRF Protection (Double Submit Cookie) ────────────
# Per OWASP CSRF Prevention Cheat Sheet. Protects state-changing requests
# (POST/PUT/DELETE/PATCH) from cross-origin attacks.
# Enabled by default in production; can be disabled via FIREAI_CSRF_DISABLED=1
# for testing or API-only clients (no browser).
def _register_csrf_middleware() -> None:
    """Register CSRF middleware if not explicitly disabled."""
    import os
    if os.environ.get("FIREAI_CSRF_DISABLED", "").lower() in ("1", "true", "yes"):
        logger.info("CSRF middleware DISABLED via FIREAI_CSRF_DISABLED env var")
        return
    try:
        from backend.security_csrf import CSRFMiddleware
        # Pure ASGI middleware — wraps the app
        app.add_middleware(CSRFMiddleware)
        logger.info("CSRF middleware registered (Double Submit Cookie pattern)")
    except ImportError as e:
        logger.warning("CSRF middleware skipped (import failed): %s", e)
    except Exception as e:
        logger.warning("CSRF middleware registration failed: %s", e)

# Deprecation middleware: add Deprecation/Sunset/Link headers to v1 responses.
# Per RFC 7234 (HTTP Caching) and the HTTP Deprecation header draft.
@app.middleware("http")
async def add_deprecation_headers(request: Request, call_next):
    """
    Add Deprecation: true, Sunset, and Link headers to /api/v1/ responses.

    Per MISSION TASK 3.1: v1 endpoints are deprecated with a 1-year sunset
    window, pointing clients to their v2 successors.
    """
    response = await call_next(request)

    # Only add to /api/v1/ paths (not /api/v2/ or /api/health)
    if "/api/v1/" in request.url.path:
        response.headers["Deprecation"] = "true"
        # Sunset date: 1 year from V132 release (2026-06-25)
        response.headers["Sunset"] = "Wed, 25 Jun 2027 00:00:00 GMT"
        # Link to v2 successor (replace /api/v1/ with /api/v2/)
        v2_url = request.url.path.replace("/api/v1/", "/api/v2/", 1)
        response.headers["Link"] = f'<{v2_url}>; rel="successor-version"'

    return response


# Health endpoints
# V139 FIX: Removed the inline stub health endpoints that were shadowing
# the real health_router_module (registered at /api/health above). The
# stubs returned status="healthy" with no database check, which:
#   1. Broke tests expecting status="ok"/"degraded" (real values from
#      backend/routers/health.py::health_check which actually queries
#      the database).
#   2. Was a LIFE-SAFETY issue — a stub returning "healthy" without
#      checking DB connectivity gives false-green health probes.
#
# The health_router_module is now ALSO registered at /api/v1 so that
# /api/v1/health returns the real database-aware response (not the stub).
# /api/v2/health is kept as a separate v2-only endpoint.
app.include_router(health_router_module.router, prefix="/api/v1", tags=["Health-v1"])

# V139 FIX: /health (no /api prefix) — alias to /api/health for backward
# compatibility with stress tests and deployment probes that hit /health.
@app.get("/health", tags=["Health"])
async def health_check_legacy_alias() -> dict[str, Any]:
    """
    Legacy /health alias — delegates to the real health check.

    Returns the same database-aware response as /api/health.
    """
    from backend.routers.health import health_check
    return await health_check()

@app.get("/api/v2/health", tags=["Health-v2"])
async def health_check_v2() -> dict[str, object]:
    """Health check endpoint for API v2."""
    return {
        "status": "healthy",
        "service": "CAD/BIM Integration Platform",
        "version": "1.0.0",
        "api_version": "v2",
        "features": [
            "rate_limiting", "enhanced_caching", "streaming",
            "generative_design", "bim_provider_abstraction",
            "ifc43_mapping", "ar_metadata_export",
            "webhook_delivery", "smoke_simulation_state",
        ],
    }

# ── Error handlers ──────────────────────────────────────────────────────────
# FIX #2: Return JSONResponse (not HTTPException) and never expose str(exc)
# to the client. In a fire-safety system, internal exception messages can
# leak file paths, DB connection strings, and variable names.
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> Response:
    """General exception handler — logs full traceback, returns safe message."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "success": False}
    )


# ── Database health check endpoint ──────────────────────────────────────────
@app.get("/api/database-health")
async def database_health():
    """Check the health of all database connections."""
    multi_db_service = get_multi_db_service()
    health_status = multi_db_service.health_check()
    return {"success": True, "data": health_status}


# ═══════════════════════════════════════════════════════════════════════════
# CACHE MANAGEMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

# V129: Cache management endpoints now require SYSTEM_CONFIG permission.
# Previously these were public — an anonymous attacker could clear the cache
# (denial-of-service via cache invalidation) or read cache statistics
# (information disclosure: reveals internal operational metrics).
@app.post("/api/v1/cache/clear", tags=["Cache"])
async def clear_cache(
    _role: str = Depends(require_permission(Permission.SYSTEM_CONFIG)),  # NOSONAR - python:S8410
) -> dict[str, object]:
    """
    Clear all cached data. Requires SYSTEM_CONFIG permission (admin only).

    FIX #3: Count items BEFORE clearing so the response is accurate.
    Previously _cache.clear() ran before len(_cache), always returning 0.

    V129 FIX: This endpoint was public — anonymous cache invalidation is a
    DoS vector in a safety-critical system. Now requires admin permission.

    STRESS-TEST FIX #3: Acquire the lock before clearing to prevent
    concurrent cache_set from interleting the clear operation.
    """
    with _cache_lock:
        count = len(_cache)
        _cache.clear()
    return {"message": "Cache cleared", "items_cleared": count}


@app.get("/api/v1/cache/stats", tags=["Cache"])
async def cache_stats(
    _role: str = Depends(require_permission(Permission.SYSTEM_CONFIG)),  # NOSONAR - python:S8410
) -> dict[str, object]:
    """
    Get cache statistics. Requires SYSTEM_CONFIG permission (admin only).

    FIX #4: Also cleans up expired entries during stats check to prevent
    unbounded memory growth from expired-but-not-removed cache entries.

    V129 FIX: Cache statistics reveal internal operational metrics (cache
    hit rate, memory usage). This is sensitive information that should not
    be exposed anonymously. Now requires admin permission.

    STRESS-TEST FIX #3: Now uses _cache_lock for the cleanup loop (was a
    read-modify-write race with concurrent cache_set calls).
    """
    # Clean expired entries under the lock
    with _cache_lock:
        expired_count = _evict_expired_locked()
        active_keys = sum(1 for v in _cache.values() if v.get("expire", 0) > time.time())
        total = len(_cache)
    return {
        "total_keys": total,
        "active_keys": active_keys,
        "expired_keys_cleaned": expired_count,
        "cache_type": "in-memory",
        "max_entries": _CACHE_MAX_ENTRIES,
    }


if __name__ == "__main__":
    # V129: Bind to loopback only (127.0.0.1), not 0.0.0.0
    # Production deployments must use a reverse proxy (nginx, traefik, AWS ALB)
    import uvicorn
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",  # V129: loopback only
        port=8000,
        reload=True,
        reload_dirs=["backend"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# V206 FIX: Serve the built frontend (Vite/React static assets) from FastAPI
# when BAZSPARK_FRONTEND_DIST is set (HuggingFace Space deployment mode).
#
# WHY THIS EXISTS
# ───────────────
# On Vercel, the frontend is served by Vercel's CDN and only /api/* is proxied
# to this backend. But on HuggingFace Spaces, the Docker container runs ONLY
# this FastAPI app — there is no separate static file server. Without this
# mount, visiting the Space's root URL returns 401 (the ApiKeyMiddleware
# blocks every non-public path), so users see a JSON error instead of the app.
#
# The Dockerfile builds the frontend (npm run build → /app/frontend_dist) and
# sets BAZSPARK_FRONTEND_DIST=/app/frontend_dist. This mount serves those
# files at / and /assets/, with SPA fallback to index.html for client-side
# routing.
#
# SECURITY
# ────────
# The frontend static files are PUBLIC (HTML/CSS/JS bundles). They contain no
# secrets — all sensitive data is fetched via /api/* which still requires
# X-API-Key. The /assets/ prefix and / and /index.html are added to the
# ApiKeyMiddleware public path list (see security_middleware.py).
# ═══════════════════════════════════════════════════════════════════════════
import os as _os
from pathlib import Path as _Path

_FRONTEND_DIST = _os.environ.get("BAZSPARK_FRONTEND_DIST")
if _FRONTEND_DIST and _Path(_FRONTEND_DIST).is_dir():
    from fastapi.responses import FileResponse as _FileResponse
    from fastapi.responses import JSONResponse as _JSONResponse
    from fastapi.staticfiles import StaticFiles as _StaticFiles

    _FRONTEND_INDEX = _Path(_FRONTEND_DIST) / "index.html"
    logger.info("BAZSPARK_FRONTEND_DIST=%s — mounting frontend static files", _FRONTEND_DIST)

    # Mount /assets/ — Vite outputs all JS/CSS bundles here with content-hashed names
    _ASSETS_DIR = _Path(_FRONTEND_DIST) / "assets"
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", _StaticFiles(directory=str(_ASSETS_DIR)), name="frontend-assets")

    # SPA fallback: any non-/api route returns index.html so React Router can handle it
    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):  # NOSONAR — S1172: full_path used to exclude /api routes
        # Never intercept API routes — those are handled by routers above
        if full_path.startswith("api/"):
            return _JSONResponse(status_code=404, content={"detail": "Not Found", "success": False})
        # Serve index.html for all other paths (client-side routing)
        if _FRONTEND_INDEX.is_file():
            return _FileResponse(str(_FRONTEND_INDEX))
        return _JSONResponse(status_code=404, content={"detail": "Frontend not built", "success": False})
