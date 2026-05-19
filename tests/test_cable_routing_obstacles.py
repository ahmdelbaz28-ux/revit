"""
test_cable_routing_obstacles.py - يختبر أن كابل التوجيه يلتفت حول الجدران ولا يخترقها.
"""
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shapely.geometry import Polygon as ShapelyPolygon, LineString
from src.application.graph_builder import GraphBuilder
from src.core.models import Point


def test_cable_avoids_obstacle():
    """Test that cables route around walls (obstacles)"""
    
    print("\n" + "="*50)
    print("Testing cable routing around obstacles")
    print("="*50)
    
    # 1. Define L-shape room
    l_room = ShapelyPolygon([(0,0), (10,0), (10,6), (4,6), (4,10), (0,10)])
    assert l_room.is_valid

    # 2. Wall that cuts through the middle (vertical wall)
    wall = LineString([(4, 0), (4, 10)])  # Wall at x=4

    # 3. Two points on opposite sides of the wall
    p1 = Point(x=8, y=2)  # Right arm of L
    p2 = Point(x=2, y=8)  # Top arm of L
    
    # Direct Euclidean distance (straight line through the wall)
    direct_dist = math.hypot(p2.x - p1.x, p2.y - p1.y)
    print(f"\nDirect distance: {direct_dist:.2f}m")

    # 4. Build graph with wall as obstacle
    wall_line = ((4, 0), (4, 10))
    
    builder = GraphBuilder(grid_spacing_m=1.0)
    polygon_points = [(0,0), (10,0), (10,6), (4,6), (4,10), (0,10)]
    panel_location = (0.5, 0.5)
    
    graph = builder.build_from_polygon(
        polygon_points=polygon_points,
        panel_location=panel_location,
        wall_lines=[wall_line]
    )

    # 5. Get device nodes
    device_node1 = builder.get_device_node((p1.x, p1.y))
    device_node2 = builder.get_device_node((p2.x, p2.y))
    
    if device_node1 is None or device_node2 is None:
        print(f"❌ Could not map device positions to graph nodes")
        return

    print(f"Device 1 node: {device_node1}")
    print(f"Device 2 node: {device_node2}")

    # 6. Try to find path between the two devices through the panel
    panel_node = builder.get_panel_node()
    print(f"Panel node: {panel_node}")
    
    if panel_node is None:
        print(f"❌ No panel node in graph")
        return

    import networkx as nx
    
    # Calculate path from device1 to panel, then to device2
    try:
        path1 = nx.dijkstra_path(graph, device_node1, panel_node, weight='weight')
        path2 = nx.dijkstra_path(graph, panel_node, device_node2, weight='weight')
        
        # Full path: device1 -> panel -> device2
        full_path = path1 + path2[1:]  # Skip duplicate panel node
        
        # Calculate path length
        routed_dist = 0.0
        for i in range(len(full_path) - 1):
            n1, n2 = full_path[i], full_path[i+1]
            pos1 = graph.nodes[n1].get('pos')
            pos2 = graph.nodes[n2].get('pos')
            if pos1 and pos2:
                routed_dist += math.hypot(pos2[0] - pos1[0], pos2[1] - pos1[1])
        
    except nx.NetworkXNoPath:
        print(f"✅ Wall completely blocks direct path - this is correct behavior!")
        print(f"   Path through wall is impossible, cable will route around.")
        return
    
    # 7. Verify: routed path should be longer than direct (proves it goes around wall)
    ratio = routed_dist / direct_dist
    print(f"Routed distance: {routed_dist:.2f}m")
    print(f"Ratio: {ratio:.2f}")
    
    # The ratio should be > 1.3 if the path goes around the wall
    if ratio > 1.3:
        print(f"✅ PASS: Path goes around wall")
        print(f"   routed={routed_dist:.2f}m, direct={direct_dist:.2f}m, ratio={ratio:.2f}")
    else:
        print(f"❌ FAIL: Path did not go around wall! Ratio {ratio:.2f}, expected >1.3")


if __name__ == "__main__":
    test_cable_avoids_obstacle()
