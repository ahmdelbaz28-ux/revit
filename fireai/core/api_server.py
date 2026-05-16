#!/usr/bin/env python3
"""
api_server.py — FastAPI REST wrapper for FireAI
Based on V10 Enhanced + LearningStore

Install:  pip install fastapi uvicorn
Run:      python fireai/core/api_server.py
Docs:     http://localhost:8000/docs

Endpoints:
  POST /analyse          — analyse one room
  POST /analyse/floor    — analyse multiple rooms (shared memory)
  GET  /memory/summary   — live learning stats
  GET  /health           — liveness probe
"""
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

logging.basicConfig(level=logging.INFO)

# ── Shared system instance (one DB, shared across requests) ────────────
from fireai.core.fireai_core import FireAISystem
from fireai.core.nfpa72_models import RoomSpec, CeilingSpec, CeilingType

_DB_PATH = Path("fireai.sqlite3")
_SYSTEM = FireAISystem(db_path=_DB_PATH)

app = FastAPI(
    title="FireAI - NFPA 72 Expert System",
    description="Adaptive detector placement with persistent learning.",
    version="10.0.0",
)

# ── Request / Response models ─────────────────────────────────────────────

class RoomRequest(BaseModel):
    room_id: str
    polygon: List[List[float]] = Field(..., min_items=3)
    height: float = Field(3.0, gt=0)
    height_high: Optional[float] = None
    ceiling_type: str = "FLAT"
    occupancy_type: str = "office"  # FIX: Allow user to specify
    run_resilience: bool = True

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

# ── Helpers ─────────────────────────────────────────────────────────

def _build_spec(req: RoomRequest) -> RoomSpec:
    """Convert request to RoomSpec."""
    ceiling = CeilingSpec.create_safe(
        height_at_low_point_m=req.height,
        height_at_high_point_m=req.height_high or req.height,
        ceiling_type=CeilingType[req.ceiling_type] if req.ceiling_type in [c.name for c in CeilingType] else CeilingType.FLAT,
    )
    # Calculate width/depth from polygon
    poly = [tuple(p) for p in req.polygon]
    width = max(p[0] for p in poly)
    depth = max(p[1] for p in poly)
    
    return RoomSpec(
        room_id=req.room_id,
        width_m=width,
        depth_m=depth,
        occupancy_type=req.occupancy_type,  # FIX: Use user-provided
        ceiling_spec=ceiling,
        polygon=poly,
    )

def _to_response(r) -> RoomResponse:
    """Convert EnhancedExpertResult to response."""
    return RoomResponse(
        room_id=r.room_id,
        compliant=r.compliant,
        safe_to_submit=r.safe_to_submit if hasattr(r, 'safe_to_submit') else False,
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

# ── Endpoints ─────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok", "version": "10.0.0"}

@app.get("/memory/summary")
def memory_summary():
    """Learning store summary."""
    try:
        return _SYSTEM.get_memory_summary()
    except Exception as e:
        return {"error": str(e)}

@app.post("/analyse", response_model=RoomResponse)
def analyse_room(req: RoomRequest):
    """Analyse a single room."""
    try:
        spec = _build_spec(req)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid room spec: {exc}")
    
    result = _SYSTEM.analyse_room(spec, user_id="api", run_resilience=req.run_resilience)
    return _to_response(result)

@app.post("/analyse/floor", response_model=List[RoomResponse])
def analyse_floor(rooms: List[RoomRequest]):
    """Analyse multiple rooms (floor)."""
    if not rooms:
        raise HTTPException(status_code=422, detail="No rooms provided.")
    
    specs = [_build_spec(r) for r in rooms]
    results = [_SYSTEM.analyse_room(spec, user_id="api") for spec in specs]
    return [_to_response(r) for r in results]

# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("fireai.core.api_server:app", host="0.0.0.0", port=8000, reload=False)