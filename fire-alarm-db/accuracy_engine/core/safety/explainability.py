def explain_placement(device: dict, room: dict, coverage_before: float, coverage_after: float) -> dict:
    reasons = []

    if coverage_before < 0.90:
        reasons.append("coverage_gap_detected")

    room_type = room.get("type")
    if room_type in ["storage", "electrical", "mechanical"]:
        reasons.append("high_risk_room")

    area = room.get("area", 0)
    if area > 200:
        reasons.append("large_area_requires_coverage")

    return {
        "device_id": device.get("device_id", "unknown"),
        "placement_reason": reasons,
        "coverage_improvement": coverage_after - coverage_before,
        "position": (device.get("x"), device.get("y"))
    }

def explain_failure(failure: dict) -> str:
    severity = failure.get("severity", "unknown")
    device = failure.get("failed_device_position", "unknown")
    coverage = failure.get("coverage_after_failure", 0)

    if severity == "high":
        return f"CRITICAL: If device at {device} fails, coverage drops below 70%. Redundancy required."
    elif severity == "medium":
        return f"WARNING: If device at {device} fails, coverage drops to {coverage:.0%}."
    return f"OK: Failure of device at {device} has limited impact."