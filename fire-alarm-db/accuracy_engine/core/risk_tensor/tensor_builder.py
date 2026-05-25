from core.risk_tensor.tensor_types import RiskTensor, ImpactVector, SpatialPoint


def build_risk_tensor(
    scenario_id: int,
    room: dict,
    devices: list,
    failure_scenario: dict,
    coverage_after_failure: float,
    base_coverage: float
) -> RiskTensor:
    coverage_loss = max(0.0, base_coverage - coverage_after_failure)
    detection_delay = coverage_loss * 30.0

    exit_blocked = failure_scenario.get("exit_blocked", False)
    evacuation_risk = 0.6 if exit_blocked else coverage_loss * 0.8

    failed_count = failure_scenario.get("failed_count", 0)
    total_devices = failure_scenario.get("total_devices", 1)
    redundancy_loss = failed_count / max(total_devices, 1)

    impact = ImpactVector(
        coverage_loss=coverage_loss,
        detection_delay_seconds=detection_delay,
        evacuation_risk_increase=evacuation_risk,
        redundancy_loss=redundancy_loss
    )

    polygon = room.get("polygon", [])
    spatial_map = []
    if polygon and len(polygon) >= 4:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        step_x = (max_x - min_x) / 5
        step_y = (max_y - min_y) / 5

        for i in range(6):
            for j in range(6):
                x = min_x + i * step_x
                y = min_y + j * step_y

                intensity = coverage_loss
                center_x = (min_x + max_x) / 2
                center_y = (min_y + max_y) / 2
                dist_from_center = ((x - center_x)**2 + (y - center_y)**2) ** 0.5
                max_dist = ((max_x - min_x)**2 + (max_y - min_y)**2) ** 0.5 / 2
                if max_dist > 0:
                    intensity += 0.1 * (1 - dist_from_center / max_dist)

                spatial_map.append(SpatialPoint(
                    x=round(x, 2),
                    y=round(y, 2),
                    risk_intensity=round(min(1.0, intensity), 3),
                    zone_id=room.get("id", "unknown")
                ))

    failure_prob = failure_scenario.get("failed_count", 0) / max(failure_scenario.get("total_devices", 1), 1)

    room_type = room.get("type", "office")
    confidence = 0.85
    if failure_scenario.get("power_failed"):
        confidence -= 0.10
    if room_type in ["electrical", "storage"]:
        confidence -= 0.05
    confidence = max(0.5, confidence)

    affected_zones = [room.get("id", "unknown")]
    contributing_rules = ["NFPA72-17.6.3.1-COVERAGE"]
    if failure_scenario.get("failed_count", 0) >= 2:
        contributing_rules.append("NFPA72-17.7.1-REDUNDANCY")

    return RiskTensor(
        scenario_id=scenario_id,
        failure_probability=failure_prob,
        impact_vector=impact,
        spatial_map=spatial_map,
        confidence=confidence,
        affected_zones=affected_zones,
        contributing_rules=contributing_rules
    )