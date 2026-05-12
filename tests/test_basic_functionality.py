"""
tests/test_basic_functionality.py
=========================
اختبارات الوظائف الأساسية للتأكد من أن النظام يعمل صح.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import UniversalDataModel
from core.models import UniversalElement, SemanticProperties, ElementType, Geometry, Point3D, ChangeSource


class TestBasicFunctionality:
    """اختبارات الوظائف الأساسية"""

    def test_add_element_exists(self):
        """1. أضف عنصرًا، تأكد من وجوده في model.elements"""
        m = UniversalDataModel(db_path=":memory:")
        
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="TestWall",
                height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0,0), Point3D(10,0,0), Point3D(10,5,0), Point3D(0,5,0)],
                polyline_closed=True
            )
        )
        m.add_element(elem)
        
        # لازم يكون موجود في القاموس
        assert elem.element_id in m.elements
        assert m.elements[elem.element_id] is not None

    def test_update_element_saves_value(self):
        """2. حدث ارتفاع عنصر، تأكد من تغير القيمة"""
        m = UniversalDataModel(db_path=":memory:")
        
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="TestWall",
                height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0,0), Point3D(10,0,0), Point3D(10,5,0), Point3D(0,5,0)],
                polyline_closed=True
            )
        )
        m.add_element(elem)
        
        # التحديث - لازم يتم dict صح
        new_height = 7.5
        m.update_element(elem.element_id, {"properties": {"height": new_height}}, source=ChangeSource.AUTOCAD)
        
        # لازم القيمة تتغير
        assert m.elements[elem.element_id].properties.height == new_height

    def test_calculate_area_correct(self):
        """3. أنشئ مستطيل 10×5، تأكد أن area = 50"""
        m = UniversalDataModel(db_path=":memory:")
        
        # مستطيل 10 × 5 = منطقة 50
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="Rectangle",
                height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0,0), Point3D(10,0,0), Point3D(10,5,0), Point3D(0,5,0)],
                polyline_closed=True
            )
        )
        m.add_element(elem)
        
        # حساب المساحة
        area = m.elements[elem.element_id].geometry.calculate_area()
        
        # 10 × 5 = 50
        assert area == 50.0, f"Expected 50.0, got {area}"

    def test_calculate_perimeter_correct(self):
        """4. أنشئ مستطيل 10×5، تأكد أن perimeter = 30"""
        m = UniversalDataModel(db_path=":memory:")
        
        # مستطيل 10 × 5
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="Rectangle",
                height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0,0), Point3D(10,0,0), Point3D(10,5,0), Point3D(0,5,0)],
                polyline_closed=True
            )
        )
        m.add_element(elem)
        
        # حساب المحيط
        perimeter = m.elements[elem.element_id].geometry.calculate_perimeter()
        
        # (10 + 5) × 2 = 30
        assert perimeter == 30.0, f"Expected 30.0, got {perimeter}"

    def test_soft_delete_marks_deleted(self):
        """5. احذف عنصرًا، تأكد أن is_deleted = True"""
        m = UniversalDataModel(db_path=":memory:")
        
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="ToDelete",
                height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0,0), Point3D(1,0,0), Point3D(1,1,0), Point3D(0,1,0)],
                polyline_closed=True
            )
        )
        m.add_element(elem)
        eid = elem.element_id
        
        # الحذف الناعم
        m.delete_element(eid, source=ChangeSource.SYSTEM)
        
        # لازم is_deleted يكون True
        assert m.elements[eid].is_deleted == True

    def test_soft_delete_still_exists(self):
        """6. احذف عنصرًا، تأكد أنه ما زال في model.elements"""
        m = UniversalDataModel(db_path=":memory:")
        
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="ToDelete",
                height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0,0), Point3D(1,0,0), Point3D(1,1,0), Point3D(0,1,0)],
                polyline_closed=True
            )
        )
        m.add_element(elem)
        eid = elem.element_id
        
        # الحذف الناعم
        m.delete_element(eid, source=ChangeSource.SYSTEM)
        
        # لازم يظل موجود في القاموس بعد الحذف
        assert eid in m.elements

    def test_to_dict_from_dict_preserves_data(self):
        """7. أنشئ عنصرًا بكل خصائصه، حوله لـ dict، أعد إنشاءه، تأكد من تطابق كل شيء"""
        m = UniversalDataModel(db_path=":memory:")
        
        # إنشاء العنصر الأصلي
        original = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="OriginalWall",
                height=3.0,
                width=0.3,
                material="Steel",
                fire_rating="2-Hour",
                load_bearing=True
            ),
            geometry=Geometry(
                points=[Point3D(0,0,0), Point3D(10,0,0), Point3D(10,5,0), Point3D(0,5,0)],
                polyline_closed=True
            )
        )
        m.add_element(original)
        
        # التحويل لـ dict
        as_dict = original.to_dict()
        
        # إعادة الإنشاء من dict
        restored = UniversalElement.from_dict(as_dict)
        
        # التحقق من تطابق كل الخصائص
        assert restored.properties.name == original.properties.name
        assert restored.properties.height == original.properties.height
        assert restored.properties.width == original.properties.width
        assert restored.properties.material == original.properties.material
        assert restored.properties.fire_rating == original.properties.fire_rating
        assert restored.properties.load_bearing == original.properties.load_bearing

    def test_add_multiple_elements(self):
        """8. أضف 10 عناصر، تأكد من len(model.elements) == 10"""
        m = UniversalDataModel(db_path=":memory:")
        
        for i in range(10):
            elem = UniversalElement(
                properties=SemanticProperties(
                    element_type=ElementType.WALL,
                    name=f"Wall_{i}",
                    height=3.0
                ),
                geometry=Geometry(
                    points=[Point3D(0,0,0), Point3D(1,0,0), Point3D(1,1,0), Point3D(0,1,0)],
                    polyline_closed=True
                )
            )
            m.add_element(elem)
        
        # لازم يكون 10 عناصر
        assert len(m.elements) == 10

    def test_delete_reduces_active_count(self):
        """9. أضف 5، احذف 2، تأكد من active count"""
        m = UniversalDataModel(db_path=":memory:")
        
        # إضافة 5 عناصر
        ids = []
        for i in range(5):
            elem = UniversalElement(
                properties=SemanticProperties(
                    element_type=ElementType.WALL,
                    name=f"Wall_{i}",
                    height=3.0
                ),
                geometry=Geometry(
                    points=[Point3D(0,0,0), Point3D(1,0,0), Point3D(1,1,0), Point3D(0,1,0)],
                    polyline_closed=True
                )
            )
            m.add_element(elem)
            ids.append(elem.element_id)
        
        # حذف 2
        m.delete_element(ids[0], source=ChangeSource.SYSTEM)
        m.delete_element(ids[1], source=ChangeSource.SYSTEM)
        
        # Active count = 5 - 2 = 3
        active_count = sum(1 for eid in m.elements if not m.elements[eid].is_deleted)
        assert active_count == 3

    def test_version_increments_on_update(self):
        """10. حدث عنصرًا، تأكد أن version زاد"""
        m = UniversalDataModel(db_path=":memory:")
        
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="VersionTest",
                height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0,0), Point3D(1,0,0), Point3D(1,1,0), Point3D(0,1,0)],
                polyline_closed=True
            )
        )
        m.add_element(elem)
        
        initial_version = m.elements[elem.element_id].version
        
        # تحديث
        m.update_element(elem.element_id, {"height": 5.0}, source=ChangeSource.AUTOCAD)
        
        # لازم_version يزيد
        new_version = m.elements[elem.element_id].version
        assert new_version > initial_version, f"Version didn't increment: {initial_version} -> {new_version}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])