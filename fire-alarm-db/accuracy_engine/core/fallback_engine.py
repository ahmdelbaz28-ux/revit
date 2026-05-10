from typing import List, Dict

def fallback_strategy(room: dict, level: int) -> List[Dict]:
    if level == 1:
        return advanced_placement(room)
    elif level == 2:
        return simplified_grid(room)
    else:
        return manual_review(room)

def advanced_placement(room: dict) -> List[Dict]:
    from core.placement_engine import place_devices_in_room, place_corridor_devices
    if room.get("type") == "corridor":
        return place_corridor_devices(room.get("polygon", []), [])
    return place_devices_in_room(room.get("polygon", []), room.get("type", "office"), room.get("area", 0), [])

def simplified_grid(room: dict) -> List[Dict]:
    devices = []
    polygon = room.get("polygon", [])
    if not polygon:
        return devices

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    x = min_x + 3
    while x <= max_x - 3:
        y = min_y + 3
        while y <= max_y - 3:
            devices.append({
                "type": "smoke",
                "x": x,
                "y": y,
                "room_id": room.get("id")
            })
            y += 7.5
        x += 7.5

    return devices

def manual_review(room: dict) -> List[Dict]:
    return [{
        "status": "requires_manual_review",
        "room_id": room.get("id"),
        "reason": "Room cannot be designed automatically. Human input required."
    }]