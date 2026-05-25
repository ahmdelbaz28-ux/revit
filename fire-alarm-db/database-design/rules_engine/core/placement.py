import math
from typing import List, Tuple
from core.models import Device
from core.rules.smoke_rules import detectors_required, max_spacing
from core.rules.corridor_rules import is_corridor, is_staircase, is_bathroom, is_mechanical, is_electrical, corridor_spacing, staircase_rule

def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def is_covered(point, devices, radius=7.5):
    for d in devices:
        if distance(point, (d.x, d.y)) <= radius:
            return True
    return False

def generate_grid(polygon, step=5):
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    points = []
    x = min_x
    while x <= max_x:
        y = min_y
        while y <= max_y:
            points.append((x, y))
            y += step
        x += step
    return points

def place_smoke_detectors(room, devices, ceiling_height=3.0):
    grid = generate_grid(room.polygon)
    required = detectors_required(room.area, room.type, ceiling_height)
    spacing = max_spacing(room.type)

    for point in grid:
        if len([d for d in devices if d.type == "smoke"]) >= required:
            break
        if not is_covered(point, devices, spacing/2):
            devices.append(Device("smoke", point[0], point[1]))

    while len([d for d in devices if d.type == "smoke"]) < required:
        grid = generate_grid(room.polygon, step=3)
        for point in grid:
            if len([d for d in devices if d.type == "smoke"]) >= required:
                break
            if not is_covered(point, devices, spacing/3):
                devices.append(Device("smoke", point[0], point[1]))

    return devices

def place_heat_detectors(room, devices):
    grid = generate_grid(room.polygon, step=4)
    for point in grid:
        if not is_covered(point, devices, radius=5.0):
            devices.append(Device("heat", point[0], point[1]))
    return devices

def place_corridor_devices(room, devices):
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    spacing = corridor_spacing()

    if (max_x - min_x) > (max_y - min_y):
        y_center = (min_y + max_y) / 2
        x = min_x + (spacing / 2)
        while x <= max_x:
            if not is_covered((x, y_center), devices):
                devices.append(Device("smoke", x, y_center))
            x += spacing
    else:
        x_center = (min_x + max_x) / 2
        y = min_y + (spacing / 2)
        while y <= max_y:
            if not is_covered((x_center, y), devices):
                devices.append(Device("smoke", x_center, y))
            y += spacing

    return devices

def place_staircase_devices(room, devices):
    rule = staircase_rule()
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    if rule["placement_priority"] == "top_and_bottom":
        devices.append(Device("smoke", (min_x + max_x) / 2, max_y - 0.5))
        devices.append(Device("smoke", (min_x + max_x) / 2, min_y + 0.5))
    else:
        devices.append(Device("smoke", (min_x + max_x) / 2, (min_y + max_y) / 2))

    return devices