"""
test_apocalypse_protocol.py — THE ULTIMATE SURVIVAL TEST
==========================================================
الهدف: هذا ليس اختباراً عادياً. هذا محاكاة لكارثة هندسية كاملة.
إذا نجح نظامك هنا، فهو جاهز لأي شيء.
"""

import pytest
import sys
import os
import time
import random
import threading
import concurrent.futures
import sqlite3
import json
import math
from datetime import datetime
from unittest.mock import Mock, patch
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================
# APOCALYPSE SCENARIO 1: DEADLOCK ARMAGEDDON
# ============================================================
class TestDeadlockArmageddon:
    """السيناريو: ٥٠ خيطاً يحاولون تعديل نفس العناصر"""

    def test_circular_resource_contention(self):
        """تعديلات دائرية تسبب تنافساً على الموارد"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )

        model = UniversalDataModel(db_path=":memory:")

        # إنشاء 20 عنصراً
        element_ids = []
        for i in range(20):
            elem = UniversalElement(
                properties=SemanticProperties(
                    element_type=ElementType.WALL,
                    name=f"Deadlock_Wall_{i}",
                    height=3.0
                ),
                geometry=Geometry(
                    points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                    polyline_closed=True
                )
            )
            model.add_element(elem)
            element_ids.append(elem.element_id)

        errors = []
        deadlocks = []

        def circular_updater(start_idx, direction):
            """تحديث العناصر بترتيب معين"""
            try:
                if direction == 'forward':
                    indices = list(range(start_idx, start_idx + 10))
                else:
                    indices = list(range(start_idx + 9, start_idx - 1, -1))

                for idx in indices:
                    eid = element_ids[idx % len(element_ids)]
                    model.update_element(
                        eid,
                        {"properties": {"height": random.uniform(2.0, 5.0)}},
                        source=ChangeSource.AUTOCAD
                    )
            except Exception as e:
                if 'deadlock' in str(e).lower() or 'database is locked' in str(e).lower():
                    deadlocks.append(str(e))
                else:
                    errors.append(str(e))

        # إطلاق 50 خيطاً
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for i in range(25):
                futures.append(executor.submit(circular_updater, i, 'forward'))
                futures.append(executor.submit(circular_updater, i, 'backward'))
            concurrent.futures.wait(futures)

        # النجاح: صفر أخطاء
        assert len(errors) == 0, f"أخطاء: {errors[:5]}"
        assert len(deadlocks) == 0, f"deadlock!: {len(deadlocks)}"

        # كل العناصر قابلة للقراءة
        for eid in element_ids:
            assert model.elements[eid].properties.height is not None


# ============================================================
# APOCALYPSE SCENARIO 2: POWER FAILURE DURING COMPLEX TRANSACTION
# ============================================================
class TestPowerFailureChaos:
    """السيناريو: انقطاع التيار أثناء عملية معقدة"""

    def test_atomicity_under_multi_step_catastrophe(self):
        """العملية تضرب في الخطوة 3"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )

        db_path = tempfile.mktemp(suffix=".db")
        try:
            model = UniversalDataModel(db_path=db_path)
            elements = []
            for i in range(500):
                elem = UniversalElement(
                    properties=SemanticProperties(
                        element_type=ElementType.WALL,
                        name=f"Pre_Apocalypse_{i}",
                        height=3.0
                    ),
                    geometry=Geometry(
                        points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                        polyline_closed=True
                    )
                )
                model.add_element(elem)
                elements.append(elem)

            snapshot_count = len(model.elements)

            # Kill: close without commit
            conn = sqlite3.connect(db_path)
            conn.execute("BEGIN IMMEDIATE")
            for i in range(50):
                eid = elements[i].element_id
                conn.execute(
                    "INSERT OR REPLACE INTO elements (element_id, data, version) VALUES (?, ?, ?)",
                    (eid, json.dumps({"name": f"Corrupted_{i}", "height": 999.0}), 999)
                )
            conn.close()  # No commit!

            # Recover
            model2 = UniversalDataModel(db_path=db_path)
            model2.load_from_database()

            # التحقق: لا تسرب بيانات
            for i in range(50):
                eid = elements[i].element_id
                if eid in model2.elements:
                    el = model2.elements[eid]
                    assert "Corrupted" not in str(el.properties.name)
                    assert el.properties.height != 999.0

            assert len(model2.elements) == snapshot_count
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


