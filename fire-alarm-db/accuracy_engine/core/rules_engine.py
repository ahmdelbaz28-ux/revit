from math import ceil

def detector_density(room_type: str) -> float:
    densities = {
        "storage": 40.0,
        "kitchen": 40.0,
        "bathroom": 40.0,
        "corridor": 50.0,
        "office": 60.0,
        "meeting": 60.0,
        "lobby": 60.0,
        "hall": 60.0,
        "stair": 60.0
    }
    return densities.get(room_type, 55.0)

def detectors_required(area: float, room_type: str) -> int:
    density = detector_density(room_type)
    return max(1, ceil(area / density))

def device_type_for_room(room_type: str) -> str:
    if room_type in ["storage", "kitchen", "bathroom"]:
        return "heat"
    return "smoke"

def is_corridor(room_type: str) -> bool:
    return room_type == "corridor"

def is_staircase(room_type: str) -> bool:
    return room_type == "stair"