"""Occupancy-based risk analyzer."""


def occupancy_risk(room: dict) -> float:
    """Calculate occupancy-based risk score.
    
    Args:
        room: Room configuration dictionary
        
    Returns:
        Risk score based on occupancy factors (0.0 to 3.0+)
    """
    score = 0.0

    # Occupancy type risk factors
    occupancy_factors = {
        "office": 1.0,
        "corridor": 1.2,
        "storage": 1.5,
        "electrical": 1.8,
        "assembly": 2.0,
        "mechanical": 1.5,
        "lobby": 1.3,
        "meeting": 1.1
    }

    score += occupancy_factors.get(room.get("type", "office"), 1.0)

    # Area-based risk
    if room.get("area", 0) > 150:
        score += 0.5

    # Occupancy load risk
    if room.get("occupancy_load", 0) > 50:
        score += 0.5

    return score
