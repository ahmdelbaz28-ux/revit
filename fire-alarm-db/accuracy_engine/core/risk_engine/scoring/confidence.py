"""Multi-factor confidence scoring."""


def confidence_score(room: dict, validation: dict) -> float:
    """Calculate confidence score based on multiple factors.
    
    Args:
        room: Room configuration dictionary
        validation: Validation result dictionary
        
    Returns:
        Confidence score from 0.0 to 1.0
    """
    confidence = 1.0

    # Coverage confidence
    coverage = validation.get("coverage", validation.get("overall_coverage", 0))
    if coverage < 0.95:
        confidence -= 0.2

    # Spacing confidence
    if validation.get("spacing_violation", False):
        confidence -= 0.2

    # Critical points confidence
    if validation.get("critical_points_uncovered", False):
        confidence -= 0.3

    # Large room confidence
    if room.get("area", 0) > 500:
        confidence -= 0.1

    return max(confidence, 0.0)
