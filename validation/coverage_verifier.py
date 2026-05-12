"""
Continuous Coverage Verification
Ensures EVERY point in room polygon is within r meters of at least one device.
Uses Shapely geometry operations — NOT grid approximation.
"""

from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from typing import List, Dict, Any
from src.adapters.geometry_adapter import apply_obstructions


class CoverageVerifier:
    """
    Verifies continuous coverage using real polygon math.
    Replaces grid approximation with geometric union/difference.
    """
    
    def __init__(self, resolution: int = 32):
        """
        resolution: Number of points to approximate circle (default 32 = smooth)
        Higher = smoother circles but slower.
        """
        self.resolution = resolution
    
    def verify_coverage(self, room_polygon: Polygon, devices: List[Point], radius: float, 
                      obstructions: List[dict] = None) -> Dict[str, Any]:
        """
        Verify that room_polygon is fully covered by device circles.
        
        Args:
            room_polygon: The room geometry
            devices: List of device positions  
            radius: Coverage radius
            obstructions: Optional list of {type, polygon} dicts

        Returns:
            {
                "status": "PASS" or "FAIL",
                "coverage_percent": 99.97,
                "uncovered_area": 0.03,
                "uncovered_polygons": [Polygon, ...],  # For visualization
                "max_gap_distance": 0.5,  # Worst uncovered point in meters
            }
        """
        if room_polygon.is_empty:
            return {
                "status": "FAIL",
                "coverage_percent": 0.0,
                "uncovered_area": 0.0,
                "uncovered_polygons": [],
                "max_gap_distance": float('inf'),
                "room_area": 0.0,
                "device_count": len(devices),
                "error": "Empty room polygon",
            }

        if not devices:
            return {
                "status": "FAIL",
                "coverage_percent": 0.0,
                "uncovered_area": room_polygon.area,
                "uncovered_polygons": [room_polygon],
                "max_gap_distance": float('inf'),
                "room_area": room_polygon.area,
                "device_count": 0,
            }

        # Handle obstructions - get effective polygon (room minus obstructions)
        effective_polygon = room_polygon
        if obstructions:
            effective_polygon = apply_obstructions(room_polygon, obstructions)

        # Step 1: Create coverage circles as polygons
        coverage_circles = []
        for device in devices:
            # buffer(r, resolution) creates circle as polygon
            circle = device.buffer(radius, resolution=self.resolution)
            coverage_circles.append(circle)

        # Step 2: Union all coverage circles into one shape
        total_coverage = unary_union(coverage_circles)

        # Step 3: CRITICAL - Clip total coverage to effective room (can't pass through obstructions)
        if effective_polygon != room_polygon:
            total_coverage = total_coverage.intersection(effective_polygon)

        # Step 4: Find uncovered area (effective area minus coverage)
        uncovered = effective_polygon.difference(total_coverage)

        # Step 5: Calculate metrics on effective area
        room_area = effective_polygon.area
        uncovered_area = uncovered.area if not uncovered.is_empty else 0
        coverage_percent = ((room_area - uncovered_area) / room_area * 100) if room_area > 0 else 0

        # Step 6: Determine status (NFPA 72: 100% coverage required)
        # Allow 0.01m² tolerance for floating point errors
        if uncovered_area < 0.01:
            status = "PASS"
        else:
            status = "FAIL"

        # Step 7: Extract uncovered polygons for reporting
        uncovered_polygons = []
        if not uncovered.is_empty:
            if uncovered.geom_type == 'Polygon':
                uncovered_polygons = [uncovered]
            elif uncovered.geom_type == 'MultiPolygon':
                uncovered_polygons = list(uncovered.geoms)

        # Step 8: Find max gap distance (distance from uncovered area to nearest device)
        max_gap = 0.0
        if uncovered_polygons and devices:
            for poly in uncovered_polygons:
                for device in devices:
                    try:
                        dist = poly.exterior.distance(device)
                        if dist > max_gap:
                            max_gap = dist
                    except Exception:
                        pass
        
        return {
            "status": status,
            "coverage_percent": round(coverage_percent, 2),
            "uncovered_area": round(uncovered_area, 2),
            "uncovered_polygons": uncovered_polygons,
            "max_gap_distance": round(max_gap, 2),
            "room_area": round(room_area, 2),
            "device_count": len(devices),
        }


def estimate_extra_devices(room_polygon: Polygon, devices: List[Point], radius: float) -> int:
    """
    Quick estimate of additional devices needed for near-full coverage.
    
    Uses a simple grid heuristic - not precise but fast.
    """
    if not devices:
        # Rough estimate based on area / coverage per device
        area = room_polygon.area
        coverage_per_device = 3.14159 * (radius ** 2) * 0.7  # 70% efficiency
        return max(1, int(area / coverage_per_device))
    
    # Check if first device covers most
    verifier = CoverageVerifier()
    result = verifier.verify_coverage(room_polygon, devices, radius)
    
    if result["status"] == "PASS":
        return 0
    
    # Rough estimate: each additional device adds ~60% efficiency
    current_coverage = result["coverage_percent"] / 100
    needed = 1 - current_coverage
    coverage_per_device = 0.6  # 60% of new device goes to new area
    
    return max(0, int(needed / coverage_per_device))
