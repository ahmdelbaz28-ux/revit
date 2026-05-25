from shapely.geometry import Polygon
from typing import Tuple, List

def validate_geometry(room: dict) -> Tuple[bool, str]:
    polygon = room.get("polygon")
    if not polygon or len(polygon) < 3:
        return False, "invalid_polygon"

    try:
        poly = Polygon(polygon)

        if not poly.is_valid:
            return False, "invalid_geometry"

        if poly.area < 1.0:
            return False, "area_too_small"

        return True, "valid"
    except Exception:
        return False, "geometry_exception"

def is_polygon_complex(polygon: list) -> bool:
    if len(polygon) > 8:
        return True
    return False

def check_rooms_overlap(rooms: list) -> List[tuple]:
    overlapping_pairs = []
    polygons = []

    for room in rooms:
        polygon = room.get("polygon")
        if polygon and len(polygon) >= 3:
            try:
                polygons.append((room["id"], Polygon(polygon)))
            except:
                pass

    for i in range(len(polygons)):
        for j in range(i + 1, len(polygons)):
            if polygons[i][1].intersects(polygons[j][1]):
                overlapping_pairs.append((polygons[i][0], polygons[j][0]))

    return overlapping_pairs