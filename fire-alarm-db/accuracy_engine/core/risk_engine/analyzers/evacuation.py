"""Evacuation risk analyzer."""


def evacuation_risk(room: dict) -> float:
    """Calculate evacuation risk score.
    
    Args:
        room: Room configuration dictionary
        
    Returns:
        Risk score based on evacuation factors (0.0 to 5.0+)
    """
    score = 0.0

    # Exit count factor
    exits = room.get("exit_count", 1)
    if exits < 2:
        score += 2.0

    # Corridor width factor
    width = room.get("corridor_width", room.get("width", 1.2))
    if width < 1.5:
        score += 1.0

    # Travel distance factor
    distance = room.get("travel_distance", 20)
    if distance > 30:
        score += 2.0

    return score
