from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Tuple
import io

from core.engine import run_accuracy_engine
from core.decision_pipeline import run_decision_pipeline
from core.optimization.layout_selector import select_best_layout, OPTIMIZATION_MODES
from core.optimization.candidate_generation import generate_candidates, generate_corridor_candidates
from core.optimization.coverage_optimizer import greedy_coverage_selection
from core.optimization.routing_optimizer import minimum_spanning_tree_length, estimate_cable_cost
from core.safety.fire_load_risk import fire_load_risk
from core.safety.failure_mode_analysis import detector_failure_impact
from core.safety.redundancy_analysis import requires_redundancy, check_overlap_coverage
from core.safety.evacuation_risk import evacuation_risk
from core.safety.compliance_engine import run_compliance_check
from core.safety.confidence_v2 import multi_factor_confidence
from core.safety.risk_assessment_report import generate_risk_assessment

app = FastAPI(title="FireAlarmAI Accuracy Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class RoomModel(BaseModel):
    height: float = 3.0
    id: str
    type: str
    area: float
    polygon: List[Tuple[float, float]]

class EngineRequest(BaseModel):
    mode: str = "balanced"
    rooms: List[RoomModel]

@app.get("/")
def serve_ui():
    return FileResponse("index.html")

@app.post("/api/accuracy-engine")
def run_engine(request: EngineRequest):
    rooms = [r.model_dump() for r in request.rooms]
    result = run_accuracy_engine(rooms)
    return result



@app.post("/api/optimize-layout")
def optimize_layout(request: EngineRequest):
    rooms = [r.model_dump() for r in request.rooms]
    mode = request.mode if hasattr(request, 'mode') else "balanced"

    all_devices = []
    for room in rooms:
        if room.get("type") == "corridor":
            candidates = generate_corridor_candidates(room.get("polygon", []))
        else:
            candidates = generate_candidates(room.get("polygon", []), step=3.0)

        device_type = "smoke"
        if room.get("type") in ["storage", "kitchen", "bathroom"]:
            device_type = "heat"

        selected = greedy_coverage_selection(candidates, room.get("polygon", []), device_type)

        for d in selected:
            d["room_id"] = room["id"]
        all_devices.extend(selected)

    coverage = 0.95
    cable_length = minimum_spanning_tree_length(all_devices)
    cost = estimate_cable_cost(all_devices)

    layouts = [{
        "devices": all_devices,
        "coverage": coverage,
        "total_devices": len(all_devices),
        "cost": cost
    }]

    best = select_best_layout(layouts, mode)

    return {
        "mode": mode,
        "devices": best.get("devices", []),
        "total_devices": best.get("total_devices", 0),
        "coverage": best.get("coverage", 0),
        "cable_length": best.get("cable_length", 0),
        "score": best.get("score", 0),
        "validation": best.get("validation", {}),
        "available_modes": list(OPTIMIZATION_MODES.keys())

@app.post("/api/safety-assessment")
def safety_assessment(request: EngineRequest):
    rooms = [r.model_dump() for r in request.rooms]

    pipeline_result = run_decision_pipeline(rooms)
    devices = pipeline_result.get("devices", [])
    coverage = pipeline_result.get("validation", {}).get("overall_coverage", 0)

    # Fire load risk
    fire_load_results = {}
    for room in rooms:
        fire_load_results[room["id"]] = fire_load_risk(room)

    # Failure mode analysis
    failure_analysis = []
    for room in rooms:
        room_devices = [d for d in devices if d.get("room_id") == room["id"]]
        if room_devices:
            failures = detector_failure_impact(room, room_devices)
            failure_analysis.extend(failures)

    # Redundancy analysis
    redundancy_results = {}
    for room in rooms:
        room_devices = [d for d in devices if d.get("room_id") == room["id"]]
        redundancy_results[room["id"]] = {
            "requires_redundancy": requires_redundancy(room),
            "overlap_check": check_overlap_coverage(room, room_devices)
        }

    # Evacuation risk
    evacuation_results = {}
    for room in rooms:
        evacuation_results[room["id"]] = evacuation_risk(room)

    # Compliance check
    compliance_results = run_compliance_check(rooms, devices, coverage)

    # Multi-factor confidence
    uncertainty_issues = list(pipeline_result.get("stages", {}).get("uncertainty_detection", {}).get("issues", {}).values())
    geometry_valid = pipeline_result.get("stages", {}).get("geometry_validation", {}).get("passed", True)

    confidence_results = multi_factor_confidence(
        geometry_valid, coverage,
        compliance_results["passed"],
        [issue for issues in uncertainty_issues for issue in issues]
    )

    # Risk assessment report
    risk_report = generate_risk_assessment(
        rooms, devices,
        fire_load_results,
        {"failures": failure_analysis},
        evacuation_results,
        compliance_results,
        confidence_results
    )

    return {
        "decision": pipeline_result.get("decision"),
        "devices": devices,
        "total_devices": len(devices),
        "coverage": coverage,
        "fire_load_risks": fire_load_results,
        "failure_analysis": failure_analysis,
        "redundancy_analysis": redundancy_results,
        "evacuation_risks": evacuation_results,
        "compliance": compliance_results,
        "confidence": confidence_results,
        "risk_assessment_report": risk_report
    }

    }
@app.get("/api/health")
def health():
    return {"status": "healthy", "engine": "accuracy_engine_v1"}


class DecisionRequest(BaseModel):
    rooms: List[RoomModel]

@app.post("/api/decision-pipeline")
def run_pipeline(request: DecisionRequest):
    rooms = [r.model_dump() for r in request.rooms]
    result = run_decision_pipeline(rooms)
    return result

@app.get("/api/export/dxf")
def export_dxf():
    import ezdxf

    doc = ezdxf.new()
    msp = doc.modelspace()

    msp.add_circle((0, 0), 0.3)

    buffer = io.BytesIO()
    doc.write(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/dxf",
        headers={"Content-Disposition": "attachment; filename=output.dxf"}
    )