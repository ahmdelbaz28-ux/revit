from core.risk_graph.risk_types import RiskContribution, RiskExposure
from core.risk_graph.risk_functions import coverage_risk_function, spacing_risk_function, redundancy_risk_function
from core.risk_graph.normalization import normalize_risks
from core.risk_graph.risk_exposure import calculate_risk_exposure
from core.monte_carlo.scenario_generator import generate_scenario


def run_risk_graph(rooms: list, devices: list, validation: dict, num_scenarios: int = 100) -> dict:
    all_exposures = []

    for _ in range(num_scenarios):
        for room in rooms:
            room_devices = [d for d in devices if d.get("room_id") == room.get("id")]
            scenario = generate_scenario(room_devices, room)

            coverage = validation.get("coverage", validation.get("overall_coverage", 0.95))
            if scenario.get("failed_count", 0) > 0:
                survival_ratio = (len(room_devices) - scenario["failed_count"]) / max(len(room_devices), 1)
                coverage = coverage * survival_ratio

            contributions = [
                coverage_risk_function(coverage, scenario, room),
                spacing_risk_function(room_devices, 15.0, room),
                redundancy_risk_function(room_devices, room)
            ]

            normalized = normalize_risks(contributions)

            exposure = calculate_risk_exposure(
                room.get("id", "unknown"),
                room.get("name", room.get("id", "unknown")),
                normalized,
                scenario
            )

            all_exposures.append(exposure)

    if not all_exposures:
        return {"risk_map": [], "summary": {}}

    avg_composite = sum(e.composite_index for e in all_exposures) / len(all_exposures)
    max_composite = max(e.composite_index for e in all_exposures)
    critical_zones = len([e for e in all_exposures if e.risk_level == "CRITICAL"])
    high_zones = len([e for e in all_exposures if e.risk_level == "HIGH"])

    risk_map = []
    seen_zones = set()
    for e in all_exposures:
        if e.zone_id not in seen_zones:
            seen_zones.add(e.zone_id)
            risk_map.append({
                "zone_id": e.zone_id,
                "zone_name": e.zone_name,
                "base_risk": e.base_risk,
                "conditional_risk": e.conditional_risk,
                "composite_index": e.composite_index,
                "risk_level": e.risk_level,
                "confidence": e.confidence,
                "contributing_rules": e.contributing_rules
            })

    return {
        "risk_map": risk_map,
        "summary": {
            "scenarios_evaluated": num_scenarios,
            "average_composite_risk": avg_composite,
            "maximum_composite_risk": max_composite,
            "critical_zones": critical_zones,
            "high_risk_zones": high_zones,
            "overall_risk_level": "CRITICAL" if critical_zones > 0 else ("HIGH" if high_zones > 0 else "MANAGEABLE")
        }
    }