"""
FireAI Spatial Constraint Solver
Greedy algorithm for optimal device placement in rooms
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Set
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon as ShapelyPolygon

logger = logging.getLogger(__name__)

# NFPA 72 spacing rules (in meters)
MAX_WALL_DISTANCE = 1.5  # Max distance from wall
MAX_DEVICE_SPACING = 9.1  # Device must cover every point within this distance


@dataclass
class PlacementResult:
    """Result of device placement"""
    positions: List[Tuple[float, float]] = field(default_factory=list)
    coverage_percent: float = 0.0
    num_devices: int = 0


class ConstraintSolver:
    """
    Greedy algorithm for optimal device placement.
    
    Algorithm:
    1. Generate grid of candidate positions
    2. Greedy selection: pick position that covers most uncovered area
    3. Repeat until full coverage
    """
    
    def __init__(self, room_polygon: List[Tuple[float, float]], device_radius: float = MAX_DEVICE_SPACING):
        self.room_polygon = room_polygon
        self.device_radius = device_radius
        self.grid_spacing = device_radius / 2  # Finer grid for better coverage
    
    def find_optimal_placement(self, max_devices: int = 100) -> PlacementResult:
        """Find optimal device placement using greedy algorithm"""
        
        # Create shapely polygon
        poly = ShapelyPolygon(self.room_polygon)
        
        if not poly.is_valid:
            logger.warning("Invalid room polygon, attempting repair")
            poly = poly.buffer(0)
        
        bounds = poly.bounds  # (minx, miny, maxx, maxy)
        
        # Generate candidate positions
        candidates = self._generate_grid(bounds, poly)
        
        if not candidates:
            return PlacementResult()
        
        # Greedy selection
        selected = []
        covered_points = set()
        
        # Create fine grid of points to cover
        check_points = self._generate_grid(bounds, poly, density=0.5)
        
        for _ in range(min(max_devices, len(candidates))):
            if not candidates:
                break
            
            # Find candidate that covers most uncovered points
            best_candidate = None
            best_coverage = -1
            
            for candidate in candidates:
                # Check how many new points this covers
                new_coverage = self._count_coverage(candidate, check_points, covered_points)
                
                if new_coverage > best_coverage:
                    best_coverage = new_coverage
                    best_candidate = candidate
            
            if best_candidate is None or best_coverage == 0:
                break
            
            selected.append(best_candidate)
            covered_points.update(self._get_covered_points(best_candidate, check_points))
        
        # Calculate coverage
        coverage_percent = (len(covered_points) / len(check_points) * 100) if check_points else 0
        
        return PlacementResult(
            positions=selected,
            coverage_percent=coverage_percent,
            num_devices=len(selected)
        )
    
    def _generate_grid(
        self, 
        bounds: Tuple[float, float, float, float], 
        poly: ShapelyPolygon,
        density: float = None
    ) -> List[Tuple[float, float]]:
        """Generate grid of candidate positions inside polygon"""
        if density is None:
            density = self.grid_spacing
        
        minx, miny, maxx, maxy = bounds
        candidates = []
        
        x = minx
        while x <= maxx:
            y = miny
            while y <= maxy:
                point = ShapelyPoint(x, y)
                if poly.contains(point) or poly.touches(point):
                    candidates.append((x, y))
                y += density * (maxy - miny) / 10 if maxy > miny else density
            
            x += density * (maxx - minx) / 10 if maxx > minx else density
        
        return candidates
    
    def _count_coverage(
        self,
        candidate: Tuple[float, float],
        check_points: List[Tuple[float, float]],
        already_covered: Set[int]
    ) -> int:
        """Count how many new points this candidate would cover"""
        cx, cy = candidate
        count = 0
        
        for i, (px, py) in enumerate(check_points):
            if i in already_covered:
                continue
            
            dist = math.sqrt((px - cx)**2 + (py - cy)**2)
            if dist <= self.device_radius:
                count += 1
        
        return count
    
    def _get_covered_points(
        self,
        candidate: Tuple[float, float],
        check_points: List[tuple[float, float]]
    ) -> Set[int]:
        """Get indices of covered points"""
        cx, cy = candidate
        covered = set()
        
        for i, (px, py) in enumerate(check_points):
            dist = math.sqrt((px - cx)**2 + (py - cy)**2)
            if dist <= self.device_radius:
                covered.add(i)
        
        return covered
    
    def verify_coverage(self, positions: List[Tuple[float, float]]) -> float:
        """Verify coverage percentage for given positions"""
        
        poly = ShapelyPolygon(self.room_polygon)
        bounds = poly.bounds
        
        check_points = self._generate_grid(bounds, poly, density=0.5)
        
        covered = set()
        for pos in positions:
            covered.update(self._get_covered_points(pos, check_points))
        
        return (len(covered) / len(check_points) * 100) if check_points else 0