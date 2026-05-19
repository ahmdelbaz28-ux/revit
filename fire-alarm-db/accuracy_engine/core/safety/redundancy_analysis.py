from math import sqrt

CRITICAL_ROOM_TYPES = ["electrical", "server", "control", "mechanical", "storage"]

def coverage_radius(device_type: str) -> float:
    return {"smoke": 7.5, "heat": 6.0}.get(device_type, 7.5)

def distance(p1, p2):
    return sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def requires_redundancy(room: dict) -> bool:
    if room.get("type") in CRITICAL_ROOM_TYPES:
        return True
    if room.get("area", 0) > 200:
        return True
    return False

def redundancy_level(room: dict) -> str:
    if not requires_redundancy(room):
        return "standard"

    room_type = room.get("type")
    if room_type in ["electrical", "server", "control"]:
        return "critical_redundancy"
    if room.get("area", 0) > 200:
        return "high_redundancy"

    return "moderate_redundancy"

def check_overlap_coverage(room: dict, devices: list) -> dict:
    polygon = room.get("polygon", [])
    if not polygon or len(polygon) < 3:
        return {"overlap_percentage": 0, "redundancy_adequate": False}

    # Generate sample grid
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
            grid.append((x, y))
            y += step
        x += step

    total = len(grid)
    if total == 0:
        return {"overlap_percentage": 0, "redundancy_adequate": False}

    covered_by_multiple = 0
    for point in grid:
        detectors_covering = 0
        for d in devices:
            radius = coverage_radius(d.get("type", "smoke"))
            if distance(point, (d["x"], d["y"])) <= radius:
                detectors_covering += 1
        if detectors_covering >= 2:
            covered_by_multiple += 1

    overlap_pct = covered_by_multiple / total
    return {
        "overlap_percentage": overlap_pct,
        "redundancy_adequate": overlap_pct >= 0.30
    }