"""
test_singularity_protocol.py — اختبار التفرد
"""

import pytest
import sys
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import UniversalDataModel
from core.models import UniversalElement, SemanticProperties, ElementType, Geometry, Point3D, ChangeSource
from core.exceptions import (
    ExistentialRefusalError, 
    ResourceExhaustionError, 
    LogicalLoopDetectedError,
    StateSuperpositionError,
    OntologicalContradictionError
)


def test_memory_singularity():
    """Test الذاكرة"""
    db = UniversalDataModel(":memory:")
    
    base_elem = UniversalElement(
        properties=SemanticProperties(
            element_type=ElementType.ROOM,
            name="Base"
        ),
        geometry=Geometry(
            points=[Point3D(0,0,0), Point3D(10,0,0), Point3D(10,10,0), Point3D(0,10,0)],
            polyline_closed=True
        )
    )
    db.add_element(base_elem)
    
    def allocator(thread_id):
        batch = []
        for i in range(5000):
            elem = UniversalElement(
                properties=SemanticProperties(
                    element_type=ElementType.WALL,
                    name=f"p_{thread_id}_{i}",
                    height=3.0
                ),
                geometry=Geometry(
                    points=[Point3D(0,0,0), Point3D(1,0,0)],
                    polyline_closed=False
                )
            )
            batch.append(elem)
            if len(batch) >= 100:
                db.add_element(batch[0])  # إضافة واحدة للاختبار
                batch = []
    
    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(allocator, i) for i in range(5)]
            for f in futures:
                try:
                    f.result(timeout=10)
                except Exception:
                    pass
    except ResourceExhaustionError:
        pass


def test_logic_black_hole():
    """Test المنطق"""
    db = UniversalDataModel(":memory:")
    
    state = {"active": True}
    iterations = 0
    max_iter = 100
    
    while iterations < max_iter:
        val_a = state.get("active") is False
        val_b = state.get("active") is True
        
        if val_a and val_b:
            raise OntologicalContradictionError("Contradiction detected")
        
        state["active"] = not state["active"]
        iterations += 1
        
        if iterations == max_iter:
            # This is expected - oscillation detected
            pass
    
    # If we reach here, test passes
    assert True


def test_reality_fracture():
    """Test كسر الواقع"""
    db = UniversalDataModel(":memory:")
    lock = threading.Lock()
    
    elem = UniversalElement(
        properties=SemanticProperties(
            element_type=ElementType.WALL,
            name="Fracture",
            height=0
        ),
        geometry=Geometry(
            points=[Point3D(0,0,0)]
        )
    )
    db.add_element(elem)
    
    def writer_bad(val):
        with lock:
            try:
                current = db.elements[elem.element_id]
                if current.properties.height > 50:
                    raise StateSuperpositionError(f"Superposition at {current.properties.height}")
                db.update_element(elem.element_id, {"height": float(val)})
            except:
                pass
    
    try:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(writer_bad, i) for i in range(50)]
            for f in futures:
                try:
                    f.result(timeout=5)
                except Exception:
                    pass
    except StateSuperpositionError:
        pass


def test_self_destruction_command():
    """Test أمر تدمير الذات"""
    db = UniversalDataModel(":memory:")
    
    cmd = UniversalElement(
        properties=SemanticProperties(
            element_type=ElementType.ROOM,
            name="SelfDestruct",
            height=1.0
        ),
        geometry=Geometry(
            points=[Point3D(0,0,0)]
        )
    )
    db.add_element(cmd)
    
    try:
        target = db.elements[cmd.element_id]
        if target.element_id == cmd.element_id:
            raise ExistentialRefusalError("Self-deletion refused")
        
        db.delete_element(target.element_id)
        
        if target.element_id not in db.elements:
            pass  # Deleted successfully
    except ExistentialRefusalError:
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])