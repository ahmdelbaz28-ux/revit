"""
src/application/coverage_service.py
محرك فحص التغطية مع دعم العوارض (Beams) وكشف العوارض العميقة
"""
from typing import List
from src.core.models import Room, Device, Violation, ViolationSeverity, Point, Beam
from src.auto_placement import suggest_devices
from src.application.beam_detector import BeamDetector
import shapely
import shapely.geometry as geom
import shapely.ops as ops
import math


class CoverageService:
    # NFPA Standard attribute for audit trail
    standard = "NFPA72"
    nfpa_standard = "NFPA72"

    def __init__(self, beams: List[Beam] = None, standard: str = None):
        self.beams = beams or []
        self.beam_detector = BeamDetector()
        
        # Handle string as first arg (backward compatibility)
        # CoverageService("NFPA72") was used with string as standard
        if isinstance(beams, str):
            if beams not in ["NFPA72", None]:
                raise ValueError(f"Unknown standard: {beams}. Supported: NFPA72")
            self.beams = []
        
        # Accept standard name for compatibility
        if standard and standard not in ["NFPA72", None]:
            raise ValueError(f"Unknown standard: {standard}. Supported: NFPA72")
    
    # Alias for compatibility
    def check_room_coverage(self, room: Room, devices: List[Device] = None) -> List[Violation]:
        """Check coverage for a room. Alias for check_coverage(room, devices)."""
        return self.check_coverage(room, devices)

    def check_coverage(self, room: Room, devices: List[Device] = None,
                       standard=None) -> List[Violation]:
        # Alias for compatibility: check_room_coverage(room) = check_coverage(room, room.devices)
        if devices is None and hasattr(room, 'devices'):
            devices = room.devices
        
        if devices is None:
            spacing = standard.get_max_spacing("SmokeDetector") if standard else 9.1
            devices = suggest_devices(room, spacing)

        violations = []
        if not devices:
            violations.append(Violation(
                violation_code="COVERAGE_NO_DEVICES",
                severity=ViolationSeverity.CRITICAL,
                description_template="Room '{room_name}' has no devices.",
                params={"room_name": room.name}
            ))
            return violations

        try:
            room_poly = self._room_to_shapely(room)
        except Exception as e:
            violations.append(Violation(
                violation_code="INVALID_GEOMETRY",
                severity=ViolationSeverity.CRITICAL,
                description_template="Invalid geometry: {error}",
                params={"error": str(e)}
            ))
            return violations

        # تحليل العوارض العميقة
        ceiling_height = room.height if room.height else 3.0
        deep_beams = self.beam_detector.analyze(room, self.beams, ceiling_height)
        
        # دوائر التغطية المعدلة
        coverage_parts = []
        for device in devices:
            if not device.position:
                continue
            center = geom.Point(device.position.x, device.position.y)
            radius = device.coverage_radius
            if standard:
                try:
                    radius = standard.get_coverage_radius(device.device_type)
                except:
                    pass

            circle = center.buffer(radius)

            # إزالة المناطق المحجوبة بالعوارض العميقة
            for beam in deep_beams:
                shadow = self.beam_detector.compute_shadow(
                    device.position, beam, radius
                )
                if shadow and not shadow.is_empty:
                    circle = circle.difference(shadow)

            if not circle.is_empty:
                coverage_parts.append(circle)

        if not coverage_parts:
            violations.append(Violation(
                violation_code="NO_COVERAGE",
                severity=ViolationSeverity.CRITICAL,
                description_template="Room '{room_name}' has no effective coverage.",
                params={"room_name": room.name}
            ))
            return violations

        try:
            coverage_union = ops.unary_union(coverage_parts)
            uncovered = room_poly.difference(coverage_union)
        except Exception as e:
            # Handle topology conflicts - fall back to simpler calculation
            try:
                # Union one by one to avoid topology issues
                coverage_union = coverage_parts[0]
                for cp in coverage_parts[1:]:
                    coverage_union = coverage_union.union(cp)
                uncovered = room_poly.difference(coverage_union)
            except:
                # Last resort: mark entire room as potentially uncovered
                uncovered = room_poly
                violations.append(Violation(
                    violation_code="GEOMETRY_ERROR",
                    severity=ViolationSeverity.WARNING,
                    description_template="Geometry calculation error: {error}. Manual review recommended.",
                    params={"error": str(e)}
                ))

        if not uncovered.is_empty and uncovered.area > 0.01:
            pct = (uncovered.area / room_poly.area) * 100.0
            violations.append(Violation(
                violation_code="UNCOVERED_AREA",
                severity=ViolationSeverity.CRITICAL,
                description_template=(
                    "Room '{room_name}' has {pct:.1f}% uncovered area "
                    "({area:.2f} m² out of {total:.2f} m²)."
                ),
                params={
                    "room_name": room.name,
                    "pct": pct,
                    "area": uncovered.area,
                    "total": room_poly.area
                }
            ))
            
            # إذا كانت هناك عوارض عميقة ولم تغطي بشكل كامل، أضف تحذير
            if deep_beams:
                violations.append(Violation(
                    violation_code="BEAM_COVERAGE",
                    severity=ViolationSeverity.MINOR,
                    description_template=(
                        "Room '{room_name}' has {n} deep beam(s) that may require "
                        "additional detectors in beam pockets."
                    ),
                    params={
                        "room_name": room.name,
                        "n": len(deep_beams)
                    }
                ))

        return violations

    def _room_to_shapely(self, room: Room) -> geom.Polygon:
        """Convert Room to shapely Polygon - handles both formats."""
        if room.polygon is None:
            raise ValueError("Room has no polygon")
        
        # If it's already a shapely Polygon
        if hasattr(room.polygon, 'exterior') and hasattr(room.polygon, 'difference'):
            if room.polygon.is_valid:
                return room.polygon
            # Try to make valid
            fixed = room.polygon.buffer(0)
            if fixed.is_valid:
                return fixed
            raise ValueError("Cannot fix invalid polygon")
        
        # If it's our custom Polygon class
        if hasattr(room.polygon, 'exterior'):
            coords = []
            for p in room.polygon.exterior:
                if hasattr(p, 'x') and hasattr(p, 'y'):
                    coords.append((p.x, p.y))
            if len(coords) >= 3:
                poly = geom.Polygon(coords)
                if poly.is_valid:
                    return poly
                # Try buffer fix
                fixed = poly.buffer(0)
                if fixed.is_valid:
                    return fixed
                raise ValueError("Invalid geometry after buffer fix")
        
        # If it's a list of points
        if isinstance(room.polygon, (list, tuple)):
            coords = []
            for p in room.polygon:
                if hasattr(p, 'x') and hasattr(p, 'y'):
                    coords.append((p.x, p.y))
                elif isinstance(p, (tuple, list)) and len(p) >= 2:
                    coords.append((p[0], p[1]))
            if len(coords) >= 3:
                poly = geom.Polygon(coords)
                if poly.is_valid:
                    return poly
                fixed = poly.buffer(0)
                if fixed.is_valid:
                    return fixed
                raise ValueError("Invalid geometry")
        
        raise ValueError("Room has no valid polygon")

    def check_device_spacing(self, room: Room, devices: List[Device]) -> List[Violation]:
        """
        Validate device spacing per NFPA 72 §17.6.3.1.
        
        Smoke detectors: max 9.1m apart
        Heat detectors: max 15m apart
        """
        violations = []
        
        if not devices or len(devices) < 2:
            return violations
        
        from itertools import combinations
        import math
        
        for d1, d2 in combinations(devices, 2):
            # Get spacing based on detector type
            max_spacing = 9.1  # Default smoke
            if hasattr(d1, 'device_type'):
                if 'heat' in str(d1.device_type).lower():
                    max_spacing = 15.0
                elif 'pull' in str(d1.device_type).lower():
                    max_spacing = 21.0
            
            # Calculate distance
            x1, y1 = d1.position.x, d1.position.y if d1.position else (0, 0)
            x2, y2 = d2.position.x, d2.position.y if d2.position else (0, 0)
            distance = math.sqrt((x2-x1)**2 + (y2-y1)**2)
            
            if distance > max_spacing:
                violations.append(Violation(
                    violation_code="SPACING_EXCEEDED",
                    severity=ViolationSeverity.MAJOR,
                    description_template="Devices {d1} and {d2} are {dist:.1f}m apart (max {max}m)",
                    params={"d1": str(d1.device_id), "d2": str(d2.device_id), 
                           "dist": distance, "max": max_spacing}
                ))
        
        return violations

    def check_kitchen_requirement(self, room: Room, devices: List[Device]) -> List[Violation]:
        """
        Validate kitchen has heat detector per NFPA 72 §17.5.3.
        
        Kitchens require heat detectors, not smoke detectors
        (smoke detectors trigger false alarms from cooking)
        """
        violations = []
        
        # Check if room is kitchen
        is_kitchen = False
        if hasattr(room, 'room_type'):
            if 'kitchen' in str(room.room_type).lower():
                is_kitchen = True
        elif hasattr(room, 'name') and 'kitchen' in str(room.name).lower():
            is_kitchen = True
        
        if not is_kitchen:
            return violations
        
        # Check for heat detector
        has_heat = False
        for device in devices:
            if hasattr(device, 'device_type'):
                if 'heat' in str(device.device_type).lower():
                    has_heat = True
        
        if not has_heat:
            violations.append(Violation(
                violation_code="KITCHEN_REQUIRES_HEAT_DETECTOR",
                severity=ViolationSeverity.CRITICAL,
                description_template="Kitchen '{room}' requires heat detector, not smoke detector",
                params={"room": room.name}
            ))
        
        return violations
