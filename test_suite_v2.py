"""
test_suite_v2.py — FireAI Realistic Test Suite
10 غرف واقعية تُختبر بـ DensityOptimizer V7.3 + FloorAnalyser V2.0
كل غرفة = assert واحد + سبب واضح
"""
import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fireai", "core"))

from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room
from floor_analyser import FloorAnalyser

# ─────────────────────────────────────────────────────────────
# 10 غرف واقعية
# ─────────────────────────────────────────────────────────────
REALISTIC_ROOMS = [
    {"room_id": "lobby_12x8",       "name": "Lobby",              "w": 12, "l": 8,  "h": 3.5},
    {"room_id": "parking_30x20",    "name": "Parking Garage",     "w": 30, "l": 20, "h": 3.0},
    {"room_id": "stairwell_3x3",    "name": "Stairwell",          "w": 3,  "l": 3,  "h": 3.0},
    {"room_id": "server_room_8x6",  "name": "Server Room",        "w": 8,  "l": 6,  "h": 3.0},
    {"room_id": "corridor_20x2",    "name": "Corridor",           "w": 20, "l": 2,  "h": 3.0},
    {"room_id": "kitchen_6x5",      "name": "Kitchen",            "w": 6,  "l": 5,  "h": 3.0},
    {"room_id": "open_office_25x15","name": "Open Office",        "w": 25, "l": 15, "h": 3.5},
    {"room_id": "warehouse_50x40",  "name": "Warehouse",          "w": 50, "l": 40, "h": 6.0},
    {"room_id": "meeting_6x5",      "name": "Meeting Room",       "w": 6,  "l": 5,  "h": 3.0},
    {"room_id": "restroom_3x2",     "name": "Restroom",           "w": 3,  "l": 2,  "h": 3.0},
]


def test_coverage_above_99():
    """كل غرفة يجب أن تحقق تغطية >= 99.9%. NFPA 72 §17.6.3 — spacing must achieve full coverage"""
    opt = DensityOptimizer()
    for r in REALISTIC_ROOMS:
        room = Room(name=r["name"], width=r["w"], length=r["l"], ceiling_height=r["h"])
        layout = opt.optimize(room)
        assert layout.coverage_pct >= 99.9, (
            f"{r['name']}: coverage {layout.coverage_pct:.2f}% < 99.9%"
        )


def test_nfpa_zero_violations():
    """كل غرفة يجب أن تحقق nfpa_valid = True. NFPA 72 §17.6.3 — no spacing violations allowed"""
    opt = DensityOptimizer()
    for r in REALISTIC_ROOMS:
        room = Room(name=r["name"], width=r["w"], length=r["l"], ceiling_height=r["h"])
        layout = opt.optimize(room)
        assert layout.nfpa_valid, (
            f"{r['name']}: NFPA violations found — {layout.violations}"
        )


def test_at_least_one_detector():
    """كل غرفة يجب أن تحتوي كاشف واحد على الأقل. NFPA 72 §17.5.3 — at least one detector per room"""
    opt = DensityOptimizer()
    for r in REALISTIC_ROOMS:
        room = Room(name=r["name"], width=r["w"], length=r["l"], ceiling_height=r["h"])
        layout = opt.optimize(room)
        assert layout.count >= 1, (
            f"{r['name']}: zero detectors placed"
        )


