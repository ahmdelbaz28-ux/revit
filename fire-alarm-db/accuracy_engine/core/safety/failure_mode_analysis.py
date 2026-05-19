from math import sqrt

def coverage_radius(device_type: str) -> float:
    return {"smoke": 7.5, "heat": 6.0}.get(device_type, 7.5)

def distance(p1, p2):
    return sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def detector_failure_impact(room: dict, devices: list) -> list:
    impacts = []
    polygon = room.get("polygon", [])
    if not polygon or len(polygon) < 3:
        return impacts

    # Generate sample grid for coverage calculation
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    grid = []
    step = 2.0
    x = min_x
    while x <= max_x:
        y = min_y
        while y <= max_y:
            # Simple point in polygon check using bounds
            grid.append((x, y))
            y += step
        x += step
    
    total_points = len(grid)
    if total_points == 0:
        return impacts

    for i, failed_device in enumerate(devices):
        remaining_devices = [d for j, d in enumerate(devices) if j != i]

        covered = 0
        for point in grid:
            for rd in remaining_devices:
                radius = coverage_radius(rd.get("type", "smoke"))
                if distance(point, (rd["x"], rd["y"])) <= radius:
                    covered += 1
                    break

        if total_points > 0:
            coverage_after_failure = covered / total_points
        else:
            coverage_after_failure = 0

        severity = "low"
        if coverage_after_failure < 0.70:
            severity = "high"
        elif coverage_after_failure < 0.85:
            severity = "medium"

        impacts.append({
            "failed_device_index": i,
            "failed_device_position": (failed_device.get("x"), failed_device.get("y")),
            "coverage_after_failure": coverage_after_failure,
            "severity": severity,
            "single_point_of_failure": coverage_after_failure < 0.70
        })

    return impacts

def cable_failure_impact(devices: list) -> dict:
    if len(devices) <= 2:
        return {"risk": "high", "reason": "insufficient_redundancy"}

    return {"risk": "medium", "reason": "multiple_paths_exist"}

def power_loss_impact() -> dict:
    return {
        "risk": "critical",
        "mitigation": "battery_backup_required",
        "duration_hours": 24
    }