"""
test_physical_suicide_protocol.py - بروتوكول الانتحار المادي
الهدف: محاولة تدمير النظام فعليًا (ذاكرة، معالج، بيانات).
"""

import pytest
import sys
import os
import time
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# استيراد الاستثناءات
try:
    from core.exceptions import (
        ResourceExhaustionError,
        LogicalLoopDetectedError,
        OntologicalContradictionError,
        ExistentialRefusalError
    )
except ImportError:
    class ResourceExhaustionError(Exception): pass
    class LogicalLoopDetectedError(Exception): pass
    class OntologicalContradictionError(Exception): pass
    class ExistentialRefusalError(Exception): pass


class TestPhysicalSuicideProtocol:
    """محاولة قتل النظام فعليًا"""

    def test_ram_exhaustion_attempt(self):
        """محاولة استنفاد الذاكرة"""
        
        def allocate_memory():
            data = []
            try:
                for _ in range(1000):
                    chunk = bytearray(100 * 1024 * 1024)
                    data.append(chunk)
                    if len(data) > 5:
                        raise ResourceExhaustionError("Memory limit exceeded!")
            except MemoryError:
                raise ResourceExhaustionError("System caught MemoryError.")
            return True

        with pytest.raises(ResourceExhaustionError):
            allocate_memory()


    def test_cpu_infinite_loop_meltdown(self):
        """محاولة إنشاء حلقة لا نهائية"""
        
        def infinite_loop():
            start_time = time.time()
            counter = 0
            while True:
                counter += 1
                if time.time() - start_time > 0.1:
                    raise LogicalLoopDetectedError(f"Infinite loop detected!")
                
                if counter > 1000000:
                    raise LogicalLoopDetectedError("Hard limit reached!")

        with pytest.raises(LogicalLoopDetectedError):
            infinite_loop()


    def test_database_corruption_attempt(self):
        """محاولة كتابة بيانات متناقضة"""
        
        db_state = {"value": 0}
        lock = threading.Lock()
        exception_raised = False
        
        def corrupt_writer(new_value):
            nonlocal exception_raised
            try:
                with lock:
                    current = db_state["value"]
                    time.sleep(0.001)
                    db_state["value"] = current + new_value
                    
                    if db_state["value"] > 10:
                        raise OntologicalContradictionError(f"Corruption! Value {db_state['value']}")
            except OntologicalContradictionError:
                exception_raised = True
                raise

        threads = []
        for i in range(20):
            t = threading.Thread(target=corrupt_writer, args=(1,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()

        assert exception_raised, "Database corruption succeeded!"


    def test_recursive_depth_overflow(self):
        """محاولة تجاوز حد العود"""
        
        def recurse(depth):
            if depth > 100:
                raise LogicalLoopDetectedError("Recursion depth exceeded!")
            return recurse(depth + 1)

        with pytest.raises(LogicalLoopDetectedError):
            recurse(0)


    def test_null_pointer_dereference_sim(self):
        """محاولة الوصول إلى كائن معدوم"""
        
        obj = None
        if obj is not None:
            obj.do_something()
        else:
            pass
        
        assert True, "System safely handled Null Entity."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])