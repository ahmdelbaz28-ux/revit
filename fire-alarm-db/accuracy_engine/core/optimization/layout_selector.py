from core.optimization.scoring import layout_score, overlap_penalty
from core.optimization.routing_optimizer import minimum_spanning_tree_length, estimate_cable_cost
from core.optimization.constraints import validate_layout

OPTIMIZATION_MODES = {
    "budget": {"coverage": 0.30, "cost": 0.50, "routing": 0.15, "redundancy": 0.05},
    "safety": {"coverage": 0.60, "cost": 0.10, "routing": 0.10, "redundancy": 0.20},
    "balanced": {"coverage": 0.50, "cost": 0.25, "routing": 0.15, "redundancy": 0.10}
}

def select_best_layout(candidate_layouts: list, mode: str = "balanced") -> dict:
    weights = OPTIMIZATION_MODES.get(mode, OPTIMIZATION_MODES["balanced"])
    best_layout = None
    best_score = float("-inf")

    for layout in candidate_layouts:
        devices = layout.get("devices", [])
        coverage = layout.get("coverage", 0)
        cable_length = minimum_spanning_tree_length(devices)
        penalty = overlap_penalty(devices)

        score = layout_score(coverage, devices, cable_length, weights) - penalty

        if score > best_score:
            best_score = score
            best_layout = layout
            best_layout["score"] = score
            best_layout["cable_length"] = cable_length
            best_layout["mode"] = mode

    if best_layout:
        validation = validate_layout(best_layout.get("devices", []), best_layout.get("coverage", 0))
        best_layout["validation"] = validation
        best_layout["is_valid"] = validation["is_valid"]

    return best_layout