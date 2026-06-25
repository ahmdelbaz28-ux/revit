"""FireAI NFPA 72-2022 Design API — FastAPI application (V10)."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
from typing import Any, Dict, List, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from shapely.geometry import Polygon as ShapelyPolygon

# Rate limiting with slowapi
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .audit_trail import AuditTrail
from .fire_expert_system import FireExpertSystem as ExpertSystem
from .floor_orchestrator import FloorOrchestrator
from .nfpa72_models import CeilingSpec, CeilingType, DetectorType, RoomSpec

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB: int = 50
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)


def create_app() -> FastAPI:
    application = FastAPI(
        title="FireAI NFPA 72-2022 Design API",
        description="Automated fire alarm layout per NFPA 72-2022",
        version="10.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    # Security Fix (VULN-006): Read allowed CORS origins from environment variable
    _cors_origins = os.getenv("FIREAI_CORS_ORIGINS", os.getenv("CORS_ORIGINS", "http://localhost:3000")).split(",")
    # V114 FIX: Reject wildcard CORS origins — safety-critical system must not
    # allow any website to modify fire protection designs via cross-origin requests
    if "*" in _cors_origins:
        import logging

        logging.getLogger("fireai.security").critical(
            "CORS wildcard '*' detected in FIREAI_CORS_ORIGINS — REJECTED. "
            "This is a safety-critical fire protection system. Cross-origin "
            "requests from any domain could modify NFPA 72 compliance data. "
            "Specify explicit origins instead."
        )
        _cors_origins = [o for o in _cors_origins if o.strip() != "*"]
        if not _cors_origins:
            _cors_origins = ["http://localhost:3000"]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return application


app = create_app()
_expert_system = ExpertSystem()
_audit_trail = AuditTrail(project_name="api-session")

# Task store for async operations (in-memory with TTL and cap)
# CRITICAL FIX: Previously had no TTL, no cleanup, and no cap.
# This caused unbounded memory growth in long-lived API workers.
_task_store: Dict[str, Dict[str, Any]] = {}
_MAX_TASK_STORE_SIZE = 1000  # Maximum number of tasks to keep
_TASK_TTL_SECONDS = 3600  # Tasks expire after 1 hour

# Request timeout in seconds
REQUEST_TIMEOUT_SECONDS: float = 30.0


def _cleanup_task_store():
    """Remove expired and excess tasks from the store."""
    import time as _time

    now = _time.monotonic()
    # Remove expired tasks
    expired = [tid for tid, task in _task_store.items() if task.get("_expires_at", 0) < now]
    for tid in expired:
        del _task_store[tid]
    # Evict oldest if still over cap
    if len(_task_store) > _MAX_TASK_STORE_SIZE:
        # Sort by creation time and remove oldest
        sorted_tasks = sorted(_task_store.items(), key=lambda x: x[1].get("_created_at", 0))
        to_remove = sorted_tasks[: len(_task_store) - _MAX_TASK_STORE_SIZE]
        for tid, _ in to_remove:
            del _task_store[tid]


async def _run_with_timeout(coro, timeout: float = REQUEST_TIMEOUT_SECONDS):
    """Run coroutine with timeout, return 503 on timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail=f"Request timeout after {timeout}s. Please use /analyse/floor/async for large floors.",
        )


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify API key using timing-safe comparison.
    Security Fix (VULN-017): Use secrets.compare_digest instead of set membership.
    """
    raw = os.getenv("FIREAI_API_KEYS", "")
    valid_keys = {k.strip() for k in raw.split(",") if k.strip()}
    if not valid_keys:
        raise HTTPException(status_code=503, detail="Service not configured: FIREAI_API_KEYS not set")
    # Security Fix (VULN-017): Timing-safe comparison to prevent timing attacks
    if not any(secrets.compare_digest(x_api_key, k) for k in valid_keys):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class RoomSpecIn(BaseModel):
    room_id: str
    name: str = ""
    width_m: Optional[float] = None
    depth_m: Optional[float] = None
    polygon: Optional[List[List[float]]] = None
    occupancy_type: str = "office"
    ceiling_height_m: Optional[float] = None


class AnalyseRoomRequest(BaseModel):
    room: RoomSpecIn
    forced_detector_type: Optional[str] = None
    required_coverage_pct: float = 100.0


class AnalyseFloorRequest(BaseModel):
    floor_id: str
    rooms: List[RoomSpecIn]


class AnalyseFloorRequestV10(BaseModel):
    """V10 Floor analysis request with resilience option"""

    rooms: List[RoomSpecIn]
    run_resilience: bool = True


class RoomResultOut(BaseModel):
    room_id: str
    status: str
    detector_type: str
    detector_count: int
    detector_positions: List[Dict[str, float]]
    coverage_result: Optional[Dict[str, Any]] = None
    coverage_pct: float
    errors: List[str] = []
    refused: bool = False


class FloorResultOut(BaseModel):
    floor_id: str
    fully_compliant: bool
    total_detectors: int
    room_results: List[RoomResultOut]
    non_compliant_rooms: List[str] = []
    floor_warnings: List[str] = []
    floor_errors: List[str] = []


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _room_result_to_out(result) -> RoomResultOut:
    return RoomResultOut(
        room_id=result.room_id,
        status=result.status,
        detector_type=result.detector_type.value
        if hasattr(result.detector_type, "value")
        else str(result.detector_type),
        detector_count=len(result.detector_positions),
        detector_positions=[{"x": p[0], "y": p[1]} for p in result.detector_positions],
        coverage_result={"coverage_pct": result.coverage_result.coverage_pct} if result.coverage_result else None,
        coverage_pct=result.coverage_result.coverage_pct if result.coverage_result else 0.0,
        errors=result.errors,
        refused=result.refused,
    )


def _build_room_spec(room_in: RoomSpecIn) -> RoomSpec:
    polygon = None
    if room_in.polygon:
        polygon = ShapelyPolygon(room_in.polygon)

    # CRITICAL FIX: Derive width/depth from polygon when available.
    # Previously defaulted to 10.0x10.0 when only polygon was sent,
    # causing silent geometry corruption in safety-critical analysis.
    width_m = room_in.width_m
    depth_m = room_in.depth_m

    if polygon is not None and (width_m is None or depth_m is None):
        bounds = polygon.bounds  # (minx, miny, maxx, maxy)
        derived_width = bounds[2] - bounds[0]
        derived_depth = bounds[3] - bounds[1]
        if width_m is None:
            width_m = derived_width
        if depth_m is None:
            depth_m = derived_depth

    # SAFETY: If still no dimensions, REJECT rather than inject fake defaults.
    # A 10.0x10.0 default for safety-critical geometry is unacceptable.
    if width_m is None or depth_m is None:
        raise ValueError(
            f"Room '{room_in.room_id}': width_m and depth_m are required "
            f"when no polygon is provided. Refusing to inject fake geometry."
        )

    # Validate derived dimensions are physically meaningful
    if width_m <= 0 or depth_m <= 0:
        raise ValueError(
            f"Room '{room_in.room_id}': derived dimensions invalid "
            f"(width={width_m:.3f}m, depth={depth_m:.3f}m). "
            f"Check polygon coordinates."
        )

    # Use create_safe() to allow clamping of unusual heights
    ceiling_spec = None
    if room_in.ceiling_height_m is not None:
        ceiling_spec = CeilingSpec.create_safe(
            height_at_low_point_m=room_in.ceiling_height_m,
            height_at_high_point_m=room_in.ceiling_height_m,
            ceiling_type=CeilingType.FLAT,
            beam_depth_m=0.0,
        )

    return RoomSpec.create_validated(
        room_id=room_in.room_id,
        name=room_in.name or room_in.room_id,
        width_m=width_m,
        depth_m=depth_m,
        polygon=polygon,
        occupancy_type=room_in.occupancy_type,
        ceiling_spec=ceiling_spec,
    )


# ============================================================================
# API ENDPOINTS
# ============================================================================


@app.get("/health", tags=["System"])
async def get_health() -> Dict[str, str]:
    return {"status": "healthy", "version": "10.0.0"}


@app.get("/version", tags=["System"])
async def get_version() -> Dict[str, str]:
    return {"version": "10.0.0", "nfpa_version": "2022"}


@app.get("/audit", tags=["Audit"], dependencies=[Depends(verify_api_key)])
async def get_audit_trail() -> Dict[str, Any]:
    return {"summary": _audit_trail.summary(), "entries": _audit_trail.to_list()}


# Rate-limited endpoints
@app.post("/projects/", tags=["Projects"], dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def upload_file(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:  # noqa: B008
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum allowed size is {MAX_FILE_SIZE_MB} MB.")
    allowed_extensions = {".dwg", ".rvt", ".json", ".ifc"}
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=422, detail=f"Unsupported file type '{ext}'. Allowed: {sorted(allowed_extensions)}"
        )
    logger.info("upload_file: accepted '%s' (%d bytes)", filename, len(content))
    return {"filename": filename, "size_bytes": len(content), "status": "accepted"}


@app.post("/analyse/room", response_model=RoomResultOut, tags=["Design"], dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def analyse_room(request: Request, body: AnalyseRoomRequest) -> RoomResultOut:
    try:
        room_spec = _build_room_spec(body.room)  # create_validated called inside
    except ValueError as e:
        # Log rejection before returning error
        _audit_trail.log_rejection(room_id=body.room.room_id, reason=str(e))
        raise HTTPException(status_code=422, detail="Invalid room specification. Check room parameters and try again.")

    forced_type: Optional[DetectorType] = None
    if body.forced_detector_type:
        try:
            forced_type = DetectorType(body.forced_detector_type)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown detector type: {body.forced_detector_type}")
    result = _expert_system.analyse_room(  # type: ignore[call-arg]
        room_spec=room_spec, forced_detector_type=forced_type, required_coverage_pct=body.required_coverage_pct
    )
    _audit_trail.log_placement(
        room_id=result.room_id,
        detector_count=len(result.detector_positions),
        detector_type=result.detector_type.value,
        coverage_pct=result.coverage_result.coverage_pct if result.coverage_result else 0.0,
        positions=result.detector_positions,
    )
    return _room_result_to_out(result)


@app.post("/analyse/floor", response_model=FloorResultOut, tags=["Design"], dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def analyse_floor(request: Request, body: AnalyseFloorRequest) -> FloorResultOut:
    # Build and validate each room - log any rejections
    room_specs = []
    for r in body.rooms:
        try:
            room_specs.append(_build_room_spec(r))
        except ValueError as e:
            _audit_trail.log_rejection(room_id=r.room_id, reason=str(e))
            raise HTTPException(status_code=422, detail=f"Room '{r.room_id}': {e}")

    orchestrator = FloorOrchestrator(audit_trail=_audit_trail)
    floor_result = orchestrator.process(room_specs=room_specs, project_name=body.floor_id, source_dxf="")
    fully_compliant = floor_result.rooms_passed == floor_result.total_rooms and floor_result.rooms_errored == 0

    return FloorResultOut(
        floor_id=floor_result.project_name,
        fully_compliant=fully_compliant,
        total_detectors=floor_result.total_detectors,
        non_compliant_rooms=[],
        room_results=[_room_result_to_out(r) for r in floor_result.room_results],
        floor_warnings=[],
        floor_errors=[],
    )


# Exception handler for rate limit errors
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


# ============================================================================
# ENDPOINTS USING V10 ENHANCED + AUDIT STORE
# ============================================================================

# Global FireAISystem instance
_fireai_system = None


def _get_fireai_system():
    """Get or create FireAISystem instance.
    Security Fix (VULN-023): Use file-based database for persistent audit trail.
    """
    global _fireai_system
    if _fireai_system is None:
        from fireai.core.fireai_core import FireAISystem

        # Security Fix (VULN-023): Persistent DB path from environment variable
        _db_path = os.getenv("FIREAI_DB_PATH", "fireai_data/fireai.sqlite")
        _db_dir = os.path.dirname(_db_path)
        if _db_dir:
            os.makedirs(_db_dir, exist_ok=True)
        _fireai_system = FireAISystem(db_path=_db_path)
    return _fireai_system


@app.post("/analyse/room/v10", response_model=RoomResultOut, tags=["Design"], dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def analyse_room_v10(request: Request, body: AnalyseRoomRequest) -> RoomResultOut:
    """Analyze room using V10 Enhanced with resilience and audit trail."""
    try:
        room_spec = _build_room_spec(body.room)
    except ValueError as e:
        logger.warning("Room spec validation failed: %s", e)
        raise HTTPException(status_code=422, detail="Invalid room specification. Check room parameters and try again.")

    system = _get_fireai_system()
    result = system.analyse_room(
        room_spec=room_spec,
        user_id="api_user",
        run_resilience=True,
    )

    return _room_result_to_out(result)


@app.post("/analyse/floor/v10", tags=["Design"], dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def analyse_floor_v10(request: Request, body: AnalyseFloorRequestV10):
    """Analyze floor using V10 Enhanced with resilience and audit trail."""
    room_specs = []
    for r in body.rooms:
        try:
            room_specs.append(_build_room_spec(r))
        except ValueError as e:
            logger.warning("Room spec validation failed: %s", e)
            raise HTTPException(status_code=422, detail="Invalid room specification in batch. Check room parameters.")

    system = _get_fireai_system()
    results = system.analyse_floor(
        rooms=room_specs,
        user_id="api_user",
        run_resilience=body.run_resilience
        if hasattr(body, "run_resilience")
        else False,  # V112: FAIL-SAFE — don't run resilience unless explicitly requested
    )

    return {
        "room_results": [_room_result_to_out(r) for r in results],
        "total_rooms": len(results),
        "fully_compliant": all(r.confidence.value != "UNSAFE" for r in results),
    }


@app.get("/audit/trail", tags=["Audit"], dependencies=[Depends(verify_api_key)])
async def get_audit_trail_v10():
    """Get audit trail from FireAISystem."""
    system = _get_fireai_system()
    return {"events": system.get_audit_trail()}


@app.get("/audit/verify", tags=["Audit"], dependencies=[Depends(verify_api_key)])
async def verify_audit_v10():
    """Verify audit trail integrity."""
    system = _get_fireai_system()
    is_valid = system.verify_audit_integrity()
    return {"valid": is_valid, "message": "Audit chain is valid" if is_valid else "Audit chain may be tampered"}


@app.post("/analyse/floor/async", tags=["Design"], dependencies=[Depends(verify_api_key)])
@limiter.limit("20/minute")
async def analyse_floor_async(
    request: Request,
    body: AnalyseFloorRequestV10,
    background_tasks: BackgroundTasks,
):
    """Analyze floor asynchronously - returns immediately with task_id.

    For large floors (10+ rooms), use this endpoint for background processing.
    Poll GET /task/{task_id} for results.
    """
    task_id = str(uuid.uuid4())

    # Immediate response (with TTL tracking)
    import time as _time

    _cleanup_task_store()  # Clean up before adding
    _task_store[task_id] = {
        "status": "processing",
        "progress": 0,
        "result": None,
        "error": None,
        "_created_at": _time.monotonic(),
        "_expires_at": _time.monotonic() + _TASK_TTL_SECONDS,
    }

    # Schedule background task
    def _process_floor(task_id: str, body_data: AnalyseFloorRequestV10):
        """Background task to process floor."""
        room_specs = []
        for r in body_data.rooms:
            try:
                room_specs.append(_build_room_spec(r))
            except ValueError as e:
                _task_store[task_id] = {
                    "status": "error",
                    "error": str(e),
                }
                return

        try:
            system = _get_fireai_system()
            results = system.analyse_floor(
                rooms=room_specs,
                user_id="async_api_user",
                run_resilience=body_data.run_resilience
                if hasattr(body_data, "run_resilience")
                else False,  # V112: FAIL-SAFE
            )
            _task_store[task_id] = {
                "status": "completed",
                "result": {
                    "room_results": [_room_result_to_out(r) for r in results],
                    "total_rooms": len(results),
                    "fully_compliant": all(r.confidence.value != "UNSAFE" for r in results),
                },
            }
        except Exception as e:
            _task_store[task_id] = {
                "status": "error",
                "error": str(e),
            }

    background_tasks.add_task(_process_floor, task_id, body)

    return {"task_id": task_id, "status": "processing"}


@app.get("/task/{task_id}", tags=["Design"], dependencies=[Depends(verify_api_key)])
async def get_task_result(task_id: str):
    """Get async task result by task_id."""
    if task_id not in _task_store:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _task_store[task_id]
    if task["status"] == "completed":
        return {"status": "completed", "result": task["result"]}
    if task["status"] == "error":
        return {"status": "error", "error": task["error"]}
    return {"status": "processing"}
