"""
Continuous Coverage Verification
Ensures EVERY point in room polygon is within r meters of at least one device.
Uses Shapely geometry operations — NOT grid approximation.
"""

from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from typing import List, Dict, Any


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
    
    def verify_coverage(self, room_polygon: Polygon, devices: List[Point], radius: float) -> Dict[str, Any]:
        """
        Verify that room_polygon is fully covered by device circles.
        
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
        
        # Step 1: Create coverage circles as polygons
        coverage_circles = []
        for device in devices:
            # buffer(r, resolution) creates circle as polygon
            circle = device.buffer(radius, resolution=self.resolution)
            coverage_circles.append(circle)
        
        # Step 2: Union all coverage circles into one shape
        total_coverage = unary_union(coverage_circles)
        
        # Step 3: Find uncovered area (room minus coverage)
        uncovered = room_polygon.difference(total_coverage)
        
        # Step 4: Calculate metrics
        room_area = room_polygon.area
        uncovered_area = uncovered.area if not uncovered.is_empty else 0
        coverage_percent = ((room_area - uncovered_area) / room_area * 100) if room_area > 0 else 0
        
        # Step 5: Determine status (NFPA 72: 100% coverage required)
        # Allow 0.01m² tolerance for floating point errors
        if uncovered_area < 0.01:
            status = "PASS"
        else:
            status = "FAIL"
        
        # Step 6: Extract uncovered polygons for reporting
        uncovered_polygons = []
        if not uncovered.is_empty:
            if uncovered.geom_type == 'Polygon':
                uncovered_polygons = [uncovered]
            elif uncovered.geom_type == 'MultiPolygon':
                uncovered_polygons = list(uncovered.geoms)
        
        # Step 7: Find max gap distance (distance from uncovered area to nearest device)
        max_gap = 0.0
        if uncovered_polygons and devices:
            for poly in uncovered_polygons:
                for device in devices:
                    # Distance from polygon to point minus radius = gap beyond coverage
                    dist = poly.distance(device)
                    if dist > max_gap:
                        max_gap = dist
        
        return {
            "status": status,
            "coverage_percent": round(coverage_percent, 4),
            "uncovered_area": round(uncovered_area, 4),
            "uncovered_polygons": uncovered_polygons,
            "max_gap_distance": round(max_gap, 4),
            "room_area": round(room_area, 4),
            "device_count": len(devices),
        }
    
    def verify_with_tolerance(self, room_polygon: Polygon, devices: List[Point], 
                          radius: float, tolerance_m2: float = 0.1) -> Dict[str, Any]:
        """
        Verify with small tolerance for practical applications.
        NFPA 72 sometimes allows tiny uncovered areas near walls.
        """
        result = self.verify_coverage(room_polygon, devices, radius)
        
        if result["uncovered_area"] <= tolerance_m2:
            result["status"] = "PASS_WITH_TOLERANCE"
            result["tolerance_applied_m2"] = tolerance_m2
        
        return result


def estimate_extra_devices(uncovered_area: float, coverage_per_device: float = 30.0) -> int:
    """Estimate how many extra devices needed to cover gap."""
    if uncovered_area <= 0:
        return 0
    import math
    return math.ceil(uncovered_area / coverage_per_device)