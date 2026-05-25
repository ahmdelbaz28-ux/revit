#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  FireAI V29 — NUCLEAR STRESS TEST — اضغط على النواة                     ║
║  5,000,000 غرفة × 50 طابق × LINE entities × NaN/Inf poison            ║
╚══════════════════════════════════════════════════════════════════════════╝

SAFETY-CRITICAL: This test presses on the CORE of the program.
- Geometry.calculate_area() under extreme load
- DWGParser.extract_rooms_from_chaos() with millions of LINE entities
- _assemble_closed_polygons() with thousands of disjoint closed polygons
- UniversalDataModel with massive element counts
- NaN/Inf poisoning resistance at scale

PER THE CONTRACT: Never modify tests — only fix production code.
"""

import sys
import os
import time
import math
import random
import traceback
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# ═══════════════════════════════════════════════════════════════════════
# TEST 1: Geometry.calculate_area() — 5,000,000 rooms
# ═══════════════════════════════════════════════════════════════════════

def test_calculate_area_5m_rooms():
    """Press Geometry.calculate_area() with 5 million rooms."""
    from core.models import Point3D, Geometry

    ROOM_COUNT = 5_000_000
    print(f"\n[TEST 1] Geometry.calculate_area() × {ROOM_COUNT:,} rooms")

    start = time.time()
    correct_count = 0
    error_count = 0
    total_area = 0.0

    for i in range(ROOM_COUNT):
        # Generate diverse room shapes
        width = 3.0 + (i % 50) * 0.5
        depth = 3.0 + (i % 40) * 0.5

        pts = [
            Point3D(0, 0, 0),
            Point3D(width, 0, 0),
            Point3D(width, depth, 0),
            Point3D(0, depth, 0),
        ]

        geom = Geometry(points=pts, polyline_closed=True)
        area = geom.calculate_area()

        expected = width * depth
        if abs(area - expected) < 0.01:
            correct_count += 1
        else:
            error_count += 1
            if error_count <= 3:
                print(f"  ❌ Room {i}: expected area={expected:.4f}, got={area:.4f}")

        total_area += area

        if i > 0 and i % 1_000_000 == 0:
            elapsed = time.time() - start
            print(f"  ... {i:,}/{ROOM_COUNT:,} rooms processed ({elapsed:.1f}s)")

    elapsed = time.time() - start

    print(f"  ✅ {correct_count:,}/{ROOM_COUNT:,} rooms correct area")
    print(f"  ❌ {error_count:,} area errors")
    print(f"  ⏱  Total time: {elapsed:.2f}s ({ROOM_COUNT/elapsed:,.0f} rooms/sec)")
    print(f"  📐 Total area: {total_area:,.2f} m²")

    assert error_count == 0, f"{error_count} rooms had incorrect area calculations!"
    assert elapsed < 300, f"Took too long: {elapsed:.1f}s for {ROOM_COUNT:,} rooms"
    return True


# ═══════════════════════════════════════════════════════════════════════
# TEST 2: _assemble_closed_polygons() — 10,000 disjoint rooms from LINEs
# ═══════════════════════════════════════════════════════════════════════

def test_assemble_10k_closed_polygons_from_lines():
    """Press _assemble_closed_polygons() with 10,000 rooms = 40,000 LINEs."""
    from parsers.dwg_parser import DWGParser

    ROOM_COUNT = 10_000
    print(f"\n[TEST 2] _assemble_closed_polygons() × {ROOM_COUNT:,} rooms from LINEs")

    # Build 10,000 non-overlapping rectangular rooms, each from 4 LINEs
    lines = []
    expected_areas = []

    for i in range(ROOM_COUNT):
        # Grid layout: 100 columns × 100 rows, with 1m gap
        col = i % 100
        row = i // 100
        x_off = col * 12.0  # 10m room + 2m gap
        y_off = row * 12.0

        width = 6.0 + (i % 5) * 1.0  # 6-10m
        depth = 5.0 + (i % 7) * 0.5  # 5-8.5m

        # 4 LINEs forming a closed rectangle
        lines.append(((x_off, y_off), (x_off + width, y_off)))
        lines.append(((x_off + width, y_off), (x_off + width, y_off + depth)))
        lines.append(((x_off + width, y_off + depth), (x_off, y_off + depth)))
        lines.append(((x_off, y_off + depth), (x_off, y_off)))

        expected_areas.append(width * depth)

    print(f"  📦 {len(lines):,} LINE entities for {ROOM_COUNT:,} rooms")

    start = time.time()
    parser = DWGParser()
    closed_polygons = parser._assemble_closed_polygons(lines)
    elapsed = time.time() - start

    print(f"  🔶 Found {len(closed_polygons):,} closed polygons")
    print(f"  ⏱  Assembly time: {elapsed:.2f}s")

    # Verify count
    assert len(closed_polygons) >= ROOM_COUNT, (
        f"Expected ≥{ROOM_COUNT:,} polygons, got {len(closed_polygons):,}! "
        f"Missing {ROOM_COUNT - len(closed_polygons):,} rooms = ZERO FIRE PROTECTION!"
    )

    # Verify areas
    area_errors = 0
    from core.models import Point3D, Geometry
    for idx, poly in enumerate(closed_polygons[:ROOM_COUNT]):
        if len(poly) >= 3:
            pts_3d = [Point3D(x=vx, y=vy, z=0.0) for vx, vy in poly]
            geom = Geometry(points=pts_3d, polyline_closed=True)
            calc_area = geom.calculate_area()

            # Find which expected area this corresponds to (by position)
            # Since polygons may come out in different order, just check > 0
            if calc_area <= 0:
                area_errors += 1
                if area_errors <= 3:
                    print(f"  ❌ Polygon {idx}: zero/negative area={calc_area}")

    print(f"  ✅ Area check: {len(closed_polygons) - area_errors:,}/{len(closed_polygons):,} positive areas")
    assert area_errors == 0, f"{area_errors} polygons had zero/negative area!"
    assert elapsed < 120, f"Assembly took too long: {elapsed:.1f}s"

    return True


# ═══════════════════════════════════════════════════════════════════════
# TEST 3: extract_rooms_from_chaos() — 5,000 rooms + NaN/Inf poison
# ═══════════════════════════════════════════════════════════════════════

def test_extract_rooms_from_chaos_5k_rooms_poisoned():
    """Press extract_rooms_from_chaos() with 5,000 rooms + 50% NaN/Inf poison."""
    from parsers.dwg_parser import DWGParser

    ROOM_COUNT = 5_000
    POISON_RATE = 0.5
    print(f"\n[TEST 3] extract_rooms_from_chaos() × {ROOM_COUNT:,} rooms + {POISON_RATE*100:.0f}% poison")

    entities = []

    # Generate valid LINE rooms
    valid_room_count = 0
    for i in range(ROOM_COUNT):
        col = i % 70
        row = i // 70
        x_off = col * 15.0
        y_off = row * 15.0
        width = 8.0 + (i % 6)
        depth = 6.0 + (i % 8)

        for sx, sy, ex, ey in [
            (x_off, y_off, x_off + width, y_off),
            (x_off + width, y_off, x_off + width, y_off + depth),
            (x_off + width, y_off + depth, x_off, y_off + depth),
            (x_off, y_off + depth, x_off, y_off),
        ]:
            e = Mock()
            e.dxftype = Mock(return_value='LINE')
            e.dxf = Mock()
            e.dxf.start = Mock(x=sx, y=sy)
            e.dxf.end = Mock(x=ex, y=ey)
            entities.append(e)
            valid_room_count += 1

    # Generate poisoned LINE entities (NaN / Inf)
    poison_count = int(valid_room_count * POISON_RATE)
    poison_types = [float('nan'), float('inf'), float('-inf'), float('nan')]
    for i in range(poison_count):
        e = Mock()
        e.dxftype = Mock(return_value='LINE')
        e.dxf = Mock()
        poison_val = poison_types[i % len(poison_types)]
        e.dxf.start = Mock(x=poison_val, y=poison_val)
        e.dxf.end = Mock(x=poison_val, y=poison_val)
        entities.append(e)

    # Also add some LWPOLYLINE valid rooms
    for i in range(500):
        e = Mock()
        e.dxftype = Mock(return_value='LWPOLYLINE')
        e.get_points = Mock(return_value=[
            (i * 20.0, 0.0), (i * 20.0 + 10.0, 0.0),
            (i * 20.0 + 10.0, 8.0), (i * 20.0, 8.0),
        ])
        entities.append(e)

    # Add poisoned LWPOLYLINE
    for i in range(200):
        e = Mock()
        e.dxftype = Mock(return_value='LWPOLYLINE')
        e.get_points = Mock(return_value=[
            (0.0, float('nan')), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0),
        ])
        entities.append(e)

    random.shuffle(entities)  # Mix valid and poison

    mock_doc = Mock()
    mock_doc.modelspace.return_value = entities

    print(f"  📦 {len(entities):,} total entities ({valid_room_count:,} valid LINEs, {poison_count:,} poisoned LINEs, 500 valid POLYLINEs, 200 poisoned POLYLINEs)")

    start = time.time()
    parser = DWGParser()
    rooms = parser.extract_rooms_from_chaos(mock_doc)
    elapsed = time.time() - start

    print(f"  🔶 Extracted {len(rooms):,} rooms")
    print(f"  ⏱  Extraction time: {elapsed:.2f}s")

    # Must find at least the LINE-based rooms + POLYLINE rooms
    min_expected = ROOM_COUNT + 500  # 5000 LINE rooms + 500 POLYLINE rooms
    assert len(rooms) >= min_expected, (
        f"Expected ≥{min_expected:,} rooms, got {len(rooms):,}! "
        f"Missing {min_expected - len(rooms):,} rooms = PEOPLE DIE!"
    )

    # Verify no poisoned rooms slipped through
    nan_rooms = 0
    for room in rooms:
        if room.geometry and room.geometry.points:
            for pt in room.geometry.points:
                if math.isnan(pt.x) or math.isinf(pt.x) or math.isnan(pt.y) or math.isinf(pt.y):
                    nan_rooms += 1
                    break

    assert nan_rooms == 0, f"{nan_rooms} rooms with NaN/Inf coordinates leaked through! SAFETY VIOLATION!"

    # Verify all rooms have positive area
    zero_area = 0
    for room in rooms:
        if room.geometry and room.geometry.area <= 0:
            zero_area += 1

    assert zero_area == 0, f"{zero_area} rooms with zero/negative area!"

    assert elapsed < 120, f"Extraction took too long: {elapsed:.1f}s"

    return True


# ═══════════════════════════════════════════════════════════════════════
# TEST 4: UniversalDataModel — 100,000 elements CRUD stress
# ═══════════════════════════════════════════════════════════════════════

def test_database_100k_elements():
    """Press UniversalDataModel with 100,000 elements CRUD operations."""
    from core.database import UniversalDataModel
    from core.models import (
        UniversalElement, SemanticProperties, ElementType,
        Geometry, Point3D, ChangeSource
    )

    ELEMENT_COUNT = 100_000
    print(f"\n[TEST 4] UniversalDataModel × {ELEMENT_COUNT:,} elements CRUD")

    db = UniversalDataModel(":memory:")

    # Phase 1: Create
    start = time.time()
    element_ids = []
    for i in range(ELEMENT_COUNT):
        width = 5.0 + (i % 20) * 0.5
        depth = 4.0 + (i % 15) * 0.5
        elem = UniversalElement(
            properties=SemanticProperties(
                element_type=ElementType.ROOM if i % 3 != 0 else ElementType.WALL,
                name=f"Room_{i}",
                height=3.0 + (i % 5) * 0.5,
            ),
            geometry=Geometry(
                points=[
                    Point3D(0, 0, 0), Point3D(width, 0, 0),
                    Point3D(width, depth, 0), Point3D(0, depth, 0),
                ],
                polyline_closed=True,
            )
        )
        db.add_element(elem)
        element_ids.append(elem.element_id)

        if i > 0 and i % 25_000 == 0:
            elapsed = time.time() - start
            print(f"  ... Created {i:,}/{ELEMENT_COUNT:,} ({elapsed:.1f}s)")

    create_time = time.time() - start
    print(f"  ✅ Created {len(db.elements):,} elements in {create_time:.2f}s")

    assert len(db.elements) == ELEMENT_COUNT, f"Expected {ELEMENT_COUNT:,} elements, got {len(db.elements):,}"

    # Phase 2: Read & verify areas
    start = time.time()
    zero_area_count = 0
    for eid, elem in list(db.elements.items())[:10000]:  # Sample 10k
        if elem.geometry and elem.geometry.area <= 0:
            zero_area_count += 1

    read_time = time.time() - start
    print(f"  ✅ Read 10,000 samples in {read_time:.2f}s ({zero_area_count} zero-area)")

    assert zero_area_count == 0, f"{zero_area_count} elements have zero area after add!"

    # Phase 3: Update 10,000 elements
    start = time.time()
    for i in range(10_000):
        eid = element_ids[i]
        db.update_element(eid, {"properties": {"height": 4.0 + (i % 3)}}, source=ChangeSource.REVIT)

    update_time = time.time() - start
    print(f"  ✅ Updated 10,000 elements in {update_time:.2f}s")

    # Phase 4: Soft-delete 5,000 elements
    start = time.time()
    for i in range(5_000):
        eid = element_ids[i]
        db.delete_element(eid, source=ChangeSource.SYSTEM)

    delete_time = time.time() - start
    active_count = len([e for e in db.elements.values() if not e.is_deleted])
    deleted_count = len([e for e in db.elements.values() if e.is_deleted])
    print(f"  ✅ Soft-deleted 5,000 in {delete_time:.2f}s ({active_count:,} active, {deleted_count:,} deleted)")

    assert deleted_count >= 5_000, f"Expected ≥5,000 deleted, got {deleted_count}"

    return True


# ═══════════════════════════════════════════════════════════════════════
# TEST 5: Polygon assembly edge cases — fragmented, overlapping, degenerate
# ═══════════════════════════════════════════════════════════════════════

def test_polygon_assembly_edge_cases():
    """Press _assemble_closed_polygons() with pathological LINE configurations."""
    from parsers.dwg_parser import DWGParser

    print(f"\n[TEST 5] _assemble_closed_polygons() — pathological edge cases")

    parser = DWGParser()

    # Case 5a: Single open chain (not closed) — should produce 0 polygons
    open_lines = [
        ((0, 0), (10, 0)),
        ((10, 0), (10, 10)),
        ((10, 10), (20, 10)),  # Diverges — not closed
    ]
    result = parser._assemble_closed_polygons(open_lines)
    print(f"  5a. Open chain: {len(result)} polygons (expected 0)")
    assert len(result) == 0, f"Open chain should produce 0 polygons, got {len(result)}"

    # Case 5b: Triangle from 3 LINEs
    triangle_lines = [
        ((0, 0), (10, 0)),
        ((10, 0), (5, 8.66)),
        ((5, 8.66), (0, 0)),
    ]
    result = parser._assemble_closed_polygons(triangle_lines)
    print(f"  5b. Triangle: {len(result)} polygons (expected 1)")
    assert len(result) == 1, f"Triangle should produce 1 polygon, got {len(result)}"

    # Verify triangle area ≈ 43.3 m² (0.5 * 10 * 8.66)
    from core.models import Point3D, Geometry
    if result:
        pts_3d = [Point3D(x=vx, y=vy, z=0.0) for vx, vy in result[0]]
        geom = Geometry(points=pts_3d, polyline_closed=True)
        area = geom.calculate_area()
        expected = 0.5 * 10.0 * 8.66
        print(f"  5b. Triangle area: {area:.2f} (expected ≈{expected:.2f})")
        assert abs(area - expected) < 1.0, f"Triangle area off: {area:.2f} vs {expected:.2f}"

    # Case 5c: 1,000 disjoint triangles — must find all 1,000
    many_triangles = []
    for i in range(1_000):
        x_off = (i % 40) * 20.0
        y_off = (i // 40) * 20.0
        many_triangles.append(((x_off, y_off), (x_off + 10, y_off)))
        many_triangles.append(((x_off + 10, y_off), (x_off + 5, y_off + 8.66)))
        many_triangles.append(((x_off + 5, y_off + 8.66), (x_off, y_off)))

    start = time.time()
    result = parser._assemble_closed_polygons(many_triangles)
    elapsed = time.time() - start
    print(f"  5c. 1,000 disjoint triangles: {len(result)} found in {elapsed:.2f}s")
    assert len(result) == 1_000, f"Expected 1,000 triangles, got {len(result)}"

    # Case 5d: Empty input
    result = parser._assemble_closed_polygons([])
    assert len(result) == 0, "Empty input should produce 0 polygons"

    # Case 5e: Single LINE (not a polygon)
    result = parser._assemble_closed_polygons([((0, 0), (10, 10))])
    assert len(result) == 0, "Single LINE should produce 0 polygons"

    # Case 5f: Degenerate — two overlapping rectangles sharing edges
    shared_lines = [
        # Rectangle 1
        ((0, 0), (10, 0)),
        ((10, 0), (10, 10)),
        ((10, 10), (0, 10)),
        ((0, 10), (0, 0)),
        # Rectangle 2 (adjacent, sharing edge x=10)
        ((10, 0), (20, 0)),
        ((20, 0), (20, 10)),
        ((20, 10), (10, 10)),
        ((10, 10), (10, 0)),
    ]
    result = parser._assemble_closed_polygons(shared_lines)
    print(f"  5f. Two adjacent rectangles: {len(result)} polygons (expected ≥1)")
    assert len(result) >= 1, f"Adjacent rectangles should produce ≥1 polygon, got {len(result)}"

    # Case 5g: L-shaped room from 6 LINEs
    l_shape = [
        ((0, 0), (10, 0)),
        ((10, 0), (10, 5)),
        ((10, 5), (5, 5)),
        ((5, 5), (5, 10)),
        ((5, 10), (0, 10)),
        ((0, 10), (0, 0)),
    ]
    result = parser._assemble_closed_polygons(l_shape)
    print(f"  5g. L-shaped room: {len(result)} polygons (expected 1)")
    assert len(result) == 1, f"L-shaped room should produce 1 polygon, got {len(result)}"
    if result:
        pts_3d = [Point3D(x=vx, y=vy, z=0.0) for vx, vy in result[0]]
        geom = Geometry(points=pts_3d, polyline_closed=True)
        area = geom.calculate_area()
        # L-shape: 10×10 - 5×5 = 75 m²
        expected = 75.0
        print(f"  5g. L-shape area: {area:.2f} (expected ≈{expected:.2f})")
        assert abs(area - expected) < 1.0, f"L-shape area off: {area:.2f} vs {expected:.2f}"

    return True


# ═══════════════════════════════════════════════════════════════════════
# TEST 6: calculate_area() — irregular and degenerate polygons
# ═══════════════════════════════════════════════════════════════════════

def test_calculate_area_degenerate():
    """Press calculate_area() with degenerate/irregular polygons."""
    from core.models import Point3D, Geometry

    print(f"\n[TEST 6] calculate_area() — degenerate/irregular polygons")

    # 6a: Collinear points (zero area)
    pts = [Point3D(0, 0, 0), Point3D(5, 0, 0), Point3D(10, 0, 0)]
    geom = Geometry(points=pts, polyline_closed=True)
    area = geom.calculate_area()
    assert area == 0.0, f"Collinear points should have zero area, got {area}"
    print(f"  6a. Collinear: area={area} ✅")

    # 6b: Single point
    pts = [Point3D(5, 5, 0)]
    geom = Geometry(points=pts, polyline_closed=True)
    area = geom.calculate_area()
    assert area == 0.0, f"Single point should have zero area, got {area}"
    print(f"  6b. Single point: area={area} ✅")

    # 6c: Two points (line)
    pts = [Point3D(0, 0, 0), Point3D(10, 0, 0)]
    geom = Geometry(points=pts, polyline_closed=True)
    area = geom.calculate_area()
    assert area == 0.0, f"Two points should have zero area, got {area}"
    print(f"  6c. Two points: area={area} ✅")

    # 6d: Very large polygon (1km × 1km)
    pts = [
        Point3D(0, 0, 0), Point3D(1000, 0, 0),
        Point3D(1000, 1000, 0), Point3D(0, 1000, 0),
    ]
    geom = Geometry(points=pts, polyline_closed=True)
    area = geom.calculate_area()
    assert abs(area - 1_000_000.0) < 1.0, f"1km² room: expected 1,000,000, got {area}"
    print(f"  6d. 1km² room: area={area:,.2f} ✅")

    # 6e: Very small polygon (1mm × 1mm)
    pts = [
        Point3D(0, 0, 0), Point3D(0.001, 0, 0),
        Point3D(0.001, 0.001, 0), Point3D(0, 0.001, 0),
    ]
    geom = Geometry(points=pts, polyline_closed=True)
    area = geom.calculate_area()
    assert area > 0, f"1mm² room should have positive area, got {area}"
    print(f"  6e. 1mm² room: area={area:.10f} ✅")

    # 6f: 100-sided irregular polygon
    pts = []
    for i in range(100):
        angle = 2 * math.pi * i / 100
        r = 10.0 + 5.0 * math.sin(3 * angle)  # Irregular
        pts.append(Point3D(r * math.cos(angle), r * math.sin(angle), 0))
    geom = Geometry(points=pts, polyline_closed=True)
    area = geom.calculate_area()
    assert area > 0, f"100-sided polygon should have positive area, got {area}"
    print(f"  6f. 100-sided irregular: area={area:.2f} ✅")

    # 6g: 1,000,000 diverse polygons stress test
    POLY_COUNT = 1_000_000
    start = time.time()
    zero_errors = 0
    for i in range(POLY_COUNT):
        sides = 3 + (i % 8)
        pts = []
        for j in range(sides):
            angle = 2 * math.pi * j / sides
            r = 5.0 + (i % 10)
            pts.append(Point3D(r * math.cos(angle), r * math.sin(angle), 0))
        geom = Geometry(points=pts, polyline_closed=True)
        area = geom.calculate_area()
        if area <= 0:
            zero_errors += 1

    elapsed = time.time() - start
    print(f"  6g. {POLY_COUNT:,} diverse polygons: {zero_errors} errors in {elapsed:.2f}s ✅")
    assert zero_errors == 0, f"{zero_errors} polygons had zero/negative area!"

    return True


# ═══════════════════════════════════════════════════════════════════════
# TEST 7: extract_rooms_from_chaos() — 50-floor building, mixed entities
# ═══════════════════════════════════════════════════════════════════════

def test_extract_50_floor_mixed_building():
    """Press extract_rooms_from_chaos() with realistic 50-floor building."""
    from parsers.dwg_parser import DWGParser

    FLOORS = 50
    ROOMS_PER_FLOOR = 200
    TOTAL_ROOMS = FLOORS * ROOMS_PER_FLOOR  # 10,000
    print(f"\n[TEST 7] extract_rooms_from_chaos() — {FLOORS} floors × {ROOMS_PER_FLOOR} rooms = {TOTAL_ROOMS:,} rooms")

    entities = []

    for floor in range(FLOORS):
        z_base = floor * 3.5

        for room_idx in range(ROOMS_PER_FLOOR):
            col = room_idx % 20
            row = room_idx // 20
            x_off = col * 15.0
            y_off = row * 15.0

            # Alternate between LINE rooms and POLYLINE rooms
            if room_idx % 3 == 0:
                # LINE-based room
                width = 8.0 + (room_idx % 5)
                depth = 6.0 + (room_idx % 7)
                for sx, sy, ex, ey in [
                    (x_off, y_off, x_off + width, y_off),
                    (x_off + width, y_off, x_off + width, y_off + depth),
                    (x_off + width, y_off + depth, x_off, y_off + depth),
                    (x_off, y_off + depth, x_off, y_off),
                ]:
                    e = Mock()
                    e.dxftype = Mock(return_value='LINE')
                    e.dxf = Mock()
                    e.dxf.start = Mock(x=sx, y=sy)
                    e.dxf.end = Mock(x=ex, y=ey)
                    entities.append(e)
            else:
                # POLYLINE-based room
                width = 7.0 + (room_idx % 4)
                depth = 5.0 + (room_idx % 6)
                e = Mock()
                e.dxftype = Mock(return_value='LWPOLYLINE')
                e.get_points = Mock(return_value=[
                    (x_off, y_off),
                    (x_off + width, y_off),
                    (x_off + width, y_off + depth),
                    (x_off, y_off + depth),
                ])
                entities.append(e)

        # Add 10% poison per floor
        for _ in range(ROOMS_PER_FLOOR // 10):
            e = Mock()
            e.dxftype = Mock(return_value='LINE')
            e.dxf = Mock()
            e.dxf.start = Mock(x=float('nan'), y=float('inf'))
            e.dxf.end = Mock(x=float('-inf'), y=float('nan'))
            entities.append(e)

    random.shuffle(entities)

    mock_doc = Mock()
    mock_doc.modelspace.return_value = entities

    print(f"  📦 {len(entities):,} total entities")

    start = time.time()
    parser = DWGParser()
    rooms = parser.extract_rooms_from_chaos(mock_doc)
    elapsed = time.time() - start

    # LINE rooms: ROOMS_PER_FLOOR/3 per floor × FLOORS (every 3rd room)
    # POLYLINE rooms: 2*ROOMS_PER_FLOOR/3 per floor × FLOORS
    line_rooms = FLOORS * (ROOMS_PER_FLOOR // 3 + 1)  # ≈3,400
    polyline_rooms = FLOORS * (2 * ROOMS_PER_FLOOR // 3)  # ≈6,600
    min_expected = line_rooms + polyline_rooms

    print(f"  🔶 Extracted {len(rooms):,} rooms (min expected: {min_expected:,})")
    print(f"  ⏱  Time: {elapsed:.2f}s")

    assert len(rooms) >= min_expected * 0.9, (  # Allow 10% tolerance for assembly
        f"Expected ≥{min_expected * 0.9:,.0f} rooms, got {len(rooms):,}! "
        f"Missing rooms = missing fire protection!"
    )

    # Verify no NaN/Inf
    for room in rooms:
        if room.geometry and room.geometry.points:
            for pt in room.geometry.points:
                assert not math.isnan(pt.x), "NaN x leaked through!"
                assert not math.isinf(pt.x), "Inf x leaked through!"
                assert not math.isnan(pt.y), "NaN y leaked through!"
                assert not math.isinf(pt.y), "Inf y leaked through!"

    assert elapsed < 180, f"Extraction took too long: {elapsed:.1f}s"

    return True


# ═══════════════════════════════════════════════════════════════════════
# MAIN — Run all tests
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  FireAI V29 — NUCLEAR STRESS TEST — اضغط على النواة        ║")
    print("║  5M rooms × 50 floors × LINE × NaN/Inf poison              ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    tests = [
        ("TEST 1: Geometry.calculate_area() × 5M rooms", test_calculate_area_5m_rooms),
        ("TEST 2: _assemble_closed_polygons() × 10K rooms", test_assemble_10k_closed_polygons_from_lines),
        ("TEST 3: extract_rooms_from_chaos() × 5K rooms + poison", test_extract_rooms_from_chaos_5k_rooms_poisoned),
        ("TEST 4: UniversalDataModel × 100K elements", test_database_100k_elements),
        ("TEST 5: Polygon assembly edge cases", test_polygon_assembly_edge_cases),
        ("TEST 6: calculate_area() degenerate polygons", test_calculate_area_degenerate),
        ("TEST 7: 50-floor mixed building", test_extract_50_floor_mixed_building),
    ]

    results = []
    total_start = time.time()

    for name, test_fn in tests:
        try:
            test_fn()
            results.append((name, "PASSED", None))
            print(f"  ✅ {name} — PASSED")
        except AssertionError as e:
            results.append((name, "FAILED", str(e)))
            print(f"  ❌ {name} — FAILED: {e}")
        except Exception as e:
            results.append((name, "ERROR", traceback.format_exc()))
            print(f"  💥 {name} — ERROR: {e}")

    total_elapsed = time.time() - total_start

    print("\n" + "=" * 70)
    print("NUCLEAR STRESS TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, status, _ in results if status == "PASSED")
    failed = sum(1 for _, status, _ in results if status == "FAILED")
    errored = sum(1 for _, status, _ in results if status == "ERROR")

    for name, status, detail in results:
        icon = "✅" if status == "PASSED" else ("❌" if status == "FAILED" else "💥")
        print(f"  {icon} {name}: {status}")
        if detail and status != "PASSED":
            print(f"     → {detail[:200]}")

    print(f"\n  Total: {passed} PASSED / {failed} FAILED / {errored} ERROR")
    print(f"  Total time: {total_elapsed:.2f}s")

    if failed > 0 or errored > 0:
        print("\n  ⚠️  CRITICAL: NUCLEAR STRESS TEST FAILED — FIX PRODUCTION CODE!")
        sys.exit(1)
    else:
        print("\n  🎯 ALL NUCLEAR STRESS TESTS PASSED — CORE IS SOLID!")
        sys.exit(0)