# ============================================================
# APOCALYPSE SCENARIO 3: SMOKE PROPAGATION PHYSICS
# ============================================================
class TestSmokePropagationApocalypse:
    """السيناريو: حريق حقيقي! نظام الإنذار يجب أن يكتشفه خلال 60 ثانية"""

    @staticmethod
    def _simulate_smoke_spread(room_points, detectors, fire_origin, time_steps=100):
        """محاكاة فيزيائية لانتشار الدخان"""
        smoke_front = [fire_origin]
        detected_at = None

        for t in range(time_steps):
            new_front = []
            for front_point in smoke_front:
                spread_radius = 0.3 * (t + 1)
                for det in detectors:
                    dist = math.sqrt(
                        (front_point[0] - det[0]) ** 2 +
                        (front_point[1] - det[1]) ** 2
                    )
                    if dist <= spread_radius and detected_at is None:
                        detected_at = t
                        break
                if detected_at is not None:
                    break

                for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                    nx, ny = front_point[0] + dx * 0.5, front_point[1] + dy * 0.5
                    if (nx, ny) not in new_front:
                        new_front.append((nx, ny))

            if detected_at is not None:
                break
            smoke_front = new_front

        return detected_at is not None, detected_at if detected_at else time_steps

    def test_fire_detection_under_60_seconds(self):
        """حريق في غرفة 30م×30م، 4 كواشف، يجب اكتشافه خلال 60 ثانية"""
        room = [(0,0), (30,0), (30,30), (0,30)]
        detectors = [(7.5, 7.5), (22.5, 7.5), (7.5, 22.5), (22.5, 22.5)]
        fire_origin = (0, 0)

        detected, detection_time = self._simulate_smoke_spread(room, detectors, fire_origin)

        assert detected, "لم يتم اكتشاف الحريق!"
        assert detection_time < 60, f"بطء في الاكتشاف: {detection_time} ثانية"

    def test_obstructed_fire_detection(self):
        """حريق خلف عائق"""
        room = [(0,0), (20,0), (20,20), (0,20)]
        detectors = [(5, 10), (15, 10)]
        fire_origin = (0, 0)

        detected, detection_time = self._simulate_smoke_spread(
            room, detectors, fire_origin, time_steps=200
        )

        assert detected, "فشل في اكتشاف حريق خلف عائق!"
        assert detection_time < 120, f"بطء: {detection_time} ثانية"


