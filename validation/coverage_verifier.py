"""
Coverage Verifier — Spatial Field Coverage Calculation
==============================================
Computes coverage percentage and identifies dead zones.
Used by Auto-Correction to find uncovered areas.
"""

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from typing import List, Tuple, Dict, Any
import math


class CoverageVerifier:
    """
    Verifies device coverage for a given room polygon.
    Returns coverage percent and dead zone polygons.
    """
    
    def __init__(self, threshold: float = 0.95):
        """
        Args:
            threshold: Minimum coverage (0-1) to pass. Default 95%
        """
        self.threshold = threshold
    
    def verify_coverage(
        self,
        room_polygon: Polygon,
        device_points: List[Point],
        radius: float
    ) -> Dict[str, Any]:
        """
        Verify coverage percentage for given devices.
        
        Args:
            room_polygon: The room to cover (Shapely Polygon)
            device_points: List of device locations
            radius: Coverage radius per device (meters)
        
        Returns:
            Dict with:
            - status: "PASS" or "FAIL"
            - coverage_percent: 0-100
            - uncovered_area: m²
            - uncovered_polygons: List of dead zone polygons
            - max_gap_distance: largest gap between coverage circles
        """
        if not device_points:
            return {
                "status": "FAIL",
                "coverage_percent": 0.0,
                "uncovered_area": room_polygon.area,
                "uncovered_polygons": [room_polygon],
                "max_gap_distance": 0.0
            }
        
        # Create coverage circles for each device
        coverage_circles = []
        for point in device_points:
            circle = point.buffer(radius)
            coverage_circles.append(circle)
        
        # Union all coverage circles
        try:
            total_coverage = unary_union(coverage_circles)
        except Exception:
            total_coverage = coverage_circles[0]
            for c in coverage_circles[1:]:
                total_coverage = total_coverage.union(c)
        
        # Find uncovered areas (room minus coverage)
        try:
            uncovered = room_polygon.difference(total_coverage)
        except Exception:
            uncovered = room_polygon
        
        # Handle MultiPolygon result
        uncovered_polys = []
        if hasattr(uncovered, 'geoms'):
            uncovered_polys = list(uncovered.geoms)
        elif isinstance(uncovered, Polygon) and not uncovered.is_empty:
            if uncovered.area > 0.01:  # Ignore tiny slivers
                uncovered_polys = [uncovered]
        
        total_uncovered = sum(p.area for p in uncovered_polys)
        coverage_percent = ((room_polygon.area - total_uncovered) / room_polygon.area) * 100 if room_polygon.area > 0 else 0
        
        # Find max gap distance
        max_gap = 0.0
        if len(device_points) >= 2:
            for i, p1 in enumerate(device_points):
                for p2 in device_points[i+1:]:
                    dist = p1.distance(p2)
                    if dist > max_gap:
                        max_gap = dist - (2 * radius)  # Subtract overlapping coverage
        
        status = "PASS" if coverage_percent >= (self.threshold * 100) else "FAIL"
        
        return {
            "status": status,
            "coverage_percent": coverage_percent,
            "uncovered_area": total_uncovered,
            "uncovered_polygons": uncovered_polys,
            "max_gap_distance": max_gap
        }