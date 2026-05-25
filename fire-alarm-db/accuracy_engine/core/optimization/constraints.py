from math import sqrt

MAX_SPACING = 15.0
MIN_COVERAGE = 0.90

def check_spacing_constraint(devices: list, max_spacing: float = MAX_SPACING) -> bool:
    for i, d1 in enumerate(devices):
        for j, d2 in enumerate(devices):
            if j <= i:
                continue
            dist = sqrt((d1["x"] - d2["x"])**2 + (d1["y"] - d2["y"])**2)
            if dist > max_spacing:
                return False
    return True

def check_coverage_constraint(coverage: float, min_coverage: float = MIN_COVERAGE) -> bool:
    return coverage >= min_coverage

def check_critical_points_covered(critical_points: list, devices: list, radius: float = 7.5) -> bool:
    for cp in critical_points:
        covered = False
        for d in devices:
            dist = sqrt((cp[0] - d["x"])**2 + (cp[1] - d["y"])**2)
            if dist <= radius:
                covered = True
                break
        if not covered:
            return False
    return True

def validate_layout(devices: list, coverage: float, critical_points: list = None) -> dict:
    spacing_ok = check_spacing_constraint(devices)
    coverage_ok = check_coverage_constraint(coverage)
    critical_ok = check_critical_points_covered(critical_points or [], devices)

    return {
        "is_valid": spacing_ok and coverage_ok and critical_ok,
        "spacing_ok": spacing_ok,
        "coverage_ok": coverage_ok,
        "critical_points_ok": critical_ok
    }