"""Risk matrix classification."""


def classify_risk(score: float) -> str:
    """Classify risk level based on total score.
    
    Args:
        score: Total risk score from all analyzers
        
    Returns:
        Risk level: LOW, MEDIUM, HIGH, or CRITICAL
    """
    if score >= 8.0:
        return "CRITICAL"
    if score >= 5.0:
        return "HIGH"
    if score >= 3.0:
        return "MEDIUM"
    return "LOW"
