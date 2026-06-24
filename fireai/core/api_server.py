#!/usr/bin/env python3
"""api_server.py — FastAPI REST wrapper for FireAI
Based on V10 Enhanced + LearningStore

SECURITY FIXES APPLIED:
  - API Key authentication required for all design endpoints
  - Rate limiting middleware (100 req/min default)
  - Input validation with bounds checking
  - No binding to 0.0.0.0 by default (use host parameter)
  - Proper error handling without leaking internals

Install:  pip install fastapi uvicorn
Run:      python fireai/core/api_server.py
Docs:     http://localhost:8000/docs

Environment Variables:
  FIREAI_API_KEYS   — Comma-separated API keys for authentication (preferred)
  FIREAI_API_KEY    — Single API key for authentication (backward compat)
  FIREAI_HOST       — Server host (default: 127.0.0.1)
  FIREAI_PORT       — Server port (default: 8000)
  AUDIT_HMAC_KEY    — Required for audit store integrity (no default!)
  FIREAI_DB_PATH    — Path to audit database
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from fireai.core.fireai_core import FireAISystem

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# API KEY CONFIGURATION
# ============================================================================

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_or_create_api_key() -> str:
    """Get API key from environment or generate one for development."""
    key = os.environ.get("FIREAI_API_KEY")
    if key:
        return key

    # Development: auto-generate and warn
    generated = secrets.token_urlsafe(32)
    logger.warning(
        "\n"
        "╔══════════════════════════════════════════════════════════════╗\n"
        "║  ⚠️  FIREAI_API_KEY not set — auto-generated for dev:      ║\n"
        f"║  {generated:<57s}║\n"
        "║  Set this in FIREAI_API_KEY env var for production.        ║\n"
        "╚══════════════════════════════════════════════════════════════╝"
    )
    return generated


# Support multiple API keys (comma-separated in env var)
# SELF-CRITIQUE FIX: Single key is a single point of failure.
# If one client's key is compromised, you'd have to change it for
# ALL clients. Multiple keys allow per-client rotation.
_EFFECTIVE_API_KEYS: set[str] = set()


def _init_api_keys() -> None:
    """Initialize API keys from environment variable."""
    global _EFFECTIVE_API_KEYS
    keys_str = os.environ.get("FIREAI_API_KEYS", "")
    if keys_str:
        _EFFECTIVE_API_KEYS = {k.strip() for k in keys_str.split(",") if k.strip()}
    else:
        # Fallback: single key for backward compat
        single_key = os.environ.get("FIREAI_API_KEY")
        if single_key:
            _EFFECTIVE_API_KEYS = {single_key}
        else:
            # Development: auto-generate and warn
            generated = secrets.token_urlsafe(32)
            logger.warning(
                "\n"
                "╔══════════════════════════════════════════════════════════════╗\n"
                "║  FIREAI_API_KEYS not set — auto-generated for dev:         ║\n"
                f"║  {generated:<57s}║\n"
                "║  Set FIREAI_API_KEYS=key1,key2,... for production.         ║\n"
                "╚══════════════════════════════════════════════════════════════╝"
            )
            _EFFECTIVE_API_KEYS = {generated}


_init_api_keys()


async def verify_api_key(api_key: str = Security(_API_KEY_HEADER)) -> str:
    """Verify the API key from the request header.

    Raises:
        HTTPException: 401 if API key is missing or invalid.

    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Pass X-API-Key header.",
        )
    if not any(secrets.compare_digest(api_key, valid_key) for valid_key in _EFFECTIVE_API_KEYS):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )
    return api_key


# ============================================================================
# RATE LIMITER
# ============================================================================


class RateLimiter:
    """Simple in-memory rate limiter per client IP.

    SELF-CRITIQUE FIX:
      The previous version had a MEMORY LEAK: old client IPs were
      never removed from _clients dict. Over weeks/months, this would
      grow unbounded. Now we periodically evict stale entries when
      the dict exceeds a size threshold.
    """

    _MAX_CLIENTS = 10_000  # Evict stale entries beyond this

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._clients: dict[str, list[float]] = {}

    def check(self, client_id: str) -> bool:
        """Check if request is within rate limit.

        Returns:
            True if allowed, False if rate limited.

        """
        now = time.monotonic()
        requests = self._clients.get(client_id, [])

        # Remove expired entries
        cutoff = now - self._window
        requests = [t for t in requests if t > cutoff]

        if len(requests) >= self._max:
            self._clients[client_id] = requests
            # Periodic cleanup of stale clients (memory leak fix)
            self._maybe_evict(now)
            return False

        requests.append(now)
        self._clients[client_id] = requests

        # Periodic cleanup of stale clients (memory leak fix)
        self._maybe_evict(now)
        return True

    def _maybe_evict(self, now: float) -> None:
        """Evict stale client entries if dict is too large."""
        if len(self._clients) <= self._MAX_CLIENTS:
            return
        cutoff = now - self._window
        stale = [cid for cid, reqs in self._clients.items() if not reqs or reqs[-1] < cutoff]
        for cid in stale:
            del self._clients[cid]


