from math import ceil

def base_density_heat(room_type: str) -> float:
    return {
        "storage": 40.0,
        "kitchen": 40.0,
        "bathroom": 40.0,
        "mechanical": 35.0,
        "electrical": 45.0
    }.get(room_type, 45.0)

def heat_detectors_required(area: float, room_type: str) -> int:
    density = base_density_heat(room_type)
    return max(1, ceil(area / density))