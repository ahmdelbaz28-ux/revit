from core.risk_graph.risk_types import RiskContribution


def coverage_risk_function(coverage: float, failure_scenario: dict, room: dict) -> RiskContribution:
    prob_violation = 0.0
    if coverage < 0.90:
        prob_violation = (0.90 - coverage) / 0.90

    failed_count = failure_scenario.get("failed_count", 0)
    total_devices = failure_scenario.get("total_devices", 1)
    severity = failed_count / max(total_devices, 1)

    spatial_weight = 0.0
    room_type = room.get("type", "office")
    if room_type in ["electrical", "storage", "mechanical"]:
        spatial_weight = 0.8
    elif room_type in ["corridor", "stair"]:
        spatial_weight = 0.7
    elif room_type in ["office", "meeting"]:
        spatial_weight = 0.4
    else:
        spatial_weight = 0.3

    confidence = 0.85
    if failure_scenario.get("power_failed"):
        confidence = 0.70

    return RiskContribution(
        rule_id="NFPA72-17.6.3.1-COVERAGE",
        probability_violation=prob_violation,
        severity_impact=severity,
        spatial_weight=spatial_weight,
        confidence=confidence
    )


def spacing_risk_function(devices: list, max_spacing: float, room: dict) -> RiskContribution:
    from math import sqrt
    max_distance = 0
    for i, d1 in enumerate(devices):
        for j, d2 in enumerate(devices):
            if j <= i:
                continue
            dist = sqrt((d1.get("x", 0) - d2.get("x", 0))**2 + (d1.get("y", 0) - d2.get("y", 0))**2)
            if dist > max_distance:
                max_distance = dist

    prob_violation = max(0.0, (max_distance - max_spacing) / max_spacing) if max_spacing > 0 else 0
    severity = 0.5 if prob_violation > 0 else 0.0

    room_type = room.get("type", "office")
    spatial_weight = 0.6 if room_type in ["corridor", "open_office"] else 0.3

    return RiskContribution(
        rule_id="NFPA72-17.6.3-SPACING",
        probability_violation=prob_violation,
        severity_impact=severity,
        spatial_weight=spatial_weight,
        confidence=0.90
    )


def redundancy_risk_function(devices: list, room: dict) -> RiskContribution:
    critical_types = ["electrical", "server", "control", "mechanical", "storage"]
    is_critical = room.get("type") in critical_types

    if not is_critical:
        return RiskContribution(
            rule_id="NFPA72-17.7.1-REDUNDANCY",
            probability_violation=0.0,
            severity_impact=0.0,
            spatial_weight=0.0,
            confidence=1.0
        )

    device_count = len(devices)
    prob_violation = 1.0 if device_count < 2 else max(0.0, (2 - device_count) / 2)
    severity = 0.9 if device_count <= 1 else 0.3

    return RiskContribution(
        rule_id="NFPA72-17.7.1-REDUNDANCY",
        probability_violation=prob_violation,
        severity_impact=severity,
        spatial_weight=0.9,
        confidence=0.80
    )