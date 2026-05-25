from typing import Tuple
from core.geometry_validator import check_rooms_overlap

def handle_narrow_corridor(room: dict, spacing: float) -> float:
    polygon = room.get("polygon", [])
    if not polygon:
        return spacing
    
    ys = [p[1] for p in polygon]
    min_y = min(ys)
    max_y = max(ys)
    actual_width = max_y - min_y

    if actual_width < 2.0:
        return spacing * 0.7
    return spacing

def handle_large_open_space(room: dict, base_spacing: float) -> float:
    area = room.get("area", 0)
    if area > 500:
        return base_spacing * 0.8
    return base_spacing

def handle_irregular_polygon(room: dict) -> str:
    polygon = room.get("polygon", [])
    if len(polygon) > 8:
        return "subdivision"
    return "grid"

def handle_overlapping_rooms(rooms: list) -> dict:
    overlaps = check_rooms_overlap(rooms)
    if overlaps:
        return {"action": "merge_zones", "rooms": overlaps}
    return {"action": "standard"}