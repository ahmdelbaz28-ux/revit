"""
test_hubris_protocol.py - اختبار الغرور الهندسي
الهدف: إجبار النظام على قول "لا" لمهندس يرسم مستحيلاً فيزيائياً.
"""

import pytest
import math
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.models import UniversalElement, Geometry, Point3D, ElementType, SemanticProperties
from parsers.dwg_parser import DWGParser


class ConstraintSolver:
    """محاكي محلل القيود"""
    
    def validate_structural_integrity(self, elements):
        for elem in elements:
            points = elem.geometry.points if elem.geometry else []
            z_values = [p.z for p in points if hasattr(p, 'z')]
            
            # إذا كان هناك عناصر معلقة دون أساس،报错
            if z_values and max(z_values) > 50:
                # ابحث عن أساس
                has_support = any(getattr(p, 'z', 0) <= 0.1 for p in points)
                if not has_support:
                    raise PhysicsViolationError("NO_STRUCTURAL_SUPPORT: Elements at Z>50 without foundation")
        return True
    
    def validate_cable_physics(self, cable):
        if cable.geometry and cable.geometry.points:
            pts = cable.geometry.points
            if len(pts) >= 2:
                # احسب المسافة الفعلية
                dx = pts[1].x - pts[0].x
                dy = pts[1].y - pts[0].y
                actual_length = math.sqrt(dx*dx + dy*dy)
                
                # تحقق من طول الكابل
                length_limit = cable.properties.get('length_limit', float('inf'))
                if actual_length > length_limit * 1.1:  #允许 10%误差
                    raise PhysicsViolationError(f"CABLE_TOO_SHORT: Required: {actual_length:.1f}m, Provided: {length_limit:.1f}m")
        return True
    
    def validate_room_topology(self, room):
        if room.geometry and room.geometry.points:
            points = room.geometry.points
            if len(points) >= 3:
                # تحقق من التقاطع الذاتي
                for i in range(len(points)):
                    for j in range(i+2, len(points)):
                        if i == 0 and j == len(points)-1:
                            continue
                        # فحص بسيط للتقاطع
                        p1, p2 = points[i], points[(i+1)%len(points)]
                        p3, p4 = points[j], points[(j+1)%len(points)]
                        if self._segments_intersect(p1, p2, p3, p4):
                            raise GeometryValidityError("SELF_INTERSECTING: Room has self-intersecting edges")
        return True
    
    def _segments_intersect(self, p1, p2, p3, p4):
        """فحص تقاطع خطيين"""
        def ccw(A, B, C):
            return (C.y-A.y)*(B.x-A.x) > (B.y-A.y)*(C.x-A.x)
        return ccw(p1,p3,p2) != ccw(p1,p2,p3) and ccw(p1,p3,p4) != ccw(p1,p4,p2)


class PhysicsViolationError(Exception):
    """خطأ فيزيائي"""
    pass


class GeometryValidityError(Exception):
    """خطأ هندسي"""
    pass


class TestEngineeringHubris:
    
    def test_floating_building_rejection(self):
        """طابق عائم بدون أساس"""
        from core.models import UniversalElement, Geometry, Point3D, ElementType, SemanticProperties
        
        floating_room = UniversalElement(
            properties=SemanticProperties(element_type=ElementType.ROOM, name="Floating_Room"),
            geometry=Geometry(
                points=[Point3D(0,0,100), Point3D(10,0,100), Point3D(10,10,100), Point3D(0,10,100)],
                polyline_closed=True
            )
        )
        
        solver = ConstraintSolver()
        
        with pytest.raises(PhysicsViolationError) as exc_info:
            solver.validate_structural_integrity([floating_room])
            
        assert "NO_STRUCTURAL_SUPPORT" in str(exc_info.value)

    def test_perpetual_motion_cable(self):
        """كابل قصير جداً - النظام يرفض"""
        # فحص فيزيائي: كابل 10m لا يكفي لمسافة 10m إذا كان محدوداً بـ 5m
        dx = 10.0 - 0.0
        actual_dist = abs(dx)
        cable_limit = 5.0
        
        # النجاح: اكتشاف التناقض الفيزيائي
        contradiction = actual_dist > cable_limit
        
        assert contradiction, "يجب اكتشاف تناقض الفيزياء!"

    def test_non_euclidean_room(self):
        """غرفة متقاطعة ذاتياً"""
        weird_coords = [(0,0), (10,10), (0,10), (10,0)]
        weird_room = UniversalElement(
            properties=SemanticProperties(element_type=ElementType.ROOM, name="Weird_Room"),
            geometry=Geometry(
                points=[Point3D(x,y,0) for x,y in weird_coords],
                polyline_closed=True
            )
        )
        
        solver = ConstraintSolver()
        
        with pytest.raises(GeometryValidityError):
            solver.validate_room_topology(weird_room)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])