from shapely.geometry import Polygon
from core.geometry import smart_grid, coverage_radius, distance, create_polygon

def calculate_coverage(room_polygon, devices: list) -> float:
    poly = create_polygon(room_polygon)
    grid = smart_grid(poly, step=2.0)

    if len(grid) == 0:
        return 0.0

    covered = 0
    for point in grid:
        for device in devices:
            radius = coverage_radius(device.get("type", "smoke"))
            if distance(point, (device["x"], device["y"])) <= radius:
                covered += 1
                break

    return covered / len(grid)

def check_overlap(devices: list, min_distance: float = 3.0) -> list:
    warnings = []
    for i, d1 in enumerate(devices):
        for j, d2 in enumerate(devices):
            if j <= i:
                continue
            if distance((d1["x"], d1["y"]), (d2["x"], d2["y"])) < min_distance:
                warnings.append(f"Devices {i} and {j} are too close ({distance((d1['x'], d1['y']), (d2['x'], d2['y'])):.1f}m)")
    return warnings

def validate_all(rooms: list, devices: list) -> dict:
    total_coverage = 0.0
    errors = []
    warnings = []

    for room in rooms:
        if room.get("polygon"):
            cov = calculate_coverage(room["polygon"], devices)
            total_coverage += cov

            if cov < 0.90:
                errors.append(f"Room {room['id']} coverage is {cov:.2%} (required: 90%)")

    if len(rooms) > 0:
        avg_coverage = total_coverage / len(rooms)
    else:
        avg_coverage = 0.0

    overlap_warnings = check_overlap(devices)
    warnings.extend(overlap_warnings)

    for room in rooms:
        room_devices = [d for d in devices if "room_id" in d and d.get("room_id") == room["id"]]
        if len(room_devices) == 0 and len(devices) > 0:
            pass

    return {
        "coverage_score": avg_coverage,
        "is_valid": avg_coverage >= 0.90 and len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }