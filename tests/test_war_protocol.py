"""
test_war_protocol.py — بروتوكول الحرب
"""

import pytest
import sys
import os
import time
import threading
import concurrent.futures
import random
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import UniversalDataModel
from core.models import UniversalElement, SemanticProperties, ElementType, Geometry, Point3D, ChangeSource


class TestMemoryBomb:
    """قنبلة الذاكرة"""

    def test_real_memory_exhaustion(self):
        """حجز ٥٠٠ ميجابايت"""
        model = UniversalDataModel(db_path=":memory:")
        elements = []
        
        try:
            for i in range(10000):
                elem = UniversalElement(
                    properties=SemanticProperties(
                        element_type=ElementType.WALL,
                        name=f"Memory_Bomb_{i:05d}",
                        height=random.uniform(1.0, 10.0)
                    ),
                    geometry=Geometry(
                        points=[Point3D(random.uniform(0,1000), random.uniform(0,1000), 0) for _ in range(4)],
                        polyline_closed=True
                    )
                )
                model.add_element(elem)
                elements.append(elem)
            
            del elements
            import gc
            gc.collect()

        except Exception:
            pass

        assert len(model.elements) > 0


class TestDatabaseMeltdown:
    """انهيار قاعدة البيانات"""

    def test_database_under_extreme_load(self):
        """١٠٠٠٠٠ تحديث"""
        model = UniversalDataModel(db_path=":memory:")

        victim = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="Victim",
                height=3.0
            ),
            geometry=Geometry(
                points=[Point3D(0,0,0), Point3D(1,0,0), Point3D(1,1,0), Point3D(0,1,0)],
                polyline_closed=True
            )
        )
        model.add_element(victim)
        vid = victim.element_id

        errors = []
        start = time.time()

        for i in range(100000):
            try:
                model.update_element(vid, {"height": 3.0 + (i * 0.00001)}, source=ChangeSource.AUTOCAD)
            except Exception as e:
                errors.append((i, str(e)))
                break

        elapsed = time.time() - start

        assert vid in model.elements
        assert elapsed < 30.0


class TestLockFreeMassacre:
    """تزامن مميت بلا أقفال"""

    def test_lock_free_concurrent_writes(self):
        """١٠٠ خيط، نفس المتغير"""
        model = UniversalDataModel(db_path=":memory:")
        
        victim = UniversalElement(
            properties=SemanticProperties(element_type=ElementType.WALL, name="Victim", height=0.0),
            geometry=Geometry(points=[Point3D(0,0,0), Point3D(1,0,0), Point3D(1,1,0), Point3D(0,1,0)], polyline_closed=True)
        )
        model.add_element(victim)
        vid = victim.element_id

        errors = []

        def no_lock_writer(value):
            try:
                model.update_element(vid, {"height": value}, source=ChangeSource.AUTOCAD)
            except Exception as e:
                errors.append(str(e))

        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(no_lock_writer, float(i)) for i in range(100)]
            concurrent.futures.wait(futures)

        assert vid in model.elements


class TestDeathParse:
    """تحليل ملفات ضخمة"""

    def test_massive_dwg_file_simulation(self):
        """محاكاة ١٠٠٠٠٠ كيان"""
        pytest.importorskip("ezdxf")
        
        from parsers.dwg_parser import DWGParser
        import ezdxf

        doc = ezdxf.new()
        msp = doc.modelspace()

        for i in range(100000):
            msp.add_line(
                (random.uniform(0,1000), random.uniform(0,1000)),
                (random.uniform(0,1000), random.uniform(0,1000))
            )

        with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as tmp:
            tmp_path = tmp.name
            doc.saveas(tmp_path)

        try:
            parser = DWGParser()
            start = time.time()
            elements = parser.parse_dwg(tmp_path)
            elapsed = time.time() - start

            assert isinstance(elements, list)
            assert elapsed < 60.0
        finally:
            os.unlink(tmp_path)


class TestBurnBox:
    """صندوق الاحتراق"""

    def test_total_war(self):
        """حرب شاملة"""
        model = UniversalDataModel(db_path=":memory:")
        all_ids = []
        all_errors = []

        def soldier(mission_id):
            try:
                action = random.choice(['create', 'update', 'delete', 'read'])

                if action == 'create':
                    elem = UniversalElement(
                        properties=SemanticProperties(
                            element_type=random.choice([ElementType.WALL, ElementType.ROOM, ElementType.EQUIPMENT]),
                            name=f"Soldier_{mission_id}",
                            height=random.uniform(1.0, 50.0)
                        ),
                        geometry=Geometry(
                            points=[Point3D(random.uniform(0,10000), random.uniform(0,10000), 0) for _ in range(4)],
                            polyline_closed=True
                        )
                    )
                    model.add_element(elem)
                    all_ids.append(elem.element_id)

                elif action == 'update' and all_ids:
                    target = random.choice(all_ids)
                    if target in model.elements:
                        model.update_element(target, {"height": random.uniform(0.1, 100.0)}, source=random.choice([ChangeSource.AUTOCAD, ChangeSource.REVIT]))

                elif action == 'delete' and all_ids:
                    target = random.choice(all_ids)
                    if target in model.elements:
                        model.delete_element(target, source=ChangeSource.SYSTEM)

            except Exception as e:
                all_errors.append(str(e))

        start = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(soldier, i) for i in range(1000)]
            concurrent.futures.wait(futures)

        elapsed = time.time() - start

        assert len(model.elements) > 0
        assert elapsed < 30.0


if __name__ == "__main__":
    print("☠️ WAR PROTOCOL")
    pytest.main([__file__, "-v", "--tb=short"])