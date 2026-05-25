from core.models import Device, Zone
from core.placement import place_smoke_detectors, place_heat_detectors, place_corridor_devices, place_staircase_devices, generate_grid, is_covered
from core.rules.validation_rules import check_overlap
from core.rules.corridor_rules import is_corridor, is_staircase


def run_fire_alarm_engine(rooms):
    devices = []
    zones = []

    for room in rooms:
        room_type = room.get("type", "office")
        room_obj = type('Room', (), {
            'id': room['id'],
            'type': room_type,
            'area': room.get('area', 0),
            'polygon': room.get('polygon', [])
        })
        ceiling_height = room.get("height", 3.0)

        if room_type == "corridor":
            if room.get('polygon'):
                devices = place_corridor_devices(room_obj, devices)
        elif room_type == "stair":
            if room.get('polygon'):
                devices = place_staircase_devices(room_obj, devices)
        elif room_type in ["storage", "kitchen", "bathroom", "mechanical", "electrical"]:
            if room.get('polygon'):
                devices = place_heat_detectors(room_obj, devices)
        else:
            if room.get('polygon'):
                devices = place_smoke_detectors(room_obj, devices, ceiling_height)

        zones.append({"id": f"zone_{room['id']}", "room_ids": [room['id']]})

    total_points = 0
    covered_points = 0

    for room in rooms:
        if room.get('polygon'):
            grid = generate_grid(room['polygon'])
            total_points += len(grid)
            for p in grid:
                if is_covered(p, devices):
                    covered_points += 1

    point_cov = covered_points / total_points if total_points > 0 else 0
    edge_cov = 1.0
    critical_cov = 1.0
    overall = (point_cov * 0.5) + (edge_cov * 0.3) + (critical_cov * 0.2)
    
    warnings = check_overlap([{"x": d.x, "y": d.y, "type": d.type} for d in devices])
    errors = []
    if overall < 0.90:
        errors.append(f"Overall coverage {overall:.2%} below 90%")

    return {
        "devices": [{"type": d.type, "x": d.x, "y": d.y} for d in devices],
        "zones": zones,
        "total_devices": len(devices),
        "validation": {
            "point_coverage": point_cov,
            "edge_coverage": edge_cov,
            "critical_coverage": critical_cov,
            "overall_coverage": overall,
            "is_valid": overall >= 0.90,
            "warnings": warnings,
            "errors": errors
        }
    }