def coverage_score(covered, total):
    return covered / total if total > 0 else 0


def validate(coverage):
    return {
        "is_valid": coverage >= 0.90,
        "coverage_score": coverage
    }


def check_overlap(devices, min_distance=3.0):
    warnings = []
    from core.placement import distance
    for i, d1 in enumerate(devices):
        for d2 in devices[i+1:]:
            if distance((d1.x, d1.y), (d2.x, d2.y)) < min_distance:
                warnings.append(f"Devices {i} and {i+1} are too close")
    return warnings