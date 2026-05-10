import math
from typing import List, Tuple
from core.models import Device

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


def place_smoke_detectors(room, devices):
    grid = generate_grid(room.polygon)

    for point in grid:
        if not is_covered(point, devices):
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

    if (max_x - min_x) > (max_y - min_y):
        y_center = (min_y + max_y) / 2
        x = min_x + 3.75
        while x <= max_x:
            if not is_covered((x, y_center), devices):
                devices.append(Device("smoke", x, y_center))
            x += 7.5
    else:
        x_center = (min_x + max_x) / 2
        y = min_y + 3.75
        while y <= max_y:
            if not is_covered((x_center, y), devices):
                devices.append(Device("smoke", x_center, y))
            y += 7.5

    return devices