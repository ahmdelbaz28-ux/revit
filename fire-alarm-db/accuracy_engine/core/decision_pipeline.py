from core.uncertainty_detector import is_design_viable
from core.risk_classifier import risk_score, risk_level
from core.geometry_validator import validate_geometry, check_rooms_overlap
from core.hard_constraints import evaluate_constraints
from core.edge_case_handler import handle_overlapping_rooms
from core.confidence_scorer import overall_confidence
from core.engine import run_accuracy_engine

def run_decision_pipeline(rooms: list) -> dict:
    pipeline_result = {
        "pipeline_passed": True,
        "stages": {}
    }

    # Stage 1: Uncertainty Detection
    viable, issues = is_design_viable(rooms)
    pipeline_result["stages"]["uncertainty_detection"] = {
        "passed": viable,
        "issues": issues
    }

    if not viable:
        pipeline_result["pipeline_passed"] = False
        pipeline_result["decision"] = "REQUEST_CLARIFICATION"
        pipeline_result["clarification_needed"] = issues
        return pipeline_result

    # Stage 2: Geometry Validation
    geometry_results = {}
    all_valid = True
    for room in rooms:
        valid, reason = validate_geometry(room)
        geometry_results[room["id"]] = {"valid": valid, "reason": reason}
        if not valid:
            all_valid = False

    pipeline_result["stages"]["geometry_validation"] = {
        "passed": all_valid,
        "details": geometry_results
    }

    if not all_valid:
        pipeline_result["pipeline_passed"] = False
        pipeline_result["decision"] = "INVALID_GEOMETRY"
        return pipeline_result

    # Stage 3: Overlap Check
    overlaps = handle_overlapping_rooms(rooms)
    pipeline_result["stages"]["overlap_check"] = overlaps

    # Stage 4: Risk Classification
    risk_scores = {}
    for room in rooms:
        score = risk_score(room)
        risk_scores[room["id"]] = {
            "score": score,
            "level": risk_level(score)
        }
    pipeline_result["stages"]["risk_classification"] = risk_scores

    # Stage 5: Run Engine
    engine_result = run_accuracy_engine(rooms)
    pipeline_result["engine_result"] = engine_result

    # Stage 6: Constraint Evaluation
    coverage = engine_result.get("validation", {}).get("coverage_score", 0)
    constraints_result = evaluate_constraints(
        engine_result.get("devices", []),
        rooms,
        coverage
    )
    pipeline_result["stages"]["constraint_evaluation"] = constraints_result

    # Stage 7: Confidence Scoring
    confidence = overall_confidence(rooms, engine_result)
    pipeline_result["stages"]["confidence_scoring"] = confidence

    # Stage 8: Final Decision
    if confidence["action"] == "do_not_export":
        pipeline_result["pipeline_passed"] = False
        pipeline_result["decision"] = "LOW_CONFIDENCE"
    elif confidence["action"] == "review_recommended":
        pipeline_result["decision"] = "REVIEW_RECOMMENDED"
    else:
        pipeline_result["decision"] = "EXPORT_READY"

    pipeline_result["devices"] = engine_result.get("devices", [])
    pipeline_result["total_devices"] = len(engine_result.get("devices", []))
    pipeline_result["validation"] = engine_result.get("validation", {})

    return pipeline_result