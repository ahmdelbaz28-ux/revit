"""FireAI NFPA 72-2022 Design API — FastAPI application (V10)."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Rate limiting with slowapi
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .nfpa72_models import CeilingSpec, CeilingType, DetectorType, HVACDuct, RoomSpec
from .fire_expert_system import ExpertSystem
from .floor_orchestrator import FloorOrchestrator
from .audit_trail import AuditTrail
from shapely.geometry import Polygon as ShapelyPolygon

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
    application.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return application

app = create_app()
_expert_system = ExpertSystem()
_audit_trail = AuditTrail(project_name="api-session")

async def verify_api_key(x_api_key: str = Header(...)) -> str:
    raw = os.getenv("FIREAI_API_KEYS", "")
    valid_keys = {k.strip() for k in raw.split(",") if k.strip()}
    if x_api_key not in valid_keys:
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
        detector_type=result.detector_type.value if hasattr(result.detector_type, 'value') else str(result.detector_type),
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
        width_m=room_in.width_m or 10.0,
        depth_m=room_in.depth_m or 10.0,
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
async def upload_file(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum allowed size is {MAX_FILE_SIZE_MB} MB.")
    allowed_extensions = {".dwg", ".rvt", ".json", ".ifc"}
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(status_code=422, detail=f"Unsupported file type '{ext}'. Allowed: {sorted(allowed_extensions)}")
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
        raise HTTPException(status_code=422, detail=str(e))
    
    forced_type: Optional[DetectorType] = None
    if body.forced_detector_type:
        try:
            forced_type = DetectorType(body.forced_detector_type)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown detector type: {body.forced_detector_type}")
    result = _expert_system.analyse_room(
        room_spec=room_spec,
        forced_detector_type=forced_type,
        required_coverage_pct=body.required_coverage_pct
    )
    _audit_trail.log_placement(
        room_id=result.room_id,
        detector_count=len(result.detector_positions),
        detector_type=result.detector_type.value,
        coverage_pct=result.coverage_result.coverage_pct if result.coverage_result else 0.0,
        positions=result.detector_positions
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
    floor_result = orchestrator.process(
        room_specs=room_specs,
        project_name=body.floor_id,
        source_dxf=""
    )
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
    """Get or create FireAISystem instance."""
    global _fireai_system
    if _fireai_system is None:
        from fireai.core.fireai_core import FireAISystem
        _fireai_system = FireAISystem(db_path=":memory:")
    return _fireai_system


@app.post("/analyse/room/v10", response_model=RoomResultOut, tags=["Design"], dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def analyse_room_v10(request: Request, body: AnalyseRoomRequest) -> RoomResultOut:
    """Analyze room using V10 Enhanced with resilience and audit trail."""
    try:
        room_spec = _build_room_spec(body.room)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    
    system = _get_fireai_system()
    result = system.analyse_room(
        room_spec=room_spec,
        user_id="api_user",
        run_resilience=True,
    )
    
    return _room_result_to_out(result)


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