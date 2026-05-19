from typing import List
from core.risk_tensor.tensor_types import RiskTensor, CompositeRiskIndex


def aggregate_tensors(tensors: List[RiskTensor]) -> CompositeRiskIndex:
    if not tensors:
        return CompositeRiskIndex(
            scalar=0.0,
            risk_level="LOW",
            confidence_interval=(0.0, 0.0),
            contributing_dimensions={},
            spatial_heatmap=[],
            explainability=["No risk tensors to aggregate"]
        )

    n = len(tensors)

    e_failure_prob = sum(t.failure_probability for t in tensors) / n
    e_coverage_loss = sum(t.impact_vector.coverage_loss for t in tensors) / n
    e_detection_delay = sum(t.impact_vector.detection_delay_seconds for t in tensors) / n
    e_evacuation_risk = sum(t.impact_vector.evacuation_risk_increase for t in tensors) / n
    e_redundancy_loss = sum(t.impact_vector.redundancy_loss for t in tensors) / n
    e_confidence = sum(t.confidence for t in tensors) / n

    var_failure = sum((t.failure_probability - e_failure_prob)**2 for t in tensors) / n
    var_coverage = sum((t.impact_vector.coverage_loss - e_coverage_loss)**2 for t in tensors) / n

    correlation_factor = 0.0
    for t in tensors:
        correlation_factor += (t.failure_probability - e_failure_prob) * (t.impact_vector.coverage_loss - e_coverage_loss)
    correlation_factor = correlation_factor / n if n > 0 else 0

    w_failure = 0.25
    w_impact = 0.35
    w_spatial = 0.25
    w_confidence = 0.15

    scalar = (
        w_failure * e_failure_prob +
        w_impact * (e_coverage_loss * 0.5 + e_evacuation_risk * 0.3 + e_redundancy_loss * 0.2) +
        w_spatial * min(1.0, (var_failure + var_coverage) * 5.0) +
        w_confidence * (1 - e_confidence)
    )

    ci_half_width = 1.96 * ((var_failure**0.5) / (n**0.5)) if n > 0 else 0
    ci_lower = max(0.0, scalar - ci_half_width)
    ci_upper = min(1.0, scalar + ci_half_width)

    if scalar >= 0.7:
        risk_level = "CRITICAL"
    elif scalar >= 0.4:
        risk_level = "HIGH"
    elif scalar >= 0.2:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    heatmap = {}
    for t in tensors:
        for sp in t.spatial_map:
            key = f"{sp.zone_id}_{sp.x}_{sp.y}"
            if key not in heatmap:
                heatmap[key] = {"x": sp.x, "y": sp.y, "intensity": 0.0, "count": 0, "zone_id": sp.zone_id}
            heatmap[key]["intensity"] += sp.risk_intensity
            heatmap[key]["count"] += 1

    spatial_heatmap = []
    for entry in heatmap.values():
        spatial_heatmap.append({
            "x": entry["x"],
            "y": entry["y"],
            "zone_id": entry["zone_id"],
            "risk_intensity": round(entry["intensity"] / entry["count"], 3) if entry["count"] > 0 else 0.0
        })

    explainability = [
        f"Expected failure probability: {e_failure_prob:.1%}",
        f"Expected coverage loss: {e_coverage_loss:.1%}",
        f"Detection delay impact: {e_detection_delay:.1f}s",
        f"Evacuation risk factor: {e_evacuation_risk:.1%}",
        f"Model confidence: {e_confidence:.1%}",
        f"Correlation factor (failure↔coverage): {correlation_factor:.3f}",
        f"Variance in failure probability: {var_failure:.4f}",
        f"Confidence interval: [{ci_lower:.1%}, {ci_upper:.1%}]"
    ]

    return CompositeRiskIndex(
        scalar=round(scalar, 4),
        risk_level=risk_level,
        confidence_interval=(round(ci_lower, 4), round(ci_upper, 4)),
        contributing_dimensions={
            "failure_probability": round(e_failure_prob, 4),
            "coverage_loss": round(e_coverage_loss, 4),
            "detection_delay_seconds": round(e_detection_delay, 2),
            "evacuation_risk": round(e_evacuation_risk, 4),
            "redundancy_loss": round(e_redundancy_loss, 4),
            "model_confidence": round(e_confidence, 4)
        },
        spatial_heatmap=spatial_heatmap,
        explainability=explainability
    )