"""
FireAI — ULTIMATE STRESS TEST SUITE
Tests designed to BREAK the system and expose hidden flaws
"""

import json
import math
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union

# ============================================================
# TEST CATEGORY 1: GEOMETRIC NIGHTMARES
# ============================================================

def test_1a_ultra_thin_corridor():
    """
    Corridor: 100m × 0.5m
    Expected: System must handle extreme aspect ratio
    Danger: Floating point precision loss, buffer collapse
    """
    room = Polygon([[0,0], [100,0], [100,0.5], [0,0.5], [0,0]])
    devices = [Point(50, 0.25)]
    radius = 6.37

    # With 6.37m radius, one device covers ~12.7m length
    # Need ~8 devices for 100m corridor
    # System might place 1 device (center) → massive FAIL
    return {
        "name": "Ultra-Thin Corridor",
        "room_area": room.area,
        "expected_devices": math.ceil(100 / 12.7),
        "danger": "Single device will show PASS in grid approx, FAIL in polygon math"
    }

def test_1b_concave_c_shape():
    """
    C-Shape room: Inner corner creates invisible dead zone
    Expected: Coverage Verifier must detect gap behind inner wall
    Danger: Grid approximation misses the "pocket"
    """
    room = Polygon([
        [0,0], [10,0], [10,10], [7,10], [7,3], [3,3], 
        [3,10], [0,10], [0,0]
    ])
    devices = [Point(5, 5)]
    return {
        "name": "C-Shape (Concave)",
        "room_area": room.area,
        "danger": "Centroid device misses the two 'arms' of the C"
    }

def test_1c_donut_room():
    """
    Ring-shaped room (donut)
    Expected: Coverage must verify BOTH inner and outer perimeters
    Danger: System might place device in center (hole) → invalid
    """
    outer = Polygon([[0,0], [20,0], [20,20], [0,20], [0,0]])
    inner = Polygon([[8,8], [12,8], [12,12], [8,12], [8,8]])
    room = outer.difference(inner)

    return {
        "name": "Donut Room (Ring)",
        "room_area": room.area,
        "danger": "Device in center falls in hole. System must detect invalid placement"
    }

# ============================================================
# TEST CATEGORY 2: OBSTRUCTION WARFARE
# ============================================================

def test_2a_forest_of_columns():
    """
    50 columns in grid pattern (like parking garage)
    Expected: apply_obstructions must not crash
    Danger: Boolean operations become O(n²), performance death
    """
    room = Polygon([[0,0], [50,0], [50,50], [0,50], [0,0]])
    obstructions = []
    for i in range(5):
        for j in range(10):
            x, y = 5 + i*10, 2.5 + j*5
            obs = Polygon([
                [x-0.3, y-0.3], [x+0.3, y-0.3],
                [x+0.3, y+0.3], [x-0.3, y+0.3], [x-0.3, y-0.3]
            ])
            obstructions.append(obs)

    return {
        "name": "Forest of 50 Columns",
        "room_area": room.area,
        "obstruction_count": len(obstructions),
        "danger": "Performance collapse. apply_obstructions with 50 diffs = slow"
    }

def test_2b_obstruction_larger_than_room():
    """
    Obstruction bigger than room itself
    Expected: System must reject or handle gracefully
    Danger: Negative area, invalid geometry
    """
    room = Polygon([[0,0], [5,0], [5,5], [0,5], [0,0]])
    obs = Polygon([[-5,-5], [10,-5], [10,10], [-5,10], [-5,-5]])

    return {
        "name": "Oversized Obstruction",
        "room_area": room.area,
        "obs_area": obs.area,
        "danger": "effective_room = room.difference(obs) = empty polygon → crash"
    }

def test_2c_touching_obstructions():
    """
    Two obstructions touching at corner
    Expected: Union must not create self-intersection
    Danger: Touching polygons cause topology errors
    """
    obs1 = Polygon([[0,0], [2,0], [2,2], [0,2], [0,0]])
    obs2 = Polygon([[2,0], [4,0], [4,2], [2,2], [2,0]])  # Touches at x=2

    return {
        "name": "Touching Obstructions",
        "danger": "unary_union([obs1, obs2]) may create MultiPolygon issues"
    }

def test_2d_zero_width_wall():
    """
    Wall with zero thickness (line)
    Expected: System must reject or ignore
    Danger: Zero-area polygon → buffer(0) may fail
    """
    obs = Polygon([[0,0], [10,0], [10,0], [0,0], [0,0]])  # Zero height

    return {
        "name": "Zero-Width Wall",
        "obs_area": obs.area,
        "danger": "Polygon with area=0 → difference() unpredictable"
    }

# ============================================================
# TEST CATEGORY 3: NUMERICAL HELL
# ============================================================

def test_3a_floating_point_trap():
    """
    Device placed EXACTLY at obstruction boundary
    Expected: System must not crash on precision edge case
    Danger: contains() returns False due to 1e-16 error
    """
    room = Polygon([[0,0], [10,0], [10,10], [0,10], [0,0]])
    obs = Polygon([[5,0], [5,10], [6,10], [6,0], [5,0]])
    device = Point(5.0000000001, 5)  # Just outside (numerically)

    return {
        "name": "Floating Point Trap",
        "device_x": 5.0000000001,
        "danger": "Device at boundary → valid/invalid depends on epsilon"
    }

