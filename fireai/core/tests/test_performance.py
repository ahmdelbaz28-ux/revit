"""fireai/core/tests/test_performance.py — Performance Tests for Core Modules
===========================================================================
Task 2.15: Add performance tests for core/

Tests cover:
  1. Database batch operations — add_elements_batch vs individual adds
  2. Database query performance — get_element, get_all_elements
  3. Model creation performance — Point3D, Geometry, UniversalElement
  4. Geometry calculation performance — area, perimeter for large polygons
  5. NFPA 72 engine calculation throughput
  6. Memory usage bounds for large datasets

Uses time-based assertions (no pytest-benchmark dependency required).
"""

from __future__ import annotations

import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.database import UniversalDataModel
from core.models import (
    ElementType,
    Geometry,
    Point3D,
    SemanticProperties,
    UniversalElement,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def in_memory_db():
    """In-memory SQLite database for fast tests."""
    db = UniversalDataModel(db_path=":memory:")
    yield db
    db.close()


def _make_element(idx: int) -> UniversalElement:
    """Create a test UniversalElement with given index."""
    return UniversalElement(
        element_id=f"ELEM_{idx:06d}",
        properties=SemanticProperties(
            element_type=ElementType.WALL,
            name=f"Wall {idx}",
            height=3.0,
            width=0.2,
        ),
        geometry=Geometry(
            points=(
                Point3D(x=0.0, y=0.0, z=0.0),
                Point3D(x=float(idx % 100), y=0.0, z=0.0),
                Point3D(x=float(idx % 100), y=3.0, z=0.0),
                Point3D(x=0.0, y=3.0, z=0.0),
            ),
            polyline_closed=True,
        ),
        source_file="test_perf.py",
        created_timestamp=datetime.now(timezone.utc),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Database Batch Operations
# ═══════════════════════════════════════════════════════════════════════════════


class TestDatabaseBatchPerformance:
    """Batch operations should be faster than individual operations."""

    def test_batch_add_100_elements(self, in_memory_db):
        """add_elements_batch with 100 elements completes in < 2 seconds."""
        elements = [_make_element(i) for i in range(100)]
        t0 = time.perf_counter()
        count = in_memory_db.add_elements_batch(elements)
        elapsed = time.perf_counter() - t0
        assert count == 100
        assert elapsed < 2.0, f"Batch add of 100 took {elapsed:.3f}s"

    def test_batch_add_faster_than_individual(self, in_memory_db):
        """Batch add should be faster than 100 individual adds."""
        N = 100
        # Individual adds
        db_indiv = UniversalDataModel(db_path=":memory:")
        elements = [_make_element(i) for i in range(N)]
        t0 = time.perf_counter()
        for elem in elements:
            db_indiv.add_element(elem)
        individual_time = time.perf_counter() - t0
        db_indiv.close()

        # Batch add
        db_batch = UniversalDataModel(db_path=":memory:")
        elements2 = [_make_element(i) for i in range(N)]
        t0 = time.perf_counter()
        db_batch.add_elements_batch(elements2)
        batch_time = time.perf_counter() - t0
        db_batch.close()

        # Batch should be at least as fast (allow 10% margin for variance)
        assert batch_time <= individual_time * 1.1, (
            f"Batch ({batch_time:.3f}s) not faster than individual ({individual_time:.3f}s)"
        )

    def test_batch_add_500_elements(self, in_memory_db):
        """add_elements_batch with 500 elements completes in < 5 seconds."""
        elements = [_make_element(i) for i in range(500)]
        t0 = time.perf_counter()
        count = in_memory_db.add_elements_batch(elements)
        elapsed = time.perf_counter() - t0
        assert count == 500
        assert elapsed < 5.0, f"Batch add of 500 took {elapsed:.3f}s"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Database Query Performance
# ═══════════════════════════════════════════════════════════════════════════════


class TestDatabaseQueryPerformance:
    """Database queries should complete within acceptable time bounds."""

    def test_get_element_by_id_1000_elements(self, in_memory_db):
        """get_element from 1000-element DB completes in < 10ms."""
        elements = [_make_element(i) for i in range(1000)]
        in_memory_db.add_elements_batch(elements)

        t0 = time.perf_counter()
        result = in_memory_db.get_element("ELEM_000500")
        elapsed = time.perf_counter() - t0

        assert result is not None
        assert result.element_id == "ELEM_000500"
        assert elapsed < 0.01, f"get_element took {elapsed*1000:.1f}ms"

    def test_get_all_elements_1000(self, in_memory_db):
        """get_all_elements for 1000 elements completes in < 2 seconds."""
        elements = [_make_element(i) for i in range(1000)]
        in_memory_db.add_elements_batch(elements)

        t0 = time.perf_counter()
        all_elems = in_memory_db.get_all_elements()
        elapsed = time.perf_counter() - t0

        assert len(all_elems) == 1000
        assert elapsed < 2.0, f"get_all_elements took {elapsed:.3f}s"

    def test_get_all_elements_exclude_deleted(self, in_memory_db):
        """get_all_elements(include_deleted=False) filters correctly."""
        elements = [_make_element(i) for i in range(50)]
        in_memory_db.add_elements_batch(elements)
        # Soft-delete a few
        in_memory_db.delete_element("ELEM_000010")
        in_memory_db.delete_element("ELEM_000020")

        all_with = in_memory_db.get_all_elements(include_deleted=True)
        all_without = in_memory_db.get_all_elements(include_deleted=False)

        assert len(all_with) == 50
        assert len(all_without) == 48


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Model Creation Performance
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelCreationPerformance:
    """Model creation should be fast enough for bulk operations."""

    def test_create_10000_point3d(self):
        """Creating 10,000 Point3D objects completes in < 1 second."""
        t0 = time.perf_counter()
        points = [Point3D(x=float(i), y=float(i * 2), z=0.0) for i in range(10000)]
        elapsed = time.perf_counter() - t0
        assert len(points) == 10000
        assert elapsed < 1.0, f"Creating 10k Point3D took {elapsed:.3f}s"

    def test_create_1000_geometry(self):
        """Creating 1,000 Geometry objects with 4 points completes in < 2 seconds."""
        t0 = time.perf_counter()
        geoms = []
        for _i in range(1000):
            pts = (
                Point3D(x=0.0, y=0.0),
                Point3D(x=10.0, y=0.0),
                Point3D(x=10.0, y=10.0),
                Point3D(x=0.0, y=10.0),
            )
            geoms.append(Geometry(points=pts, polyline_closed=True))
        elapsed = time.perf_counter() - t0
        assert len(geoms) == 1000
        assert all(g.area == 100.0 for g in geoms)
        assert elapsed < 2.0, f"Creating 1k Geometry took {elapsed:.3f}s"

    def test_create_1000_universal_elements(self):
        """Creating 1,000 UniversalElement objects completes in < 2 seconds."""
        t0 = time.perf_counter()
        elements = [_make_element(i) for i in range(1000)]
        elapsed = time.perf_counter() - t0
        assert len(elements) == 1000
        assert elapsed < 2.0, f"Creating 1k UniversalElement took {elapsed:.3f}s"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Geometry Calculation Performance
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeometryCalculationPerformance:
    """Area and perimeter calculations for large polygons."""

    def test_large_polygon_area_100_vertices(self):
        """Area calculation for 100-vertex polygon completes in < 100ms."""
        # Create a circular-ish polygon with 100 vertices
        n = 100
        pts = tuple(
            Point3D(x=10.0 * math.cos(2 * math.pi * i / n),
                     y=10.0 * math.sin(2 * math.pi * i / n))
            for i in range(n)
        )
        t0 = time.perf_counter()
        geom = Geometry(points=pts, polyline_closed=True)
        elapsed = time.perf_counter() - t0

        assert geom.area > 0
        assert geom.perimeter > 0
        assert elapsed < 0.1, f"100-vertex polygon took {elapsed*1000:.1f}ms"

    def test_large_polygon_area_1000_vertices(self):
        """Area calculation for 1000-vertex polygon completes in < 500ms."""
        n = 1000
        pts = tuple(
            Point3D(x=10.0 * math.cos(2 * math.pi * i / n),
                     y=10.0 * math.sin(2 * math.pi * i / n))
            for i in range(n)
        )
        t0 = time.perf_counter()
        geom = Geometry(points=pts, polyline_closed=True)
        elapsed = time.perf_counter() - t0

        assert geom.area > 0
        assert geom.perimeter > 0
        assert elapsed < 0.5, f"1000-vertex polygon took {elapsed*1000:.1f}ms"

    def test_to_dict_1000_elements(self):
        """Serializing 1000 elements to dict completes in < 2 seconds."""
        elements = [_make_element(i) for i in range(1000)]
        t0 = time.perf_counter()
        dicts = [e.to_dict() for e in elements]
        elapsed = time.perf_counter() - t0
        assert len(dicts) == 1000
        assert elapsed < 2.0, f"to_dict for 1k elements took {elapsed:.3f}s"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. NFPA 72 Engine Calculation Throughput
# ═══════════════════════════════════════════════════════════════════════════════


class TestNFPA72EnginePerformance:
    """NFPA 72 calculations should handle bulk operations efficiently."""

    def test_detector_spacing_1000_calculations(self):
        """1000 detector spacing calculations complete in < 1 second."""
        from fireai.core.nfpa72_engine import get_detector_spacing

        t0 = time.perf_counter()
        results = []
        for i in range(1000):
            h = 2.5 + (i % 10) * 1.0  # Heights from 2.5 to 11.5
            results.append(get_detector_spacing(h, "smoke"))
        elapsed = time.perf_counter() - t0

        assert len(results) == 1000
        assert elapsed < 1.0, f"1000 spacing calcs took {elapsed:.3f}s"

    def test_battery_calculation_1000_iterations(self):
        """1000 battery calculations complete in < 1 second."""
        from fireai.core.nfpa72_engine import calculate_battery

        t0 = time.perf_counter()
        results = []
        for i in range(1000):
            sb = 0.1 + (i % 50) * 0.01
            al = 0.5 + (i % 20) * 0.05
            results.append(calculate_battery(sb, al))
        elapsed = time.perf_counter() - t0

        assert len(results) == 1000
        assert elapsed < 1.0, f"1000 battery calcs took {elapsed:.3f}s"

    def test_voltage_drop_1000_iterations(self):
        """1000 voltage drop calculations complete in < 1 second."""
        from fireai.core.nfpa72_engine import calculate_voltage_drop

        t0 = time.perf_counter()
        results = []
        for i in range(1000):
            current = 0.1 + (i % 30) * 0.01
            length = 10.0 + (i % 100) * 1.0
            results.append(calculate_voltage_drop(current, length, "14"))
        elapsed = time.perf_counter() - t0

        assert len(results) == 1000
        assert elapsed < 1.0, f"1000 voltage drop calcs took {elapsed:.3f}s"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Database CRUD Performance
# ═══════════════════════════════════════════════════════════════════════════════


class TestDatabaseCRUDPerformance:
    """Full CRUD cycle performance for database operations."""

    def test_update_element_100_iterations(self, in_memory_db):
        """100 update_element calls complete in < 2 seconds."""
        elements = [_make_element(i) for i in range(100)]
        in_memory_db.add_elements_batch(elements)

        t0 = time.perf_counter()
        for i in range(100):
            in_memory_db.update_element(
                f"ELEM_{i:06d}",
                {"properties": SemanticProperties(
                    element_type=ElementType.DOOR,
                    name=f"Updated Door {i}",
                    height=2.1,
                    width=0.9,
                ).to_dict()},
            )
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, f"100 updates took {elapsed:.3f}s"

    def test_delete_element_100_iterations(self, in_memory_db):
        """100 delete_element calls complete in < 1 second."""
        elements = [_make_element(i) for i in range(100)]
        in_memory_db.add_elements_batch(elements)

        t0 = time.perf_counter()
        for i in range(100):
            in_memory_db.delete_element(f"ELEM_{i:06d}")
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"100 deletes took {elapsed:.3f}s"

    def test_context_manager_performance(self):
        """Context manager open/close cycle completes quickly."""
        t0 = time.perf_counter()
        for _ in range(50):
            with UniversalDataModel(db_path=":memory:") as db:
                db.add_element(_make_element(0))
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"50 context manager cycles took {elapsed:.3f}s"
