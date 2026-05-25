"""Detector failure mode analyzer (FMEA)."""


def detector_failure_risk(room: dict, devices: list) -> float:
    """Calculate detector failure mode risk using FMEA methodology.
    
    Args:
        room: Room configuration dictionary
        devices: List of detection devices in the room
        
    Returns:
        Risk score based on single-points-of-failure (0.0 to 3.0+)
    """
    if not devices:
        return 0.0
        
    from math import sqrt
    critical_failures = 0

    # Check each device for backup coverage
    for failed in devices:
        has_backup = False
        for d in devices:
            if d == failed:
                continue
            # Check if backup detector is within 7.5m (NFPA spacing)
            dist = sqrt((failed.get("x", 0) - d.get("x", 0))**2 + 
                      (failed.get("y", 0) - d.get("y", 0))**2)
            if dist < 7.5:
                has_backup = True
                break

        if not has_backup:
            critical_failures += 1

    return float(critical_failures) * 1.5
