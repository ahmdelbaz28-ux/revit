"""
src/application/coverage_service.py
محرك فحص التغطية مع دعم العوارض (Beams) وكشف العوارض العميقة
"""
from typing import List
from src.core.models import Room, Device, Violation, ViolationSeverity, Point, Beam
from src.auto_placement import suggest_devices
from src.application.beam_detector import BeamDetector
import shapely.geometry as geom
import shapely.ops as ops
import math


class CoverageService:

    def __init__(self, beams: List[Beam] = None):
        self.beams = beams or []
        self.beam_detector = BeamDetector()

    def check_coverage(self, room: Room, devices: List[Device] = None,
                       standard=None) -> List[Violation]:
        if devices is None:
            spacing = standard.get_max_spacing("SmokeDetector") if standard else 9.1
            devices = suggest_devices(room, spacing)

        violations = []
        if not devices:
            violations.append(Violation(
                violation_code="NO_DEVICES",
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

        coverage_union = ops.unary_union(coverage_parts)
        uncovered = room_poly.difference(coverage_union)

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
        if room.polygon and room.polygon.exterior:
            coords = [(p.x, p.y) for p in room.polygon.exterior]
            return geom.Polygon(coords)
        raise ValueError("Room has no valid polygon")

    def check_room_coverage(self, room: Room, devices: List[Device] = None) -> List[dict]:
        """Check room coverage - delegates to check_coverage."""
        if devices is None:
            devices = []
        violations = self.check_coverage(room, devices)
        return [{'type': v.violation_code, 'severity': v.severity.value} for v in violations]

    def check_device_spacing(self, room: Room, devices: List[Device] = None) -> List[dict]:
        """Check device spacing violations."""
        violations = []
        if not devices or len(devices) < 2:
            return violations
        for i, d1 in enumerate(devices):
            for d2 in devices[i+1:]:
                dist = math.sqrt((d1.x - d2.x)**2 + (d1.y - d2.y)**2)
                if dist < 4.55:
                    violations.append({
                        'type': 'spacing',
                        'device1': d1.id,
                        'device2': d2.id,
                        'distance': dist
                    })
        return violations
