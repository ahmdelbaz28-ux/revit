from math import sqrt

def point_coverage(covered: int, total: int) -> float:
    return covered / total if total > 0 else 0.0

def edge_coverage(edge_points_covered: int, total_edge_points: int) -> float:
    return edge_points_covered / total_edge_points if total_edge_points > 0 else 0.0

def critical_point_coverage(critical_covered: int, total_critical: int) -> float:
    return critical_covered / total_critical if total_critical > 0 else 0.0

def overall_coverage(point_cov: float, edge_cov: float, critical_cov: float) -> float:
    return (point_cov * 0.5) + (edge_cov * 0.3) + (critical_cov * 0.2)

def validate_full(point_cov: float, edge_cov: float, critical_cov: float) -> dict:
    overall = overall_coverage(point_cov, edge_cov, critical_cov)
    return {
        "is_valid": overall >= 0.90 and critical_cov >= 1.0,
        "point_coverage": point_cov,
        "edge_coverage": edge_cov,
        "critical_coverage": critical_cov,
        "overall_coverage": overall
    }

def check_overlap(devices: list, min_distance: float = 3.0) -> list:
    warnings = []
    for i, d1 in enumerate(devices):
        for j, d2 in enumerate(devices):
            if j <= i:
                continue
            dist = sqrt((d1["x"] - d2["x"])**2 + (d1["y"] - d2["y"])**2)
            if dist < min_distance:
                warnings.append(f"Devices {i} and {j} too close: {dist:.1f}m")
    return warnings

def generate_edge_points(polygon: list, step: float = 2.0) -> list:
    points = []
    for i in range(len(polygon)):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % len(polygon)]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = sqrt(dx**2 + dy**2)
        if length == 0:
            continue
        num_steps = int(length / step)
        for j in range(num_steps + 1):
            t = j / max(num_steps, 1)
            points.append((p1[0] + t * dx, p1[1] + t * dy))
    return points

def get_critical_points(polygon: list) -> list:
    return polygon[:4] if len(polygon) >= 4 else polygon[:]