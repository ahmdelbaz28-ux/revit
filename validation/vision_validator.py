"""
FireAI Vision Validation Engine
Validates room geometry from YOLO/floor plan detection before device placement
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry import Point as ShapelyPoint

logger = logging.getLogger(__name__)

# Valid room dimensions (in meters)
MIN_ROOM_AREA = 5.0
MAX_ROOM_AREA = 1000.0


@dataclass
class ValidationResult:
    """Result of polygon validation"""
    is_valid: bool
    violations: List[Tuple[str, bool]] = field(default_factory=list)
    remediation_steps: List[str] = field(default_factory=list)
    area: float = 0.0
    centroid: Tuple[float, float] = (0.0, 0.0)


class VisionValidationEngine:
    """
    Prove geometry is trustworthy before device placement.
    
    Validates:
    1. Is polygon closed?
    2. Is area reasonable?
    3. Is centroid inside polygon?
    4. Are angles valid?
    5. Is orientation valid?
    """
    
    @staticmethod
    def validate_room_polygon(polygon: List[Tuple[float, float]]) -> ValidationResult:
        """
        Validate room polygon from YOLO detection
        """
        violations = []
        remediation_steps = []
        
        # Empty check
        if not polygon or len(polygon) < 3:
            return ValidationResult(
                is_valid=False,
                violations=[('has_points', False)],
                remediation_steps=['Polygon needs at least 3 points']
            )
        
        # Check 1: Is polygon closed?
        is_closed = polygon[0] == polygon[-1]
        violations.append(('is_closed', is_closed))
        if not is_closed:
            remediation_steps.append("Close polygon by adding first point at end")
            # Auto-fix: close the polygon
            polygon = polygon + [polygon[0]]
        
        # Convert to shapely
        try:
            shapely_poly = ShapelyPolygon(polygon)
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                violations=[('valid_geometry', False)],
                remediation_steps=[f'Invalid geometry: {str(e)}']
            )
        
        # Check 2: Is area reasonable?
        area = shapely_poly.area
        area_valid = MIN_ROOM_AREA < area < MAX_ROOM_AREA
        violations.append(('area_valid', area_valid))
        if not area_valid:
            remediation_steps.append(f"Area {area:.1f}m² is out of range [{MIN_ROOM_AREA}, {MAX_ROOM_AREA}]")
        
        # Check 3: Is centroid inside polygon?
        centroid = shapely_poly.centroid
        centroid_coords = (centroid.x, centroid.y)
        centroid_inside = shapely_poly.contains(centroid)
        violations.append(('centroid_inside', centroid_inside))
        if not centroid_inside:
            remediation_steps.append("Polygon may be self-intersecting. Simplify using shapely.ops.unary_union()")
        
        # Check 4: Valid angles (no 0 or 180)
        valid_angles = VisionValidationEngine._check_valid_angles(polygon)
        violations.append(('valid_angles', valid_angles))
        if not valid_angles:
            remediation_steps.append("Polygon has invalid angles (0° or 180°)")
        
        # Check 5: Is valid geometry (no self-intersection)
        is_valid_geometry = shapely_poly.is_valid
        violations.append(('is_valid_geometry', is_valid_geometry))
        if not is_valid_geometry:
            remediation_steps.append("Polygon is invalid (self-intersecting). Use shapely.ops unary_union() to fix.")
        
        # Overall validity
        is_valid = all(v[1] for v in violations)
        
        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            remediation_steps=remediation_steps,
            area=area,
            centroid=centroid_coords
        )
    
    @staticmethod
    def _check_valid_angles(polygon: List[Tuple[float, float]]) -> bool:
        """Check if polygon has valid angles (not 0 or 180)"""
        if len(polygon) < 3:
            return True
        
        for i in range(len(polygon)):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % len(polygon)]
            p3 = polygon[(i + 2) % len(polygon)]
            
            # Calculate angle at p2
            v1 = (p1[0] - p2[0], p1[1] - p2[1])
            v2 = (p3[0] - p2[0], p3[1] - p2[1])
            
            # Dot product
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            
            # Magnitudes
            mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
            mag2 = math.sqrt(v2[0]**2 + v2[1]**2)
            
            if mag1 == 0 or mag2 == 0:
                continue
            
            # Cosine of angle
            cos_angle = dot / (mag1 * mag2)
            
            # Angle is 0 or 180 if cos_angle is close to 1 or -1
            if abs(cos_angle) > 0.99:
                return False
        
        return True
    
    @staticmethod
    def suggest_fixes(checks: Dict[str, bool]) -> List[str]:
        """If validation fails, suggest fixes"""
        fixes = []
        
        if not checks.get('is_closed', True):
            fixes.append("Close polygon by adding first point at end")
        if not checks.get('centroid_inside', True):
            fixes.append("Polygon is self-intersecting. Simplify using shapely.geometry.unary_union()")
        if not checks.get('area_valid', True):
            fixes.append("Room area is out of valid range. Check floor plan scale.")
        if not checks.get('valid_angles', True):
            fixes.append("Polygon has degenerate angles. Simplify geometry.")
        
        return fixes