"""Fire load risk analyzer."""


def fire_load_risk(room: dict) -> float:
    """Calculate fire load risk score.
    
    Args:
        room: Room configuration dictionary
        
    Returns:
        Risk score based on fire load factors (1.0 to 4.0+)
    """
    risk = 1.0

    # Room type fire load factors
    if room.get("type") == "storage":
        risk += 1.0

    if room.get("type") == "electrical":
        risk += 1.5

    if room.get("type") == "mechanical":
        risk += 0.8

    # Ceiling height factor
    if room.get("height", 3.0) > 6:
        risk += 0.5

    # Area factor
    if room.get("area", 0) > 200:
        risk += 0.5

    return risk
