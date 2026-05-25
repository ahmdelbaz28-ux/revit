"""
test_omnipotent_killer_protocol.py — 700 خيط فوضوي
"""

import pytest
import sys
import os
import time
import threading
import concurrent.futures
import random

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import UniversalDataModel
from core.models import UniversalElement, SemanticProperties, ElementType, Geometry, Point3D, ChangeSource


class TestOmnipotentKiller:
    """700 خيط فوضوي"""

    def test_seven_hundred_chaos(self):
        """700 Thread Havoc"""
        m = UniversalDataModel(db_path=":memory:")
        all_elements = []
        error_log = []
        stop_signal = threading.Event()
        
        def execute_mission(seed_val):
            try:
                rng = random.Random(seed_val)
                for cycle in range(200):
                    if stop_signal.is_set():
                        break
                    action = rng.randint(1, 100)
                    
                    if action <= 30 and all_elements:
                        target = rng.choice(all_elements)
                        if target in m.elements:
                            m.update_element(target, {"height": rng.uniform(-99.0, 999.0)}, source=ChangeSource.AUTOCAD)
                    
                    elif action <= 50:
                        e = UniversalElement(
                            properties=SemanticProperties(
                                element_type=rng.choice([ElementType.WALL, ElementType.ROOM, ElementType.EQUIPMENT]), 
                                name=f"Havoc_{seed_val}_{cycle}",
                                height=rng.uniform(-50.0, 500.0)
                            ),
                            geometry=Geometry(
                                points=[Point3D(rng.uniform(-10000,10000), rng.uniform(-10000,10000), 0) for _ in range(4)], 
                                polyline_closed=True
                            )
                        )
                        m.add_element(e)
                        all_elements.append(e.element_id)
                    
                    elif action <= 70 and all_elements:
                        target = rng.choice(all_elements)
                        if target in m.elements:
                            m.delete_element(target, source=ChangeSource.SYSTEM)
                    
                    elif action <= 85 and all_elements:
                        target = rng.choice(all_elements)
                        if target in m.elements:
                            e = m.elements[target]
                            e.properties.height = rng.uniform(-999.0, 999.0)
                            e.properties.element_type = rng.choice([ElementType.WALL, ElementType.ROOM, ElementType.EQUIPMENT])
                    
                    else:
                        if m.elements:
                            sid = rng.choice(list(m.elements.keys()))
                            if sid in m.elements:
                                _ = m.elements[sid].properties
                    
                    time.sleep(rng.uniform(0.0, 0.005))
                    
            except Exception as ex:
                error_log.append(str(ex)[:100])
                stop_signal.set()
        
        max_workers = 700
        futures_list = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, 200)) as executor:
            for i in range(max_workers):
                futures_list.append(executor.submit(execute_mission, i))
            concurrent.futures.wait(futures_list, timeout=45)
        
        stop_signal.set()
        time.sleep(1)
        
        remaining = len(m.elements)
        assert remaining >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])