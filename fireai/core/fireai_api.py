"""FireAI NFPA 72-2022 Design API — FastAPI application (V9)."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    _SLOWAPI_AVAILABLE = True
except ImportError:
    _SLOWAPI_AVAILABLE = False

from .nfpa72_models import CeilingSpec, CeilingType, DetectorType, HVACDuct, RoomSpec
from .fire_expert_system import ExpertSystem
from .floor_orchestrator import FloorOrchestrator
from .audit_trail import AuditTrail
from shapely.geometry import Polygon as ShapelyPolygon

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB: int = 50
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024

if _SLOWAPI_AVAILABLE:
    limiter = Limiter(key_func=get_remote_address)
else:
    limiter = None  # type: ignore[assignment]

def create_app() -> FastAPI:
    application = FastAPI(
        title="FireAI NFPA 72-2022 Design API",
        description="Automated fire alarm layout per NFPA 72-2022",
        version="9.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])
    if _SLOWAPI_AVAILABLE and limiter is not None:
        application.state.limiter = limiter
        application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return application

app = create_app()
_expert_system = ExpertSystem()
_audit_trail = AuditTrail(project_name="api-session")

async def verify_api_key(x_api_key: str = Header(...)) -> str:
    raw = os.getenv("FIREAI_API_KEYS", "")
    valid_keys = {k.strip() for k in raw.split(",") if k.strip()}
    if not valid_keys:
        raise HTTPException(status_code=401, detail="API authentication not configured.")
    if x_api_key not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return x_api_key

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error. Contact support."})

class CeilingSpecIn(BaseModel):
    height_at_low_point_m:  float = Field(3.0, ge=0.1, le=50.0)
    height_at_high_point_m: float = Field(3.0, ge=0.1, le=50.0)
    ceiling_type:           str = Field("SMOOTH")
    beam_depth_m:           float = Field(0.0, ge=0.0)
    beam_spacing_m:         float = Field(0.0, ge=0.0)

class HVACDuctIn(BaseModel):
    duct_id:     str
    centerline:  List[List[float]]
    width_m:     float = Field(0.3, ge=0.0)
    height_m:    float = Field(0.3, ge=0.0)
    airflow_m3s: float = Field(0.0, ge=0.0)

class RoomSpecIn(BaseModel):
    room_id:        str
    name:           str
    polygon_coords: List[List[float]]
    ceiling:        CeilingSpecIn
    room_type:      str = "office"
    hvac_ducts:     List[HVACDuctIn] = Field(default_factory=list)

class AnalyseRoomRequest(BaseModel):
    room:                  RoomSpecIn
    required_coverage_pct: float = Field(100.0, ge=50.0, le=100.0)
    forced_detector_type:  Optional[str] = None

class AnalyseFloorRequest(BaseModel):
    floor_id:              str
    rooms:                 List[RoomSpecIn]
    required_coverage_pct: float = Field(100.0, ge=50.0, le=100.0)
    parallel:              bool  = False

class RoomResultOut(BaseModel):
    room_id:            str
    compliant:          bool
    coverage_pct:       float
    detector_count:     int
    detector_type:      str
    wall_violations:    List[str]
    duct_device_count:  int
    warnings:           List[str]
    errors:             List[str]

class FloorResultOut(BaseModel):
    floor_id:           str
    fully_compliant:    bool
    total_detectors:    int
    non_compliant_rooms:List[str]
    room_results:       List[RoomResultOut]
    floor_warnings:     List[str]
    floor_errors:       List[str]

def _build_room_spec(room_in: RoomSpecIn) -> RoomSpec:
    ceiling = CeilingSpec.create_safe(
        height_at_low_point_m=room_in.ceiling.height_at_low_point_m,
        height_at_high_point_m=room_in.ceiling.height_at_high_point_m,
        ceiling_type=CeilingType(room_in.ceiling.ceiling_type),
        beam_depth_m=room_in.ceiling.beam_depth_m,
        beam_spacing_m=room_in.ceiling.beam_spacing_m,
    )
    hvac_ducts = [HVACDuct(duct_id=d.duct_id, centerline=[tuple(p) for p in d.centerline],
                           width_m=d.width_m, height_m=d.height_m, airflow_m3s=d.airflow_m3s)
                  for d in room_in.hvac_ducts]
    return RoomSpec(room_id=room_in.room_id, name=room_in.name,
                    polygon=ShapelyPolygon([tuple(p) for p in room_in.polygon_coords]),
                    ceiling=ceiling, occupancy_type=room_in.room_type, hvac_ducts=hvac_ducts)

def _room_result_to_out(result: Any) -> RoomResultOut:
    coverage_pct = result.coverage_result.coverage_percentage if result.coverage_result else 0.0
    return RoomResultOut(
        room_id=result.room_id, compliant=result.compliant, coverage_pct=coverage_pct,
        detector_count=len(result.detector_positions), detector_type=result.detector_type.value,
        wall_violations=[wv.violation for wv in result.wall_violations],
        duct_device_count=len(result.duct_devices),
        warnings=result.warnings, errors=result.errors,
    )

@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, str]:
    return {"status": "healthy"}

@app.get("/version", tags=["System"])
async def version() -> Dict[str, str]:
    return {"version": "9.0.0", "nfpa_edition": "2022"}

@app.get("/audit", tags=["Audit"], dependencies=[Depends(verify_api_key)])
async def get_audit_trail() -> Dict[str, Any]:
    return {"summary": _audit_trail.summary(), "entries": _audit_trail.to_list()}

async def analyse_room(body: AnalyseRoomRequest) -> RoomResultOut:
    room_spec = _build_room_spec(body.room)
    forced_type: Optional[DetectorType] = None
    if body.forced_detector_type:
        try:
            forced_type = DetectorType(body.forced_detector_type)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown detector type: {body.forced_detector_type}")
    result = _expert_system.analyse_room(room_spec=room_spec, forced_detector_type=forced_type,
                                         required_coverage_pct=body.required_coverage_pct)
    _audit_trail.log_placement(room_id=result.room_id, detector_count=len(result.detector_positions),
                               detector_type=result.detector_type.value,
                               coverage_pct=result.coverage_result.coverage_pct if result.coverage_result else 0.0,
                               positions=result.detector_positions)
    return _room_result_to_out(result)

async def analyse_floor(body: AnalyseFloorRequest) -> FloorResultOut:
    room_specs = [_build_room_spec(r) for r in body.rooms]
    orchestrator = FloorOrchestrator()
    floor_result = orchestrator.process(
        room_specs=room_specs, 
        project_name=body.floor_id,
        source_dxf=""
    )
    # Calculate fully_compliant from rooms_passed
    fully_compliant = floor_result.rooms_passed == floor_result.total_rooms and floor_result.rooms_errored == 0
    
    return FloorResultOut(
        floor_id=floor_result.project_name,  # Use project_name as floor_id
        fully_compliant=fully_compliant,
        total_detectors=floor_result.total_detectors,
        non_compliant_rooms=[],  # FloorResult doesn't have this
        room_results=[_room_result_to_out(r) for r in floor_result.room_results],
        floor_warnings=[],  # FloorResult doesn't have this
        floor_errors=[],  # FloorResult doesn't have this
    )

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

# Rate limit fix (applied before route registration)
if _SLOWAPI_AVAILABLE and limiter is not None:
    upload_file_limited = limiter.limit("10/minute")(upload_file)
    analyse_room_limited = limiter.limit("30/minute")(analyse_room)
    analyse_floor_limited = limiter.limit("10/minute")(analyse_floor)
    app.post("/projects/", tags=["Projects"], dependencies=[Depends(verify_api_key)])(upload_file_limited)
    app.post("/analyse/room", response_model=RoomResultOut, tags=["Design"], dependencies=[Depends(verify_api_key)])(analyse_room_limited)
    app.post("/analyse/floor", response_model=FloorResultOut, tags=["Design"], dependencies=[Depends(verify_api_key)])(analyse_floor_limited)
else:
    app.post("/projects/", tags=["Projects"], dependencies=[Depends(verify_api_key)])(upload_file)
    app.post("/analyse/room", response_model=RoomResultOut, tags=["Design"], dependencies=[Depends(verify_api_key)])(analyse_room)
    app.post("/analyse/floor", response_model=FloorResultOut, tags=["Design"], dependencies=[Depends(verify_api_key)])(analyse_floor)
