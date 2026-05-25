from shapely.geometry import Polygon, Point
from core.geometry import smart_grid, coverage_radius, distance, create_polygon
from core.rules_engine import device_type_for_room, is_corridor, is_staircase, detectors_required

def place_devices_in_room(room_polygon, room_type: str, room_area: float, existing_devices: list, step: float = 5.0) -> list:
    poly = create_polygon(room_polygon)
    required = detectors_required(room_area, room_type)
    device_type = device_type_for_room(room_type)
    radius = coverage_radius(device_type)
    grid = smart_grid(poly, step)
    devices_placed = []

    for point in grid:
        if len(devices_placed) >= required:
            break
        is_covered = False
        for d in existing_devices + devices_placed:
            if distance(point, (d["x"], d["y"])) <= radius:
                is_covered = True
                break
        if not is_covered:
            devices_placed.append({"type": device_type, "x": point[0], "y": point[1]})

    if is_staircase(room_type) and len(devices_placed) == 0:
        center = poly.centroid
        devices_placed.append({"type": "smoke", "x": center.x, "y": center.y})

    return devices_placed

def place_corridor_devices(room_polygon, existing_devices: list) -> list:
    poly = create_polygon(room_polygon)
    minx, miny, maxx, maxy = poly.bounds
    devices_placed = []

    if (maxx - minx) > (maxy - miny):
        y_center = (miny + maxy) / 2
        x = minx + 3.75
        while x <= maxx:
            point = (x, y_center)
            if poly.contains(Point(point)):
                is_covered = False
                for d in existing_devices + devices_placed:
                    if distance(point, (d["x"], d["y"])) <= 7.5:
                        is_covered = True
                        break
                if not is_covered:
                    devices_placed.append({"type": "smoke", "x": point[0], "y": point[1]})
            x += 7.5
    else:
        x_center = (minx + maxx) / 2
        y = miny + 3.75
        while y <= maxy:
            point = (x_center, y)
            if poly.contains(Point(point)):
                is_covered = False
                for d in existing_devices + devices_placed:
                    if distance(point, (d["x"], d["y"])) <= 7.5:
                        is_covered = True
                        break
                if not is_covered:
                    devices_placed.append({"type": "smoke", "x": point[0], "y": point[1]})
            y += 7.5

    return devices_placed