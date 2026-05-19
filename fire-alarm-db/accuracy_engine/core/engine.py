from core.placement_engine import place_devices_in_room, place_corridor_devices
from core.validation_engine import validate_all
from core.rules_engine import is_corridor

def run_accuracy_engine(rooms: list) -> dict:
    all_devices = []

    for room in rooms:
        room_type = room.get("type", "office")
        room_area = room.get("area", 0)
        room_polygon = room.get("polygon", [])

        if len(room_polygon) < 3:
            continue

        if is_corridor(room_type):
            devices = place_corridor_devices(room_polygon, all_devices)
        else:
            devices = place_devices_in_room(room_polygon, room_type, room_area, all_devices)

        for d in devices:
            d["room_id"] = room["id"]

        all_devices.extend(devices)

    validation = validate_all(rooms, all_devices)

    return {
        "devices": all_devices,
        "total_devices": len(all_devices),
        "validation": validation
    }