def test_3b_micro_room():
    """
    Room smaller than device coverage radius
    Expected: One device should PASS easily
    Danger: Division by zero or percentage overflow
    """
    room = Polygon([[0,0], [0.5,0], [0.5,0.5], [0,0.5], [0,0]])
    devices = [Point(0.25, 0.25)]

    return {
        "name": "Micro Room (0.25m²)",
        "room_area": room.area,
        "danger": "Coverage percent calculation: (tiny / tiny) may be unstable"
    }

def test_3c_giant_room():
    """
    Airport hangar: 200m × 100m
    Expected: System handles large coordinates
    Danger: Memory overflow, slow polygon ops
    """
    room = Polygon([[0,0], [200,0], [200,100], [0,100], [0,0]])

    return {
        "name": "Giant Hangar (20,000m²)",
        "room_area": room.area,
        "expected_devices": math.ceil(20000 / 127),
        "danger": "20,000m² / 127m² per device = ~157 devices. MIP solver timeout?"
    }

# ============================================================
# TEST CATEGORY 4: NFPA 72 EDGE CASES
# ============================================================

def test_4a_heat_detector_in_small_room():
    """
    Heat detector (radius 4.27m) in 8×8m room
    Expected: FAIL with 1 device, PASS with 4 devices
    Danger: Wrong device type selection = wrong radius
    """
    room = Polygon([[0,0], [8,0], [8,8], [0,8], [0,0]])
    # Heat detector: spacing 6.1m, radius 4.27m
    # Corner distance: sqrt(4²+4²) = 5.66m > 4.27m
    devices = [Point(4, 4)]

    return {
        "name": "Heat Detector (Small Radius)",
        "device_type": "HEAT_FIXED",
        "radius": 4.27,
        "corner_distance": round(math.sqrt(32), 2),
        "danger": "1 device will FAIL. System must auto-correct to 4 devices"
    }

def test_4b_mixed_device_types():
    """
    Room with both smoke and heat detectors
    Expected: System must use correct radius for each
    Danger: Using smoke radius (6.37) for heat detector (4.27) = unsafe PASS
    """
    return {
        "name": "Mixed Device Types",
        "danger": "If system uses global radius instead of per-device radius → CATASTROPHE"
    }

# ============================================================
# TEST CATEGORY 5: REAL-WORLD CATASTROPHES
# ============================================================

def test_5a_atrium_with_mezzanine():
    """
    Atrium: 30×30m, mezzanine floor at 5m height
    Expected: Ceiling height affects device selection
    Danger: System ignores ceiling height → wrong device type → wrong radius
    """
    return {
        "name": "Atrium with Mezzanine",
        "ceiling_height": 10,
        "mezzanine_height": 5,
        "danger": "NFPA 72: >9.1m ceiling needs beam detector, not spot detector"
    }

def test_5b_stairwell():
    """
    Stairwell: L-shape vertical, each tread is obstruction
    Expected: 3D coverage needed
    Danger: System is 2D only → misses vertical gaps
    """
    return {
        "name": "Stairwell (3D Problem)",
        "danger": "FireAI is 2D. Stairwell needs 3D coverage. System gives FALSE PASS"
    }

def test_5c_open_office_with_partitions():
    """
    Open office: 40×20m, 20 cubicle partitions
    Expected: Partitions block smoke → need more devices
    Danger: Partitions < ceiling height = partial obstruction
    """
    return {
        "name": "Open Office with Partitions",
        "partition_count": 20,
        "danger": "Partitions block smoke path but not fully. System treats as full obstruction or ignores"
    }

# ============================================================
# SUMMARY
# ============================================================

def run_all_stress_tests():
    tests = [
        test_1a_ultra_thin_corridor,
        test_1b_concave_c_shape,
        test_1c_donut_room,
        test_2a_forest_of_columns,
        test_2b_obstruction_larger_than_room,
        test_2c_touching_obstructions,
        test_2d_zero_width_wall,
        test_3a_floating_point_trap,
        test_3b_micro_room,
        test_3c_giant_room,
        test_4a_heat_detector_in_small_room,
        test_4b_mixed_device_types,
        test_5a_atrium_with_mezzanine,
        test_5b_stairwell,
        test_5c_open_office_with_partitions,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            result["status"] = "DEFINED"
        except Exception as e:
            result = {"name": test.__name__, "status": "CRASH", "error": str(e)}
        results.append(result)

    return results

if __name__ == "__main__":
    results = run_all_stress_tests()
    print("\n" + "="*70)
    print("FIREAI STRESS TEST RESULTS")
    print("="*70)
    for r in results:
        status = r.get("status", "UNKNOWN")
        icon = "✅" if status == "DEFINED" else "💥"
        print(f"\n{icon} {r.get('name', 'UNKNOWN')}")
        for k, v in r.items():
            if k not in ["name", "status"]:
                print(f"   {k}: {v}")