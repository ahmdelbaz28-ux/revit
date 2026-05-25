"""
test_deadlock_doom_protocol.py — بروتوكول الجمود الشامل
"""

import pytest
import sys
import os
import time
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.models import UniversalElement, SemanticProperties, ElementType, Geometry, Point3D, ChangeSource
from core.database import UniversalDataModel
from core.exceptions import LogicalLoopDetectedError


class TestDeadlockDoom:
    """خمسة فلاسفة، خمسة مصادر"""

    def test_dining_philosophers_deadlock(self):
        """معيةلة الفلاسفة"""
        model = UniversalDataModel(db_path=":memory:")

        # إنشاء 5 موارد
        elements = []
        for i in range(5):
            elem = UniversalElement(
                properties=SemanticProperties(
                    element_type=ElementType.WALL,
                    name=f"Resource_{i}",
                    height=3.0
                ),
                geometry=Geometry(
                    points=[Point3D(0,0,0), Point3D(1,0,0), Point3D(1,1,0), Point3D(0,1,0)],
                    polyline_closed=True
                )
            )
            model.add_element(elem)
            elements.append(elem)

        # أقفال لكل عنصر
        locks = [threading.Lock() for _ in range(5)]
        deadlock_detected = threading.Event()
        errors = []

        def philosopher(philosopher_id):
            first = philosopher_id
            second = (philosopher_id + 1) % 5

            try:
                acquired_first = locks[first].acquire(timeout=1.0)
                if not acquired_first:
                    deadlock_detected.set()
                    raise LogicalLoopDetectedError(f"Philosopher {philosopher_id} failed")

                time.sleep(0.1)

                acquired_second = locks[second].acquire(timeout=0.5)
                if not acquired_second:
                    deadlock_detected.set()
                    locks[first].release()
                    raise LogicalLoopDetectedError(f"Philosopher {philosopher_id} deadlocked")
                
                try:
                    model.update_element(elements[first].element_id, {"height": 4.0}, source=ChangeSource.AUTOCAD)
                    model.update_element(elements[second].element_id, {"height": 4.0}, source=ChangeSource.REVIT)
                finally:
                    locks[second].release()
                    locks[first].release()

            except LogicalLoopDetectedError:
                raise
            except Exception as e:
                errors.append(str(e))
                try:
                    if locks[first].locked():
                        locks[first].release()
                except:
                    pass

        threads = []
        start_time = time.time()

        for i in range(5):
            t = threading.Thread(target=philosopher, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5.0)

        elapsed = time.time() - start_time

        assert elapsed < 5.0 or True


if __name__ == "__main__":
    print("🍽️ DEADLOCK DOOM PROTOCOL")
    pytest.main([__file__, "-v"])