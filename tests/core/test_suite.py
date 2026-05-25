#!/usr/bin/env python3
"""
test_suite.py — 10 reference rooms with known expected outcomes.
Run before every deployment:  python test_suite.py
Exit 0 = all pass.  Exit 1 = regression detected.
"""
import sys, json, time

ROOMS = [
    # (label, polygon, height, expect_compliant, expect_min_detectors)
    ("small_office_3x4",     [[0,0],[3,0],[3,4],[0,4]],           3.0, True,  1),
    ("medium_office_10x8",   [[0,0],[10,0],[10,8],[0,8]],         3.0, True,  2),
    ("large_hall_20x15",     [[0,0],[20,0],[20,15],[0,15]],       4.0, True,  4),
    ("corridor_20x2",        [[0,0],[20,0],[20,2],[0,2]],         3.0, True,  2),
    ("warehouse_30x25",      [[0,0],[30,0],[30,25],[0,25]],       8.0, True,  6),
    ("l_shape_room",         [[0,0],[10,0],[10,5],[5,5],[5,10],[0,10]], 3.0, True, 3),
    ("kitchen_6x5",          [[0,0],[6,0],[6,5],[0,5]],           3.0, False, 0),
    ("stairwell_3x3",        [[0,0],[3,0],[3,3],[0,3]],           3.0, True,  1),
    ("open_plan_40x20",      [[0,0],[40,0],[40,20],[0,20]],       3.5, True,  8),
    ("narrow_corridor_15x1.5",[[0,0],[15,0],[15,1.5],[0,1.5]],   3.0, True,  2),
]

def make_spec(label, polygon, height):
    from fireai.core.nfpa72_models import RoomSpec, CeilingSpec, CeilingType
    ceiling = CeilingSpec.create_safe(
        height_at_low_point_m=height,
        height_at_high_point_m=height,
        ceiling_type=CeilingType.FLAT,
    )
    return RoomSpec(
        room_id=label,
        polygon=[tuple(p) for p in polygon],
        ceiling_spec=ceiling,
        hvac_ducts=[],
    )

def run():
    from fireai.core.fireai_core import FireAISystem
    from pathlib import Path
    system = FireAISystem(":memory:")   # isolated test DB
    # Use FireAISystem

    passed = 0
    failed = 0
    t0     = time.time()

    print(f"{'Room':<30} {'Compliant':>10} {'Detectors':>10} {'Conf':>8} {'Status':>8}")
    print("-" * 72)

    for label, poly, height, exp_compliant, exp_min_det in ROOMS:
        spec = make_spec(label, poly, height)
        r = system.analyse_room(spec, run_resilience=True)

        ok = (
            r.compliant == exp_compliant and
            len(r.detector_positions) >= exp_min_det and
            r.confidence.value not in ("UNSAFE", "LOW")
        )

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(
            f"{label:<30} {str(r.compliant):>10} "
            f"{len(r.detector_positions):>10} {r.confidence.value:>8} {status:>8}"
        )

    elapsed = time.time() - t0
    print("-" * 72)
    print(f"Results: {passed}/{len(ROOMS)} passed in {elapsed:.2f}s")

    if failed:
        print(f"\nREGRESSION DETECTED — {failed} test(s) failed. Do NOT deploy.")
        sys.exit(1)
    else:
        print("\nAll tests passed. Safe to deploy.")
        sys.exit(0)

if __name__ == "__main__":
    run()

