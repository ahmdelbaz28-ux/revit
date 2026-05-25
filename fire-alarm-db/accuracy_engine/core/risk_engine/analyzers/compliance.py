"""Compliance risk analyzer."""


def compliance_risk(validation_result: dict) -> float:
    """Calculate compliance risk score based on validation results.
    
    Args:
        validation_result: Validation result dictionary
        
    Returns:
        Risk score based on compliance violations (0.0 to 8.0+)
    """
    risk = 0.0

    # Coverage check (NFPA requires 90%)
    coverage = validation_result.get("coverage", 
                    validation_result.get("overall_coverage", 0))
    if coverage < 0.9:
        risk += 3.0

    # Spacing violation check
    if validation_result.get("spacing_violation", False):
        risk += 2.0

    # Critical points uncovered
    if validation_result.get("critical_points_uncovered", False):
        risk += 3.0

    return risk
