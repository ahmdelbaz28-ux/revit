#!/usr/bin/env python3
"""
run_real_dxf_test.py — FireAI V5.1.2 Real DXF Test Script
Tests the system on real-world DXF files from consulting engineers.
"""

import sys
import argparse
from pathlib import Path
from shapely.geometry import Polygon

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.dxf_parser import DXFParser
from nfpa72_models import RoomSpec, CeilingSpec, CeilingType, DetectorType
from core.floor_orchestrator import FloorOrchestrator
from audit_trail import AuditTrail


def test_dxf_file(dxf_path: str, verbose: bool = False) -> bool:
    """Test a single DXF file. Returns True if successful."""
    path = Path(dxf_path)
    if not path.exists():
        print(f"❌ File not found: {dxf_path}")
        return False
    
    print(f"\n{'='*60}")
    print(f"Testing: {path.name}")
    print('='*60)
    
    # 1. Parse DXF
    if verbose:
        print(f"\n[1/3] Parsing DXF...")
    
    parser = DXFParser()
    try:
        result = parser.parse(str(path))
    except Exception as e:
        print(f"❌ Parse failed: {e}")
        return False
    
    print(f"  → Found {result.room_count} rooms ({result.total_area_m2:.1f} m²)")
    
    if result.room_count == 0:
        print(f"⚠️  WARNING: No rooms detected!")
        # Don't fail - might be empty floor
    
    # 2. Build RoomSpecs
    if verbose:
        print(f"\n[2/3] Building RoomSpecs...")
    
    room_specs = []
    for room in result.rooms:
        # RoomSpec: name, width, depth, height, polygon, ceiling, detector, occupancy
        bbox = room.polygon.bounds  # (minx, miny, maxx, maxy)
        width = bbox[2] - bbox[0]
        depth = bbox[3] - bbox[1]
        
        spec = RoomSpec(
            name=room.room_id,
            width_m=width,
            depth_m=depth,
            height_m=3.0,  # 3m height
            polygon=room.polygon,
            ceiling_spec=CeilingSpec(3.0),
            detector_type=DetectorType.SMOKE,
            occupancy_type="office",
        )
        room_specs.append(spec)
    
    if not room_specs:
        print(f"⚠️  No valid rooms to process")
        return True  # Not a failure
    
    # 3. Process rooms
    if verbose:
        print(f"\n[3/3] Solving...")
    
    try:
        orch = FloorOrchestrator()
        floor_result = orch.process(room_specs, project_name=path.stem, source_dxf=str(path))
    except Exception as e:
        print(f"❌ Processing failed: {e}")
        return False
    
    # Report
    print(f"\n  Rooms: {floor_result.rooms_passed}/{floor_result.total_rooms} passed")
    print(f"  Detectors: {floor_result.total_detectors}")
    print(f"  Status: {floor_result.status}")
    
    if floor_result.rooms_failed > 0:
        print(f"  ⚠️  {floor_result.rooms_failed} rooms failed coverage")
        for r in floor_result.room_results:
            if r.status == "FAIL":
                print(f"    - {r.room_id}: {r.errors}")
    
    success = floor_result.status in ("PASS", "PARTIAL")
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}")
    
    return success


def main():
    parser = argparse.ArgumentParser(description="Test FireAI on real DXF files")
    parser.add_argument("dxf_files", nargs="*", help="DXF files to test")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-d", "--dir", help="Directory containing DXF files")
    args = parser.parse_args()
    
    files = []
    
    if args.dir:
        dir_path = Path(args.dir)
        if dir_path.exists():
            files = list(dir_path.glob("*.dxf"))
            print(f"Found {len(files)} DXF files in {args.dir}")
    
    if args.dxf_files:
        files.extend([Path(f) for f in args.dxf_files])
    
    if not files:
        # Use fixtures
        fixtures = Path("tests/fixtures")
        if fixtures.exists():
            files = list(fixtures.glob("*.dxf"))
            print(f"Using {len(files)} fixture files")
    
    if not files:
        print("❌ No DXF files found")
        return 1
    
    passed = 0
    failed = 0
    
    for f in files:
        if test_dxf_file(str(f), args.verbose):
            passed += 1
        else:
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print('='*60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())