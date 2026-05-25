"""
Multi-floor test scenario generator
5 طوابق، 20×30 متر لكل طابق
"""

import sys
sys.path.insert(0, '/workspace/project/revit')

from src.dxf_writer import write_simple_dxf


FLOORS = [
    # Floor 1: Basic rectangle with fire wall around riser
    {
        "name": "floor_1",
        "rooms": [
            {"type": "rect", "x": 0, "y": 0, "w": 10, "h": 15, "name": "main_area"},
            {"type": "rect", "x": 10, "y": 0, "w": 10, "h": 15, "name": "east_wing"},
            {"type": "rect", "x": 5, "y": 12, "w": 3, "h": 3, "name": "riser_shaft"},
        ],
        "fire_walls": [
            ((5, 12), (8, 12)),  # Around riser
            ((5, 12), (5, 15)),
        ],
        "beams": [
            ((3, 7.5), 0.4),  # Beam at center
        ],
        "panel": (1, 1),
    },
    
    # Floor 2: L-shaped room
    {
        "name": "floor_2", 
        "rooms": [
            {"type": "L", "x": 0, "y": 0, "w": 10, "h": 15, "arm": 6},
            {"type": "rect", "x": 6, "y": 9, "w": 4, "h": 6, "name": "interior_meeting"},
            {"type": "rect", "x": 8, "y": 12, "w": 2, "h": 3, "name": "riser_shaft"},
        ],
        "fire_walls": [
            ((8, 12), (10, 12)),
        ],
        "beams": [
            ((5, 5), 0.4),
            ((7, 10), 0.4),
        ],
        "panel": (1, 1),
    },
    
    # Floor 3: Complex with multiple rooms
    {
        "name": "floor_3",
        "rooms": [
            {"type": "rect", "x": 0, "y": 0, "w": 20, "h": 30, "name": "open_space"},
            {"type": "rect", "x": 0, "y": 0, "w": 8, "h": 10, "name": "room_a"},
            {"type": "rect", "x": 8, "y": 0, "w": 6, "h": 10, "name": "room_b"},
            {"type": "rect", "x": 14, "y": 0, "w": 6, "h": 10, "name": "room_c"},
            {"type": "rect", "x": 0, "y": 20, "w": 10, "h": 10, "name": "conference"},
            {"type": "rect", "x": 10, "y": 20, "w": 10, "h": 10, "name": "storage"},
            {"type": "rect", "x": 9, "y": 12, "w": 2, "h": 3, "name": "riser_shaft"},
        ],
        "fire_walls": [
            ((9, 12), (11, 12)),
        ],
        "beams": [
            ((4, 5), 0.4),
            ((10, 15), 0.4),
            ((16, 25), 0.4),
        ],
        "panel": (1, 1),
    },
    
    # Floor 4: Industrial with long corridor
    {
        "name": "floor_4",
        "rooms": [
            {"type": "rect", "x": 0, "y": 0, "w": 20, "h": 30, "name": "main"},
            {"type": "rect", "x": 2, "y": 10, "w": 16, "h": 2, "name": "corridor"},
            {"type": "rect", "x": 0, "y": 12, "w": 3, "h": 8, "name": "office_1"},
            {"type": "rect", "x": 3, "y": 12, "w": 3, "h": 8, "name": "office_2"},
            {"type": "rect", "x": 6, "y": 12, "w": 3, "h": 8, "name": "office_3"},
            {"type": "rect", "x": 9, "y": 12, "w": 3, "h": 8, "name": "office_4"},
            {"type": "rect", "x": 12, "y": 12, "w": 3, "h": 8, "name": "office_5"},
            {"type": "rect", "x": 15, "y": 12, "w": 3, "h": 8, "name": "office_6"},
            {"type": "rect", "x": 9, "y": 25, "w": 2, "h": 5, "name": "riser_shaft"},
        ],
        "fire_walls": [
            ((9, 25), (11, 25)),
        ],
        "beams": [
            ((10, 11), 0.5),  # Long beam
        ],
        "panel": (1, 1),
    },
    
    # Floor 5: Roof access + mechanical
    {
        "name": "floor_5",
        "rooms": [
            {"type": "rect", "x": 0, "y": 0, "w": 20, "h": 30, "name": "roof_area"},
            {"type": "rect", "x": 5, "y": 10, "w": 10, "h": 10, "name": "mechanical"},
            {"type": "rect", "x": 0, "y": 25, "w": 5, "h": 5, "name": "stair_vestibule"},
            {"type": "rect", "x": 9, "y": 25, "w": 2, "h": 5, "name": "riser_shaft"},
        ],
        "fire_walls": [
            ((9, 25), (11, 25)),
        ],
        "beams": [
            ((10, 15), 0.6),  # Heavy beam
        ],
        "panel": (1, 1),
    },
]


def generate_all_floors(output_dir: str = "/workspace/project/revit/test_data/multi_floor"):
    """Generate all 5 floor DXF files"""
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    for i, floor in enumerate(FLOORS, 1):
        filename = f"{output_dir}/floor_{i}.dxf"
        print(f"Generating {filename}...")
        
        # Generate simple DXF
        try:
            write_simple_dxf(filename, floor)
            print(f"  ✅ Created {filename}")
        except Exception as e:
            print(f"  ❌ Error: {e}")


if __name__ == "__main__":
    generate_all_floors()