def test_realistic_rooms():
    """10 غرف واقعية — كل غرفة يجب أن تجتاز triple-check gate."""
    opt = DensityOptimizer()
    analyser = FloorAnalyser("test_floor", opt)

    rooms_dicts = [
        {**r, "polygon_coords": [(0, 0), (r["w"], 0), (r["w"], r["l"]), (0, r["l"])]}
        for r in REALISTIC_ROOMS
    ]

    report = analyser.analyse(rooms_dicts)

    print(f"\n{'Room':<25} {'Dets':<5} {'Cov%':<8} {'NFPA':<6} {'Proof':<6} {'FB':<4} {'Method':<12} {'Status'}")
    print("-" * 85)

    for s in report.room_summaries:
        status = "PASS" if s.compliant else "FAIL"
        print(f"{s.name:<25} {s.detector_count:<5} {s.coverage_pct:<8.2f} "
              f"{str(s.nfpa_valid):<6} {str(s.proof_valid):<6} "
              f"{str(s.fallback_used):<4} {s.method:<12} {status}")

    print(f"\nTotal detectors: {report.total_detectors}")
    print(f"Fully compliant: {report.fully_compliant}")
    print(f"Safe to submit:  {report.safe_to_submit}")
    print(f"Non-compliant:   {report.non_compliant_rooms}")
    print(f"Unsafe:          {report.unsafe_rooms}")
    print(f"Warnings:        {report.floor_warnings}")

    failed = [s for s in report.room_summaries if not s.compliant]
    if failed:
        print(f"\nFAILED ROOMS ({len(failed)}/10):")
        for s in failed:
            print(f"  * {s.name}: cov={s.coverage_pct:.2f}% nfpa={s.nfpa_valid} "
                  f"proof={s.proof_valid} fallback={s.fallback_used}")

    assert report.fully_compliant, (
        f"Realistic test FAILED: {len(failed)}/10 rooms non-compliant. "
        f"Rooms: {[s.name for s in failed]}"
    )


def test_boundary_condition_detection():
    """
    يتحقق من وجود حالة boundary (proof_valid=False مع coverage>99.9%).
    هذه تمثل الـ 0.8% من الحالات المعروفة الموثقة في TECHNICAL_HONESTY.md.

    ملاحظة: التحذير الحي BOUNDARY_LIMIT سيُنفذ في المرحلة 2.
    هذا الاختبار يكشف الحالة فقط — لا يتحقق من التحذير بعد.
    """
    opt = DensityOptimizer()
    boundary_cases = []
    for r in REALISTIC_ROOMS:
        room = Room(name=r["name"], width=r["w"], length=r["l"], ceiling_height=r["h"])
        layout = opt.optimize(room)
        if not layout.proof_valid and layout.coverage_pct > 99.9:
            boundary_cases.append((r["name"], layout.coverage_pct, layout.count))

    if boundary_cases:
        print(f"\nBOUNDARY CASES DETECTED ({len(boundary_cases)}):")
        for name, cov, cnt in boundary_cases:
            print(f"  * {name}: coverage={cov:.2f}% detectors={cnt} — needs BOUNDARY_LIMIT warning (Phase 2)")
    else:
        print("\nNo boundary cases in 10 realistic rooms (expected — 0.8% frequency).")
        print("BOUNDARY_LIMIT warning will be verified in Phase 2 with larger test set.")


if __name__ == "__main__":
    print("=" * 85)
    print("FireAI Test Suite V2 — 10 Realistic Rooms")
    print("DensityOptimizer V7.3 + FloorAnalyser V2.0")
    print("=" * 85)

    results = []

    try:
        test_coverage_above_99()
        results.append(("test_coverage_above_99", "PASS"))
    except AssertionError as e:
        results.append(("test_coverage_above_99", f"FAIL: {e}"))

    try:
        test_nfpa_zero_violations()
        results.append(("test_nfpa_zero_violations", "PASS"))
    except AssertionError as e:
        results.append(("test_nfpa_zero_violations", f"FAIL: {e}"))

    try:
        test_at_least_one_detector()
        results.append(("test_at_least_one_detector", "PASS"))
    except AssertionError as e:
        results.append(("test_at_least_one_detector", f"FAIL: {e}"))

    try:
        test_realistic_rooms()
        results.append(("test_realistic_rooms", "PASS"))
    except AssertionError as e:
        results.append(("test_realistic_rooms", f"FAIL: {e}"))

    # الاختبار الخامس — كشف فقط، لا فشل
    test_boundary_condition_detection()
    results.append(("test_boundary_condition_detection", "INFO (see output)"))

    print("\n" + "=" * 85)
    print("RESULTS SUMMARY")
    print("=" * 85)
    for name, status in results:
        print(f"  {name:<40} {status}")

    all_passed = all(s == "PASS" for n, s in results if "INFO" not in s)
    if all_passed:
        print("\nALL TESTS PASSED — V7.3 verified on 10 realistic rooms")
    else:
        print("\nSOME TESTS FAILED — see details above")
    print("=" * 85)
