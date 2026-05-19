def is_corridor(room_type: str) -> bool:
    return room_type == "corridor"

def is_staircase(room_type: str) -> bool:
    return room_type == "stair"

def is_bathroom(room_type: str) -> bool:
    return room_type == "bathroom"

def is_mechanical(room_type: str) -> bool:
    return room_type == "mechanical"

def is_electrical(room_type: str) -> bool:
    return room_type == "electrical"

def corridor_spacing() -> float:
    return 7.0

def staircase_rule() -> dict:
    return {
        "min_devices": 1,
        "mandatory_smoke": True,
        "placement_priority": "top_and_bottom"
    }

def bathroom_rule() -> dict:
    return {
        "allowed_devices": ["heat"],
        "no_smoke": True
    }

def mechanical_room_rule() -> dict:
    return {
        "allowed_devices": ["heat", "smoke"],
        "preferred": "heat",
        "ceiling_check_required": True
    }