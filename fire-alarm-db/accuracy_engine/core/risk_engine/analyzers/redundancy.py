"""Redundancy risk analyzer."""


def redundancy_risk(room: dict, devices: list) -> float:
    """Calculate redundancy risk score.
    
    Args:
        room: Room configuration dictionary
        devices: List of detection devices in the room
        
    Returns:
        Risk score based on redundancy (0.0 = adequate, 2.0 = no redundancy)
    """
    # Single device = critical failure point
    if len(devices) <= 1:
        return 2.0
    return 0.0