_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)


# ============================================================================
# APPLICATION
# ============================================================================

from fireai.core.nfpa72_models import CeilingSpec, CeilingType, RoomSpec

# ✅ FIX (from consultant review): Lazy initialization instead of module-level
# instantiation. The old code created FireAISystem at import time, which meant:
# 1. Any import error crashed the entire module
# 2. Database was opened before env vars were set
# 3. Testing required mocking the global singleton
_system: Optional[FireAISystem] = None
_system_lock = threading.Lock()


def _get_system() -> FireAISystem:
    """Get or lazily create the FireAI system instance (thread-safe).

    Uses double-checked locking for thread-safe lazy initialization.
    This prevents race conditions when multiple threads call _get_system()
    simultaneously during startup.
    """
    global _system
    if _system is None:
        with _system_lock:
            if _system is None:
                from fireai.core.fireai_core import FireAISystem

                db_path = os.environ.get("FIREAI_DB_PATH", "fireai.sqlite3")
                _system = FireAISystem(db_path=db_path)
    return _system


app = FastAPI(
    title="FireAI - NFPA 72 Expert System",
    description="Adaptive detector placement with persistent learning. "
    "Requires API key authentication via X-API-Key header.",
    version="10.1.0",
)

# ✅ CORS — restrict in production
# V114 FIX: Reject wildcard CORS origins for safety-critical system
_api_cors_origins = os.environ.get("FIREAI_CORS_ORIGINS", "http://localhost:3000").split(",")
if "*" in _api_cors_origins:
    import logging

    logging.getLogger("fireai.security").critical(
        "CORS wildcard '*' detected in FIREAI_CORS_ORIGINS — REJECTED. "
        "Safety-critical system: specify explicit origins."
    )
    _api_cors_origins = [o for o in _api_cors_origins if o.strip() != "*"]
    if not _api_cors_origins:
        _api_cors_origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_api_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware per client IP."""
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.check(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
        )
    response = await call_next(request)
    return response


# ============================================================================
# REQUEST / RESPONSE MODELS — WITH VALIDATION
# ============================================================================

# NFPA 72 physical limits
MAX_ROOM_DIMENSION = 200.0  # meters (no room is bigger)
MAX_POLYGON_POINTS = 100  # prevent DoS
MIN_CEILING_HEIGHT = 0.5  # meters
MAX_CEILING_HEIGHT = 30.0  # meters (per NFPA 72 scope)
VALID_OCCUPANCY_TYPES = {
    "office",
    "commercial",
    "industrial",
    "warehouse",
    "residential",
    "healthcare",
    "education",
    "assembly",
    "mercantile",
    "storage",
    "utility",
    "corridor",
}


class RoomRequest(BaseModel):
    room_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    polygon: List[List[float]] = Field(..., min_length=3, max_length=MAX_POLYGON_POINTS)
    height: float = Field(3.0, gt=MIN_CEILING_HEIGHT, le=MAX_CEILING_HEIGHT)
    height_high: Optional[float] = Field(None, gt=MIN_CEILING_HEIGHT, le=MAX_CEILING_HEIGHT)
    ceiling_type: str = "FLAT"
    occupancy_type: str = "office"
    run_resilience: bool = True

    @field_validator("room_id")
    @classmethod
    def validate_room_id(cls, v):
        """Prevent injection in room_id."""
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("room_id contains invalid characters")
        return v

    @field_validator("polygon")
    @classmethod
    def validate_polygon(cls, v):
        """Validate polygon coordinates are within reasonable bounds."""
        for i, point in enumerate(v):
            if len(point) != 2:
                raise ValueError(f"Point {i} must have exactly 2 coordinates (x, y)")
            x, y = point
            if abs(x) > MAX_ROOM_DIMENSION or abs(y) > MAX_ROOM_DIMENSION:
                raise ValueError(f"Point {i} coordinates exceed maximum room dimension ({MAX_ROOM_DIMENSION}m)")
        return v

    @field_validator("height_high")
    @classmethod
    def validate_height_high(cls, v, info):
        """Ensure height_high >= height."""
        if v is not None and info.data.get("height") is not None and v < info.data["height"]:
            raise ValueError("height_high must be >= height")
        return v

    @field_validator("occupancy_type")
    @classmethod
    def validate_occupancy(cls, v):
        """Validate occupancy type against known types."""
        v_lower = v.lower().strip()
        if v_lower not in VALID_OCCUPANCY_TYPES:
            raise ValueError(f"Unknown occupancy type: '{v}'. Valid types: {sorted(VALID_OCCUPANCY_TYPES)}")
        return v_lower

    @field_validator("ceiling_type")
    @classmethod
    def validate_ceiling_type(cls, v):
        """Validate ceiling type."""
        valid_types = {c.name for c in CeilingType}
        if v not in valid_types:
            raise ValueError(f"Invalid ceiling_type: '{v}'. Valid: {sorted(valid_types)}")
        return v


class DetectorPos(BaseModel):
    x: float
    y: float


class RoomResponse(BaseModel):
    room_id: str
    compliant: bool
    safe_to_submit: bool
    confidence: str
    confidence_score: float
    detector_count: int
    detector_type: str
    occupancy: str
    coverage_pct: float
    wall_violations: int
    resilient: Optional[bool]
    resilience_pass_rate: Optional[float]
    warnings: List[str]
    errors: List[str]
    detector_positions: List[DetectorPos]


# ============================================================================
# HELPERS
# ============================================================================


def _build_spec(req: RoomRequest) -> RoomSpec:
    """Convert request to RoomSpec."""
    ceiling = CeilingSpec.create_safe(
        height_at_low_point_m=req.height,
        height_at_high_point_m=req.height_high or req.height,
        ceiling_type=next((c for c in CeilingType if c.value == req.ceiling_type), CeilingType.FLAT)
    )
    # CRITICAL FIX: Calculate width/depth from polygon using geometric SPAN.
    # Previously used max(x) and max(y) which is WRONG for translated/negative
    # coordinate polygons. Correct: (max - min) = actual geometric span.
    poly = [tuple(p) for p in req.polygon]
    width = max(p[0] for p in poly) - min(p[0] for p in poly)
    depth = max(p[1] for p in poly) - min(p[1] for p in poly)

    return RoomSpec(
        room_id=req.room_id,
        width_m=width,
        depth_m=depth,
        occupancy_type=req.occupancy_type,
        ceiling_spec=ceiling,
        polygon=poly,
    )


def _to_response(r) -> RoomResponse:
    """Convert EnhancedExpertResult to response."""
    return RoomResponse(
        room_id=r.room_id,
        compliant=r.compliant,
        safe_to_submit=r.safe_to_submit if hasattr(r, "safe_to_submit") else False,
        confidence=r.confidence.value if r.confidence else "UNKNOWN",
        confidence_score=r.confidence_score or 0,
        detector_count=len(r.detector_positions),
        detector_type=r.detector_type.value if r.detector_type else "SMOKE",
        occupancy=r.occupancy_class.value if r.occupancy_class else "office",
        coverage_pct=round(r.placement_proof.coverage_fraction * 100, 2) if r.placement_proof else 0,
        wall_violations=len(r.wall_violations),
        resilient=r.resilience.resilient if r.resilience else None,
        resilience_pass_rate=round(r.resilience.pass_rate, 3) if r.resilience else None,
        warnings=r.warnings,
        errors=r.errors,
        detector_positions=[DetectorPos(x=round(x, 3), y=round(y, 3)) for x, y in r.detector_positions],
    )


# ============================================================================
# ENDPOINTS
# ============================================================================


@app.get("/health")
def health():
    """Liveness probe (no auth required)."""
    return {"status": "ok", "version": "10.1.0"}


@app.get("/memory/summary", dependencies=[Depends(verify_api_key)])
def memory_summary():
    """Learning store summary (authenticated)."""
    try:
        return _get_system().get_memory_summary()
    except Exception as e:
        logger.error("Memory summary failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal error")


@app.post("/analyse", response_model=RoomResponse, dependencies=[Depends(verify_api_key)])
def analyse_room(req: RoomRequest):
    """Analyse a single room (authenticated)."""
    try:
        spec = _build_spec(req)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid room spec: {exc}")

    try:
        result = _get_system().analyse_room(spec, user_id="api", run_resilience=req.run_resilience)
        return _to_response(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Room analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Analysis failed")


@app.post("/analyse/floor", response_model=List[RoomResponse], dependencies=[Depends(verify_api_key)])
def analyse_floor(rooms: List[RoomRequest]):
    """Analyse multiple rooms (floor) — authenticated, max 50 rooms."""
    if not rooms:
        raise HTTPException(status_code=422, detail="No rooms provided.")
    if len(rooms) > 50:
        raise HTTPException(status_code=422, detail="Maximum 50 rooms per floor request.")

    try:
        specs = [_build_spec(r) for r in rooms]
        results = [_get_system().analyse_room(spec, user_id="api") for spec in specs]
        return [_to_response(r) for r in results]
    except Exception as exc:
        logger.error("Floor analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Floor analysis failed")


# ✅ NEW: Audit verification endpoint (from consultant suggestion)
@app.get("/audit/verify", dependencies=[Depends(verify_api_key)])
def audit_verify():
    """Verify audit trail integrity — authenticated.

    Checks the entire hash chain and HMAC signatures.
    Returns verification status with details if tampered.
    """
    try:
        system = _get_system()
        is_valid = system.verify_audit_integrity()
        return {
            "valid": is_valid,
            "message": "Audit chain is valid" if is_valid else "AUDIT CHAIN MAY BE COMPROMISED",
        }
    except Exception as exc:
        logger.error("Audit verification failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Verification failed")


# ============================================================================
# V25 — Integration Pipeline Endpoints
# ============================================================================


class IntegrationRequest(BaseModel):
    """Request model for the full integration pipeline."""

    building_id: str = Field(..., min_length=1, max_length=256)
    floors: Optional[List[dict]] = None
    panel_positions: Optional[List[List[float]]] = None
    obstacle_polygons: Optional[List[List[List[float]]]] = None
    acoustic_config: Optional[dict] = None
    nfpa_year: int = Field(2022, ge=2019, le=2025)
    enable_kernel_v30: bool = True
    enable_hash_chain_audit: bool = True
    enable_monte_carlo: bool = True
    enable_bim_sync: bool = True
    bim_source: Optional[str] = None


@app.post("/integration", dependencies=[Depends(verify_api_key)])
def run_integration(req: IntegrationRequest):
    """Run the FULL integration pipeline — all 8 subsystems.

    Wires together: cable routing, digital twin sync, acoustics,
    multi-floor orchestrator, kernel V30, hash chain audit,
    Monte Carlo reliability, and BIM/Revit sync.

    This is the primary endpoint for building-level analysis that
    goes beyond individual room analysis.

    Reference: NFPA 72-2022 §10.14, §12.2, §18.4, §21.
    """
    try:
        # Convert panel_positions from list[list] to list[tuple]
        panel_positions = None
        if req.panel_positions:
            panel_positions = [(p[0], p[1], p[2]) if len(p) == 3 else (p[0], p[1], 0.0) for p in req.panel_positions]

        # Convert obstacle_polygons from list[list[list]] to list[list[tuple]]
        obstacle_polygons = None
        if req.obstacle_polygons:
            obstacle_polygons = [[(v[0], v[1]) for v in poly] for poly in req.obstacle_polygons]

        result = _get_system().run_integration(
            building_id=req.building_id,
            floors=req.floors,
            panel_positions=panel_positions,
            obstacle_polygons=obstacle_polygons,
            acoustic_config=req.acoustic_config,
            nfpa_year=req.nfpa_year,
            enable_kernel_v30=req.enable_kernel_v30,
            enable_hash_chain_audit=req.enable_hash_chain_audit,
            enable_monte_carlo=req.enable_monte_carlo,
            enable_bim_sync=req.enable_bim_sync,
            bim_source=req.bim_source,
            user_id="api",
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Integration pipeline failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Integration pipeline failed")


@app.get("/audit/hashchain", dependencies=[Depends(verify_api_key)])
def hashchain_report():
    """Get SHA-256 hash chain audit compliance report.

    Returns the tamper-evident audit trail compliance report that
    AHJs can verify independently per NFPA 72 §10.6.
    """
    try:
        system = _get_system()
        if hasattr(system, "_hash_chain") and system._hash_chain is not None:
            return system._hash_chain.compliance_report()
        return {
            "status": "no_hash_chain",
            "message": "Hash chain audit not yet initialized. Run an analysis first.",
        }
    except Exception as exc:
        logger.error("Hash chain report failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Hash chain report failed")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    host = os.environ.get("FIREAI_HOST", "127.0.0.1")  # ✅ NOT 0.0.0.0 by default
    port = int(os.environ.get("FIREAI_PORT", "8000"))
    logger.info("Starting FireAI server on %s:%d", host, port)
    uvicorn.run("fireai.core.api_server:app", host=host, port=port, reload=False)
