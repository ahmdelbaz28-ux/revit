"""
src/application/coverage_service.py
محرك فحص التغطية الحقيقي - يستخدم Shapely للتحقق من المناطق المكشوفة
"""
from typing import List
from src.core.models import Room, Device, Violation, ViolationSeverity, Point
from src.auto_placement import suggest_devices
import shapely.geometry as geom
import shapely.ops as ops

class CoverageService:
    """
    يفحص تغطية الغرفة بناءً على دوائر نصف قطرها الحقيقي.
    إذا لم تُمرر أجهزة، يُولد اقتراحاً تلقائياً ثم يفحصه.
    """

    def check_coverage(self, room: Room, devices: List[Device] = None,
                       standard=None) -> List[Violation]:
        """
        الفحص الأساسي: يحسب المناطق المغطاة ويُصدر انتهاكات على المكشوف.
        """
        # 1. إذا لم تُمرر أجهزة، استخدم الاقتراح التلقائي
        if devices is None:
            if standard:
                spacing = standard.get_max_spacing("SmokeDetector")
            else:
                spacing = 9.1  # افتراضي NFPA 72
            devices = suggest_devices(room, spacing)

        violations = []

        # 2. إذا لم توجد أجهزة على الإطلاق
        if not devices:
            violations.append(Violation(
                violation_code="NO_DEVICES",
                severity=ViolationSeverity.CRITICAL,
                description_template="Room '{room_name}' has no devices at all.",
                params={"room_name": room.name}
            ))
            return violations

        # 3. بناء مضلع الغرفة بصيغة Shapely
        try:
            room_poly = self._room_to_shapely(room)
        except Exception as e:
            violations.append(Violation(
                violation_code="INVALID_GEOMETRY",
                severity=ViolationSeverity.CRITICAL,
                description_template="Room '{room_name}' has invalid geometry: {error}",
                params={"room_name": room.name, "error": str(e)}
            ))
            return violations

        # 4. بناء دوائر التغطية وحساب الاتحاد الكلي
        coverage_circles = []
        for device in devices:
            if device.position:
                center = geom.Point(device.position.x, device.position.y)
                radius = device.coverage_radius
                # إذا كان المعيار يوفر نصف قطر، استخدمه
                if standard:
                    try:
                        radius = standard.get_coverage_radius(device.device_type)
                    except Exception:
                        pass
                circle = center.buffer(radius)
                coverage_circles.append(circle)

        if not coverage_circles:
            violations.append(Violation(
                violation_code="NO_COVERAGE",
                severity=ViolationSeverity.CRITICAL,
                description_template="Room '{room_name}' has devices but no coverage circles.",
                params={"room_name": room.name}
            ))
            return violations

        # اتحاد جميع دوائر التغطية
        coverage_union = ops.unary_union(coverage_circles)

        # 5. حساب المنطقة المكشوفة (الغرفة - التغطية)
        uncovered_area = room_poly.difference(coverage_union)

        # 6. إذا كانت هناك مساحة مكشوفة فعلية (> 0.01 متر مربع لتجنب أخطاء التقريب)
        if not uncovered_area.is_empty and uncovered_area.area > 0.01:
            # حساب نسبة التغطية
            pct_uncovered = (uncovered_area.area / room_poly.area) * 100.0
            violations.append(Violation(
                violation_code="UNCOVERED_AREA",
                severity=ViolationSeverity.CRITICAL,
                description_template=(
                    "Room '{room_name}' has {pct:.1f}% uncovered area "
                    "({area:.2f} m² out of {total:.2f} m²)."
                ),
                params={
                    "room_name": room.name,
                    "pct": pct_uncovered,
                    "area": uncovered_area.area,
                    "total": room_poly.area
                }
            ))

        return violations

    def _room_to_shapely(self, room: Room) -> geom.Polygon:
        """تحويل غرفة النظام إلى مضلع Shapely"""
        if room.polygon and room.polygon.exterior:
            coords = [(p.x, p.y) for p in room.polygon.exterior]
            return geom.Polygon(coords)
        else:
            raise ValueError("Room has no valid polygon")
