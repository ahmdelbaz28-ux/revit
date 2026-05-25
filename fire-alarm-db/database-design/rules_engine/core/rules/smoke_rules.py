from math import ceil

def base_density(room_type: str) -> float:
    return {
        "office": 60.0,
        "corridor": 50.0,
        "storage": 40.0,
        "mechanical": 35.0,
        "electrical": 45.0,
        "lobby": 55.0,
        "meeting": 60.0,
        "hall": 60.0,
        "bathroom": 40.0,
        "kitchen": 40.0,
        "stair": 60.0
    }.get(room_type, 55.0)

def risk_multiplier(room_type: str, area: float) -> float:
    factor = 1.0
    if area > 100.0:
        factor += 0.15
    if room_type in ["storage", "mechanical"]:
        factor += 0.25
    if room_type == "electrical":
        factor += 0.20
    return factor

def occupancy_risk(room_type: str) -> float:
    return {
        "assembly": 1.5,
        "storage": 1.4,
        "corridor": 1.2,
        "meeting": 1.1,
        "lobby": 1.2
    }.get(room_type, 1.0)

def height_factor(ceiling_height: float) -> float:
    if ceiling_height <= 3.0:
        return 1.0
    if ceiling_height <= 6.0:
        return 1.2
    if ceiling_height <= 10.0:
        return 1.5
    return 1.8

def final_density(room_type: str, area: float, ceiling_height: float) -> float:
    base = base_density(room_type)
    risk = risk_multiplier(room_type, area)
    occupancy = occupancy_risk(room_type)
    height = height_factor(ceiling_height)
    adjusted = base / (risk * occupancy * height)
    return max(10.0, min(adjusted, 80.0))

def detectors_required(area: float, room_type: str, ceiling_height: float = 3.0) -> int:
    density = final_density(room_type, area, ceiling_height)
    return max(1, ceil(area / density))

def spacing_limit(room_type: str) -> float:
    return {
        "corridor": 7.0,
        "office": 7.5,
        "storage": 6.0,
        "mechanical": 6.5,
        "electrical": 6.0,
        "bathroom": 6.0,
        "kitchen": 6.0
    }.get(room_type, 7.5)

def overlap_ratio() -> float:
    return 0.15

def max_spacing(room_type: str) -> float:
    return spacing_limit(room_type) * 2 * (1 - overlap_ratio())