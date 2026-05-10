from core.models import Device, Zone
from core.placement import place_smoke_detectors, place_heat_detectors, place_corridor_devices, generate_grid, is_covered
from core.rules.validation_rules import coverage_score, check_overlap
from core.rules.corridor_rules import is_corridor, is_staircase


def run_fire_alarm_engine(rooms):
    devices = []
    zones = []

    for room in rooms:
        room_type = room.get("type", "office")

        if room_type in ["office", "meeting", "lobby", "hall"]:
            room_obj = type('Room', (), {
                'id': room['id'],
                'type': room_type,
                'area': room.get('area', 0),
                'polygon': room.get('polygon', [])
            })
            if room.get('polygon'):
                devices = place_smoke_detectors(room_obj, devices)

        if room_type == "corridor":
            room_obj = type('Room', (), {
                'id': room['id'],
                'type': 'corridor',
                'area': room.get('area', 0),
                'polygon': room.get('polygon', [])
            })
            if room.get('polygon'):
                devices = place_corridor_devices(room_obj, devices)

        if room_type in ["storage", "kitchen", "bathroom"]:
            room_obj = type('Room', (), {
                'id': room['id'],
                'type': room_type,
                'area': room.get('area', 0),
                'polygon': room.get('polygon', [])
            })
            if room.get('polygon'):
                devices = place_heat_detectors(room_obj, devices)

        if is_staircase(room_type):
            room_obj = type('Room', (), {
                'id': room['id'],
                'type': 'stair',
                'area': room.get('area', 0),
                'polygon': room.get('polygon', [])
            })
            if room.get('polygon'):
                devices = place_smoke_detectors(room_obj, devices)

        zones.append({
            "id": f"zone_{room['id']}",
            "room_ids": [room['id']]
        })

    total_points = 0
    covered_points = 0

    for room in rooms:
        if room.get('polygon'):
            room_obj = type('Room', (), {'polygon': room['polygon']})
            grid = generate_grid(room_obj.polygon)
            total_points += len(grid)

            for p in grid:
                if is_covered(p, devices):
                    covered_points += 1

    coverage = coverage_score(covered_points, total_points)
    warnings = check_overlap(devices)
    errors = []

    if coverage < 0.90:
        errors.append(f"Coverage {coverage:.2f} is below 90%")

    return {
        "devices": [{"type": d.type, "x": d.x, "y": d.y} for d in devices],
        "zones": zones,
        "validation": {
            "coverage_score": coverage,
            "is_valid": coverage >= 0.90,
            "warnings": warnings,
            "errors": errors
        }
    }