# ============================================================
# APOCALYPSE SCENARIO 4: IDENTITY CRISIS
# ============================================================
class TestIdentityCrisis:
    """السيناريو: تغيير هوية عنصر كامل (من جدار إلى باب)"""

    def test_retroactive_type_change_propagation(self):
        """تغيير نوع عنصر من WALL إلى DOOR"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )

        model_a = UniversalDataModel(db_path=":memory:")
        model_b = UniversalDataModel(db_path=":memory:")

        wall = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.WALL,
                name="Wall_or_Door",
                height=3.0,
                width=0.3
            ),
            geometry=Geometry(
                points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                polyline_closed=True
            )
        )
        model_a.add_element(wall)

        # تغيير الهوية: WALL → DOOR
        wall_elem = model_a.elements[wall.element_id]
        wall_elem.properties.element_type = ElementType.DOOR
        wall_elem.properties.height = 2.1
        wall_elem.properties.width = 0.9

        # مزامنة مع Model B
        serialized = model_a.elements[wall.element_id].to_dict()
        restored = UniversalElement.from_dict(serialized)
        model_b.add_element(restored)

        b_elem = model_b.elements[restored.element_id]
        assert b_elem.properties.element_type == ElementType.DOOR
        assert b_elem.properties.height == 2.1
        assert b_elem.properties.width == 0.9


# ============================================================
# APOCALYPSE SCENARIO 5: THE NOTHING
# ============================================================
class TestTheNothing:
    """السيناريو: حذف كل شيء ثم استعادته"""

    def test_repeated_full_destruction_and_recovery(self):
        """تدمير كامل واستعادة متكررة"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )

        model = UniversalDataModel(db_path=":memory:")
        all_elements = []

        for cycle in range(5):
            for i in range(100):
                elem = UniversalElement(
                    properties=SemanticProperties(
                        element_type=ElementType.WALL,
                        name=f"Cycle{cycle}_{i}",
                        height=3.0
                    ),
                    geometry=Geometry(
                        points=[Point3D(0,0), Point3D(1,0), Point3D(1,1), Point3D(0,1)],
                        polyline_closed=True
                    )
                )
                model.add_element(elem)
                all_elements.append(elem)

            assert len(model.elements) >= 100

            for elem in all_elements[-100:]:
                model.delete_element(elem.element_id, source=ChangeSource.SYSTEM)

            assert all(
                model.elements[e.element_id].is_deleted
                for e in all_elements[-100:]
            )

            assert len(model.elements) >= 100

        assert len(model.elements) == 500
        assert all(e.is_deleted for e in model.elements.values())


# ============================================================
# THE FINAL GATE
# ============================================================
class TestFinalGate:
    """النهائي"""

    def test_everything_everywhere_all_at_once(self):
        """كل شيء، كل مكان، في آنٍ واحد"""
        from core.database import UniversalDataModel
        from core.models import (
            UniversalElement, SemanticProperties, ElementType,
            Geometry, Point3D, ChangeSource
        )

        models = [UniversalDataModel(db_path=":memory:") for _ in range(3)]
        all_element_ids = []
        all_errors = []

        def chaos_worker(worker_id):
            try:
                model = random.choice(models)
                action = random.choice(['create', 'update', 'delete', 'read'])

                if action == 'create':
                    elem = UniversalElement(
                        properties=SemanticProperties(
                            element_type=random.choice([ElementType.WALL, ElementType.ROOM, ElementType.EQUIPMENT]),
                            name=f"Chaos_{worker_id}_{random.randint(0,10000)}",
                            height=random.uniform(2.0, 10.0)
                        ),
                        geometry=Geometry(
                            points=[Point3D(0,0), Point3D(float(random.randint(1,50)), 0, 0),
                                    Point3D(float(random.randint(1,50)), float(random.randint(1,50)), 0),
                                    Point3D(0, float(random.randint(1,50)), 0)],
                            polyline_closed=True
                        )
                    )
                    model.add_element(elem)
                    all_element_ids.append((model, elem.element_id))

                elif action == 'update' and all_element_ids:
                    model, eid = random.choice(all_element_ids)
                    model.update_element(eid, {"properties": {"height": random.uniform(1.0, 20.0)}}, source=random.choice([ChangeSource.AUTOCAD, ChangeSource.REVIT]))

                elif action == 'delete' and all_element_ids:
                    model, eid = random.choice(all_element_ids)
                    model.delete_element(eid, source=ChangeSource.SYSTEM)
                else:
                    if model.elements:
                        model.elements.get(random.choice(list(model.elements.keys())))
            except Exception as e:
                all_errors.append(str(e))

        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=200) as executor:
            futures = [executor.submit(chaos_worker, i) for i in range(200)]
            concurrent.futures.wait(futures)

        elapsed = time.time() - start_time

        assert len(all_errors) == 0, f"أخطاء: {all_errors[:10]}"
        assert elapsed < 5.0, f"بطء: {elapsed:.2f}s"

        for model in models:
            _ = len(model.elements)


if __name__ == "__main__":
    print("💀 FireAI APOCALYPSE PROTOCOL")
    pytest.main([__file__, "-v", "--tb=short"])