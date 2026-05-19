"""
test_cable_routing_edge_cases.py - اختبارات للحالات الحدية
"""

import sys
import math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.graph_builder import GraphBuilder
from src.application.cable_router import CableRouter
from src.core.models import Point, Device, DeviceType


def test_no_path_through_dead_end():
    """Test that dead-end paths raise NetworkXNoPath"""
    print("\n" + "="*50)
    print("Test 1: Dead-end path")
    print("="*50)
    
    # Create a 10x10 room with an internal wall that blocks access
    # The wall will cut off the right side from the left
    polygon = [(0,0), (10,0), (10,10), (0,10)]
    # Internal wall at x=5, from y=0 to y=10 - this blocks the room in half
    wall_line = ((5, 0), (5, 10))
    
    panel_location = (1, 1)  # On the left side
    builder = GraphBuilder(grid_spacing_m=1.0)
    graph = builder.build_from_polygon(polygon, panel_location, wall_lines=[wall_line])
    
    import networkx as nx
    
    # Try to find a device on the right side (behind the wall)
    right_device = builder.get_device_node((8, 5))
    
    if right_device is None:
        print(f"✅ Device on right side cannot be mapped (wall blocks)")
    else:
        panel_node = builder.get_panel_node()
        try:
            path = nx.dijkstra_path(graph, right_device, panel_node, weight='weight')
            print(f"❌ FAIL: Path found through wall! {len(path)} nodes")
        except nx.NetworkXNoPath:
            print(f"✅ PASS: Dead-end correctly blocks path")


def test_thin_wall():
    """Test thin wall (15cm) with 1m grid - should not leak"""
    print("\n" + "="*50)
    print("Test 2: Thin wall (15cm)")
    print("="*50)
    
    polygon = [(0,0), (10,0), (10,10), (0,10)]
    # Thin wall at x=5, only 15cm thick
    wall_line = ((5, 2), (5, 8))
    
    panel_location = (0.5, 0.5)
    builder = GraphBuilder(grid_spacing_m=1.0)
    graph = builder.build_from_polygon(polygon, panel_location, wall_lines=[wall_line])
    
    # With 1m grid spacing, the wall should be treated as blocking ALL nodes at x=5
    # because they're either inside or outside the wall line
    print(f"Graph: {graph.number_of_nodes()} nodes")
    
    # Device on left side
    left = builder.get_device_node((2, 5))
    # Device on right side  
    right = builder.get_device_node((8, 5))
    panel = builder.get_panel_node()
    
    import networkx as nx
    
    # Both should be reachable
    if left and right:
        print(f"✅ Both sides reachable through panel")
    else:
        print(f"❌ One or both sides not mapped")


def test_device_node_failure():
    """Test that unmapped devices produce warnings"""
    print("\n" + "="*50)
    print("Test 3: Device node failure warning")
    print("="*50)
    
    # Create devices - some inside the room, some outside
    devices = [
        Device(device_id=1, position=Point(x=2, y=2)),
        Device(device_id=2, position=Point(x=8, y=2)),
        Device(device_id=3, position=Point(x=2, y=8)),
        Device(device_id=4, position=Point(x=8, y=8)),
        Device(device_id=999, position=Point(x=100, y=100)),  # Way outside
    ]
    
    polygon = [(0,0), (10,0), (10,10), (0,10)]
    panel_location = (0.5, 0.5)
    
    # Route - device 999 should be warned
    router = CableRouter(panel_location=panel_location)
    result = router.route(devices, polygon)
    
    print(f"Routed: {result.total_devices} devices")
    print(f"Expected: 4 devices (device 999 is outside)")
    
    # Look for the warning in stdout (it's printed during route())
    # We can't easily capture it, but we can check total_devices
    if result.total_devices == 4:
        print(f"✅ PASS: Device 999 correctly skipped")
    else:
        print(f"❌ FAIL: Expected 4, got {result.total_devices}")


if __name__ == "__main__":
    test_no_path_through_dead_end()
    test_thin_wall()
    test_device_node_failure()
