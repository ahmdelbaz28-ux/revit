"""fireai/core/tests/test_helpers.py — Reusable Test Utilities
============================================================
Task 2.18: Improve test utilities

Provides:
  1. Fixture factories for common test objects (Point3D, Geometry, etc.)
  2. Helper functions for creating RoomSpec and CeilingSpec objects
  3. In-memory database fixture
  4. Room polygon generators
  5. Assertion helpers for NFPA 72 compliance
  6. Temp file helpers

These utilities are designed to be imported by other test files.
"""

from __future__ import annotations

import math
import os
import tempfile
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest

from core.database import UniversalDataModel
from core.models import (
    ElementType,
    Geometry,
    Point3D,
    SemanticProperties,
    UniversalElement,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Geometry Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def make_square(side: float = 10.0, x0: float = 0.0, y0: float = 0.0) -> Geometry:
    """Create a square polygon geometry.

    Args:
        side: Side length in metres.
        x0: Origin X coordinate.
        y0: Origin Y coordinate.

    Returns:
        Closed Geometry with computed area and perimeter.

    """
    pts = (
        Point3D(x=x0, y=y0),
        Point3D(x=x0 + side, y=y0),
        Point3D(x=x0 + side, y=y0 + side),
        Point3D(x=x0, y=y0 + side),
    )
    return Geometry(points=pts, polyline_closed=True)


def make_rectangle(width: float, length: float, x0: float = 0.0, y0: float = 0.0) -> Geometry:
    """Create a rectangular polygon geometry.

    Args:
        width: Width in metres (X direction).
        length: Length in metres (Y direction).
        x0: Origin X coordinate.
        y0: Origin Y coordinate.

    Returns:
        Closed Geometry with computed area and perimeter.

    """
    pts = (
        Point3D(x=x0, y=y0),
        Point3D(x=x0 + width, y=y0),
        Point3D(x=x0 + width, y=y0 + length),
        Point3D(x=x0, y=y0 + length),
    )
    return Geometry(points=pts, polyline_closed=True)


def make_l_shape() -> Geometry:
    """Create an L-shaped polygon (10x5 + 5x5 = 75 m²)."""
    pts = (
        Point3D(x=0.0, y=0.0),
        Point3D(x=10.0, y=0.0),
        Point3D(x=10.0, y=5.0),
        Point3D(x=5.0, y=5.0),
        Point3D(x=5.0, y=10.0),
        Point3D(x=0.0, y=10.0),
    )
    return Geometry(points=pts, polyline_closed=True)


def make_circle_polygon(radius: float, num_points: int = 36) -> Geometry:
    """Create a circular polygon approximation.

    Args:
        radius: Radius in metres.
        num_points: Number of vertices (more = smoother).

    Returns:
        Closed Geometry approximating a circle.

    """
    pts = tuple(
        Point3D(x=radius * math.cos(2 * math.pi * i / num_points),
                y=radius * math.sin(2 * math.pi * i / num_points))
        for i in range(num_points)
    )
    return Geometry(points=pts, polyline_closed=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Element Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def make_element(
    element_id: str = "test-elem-001",
    element_type: ElementType = ElementType.WALL,
    name: str = "Test Wall",
    height: Optional[float] = 3.0,
    width: Optional[float] = 0.2,
    geometry: Optional[Geometry] = None,
    **kwargs,
) -> UniversalElement:
    """Create a UniversalElement with sensible defaults.

    Args:
        element_id: Mandatory element ID.
        element_type: Element type enum.
        name: Human-readable name.
        height: Element height in metres.
        width: Element width in metres.
        geometry: Optional geometry.
        **kwargs: Additional UniversalElement fields.

    Returns:
        A fully-formed UniversalElement.

    """
    props = SemanticProperties(
        element_type=element_type,
        name=name,
        height=height,
        width=width,
    )
    return UniversalElement(
        element_id=element_id,
        properties=props,
        geometry=geometry,
        created_timestamp=datetime.now(timezone.utc),
        **kwargs,
    )


def make_elements_batch(count: int, prefix: str = "ELEM") -> List[UniversalElement]:
    """Create a batch of UniversalElement objects.

    Args:
        count: Number of elements to create.
        prefix: ID prefix.

    Returns:
        List of UniversalElement objects.

    """
    return [
        make_element(
            element_id=f"{prefix}_{i:06d}",
            name=f"Element {i}",
            geometry=make_square(side=5.0 + (i % 10)),
        )
        for i in range(count)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Room Dict Helpers (for BuildingEngine/FloorAnalyser)
# ═══════════════════════════════════════════════════════════════════════════════


def make_room_dict(
    room_id: str = "R001",
    name: str = "Office",
    width: float = 10.0,
    length: float = 8.0,
    ceiling_height: float = 3.0,
) -> Dict:
    """Create a room dict compatible with FloorAnalyser.

    Args:
        room_id: Room identifier.
        name: Room name.
        width: Width in metres.
        length: Length in metres.
        ceiling_height: Ceiling height in metres.

    Returns:
        Dict with polygon_coords and ceiling_height.

    """
    return {
        "room_id": room_id,
        "name": name,
        "polygon_coords": [(0, 0), (width, 0), (width, length), (0, length)],
        "ceiling_height": ceiling_height,
    }


def make_floor_rooms(
    floor_id: str = "GF",
    room_count: int = 3,
    room_width: float = 10.0,
    room_length: float = 8.0,
    ceiling_height: float = 3.0,
) -> Dict[str, List[Dict]]:
    """Create a floor dict for BuildingEngine.

    Args:
        floor_id: Floor identifier.
        room_count: Number of rooms.
        room_width: Room width in metres.
        room_length: Room length in metres.
        ceiling_height: Ceiling height in metres.

    Returns:
        Dict mapping floor_id to list of room dicts.

    """
    rooms = [
        make_room_dict(
            room_id=f"{floor_id}_R{i:03d}",
            name=f"Room {i}",
            width=room_width,
            length=room_length,
            ceiling_height=ceiling_height,
        )
        for i in range(room_count)
    ]
    return {floor_id: rooms}


# ═══════════════════════════════════════════════════════════════════════════════
# Assertion Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def assert_valid_geometry(geom: Geometry) -> None:
    """Assert that a Geometry object has valid computed properties."""
    assert isinstance(geom, Geometry)
    if geom.polyline_closed and len(geom.points) >= 3:
        assert geom.area >= 0, f"Area must be non-negative, got {geom.area}"
        assert math.isfinite(geom.area), f"Area must be finite, got {geom.area}"
    if len(geom.points) >= 2:
        assert geom.perimeter >= 0, f"Perimeter must be non-negative, got {geom.perimeter}"
        assert math.isfinite(geom.perimeter), f"Perimeter must be finite, got {geom.perimeter}"


def assert_valid_point3d(point: Point3D) -> None:
    """Assert that a Point3D has finite coordinates."""
    assert math.isfinite(point.x), f"x must be finite, got {point.x}"
    assert math.isfinite(point.y), f"y must be finite, got {point.y}"
    assert math.isfinite(point.z), f"z must be finite, got {point.z}"


def assert_compliant_spacing(result, detector_type: str = "smoke") -> None:
    """Assert that a SpacingResult is NFPA 72 compliant.

    Args:
        result: SpacingResult from get_detector_spacing().
        detector_type: 'smoke' or 'heat'.

    """
    assert result.max_spacing_m > 0
    assert result.coverage_radius_m > 0
    assert result.coverage_radius_m <= result.max_spacing_m
    if detector_type == "smoke":
        assert result.max_spacing_m <= 9.10  # SSoT flat spacing
    elif detector_type == "heat":
        assert result.max_spacing_m <= 6.10  # Max heat spacing


# ═══════════════════════════════════════════════════════════════════════════════
# Pytest Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def in_memory_db():
    """In-memory UniversalDataModel database, auto-closed."""
    db = UniversalDataModel(db_path=":memory:")
    yield db
    db.close()


@pytest.fixture
def sample_element():
    """A single sample UniversalElement."""
    return make_element("sample-001", ElementType.WALL, "Sample Wall")


@pytest.fixture
def sample_elements_10():
    """10 sample UniversalElement objects."""
    return make_elements_batch(10)


@pytest.fixture
def sample_elements_100():
    """100 sample UniversalElement objects."""
    return make_elements_batch(100)


@pytest.fixture
def square_geometry():
    """A 10x10 square geometry."""
    return make_square(10.0)


@pytest.fixture
def l_shaped_geometry():
    """An L-shaped geometry."""
    return make_l_shape()


@pytest.fixture
def sample_room_dict():
    """A standard room dict."""
    return make_room_dict()


@pytest.fixture
def sample_floor():
    """A single floor with 3 rooms."""
    return make_floor_rooms("GF", 3)


@pytest.fixture
def temp_dxf_file():
    """Create a minimal DXF temp file, return path, auto-cleanup."""
    content = (
        "0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n6\n0\nENDSEC\n"
        "0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"
    )
    fd, path = tempfile.mkstemp(suffix=".dxf", prefix="helper_test_")
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests for the Helpers Themselves
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelperGeometryFactories:
    """Verify geometry helper functions produce correct results."""

    def test_make_square_area(self):
        geom = make_square(10.0)
        assert abs(geom.area - 100.0) < 0.01

    def test_make_square_perimeter(self):
        geom = make_square(10.0)
        assert abs(geom.perimeter - 40.0) < 0.01

    def test_make_square_offset(self):
        geom = make_square(5.0, x0=100.0, y0=200.0)
        assert abs(geom.area - 25.0) < 0.01

    def test_make_rectangle_area(self):
        geom = make_rectangle(12.0, 8.0)
        assert abs(geom.area - 96.0) < 0.01

    def test_make_l_shape_area(self):
        geom = make_l_shape()
        assert abs(geom.area - 75.0) < 0.01

    def test_make_circle_polygon_area(self):
        geom = make_circle_polygon(radius=10.0, num_points=72)
        expected_area = math.pi * 100.0  # πr²
        assert abs(geom.area - expected_area) < 5.0  # Rough check for polygon approx


class TestHelperElementFactories:
    """Verify element helper functions produce correct objects."""

    def test_make_element_defaults(self):
        elem = make_element()
        assert elem.element_id == "test-elem-001"
        assert elem.properties.name == "Test Wall"

    def test_make_element_custom(self):
        elem = make_element("custom-id", ElementType.DOOR, "My Door", height=2.1, width=0.9)
        assert elem.element_id == "custom-id"
        assert elem.properties.element_type == ElementType.DOOR

    def test_make_elements_batch_count(self):
        elems = make_elements_batch(25)
        assert len(elems) == 25
        assert all(e.element_id.startswith("ELEM_") for e in elems)

    def test_make_elements_batch_unique_ids(self):
        elems = make_elements_batch(50, prefix="TEST")
        ids = [e.element_id for e in elems]
        assert len(set(ids)) == 50  # All unique


class TestHelperRoomDicts:
    """Verify room dict helper functions."""

    def test_make_room_dict_structure(self):
        room = make_room_dict()
        assert "room_id" in room
        assert "name" in room
        assert "polygon_coords" in room
        assert "ceiling_height" in room

    def test_make_room_dict_coords(self):
        room = make_room_dict(width=12.0, length=8.0)
        coords = room["polygon_coords"]
        assert len(coords) == 4
        assert coords[1] == (12.0, 0)
        assert coords[2] == (12.0, 8.0)

    def test_make_floor_rooms_structure(self):
        floor = make_floor_rooms("L1", 5)
        assert "L1" in floor
        assert len(floor["L1"]) == 5


class TestHelperAssertions:
    """Verify assertion helpers work correctly."""

    def test_assert_valid_geometry_passes(self):
        geom = make_square(10.0)
        assert_valid_geometry(geom)  # Should not raise

    def test_assert_valid_point3d_passes(self):
        point = Point3D(x=1.0, y=2.0, z=3.0)
        assert_valid_point3d(point)  # Should not raise


class TestHelperFixtures:
    """Verify pytest fixtures work correctly."""

    def test_in_memory_db_fixture(self, in_memory_db):
        elem = make_element("fixture-test")
        assert in_memory_db.add_element(elem) is True
        retrieved = in_memory_db.get_element("fixture-test")
        assert retrieved is not None

    def test_sample_element_fixture(self, sample_element):
        assert sample_element.element_id == "sample-001"
        assert sample_element.properties.element_type == ElementType.WALL

    def test_sample_elements_10_fixture(self, sample_elements_10):
        assert len(sample_elements_10) == 10

    def test_square_geometry_fixture(self, square_geometry):
        assert abs(square_geometry.area - 100.0) < 0.01

    def test_l_shaped_geometry_fixture(self, l_shaped_geometry):
        assert abs(l_shaped_geometry.area - 75.0) < 0.01

    def test_sample_room_dict_fixture(self, sample_room_dict):
        assert sample_room_dict["room_id"] == "R001"
        assert sample_room_dict["ceiling_height"] == 3.0

    def test_sample_floor_fixture(self, sample_floor):
        assert "GF" in sample_floor
        assert len(sample_floor["GF"]) == 3

    def test_temp_dxf_file_fixture(self, temp_dxf_file):
        assert os.path.exists(temp_dxf_file)
        assert temp_dxf_file.endswith(".dxf")
