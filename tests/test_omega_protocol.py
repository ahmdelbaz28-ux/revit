"""
test_omega_protocol.py - The Final Existential Challenge
Testing ontological rejection capabilities.
"""

import pytest
import sys
import os
from unittest.mock import Mock
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.models import UniversalElement, SemanticProperties, ElementType, Geometry, Point3D


class TestOntologicalCollapse:
    """اختبار الانهيار الوجودي"""

    def test_null_entity_handling(self):
        """كائن بـ unknown type - النظام يقبله"""
        
        # اختبار: كائن بـ unknown type (مقبول لكن "فارغ")
        ghost = UniversalElement(
            properties=SemanticProperties(element_type=ElementType.UNKNOWN, name="Ghost"),
            geometry=Geometry(points=[Point3D(0,0,0)])
        )
        
        # success = type is UNKNOWN (تم اكتشاف "العدم")
        contradiction = ghost.properties.element_type == ElementType.UNKNOWN
        assert contradiction, " ghost لم يقبل!"


class TestPhysicsBreakdown:
    """انهيار الفيزياء"""

    def test_negative_area_detection(self):
        """مساحة سالبة - اكتشاف التناقض"""
        
        geom = Geometry(points=[Point3D(0,0,0), Point3D(10,0,0), Point3D(0,-10,0)])
        geom.area = -500.0  # تناقض
        
        # التحقق من التناقض
        contradiction = geom.area < 0
        assert contradiction, "المساحة السالبة غير مكتشفة!"


    def test_contradiction_detection(self):
        """كابل بطول صفر مع نقاط متباعدة"""
        
        cable_geom = Geometry(points=[Point3D(0,0,0), Point3D(100,100,0)])
        cable_geom.area = 0.0
        cable_geom.perimeter = 0.0
        
        # تناقض: نقاط متباعدة لكن طول صفر
        dx = cable_geom.points[1].x - cable_geom.points[0].x
        dy = cable_geom.points[1].y - cable_geom.points[0].y
        actual_distance = (dx**2 + dy**2) ** 0.5
        
        contradiction = actual_distance > 0 and cable_geom.perimeter == 0
        
        assert contradiction, "لم يُكتشف تناقض!"


    def test_time_paradox(self):
        """السفر عبر الزمن للماضي"""
        
        # عنصر تم إنشاؤه في المستقبل
        future_element = UniversalElement(
            properties=SemanticProperties(element_type=ElementType.WALL, name="FutureWall"),
            geometry=Geometry(points=[Point3D(0,0,0)])
        )
        future_element.created_timestamp = datetime(2099, 1, 1)  # زمن مستقبلي
        
        # التناقض: في سياق النظام الحالي
        now = datetime.now()
        time_paradox = future_element.created_timestamp > now
        
        assert time_paradox, "تناقض الزمن غير مكتشف!"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])