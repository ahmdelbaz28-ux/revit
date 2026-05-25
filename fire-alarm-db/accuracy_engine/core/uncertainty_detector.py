from typing import List, Tuple

UNCERTAIN_CASES = [
    "missing_ceiling_height",
    "unknown_room_type",
    "non_closed_polygon",
    "intersecting_rooms",
    "low_resolution_floor_plan",
    "missing_area",
    "invalid_polygon",
    "missing_geometry"
]

# Valid room types
VALID_ROOM_TYPES = ["office", "corridor", "storage", "stair", "meeting", "lobby", "hall", "kitchen", "bathroom", "mechanical", "electrical", "assembly"]

def detect_uncertainty(room: dict) -> List[str]:
    issues = []

    if not room.get("polygon"):
        issues.append("missing_geometry")
    elif len(room.get("polygon", [])) < 3:
        issues.append("invalid_polygon")

    if room.get("area") is None:
        issues.append("missing_area")

    if room.get("height") is None:
        issues.append("missing_ceiling_height")

    room_type = room.get("type")
    if room_type not in VALID_ROOM_TYPES:
        issues.append("unknown_room_type")

    return issues

def is_design_viable(rooms: List[dict]) -> Tuple[bool, dict]:
    all_issues = {}
    viable = True

    for room in rooms:
        issues = detect_uncertainty(room)
        if issues:
            room_id = room.get("id", "unknown")
            all_issues[room_id] = issues
            viable = False

    return viable, all_issues