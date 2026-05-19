def multi_factor_confidence(geometry_valid: bool, coverage: float, compliance_passed: bool, uncertainty_issues: list) -> dict:
    geometry_conf = 1.0 if geometry_valid else 0.5

    if coverage >= 0.95:
        coverage_conf = 1.0
    elif coverage >= 0.90:
        coverage_conf = 0.9
    elif coverage >= 0.80:
        coverage_conf = 0.7
    else:
        coverage_conf = 0.4

    compliance_conf = 1.0 if compliance_passed else 0.6

    uncertainty_conf = 1.0 if not uncertainty_issues else max(0.3, 1.0 - len(uncertainty_issues) * 0.2)

    overall = geometry_conf * coverage_conf * compliance_conf * uncertainty_conf

    if overall >= 0.85:
        level = "HIGH_CONFIDENCE"
        action = "export_ready"
    elif overall >= 0.60:
        level = "MEDIUM_CONFIDENCE"
        action = "review_recommended"
    else:
        level = "LOW_CONFIDENCE"
        action = "manual_engineering_review_required"

    return {
        "overall_confidence": overall,
        "level": level,
        "action": action,
        "factors": {
            "geometry_confidence": geometry_conf,
            "coverage_confidence": coverage_conf,
            "compliance_confidence": compliance_conf,
            "uncertainty_confidence": uncertainty_conf
        }
    }