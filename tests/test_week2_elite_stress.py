"""
test_week2_elite_stress.py - اختبارات النخبة للأسبوع الثاني
الهدف: دفع النظام إلى أقصى حدوده وكشف أي نقاط ضعف مخفية
المعيار: 100% نجاح مطلوب للانتقال للمرحلة التالية
"""

import pytest
import sys
import os
import time
import threading
import concurrent.futures
from datetime import datetime
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================
# ١. اختبارات التزامن العالي (Concurrency Stress)
# ============================================================

class TestConcurrencyStress:
    """ماذا لو حاول ٥٠ مهندساً تعديل نفس المشروع في نفس الوقت؟"""

    def test_concurrent_updates_same_element(self):
        """٥٠ تحديثاً متزامناً لنفس الجدار"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )
        
        model = UniversalDataModel(db_path=":memory:")
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL, name="Hot_Wall", height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                polyline_closed=True
            )
        )
        model.add_element(elem)
        eid = elem.element_id
        
        errors = []
        def update_wall(height):
            try:
                model.update_element(eid, {"properties": {"height": height}}, 
                                   source=ChangeSource.AUTOCAD)
            except Exception as e:
                errors.append(str(e))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(update_wall, 3.0 + i*0.1) for i in range(50)]
            concurrent.futures.wait(futures)
        
        # يجب ألا يكون هناك أي خطأ
        assert len(errors) == 0, f"أخطاء تزامن: {errors}"
        # العنصر يجب أن يظل قابلاً للقراءة
        assert model.elements[eid].properties.height is not None

    def test_concurrent_add_and_delete(self):
        """إضافة وحذف متزامن لنفس المعرف"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )
        
        model = UniversalDataModel(db_path=":memory:")
        errors = []
        
        def add_and_delete(i):
            try:
                elem = UniversalElement(
                    properties=SemanticProperties(
                        element_type=ElementType.EQUIPMENT,
                        name=f"Device_{i}"
                    ),
                    geometry=Geometry(
                        points=[Point3D(i, 0, 0)],
                        polyline_closed=False
                    )
                )
                model.add_element(elem)
                model.delete_element(elem.element_id, source=ChangeSource.SYSTEM)
            except Exception as e:
                errors.append(str(e))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(add_and_delete, i) for i in range(100)]
            concurrent.futures.wait(futures)
        
        assert len(errors) == 0, f"أخطاء في الإضافة/الحذف المتزامن: {errors}"

    def test_read_while_writing(self):
        """قراءة عنصر أثناء تحديثه من خيط آخر"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )
        
        model = UniversalDataModel(db_path=":memory:")
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL, name="Read_Write_Wall", height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                polyline_closed=True
            )
        )
        model.add_element(elem)
        eid = elem.element_id
        
        read_errors = []
        write_errors = []
        stop_event = threading.Event()
        
        def reader():
            while not stop_event.is_set():
                try:
                    el = model.elements.get(eid)
                    if el:
                        _ = el.properties.height
                except Exception as e:
                    read_errors.append(str(e))
                time.sleep(0.001)
        
        def writer():
            for i in range(500):
                try:
                    model.update_element(eid, {"properties": {"height": 3.0 + i*0.01}},
                                       source=ChangeSource.AUTOCAD)
                except Exception as e:
                    write_errors.append(str(e))
                time.sleep(0.001)
        
        threads = [threading.Thread(target=reader) for _ in range(5)]
        threads.append(threading.Thread(target=writer))
        
        for t in threads:
            t.start()
        
        time.sleep(3)
        stop_event.set()
        
        for t in threads:
            t.join(timeout=2)
        
        assert len(read_errors) == 0, f"أخطاء قراءة: {read_errors[:5]}"
        assert len(write_errors) == 0, f"أخطاء كتابة: {write_errors[:5]}"

# ============================================================
# ٢. اختبارات الذاكرة والتسريب (Memory & Resource Leaks)
# ============================================================

class TestMemoryAndResources:
    """تأكد من أن النظام لا يُسرب ذاكرة أو موارد"""

    def test_no_memory_leak_repeated_add_delete(self):
        """إضافة وحذف ١٠٠٠ عنصر - يجب ألا يتضاعف استخدام الذاكرة"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D
        )
        import gc
        from core.models import ChangeSource
        
        model = UniversalDataModel(db_path=":memory:")
        initial_count = len(model.elements)
        
        for cycle in range(10):
            # Add 100 elements
            created = []
            for i in range(100):
                elem = UniversalElement(
                    properties=SemanticProperties(
                        element_type=ElementType.EQUIPMENT,
                        name=f"Leak_Test_{cycle}_{i}",
                        height=2.4
                    ),
                    geometry=Geometry(
                        points=[Point3D(float(i), float(cycle), 0)],
                        polyline_closed=False
                    )
                )
                model.add_element(elem)
                created.append(elem.element_id)
            
            # Delete them all
            for eid in created:
                try:
                    model.delete_element(eid, source=ChangeSource.SYSTEM)
                except:
                    pass
            
            gc.collect()
        
        # لا يجب أن يكون هناك تسريب في عدد العناصر النشطة
        active = len([e for e in model.elements.values() if not e.is_deleted])
        assert active < 200, f"احتمال تسريب ذاكرة: {active} عناصر نشطة"

    def test_database_file_size_reasonable(self):
        """ملف قاعدة البيانات يجب ألا ينفجر حجماً"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D
        )
        
        db_path = tempfile.mktemp(suffix=".db")
        try:
            model = UniversalDataModel(db_path=db_path)
            
            for i in range(500):
                elem = UniversalElement(
                    properties=SemanticProperties(
                        element_type=ElementType.WALL,
                        name=f"Wall_{i:04d}",
                        height=3.0,
                        material="Concrete",
                        fire_rating="2-Hour"
                    ),
                    geometry=Geometry(
                        points=[Point3D(0,0), Point3D(10,0), Point3D(10,5), Point3D(0,5)],
                        polyline_closed=True
                    )
                )
                model.add_element(elem)
            
            file_size = os.path.getsize(db_path)
            # 500 عنصر يجب ألا يتجاوزوا 10MB
            assert file_size < 10_000_000, f"حجم قاعدة البيانات كبير جداً: {file_size:,} bytes"
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

# ============================================================
# ٣. اختبارات سلسلة الثقة (Chain of Trust)
# ============================================================

class TestChainOfTrust:
    """تأكد من أن تدفق البيانات كامل ولا يوجد فقدان للمعلومات"""

    def test_full_element_lifecycle_tracking(self):
        """تتبع كامل لدورة حياة عنصر من الميلاد حتى الموت"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )
        
        model = UniversalDataModel(db_path=":memory:")
        
        # Phase 1: Birth (AutoCAD creates element)
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL, name="Tracked_Wall", height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                polyline_closed=True
            ),
            last_modified_by=ChangeSource.AUTOCAD.value
        )
        model.add_element(elem)
        eid = elem.element_id
        assert model.elements[eid].version == 0
        
        # Phase 2: Life (multiple updates from different sources)
        model.update_element(eid, {"properties": {"height": 3.5}}, source=ChangeSource.AUTOCAD)
        assert model.elements[eid].version == 1
        assert model.elements[eid].properties.height == 3.5
        
        model.update_element(eid, {"properties": {"material": "Steel"}}, source=ChangeSource.REVIT)
        assert model.elements[eid].version == 2
        assert model.elements[eid].properties.material == "Steel"
        
        # Phase 3: Death (soft delete)
        model.delete_element(eid, source=ChangeSource.AUTOCAD)
        assert model.elements[eid].is_deleted == True
        
        # Version may or may not increment on delete (depends on implementation)
        assert model.elements[eid].version >= 2
        
        # Verification: كل المراحل مسجلة
        assert len(model.elements[eid].change_log) >= 3

    def test_cross_model_sync_consistency(self):
        """مزامنة بين نموذجين: البيانات يجب أن تصل كاملة"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )
        
        model_a = UniversalDataModel(db_path=":memory:")
        
        # Create in Model A
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.ROOM,
                name="Sync_Room",
                height=4.0,
                material="Glass"
            ),
            geometry=Geometry(
                points=[Point3D(0,0), Point3D(20,0), Point3D(20,15), Point3D(0,15)],
                polyline_closed=True
            )
        )
        model_a.add_element(elem)
        
        # Simulate sync: serialize from A, deserialize
        data = elem.to_dict()
        restored = UniversalElement.from_dict(data)
        
        # Verify completeness
        assert restored.properties.name == "Sync_Room"
        assert restored.properties.material == "Glass"
        assert restored.properties.height == 4.0
        assert len(restored.geometry.points) == 4

# ============================================================
# ٤. اختبارات الحدود القصوى (Extreme Boundary Tests)
# ============================================================

class TestExtremeBoundaries:
    """اختبار الحدود الرياضية والمنطقية"""

    def test_enormous_coordinates(self):
        """إحداثيات ضخمة جداً"""
        from core.models import Point3D, Geometry
        
        points = [
            Point3D(0, 0, 0),
            Point3D(1e10, 0, 0),
            Point3D(1e10, 1e10, 0),
            Point3D(0, 1e10, 0)
        ]
        geom = Geometry(points=points, polyline_closed=True)
        area = geom.calculate_area()
        
        assert area > 0
        assert area < float('inf')

    def test_tiny_coordinates(self):
        """إحداثيات صغرية جداً"""
        from core.models import Point3D, Geometry
        
        points = [
            Point3D(0, 0, 0),
            Point3D(1e-10, 0, 0),
            Point3D(1e-10, 1e-10, 0),
            Point3D(0, 1e-10, 0)
        ]
        geom = Geometry(points=points, polyline_closed=True)
        area = geom.calculate_area()
        
        assert area >= 0

    def test_negative_coordinates(self):
        """إحداثيات سالبة"""
        from core.models import Point3D, Geometry
        
        points = [
            Point3D(-10, -10, -2),
            Point3D(10, -10, -2),
            Point3D(10, 10, -2),
            Point3D(-10, 10, -2)
        ]
        geom = Geometry(points=points, polyline_closed=True)
        area = geom.calculate_area()
        perimeter = geom.calculate_perimeter()
        
        assert area > 0
        assert perimeter > 0

    def test_unicode_stress(self):
        """أسماء تحتوي على كل الرموز الممكنة"""
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D
        )
        
        crazy_name = "غرفة-機械-Español-Français-日本語-한국어-עברית"
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.ROOM,
                name=crazy_name,
                description="test"
            ),
            geometry=Geometry(
                points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                polyline_closed=True
            )
        )
        
        d = elem.to_dict()
        restored = UniversalElement.from_dict(d)
        assert restored.properties.name == crazy_name

# ============================================================
# ٥. اختبار الاستمرارية (Sustained Operation)
# ============================================================

class TestSustainedOperation:
    """النظام يجب أن يبقى مستقراً تحت الضغط المستمر"""

    def test_sustained_sync_cycles(self):
        """١٠٠٠ دورة مزامنة متتالية"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )
        
        model = UniversalDataModel(db_path=":memory:")
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL, name="Endurance_Wall", height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                polyline_closed=True
            )
        )
        model.add_element(elem)
        eid = elem.element_id
        
        for cycle in range(1000):
            new_height = 3.0 + (cycle % 100) * 0.01
            model.update_element(eid, {"properties": {"height": new_height}},
                               source=ChangeSource.AUTOCAD if cycle % 2 == 0 
                               else ChangeSource.REVIT)
        
        # التحقق النهائي
        assert model.elements[eid].properties.height >= 3.0
        assert model.elements[eid].version >= 999

    def test_rapid_switch_between_models(self):
        """تنقل سريع بين قراءة وكتابة نموذجين"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )
        
        model_a = UniversalDataModel(db_path=":memory:")
        model_b = UniversalDataModel(db_path=":memory:")
        
        for i in range(200):
            target = model_a if i % 2 == 0 else model_b
            elem = UniversalElement(
                properties=SemanticProperties(
                    element_type=ElementType.EQUIPMENT,
                    name=f"Switch_Device_{i}"
                ),
                geometry=Geometry(
                    points=[Point3D(float(i), 0, 0)],
                    polyline_closed=False
                )
            )
            target.add_element(elem)
            target.update_element(elem.element_id, {"properties": {"height": 3.0}},
                                source=ChangeSource.SYSTEM)
        
        assert len(model_a.elements) + len(model_b.elements) == 200

# ============================================================
# صمام الأمان النخبوي (Elite Gate)
# ============================================================

class TestEliteReadiness:
    """لن تنتقل للمرحلة التالية إلا إذا نجحت هذه الاختبارات"""

    def test_chaos_monkey_scenario(self):
        """سيناريو القرد الفوضوي: عمليات عشوائية متزامنة"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )
        import random
        
        model = UniversalDataModel(db_path=":memory:")
        
        # Create initial elements
        elements = []
        for i in range(50):
            elem = UniversalElement(
                properties=SemanticProperties(
                    element_type=random.choice([ElementType.WALL, ElementType.ROOM, ElementType.EQUIPMENT]),
                    name=f"Chaos_{i}",
                    height=random.uniform(2.0, 10.0)
                ),
                geometry=Geometry(
                    points=[Point3D(0, 0, 0), Point3D(float(random.randint(1,100)), 0, 0),
                            Point3D(float(random.randint(1,100)), float(random.randint(1,100)), 0),
                            Point3D(0, float(random.randint(1,100)), 0)],
                    polyline_closed=True
                )
            )
            model.add_element(elem)
            elements.append(elem)
        
        chaos_errors = []
        
        def chaos_action():
            try:
                action = random.choice(['add', 'update', 'delete', 'read'])
                if action == 'add':
                    elem = UniversalElement(
                        properties=SemanticProperties(
                            element_type=ElementType.EQUIPMENT,
                            name=f"Chaos_New_{random.randint(1000,9999)}"
                        )
                    )
                    model.add_element(elem)
                elif action == 'update' and elements:
                    target = random.choice(elements)
                    model.update_element(target.element_id,
                                       {"properties": {"height": random.uniform(1.0, 20.0)}},
                                       source=random.choice([ChangeSource.AUTOCAD, ChangeSource.REVIT]))
                elif action == 'delete' and elements:
                    target = random.choice(elements)
                    model.delete_element(target.element_id,
                                       source=random.choice([ChangeSource.AUTOCAD, ChangeSource.REVIT]))
                else:
                    if model.elements:
                        _ = list(model.elements.values())[0].properties
            except Exception as e:
                chaos_errors.append(str(e))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(chaos_action) for _ in range(200)]
            concurrent.futures.wait(futures)
        
        assert len(chaos_errors) == 0, f"Chaos Monkey errors: {chaos_errors[:10]}"

    def test_snapshot_and_rollback(self):
        """التقاط لقطة واستعادة الحالة بعد كارثة"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )
        
        db_path = tempfile.mktemp(suffix=".db")
        try:
            model = UniversalDataModel(db_path=db_path)
            
            # Build state
            for i in range(100):
                elem = UniversalElement(
                    properties=SemanticProperties(
                        element_type=ElementType.WALL,
                        name=f"Snapshot_Wall_{i}",
                        height=3.0
                    ),
                    geometry=Geometry(
                        points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                        polyline_closed=True
                    )
                )
                model.add_element(elem)
            
            # Take snapshot
            snapshot = {eid: elem.to_dict() for eid, elem in model.elements.items()}
            snapshot_count = len(snapshot)
            
            # Destroy some elements
            keys = list(model.elements.keys())[:50]
            for target_id in keys:
                model.delete_element(target_id, source=ChangeSource.SYSTEM)
            
            # Verify corruption
            active_after = len([e for e in model.elements.values() if not e.is_deleted])
            assert active_after < snapshot_count
            
            # Recovery: rebuild from snapshot
            model_recovered = UniversalDataModel(db_path=":memory:")
            for eid, data in snapshot.items():
                elem = UniversalElement.from_dict(data)
                model_recovered.add_element(elem)
            
            assert len(model_recovered.elements) == snapshot_count
            assert all(not e.is_deleted for e in model_recovered.elements.values())
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

# ============================================================
# تشغيل مباشر
# ============================================================

if __name__ == "__main__":
    print("🔥 Starting FireAI Week 2 Elite Stress Tests...")
    pytest.main([__file__, "-v", "--tb=short"])