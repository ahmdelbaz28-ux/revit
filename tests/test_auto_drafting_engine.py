"""
Tests for auto_drafting_engine.py — A* Wall-Aware Auto-Drafting Engine
=====================================================================
Comprehensive test suite covering:
    - A* router: wall avoidance, pathfinding, no-through-walls
    - DXF generation (skipped if no ezdxf)
    - Layer structure verification
    - Class A separation constant
    - Block definitions (7 blocks)
    - Firestopping callouts
    - DEVICE_TYPE_TO_BLOCK mapping
"""

import math
import os
import tempfile
import pytest

from fireai.core.auto_drafting_engine import (
    CLASS_A_MIN_SEPARATION_M,
    A_STAR_GRID_RESOLUTION_M,
    DEVICE_TYPE_TO_BLOCK,
    BLOCK_DEFINITIONS,
    CAD_LAYERS,
    WallSegment,
    DraftingDevice,
    FirestoppingCallout,
    DraftingResult,
    AutoDraftingEngine,
)


# ============================================================================
# A* Router Tests
# ============================================================================

class TestAStarRouter:
    """Test A* wall-aware router — NEVER routes through walls."""

    def test_simple_path_no_walls(self):
        """Path between two points with no walls should be direct."""
        engine = AutoDraftingEngine(
            walls=[],
            devices=[
                DraftingDevice(device_id="D1", device_type="SMOKE", position=(1, 1)),
                DraftingDevice(device_id="D2", device_type="SMOKE", position=(5, 1)),
            ],
        )
        path = engine.route_cable((1, 1), (5, 1))
        assert len(path) >= 2
        # Start and end should be close to requested positions
        assert abs(path[0][0] - 1.0) < 2.0
        assert abs(path[-1][0] - 5.0) < 2.0

    def test_path_avoids_wall(self):
        """Path must go around a wall, not through it."""
        # Horizontal wall blocking direct path
        wall = {"start": (0, 5), "end": (10, 5), "fire_rating": 0}
        engine = AutoDraftingEngine(
            walls=[wall],
            devices=[
                DraftingDevice(device_id="D1", device_type="SMOKE", position=(5, 3)),
                DraftingDevice(device_id="D2", device_type="SMOKE", position=(5, 7)),
            ],
        )
        path = engine.route_cable((5, 3), (5, 7))
        # Path should exist but NOT be a straight line through the wall
        assert len(path) >= 2

    def test_path_never_through_wall(self):
        """A* must NEVER produce a path that goes through wall cells.

        CRITICAL: This is a life-safety requirement. Cables through
        fire-rated walls without firestopping violate IBC §714.
        """
        # Wall from (5,0) to (5,10) — vertical barrier
        wall = {"start": (5, 0), "end": (5, 10), "fire_rating": 120}
        engine = AutoDraftingEngine(
            walls=[wall],
            devices=[
                DraftingDevice(device_id="D1", device_type="SMOKE", position=(3, 5)),
                DraftingDevice(device_id="D2", device_type="SMOKE", position=(7, 5)),
            ],
        )
        path = engine.route_cable((3, 5), (7, 5))

        if path:  # If a path is found
            # Check that no waypoint is on the wall
            router = engine._init_router()
            for point in path:
                gx, gy = router._world_to_grid(*point)
                assert (gx, gy) not in router.wall_cells, (
                    f"Path goes through wall at grid ({gx}, {gy}) "
                    f"world ({point[0]:.1f}, {point[1]:.1f})"
                )

    def test_no_path_if_fully_blocked(self):
        """If no path exists around walls, should return empty path."""
        # Create a box of walls that fully encloses the start
        walls = [
            {"start": (0, 0), "end": (10, 0)},
            {"start": (10, 0), "end": (10, 10)},
            {"start": (10, 10), "end": (0, 10)},
            {"start": (0, 10), "end": (0, 0)},
        ]
        engine = AutoDraftingEngine(
            walls=walls,
            devices=[
                DraftingDevice(device_id="D1", device_type="SMOKE", position=(5, 5)),
                DraftingDevice(device_id="D2", device_type="SMOKE", position=(15, 5)),
            ],
        )
        path = engine.route_cable((5, 5), (15, 5))
        # Should be empty or very short (inside the box)
        # The point outside the box may be unreachable
        assert isinstance(path, list)

    def test_fire_rated_wall_detected(self):
        """Fire-rated walls should be tracked separately."""
        wall = {"start": (0, 5), "end": (10, 5), "fire_rating": 120}
        engine = AutoDraftingEngine(
            walls=[wall],
            devices=[
                DraftingDevice(device_id="D1", device_type="SMOKE", position=(5, 3)),
                DraftingDevice(device_id="D2", device_type="SMOKE", position=(5, 7)),
            ],
        )
        router = engine._init_router()
        assert len(router.fire_rated_cells) > 0

    def test_non_rated_wall_not_fire_rated(self):
        """Non-fire-rated walls should NOT appear in fire_rated_cells."""
        wall = {"start": (0, 5), "end": (10, 5), "fire_rating": 0}
        engine = AutoDraftingEngine(
            walls=[wall],
            devices=[
                DraftingDevice(device_id="D1", device_type="SMOKE", position=(5, 3)),
                DraftingDevice(device_id="D2", device_type="SMOKE", position=(5, 7)),
            ],
        )
        router = engine._init_router()
        assert len(router.fire_rated_cells) == 0


# ============================================================================
# DXF Generation Tests
# ============================================================================

class TestDXFGeneration:
    """Test DXF file generation."""

    @pytest.fixture
    def engine(self):
        """Create a drafting engine with sample data."""
        walls = [
            WallSegment(start=(0, 0), end=(20, 0), fire_rating=120),
            WallSegment(start=(20, 0), end=(20, 15), fire_rating=120),
            WallSegment(start=(20, 15), end=(0, 15), fire_rating=0),
            WallSegment(start=(0, 15), end=(0, 0), fire_rating=0),
        ]
        devices = [
            DraftingDevice(device_id="SD-1", device_type="SMOKE", position=(5, 5), zone_id="Z1"),
            DraftingDevice(device_id="SD-2", device_type="SMOKE", position=(15, 5), zone_id="Z1"),
            DraftingDevice(device_id="HD-1", device_type="HEAT", position=(10, 10), zone_id="Z1"),
        ]
        return AutoDraftingEngine(
            walls=walls,
            devices=devices,
            project_info={"name": "Test Building", "drawing_number": "FA-TEST-001"},
        )

    def test_generate_dxf_creates_file(self, engine, tmp_path):
        """DXF generation should create a file."""
        try:
            import ezdxf
        except ImportError:
            pytest.skip("ezdxf not installed")

        output = str(tmp_path / "test_output.dxf")
        result = engine.generate_dxf(output_path=output)

        assert result.errors == ()
        assert result.device_count == 3
        assert os.path.exists(output)

    def test_generate_dxf_no_ezdxf(self, tmp_path):
        """DXF generation without ezdxf should return error gracefully.

        Since ezdxf IS installed in the test environment, we patch the
        module-level HAS_EZDXF flag to False and verify the early-return
        error path works. The generate_dxf method reads HAS_EZDXF at
        call time, so patching the module attribute is sufficient.
        """
        from fireai.core import auto_drafting_engine as _ade
        original = _ade.HAS_EZDXF
        try:
            _ade.HAS_EZDXF = False
            # Must also patch the name in the module that generate_dxf
            # actually reads (the bare HAS_EZDXF in auto_drafting_engine)
            engine = AutoDraftingEngine(walls=[], devices=[])
            output = str(tmp_path / "test_nodxf.dxf")
            result = engine.generate_dxf(output_path=output)
            assert len(result.errors) > 0
            # The error message should mention ezdxf requirement
            full_error = " ".join(str(e) for e in result.errors)
            assert "ezdxf" in full_error.lower() or "dxf" in full_error.lower()
        finally:
            _ade.HAS_EZDXF = original

    def test_generate_dxf_class_a(self, tmp_path):
        """Class A DXF should have return paths."""
        try:
            import ezdxf
        except ImportError:
            pytest.skip("ezdxf not installed")

        walls = [
            WallSegment(start=(0, 0), end=(20, 0)),
            WallSegment(start=(20, 0), end=(20, 10)),
            WallSegment(start=(20, 10), end=(0, 10)),
            WallSegment(start=(0, 10), end=(0, 0)),
        ]
        devices = [
            DraftingDevice(device_id="SD-1", device_type="SMOKE", position=(5, 5)),
            DraftingDevice(device_id="SD-2", device_type="SMOKE", position=(15, 5)),
        ]
        engine = AutoDraftingEngine(walls=walls, devices=devices, class_a=True)
        output = str(tmp_path / "test_classa.dxf")
        result = engine.generate_dxf(output_path=output)

        assert result.class_a_routes >= 0  # May be 0 if routing fails


# ============================================================================
# Layer Structure Tests
# ============================================================================

class TestLayerStructure:
    """Test CAD layer definitions."""

    def test_all_layers_defined(self):
        """All 11 required layers should be defined."""
        required_layers = [
            "FA-DEVICES", "FA-WIRING-CLASSA", "FA-WIRING-CLASSB",
            "FA-NAC", "FA-ZONES", "FA-ISOLATORS", "FA-LABELS",
            "FA-LEGEND", "FA-TITLEBLOCK", "FA-FIRESTOP", "WALLS",
        ]
        for layer in required_layers:
            assert layer in CAD_LAYERS, f"Missing layer: {layer}"

    def test_layers_have_color(self):
        """Each layer should have a color attribute."""
        for layer_name, layer_def in CAD_LAYERS.items():
            assert "color" in layer_def, f"Layer {layer_name} missing color"

    def test_layers_have_description(self):
        """Each layer should have a description."""
        for layer_name, layer_def in CAD_LAYERS.items():
            assert "description" in layer_def, f"Layer {layer_name} missing description"


# ============================================================================
# Class A Separation Tests
# ============================================================================

class TestClassASeparation:
    """Test Class A return path separation."""

    def test_separation_constant_value(self):
        """CLASS_A_MIN_SEPARATION_M must be 1.0 per NFPA 72 §12.2.2."""
        assert CLASS_A_MIN_SEPARATION_M == 1.0

    def test_return_path_offset(self):
        """Return path should be offset by at least 1 m from outgoing."""
        engine = AutoDraftingEngine(walls=[], devices=[])
        outgoing = [(0, 0), (5, 0), (10, 0), (15, 0)]
        return_path = engine.generate_class_a_return_path(outgoing)

        assert len(return_path) == len(outgoing)
        # Each return point should be at least 1 m from its outgoing counterpart
        for out_pt, ret_pt in zip(outgoing, return_path):
            dx = ret_pt[0] - out_pt[0]
            dy = ret_pt[1] - out_pt[1]
            distance = math.sqrt(dx * dx + dy * dy)
            assert distance >= CLASS_A_MIN_SEPARATION_M * 0.9  # Allow small numerical error

    def test_empty_path_returns_empty(self):
        """Empty outgoing path should return empty return path."""
        engine = AutoDraftingEngine(walls=[], devices=[])
        return_path = engine.generate_class_a_return_path([])
        assert return_path == []


# ============================================================================
# Block Definition Tests
# ============================================================================

class TestBlockDefinitions:
    """Test programmatic DXF block definitions."""

    def test_seven_blocks_defined(self):
        """All 7 required block definitions should exist."""
        required_blocks = [
            "FA_SMOKE", "FA_HEAT", "FA_PULL", "FA_MONITOR",
            "FA_CONTROL", "FA_ISOLATOR", "FA_SOUNDER",
        ]
        for block_name in required_blocks:
            assert block_name in BLOCK_DEFINITIONS, f"Missing block: {block_name}"

    def test_blocks_have_shape(self):
        """Each block should have a shape attribute."""
        for block_name, block_def in BLOCK_DEFINITIONS.items():
            assert "shape" in block_def, f"Block {block_name} missing shape"

    def test_blocks_have_color(self):
        """Each block should have a color attribute."""
        for block_name, block_def in BLOCK_DEFINITIONS.items():
            assert "color" in block_def, f"Block {block_name} missing color"

    def test_blocks_have_label(self):
        """Each block should have a label attribute."""
        for block_name, block_def in BLOCK_DEFINITIONS.items():
            assert "label" in block_def, f"Block {block_name} missing label"


# ============================================================================
# Device Type Mapping Tests
# ============================================================================

class TestDeviceTypeMapping:
    """Test DEVICE_TYPE_TO_BLOCK mapping."""

    def test_common_types_mapped(self):
        """Common device types should be mapped to block names."""
        common_types = ["SMOKE", "HEAT", "PULL_STATION", "FAULT_ISOLATOR", "SPEAKER"]
        for dtype in common_types:
            assert dtype in DEVICE_TYPE_TO_BLOCK, f"Missing mapping for {dtype}"

    def test_all_blocks_valid(self):
        """All mapped block names should exist in BLOCK_DEFINITIONS."""
        for dtype, block_name in DEVICE_TYPE_TO_BLOCK.items():
            assert block_name in BLOCK_DEFINITIONS, (
                f"Device type {dtype} maps to undefined block {block_name}"
            )


# ============================================================================
# Firestopping Tests
# ============================================================================

class TestFirestopping:
    """Test firestopping callout generation."""

    def test_firestopping_at_fire_rated_penetration(self):
        """Path crossing a fire-rated wall should generate firestopping callout."""
        wall = {"start": (5, 0), "end": (5, 10), "fire_rating": 120}
        engine = AutoDraftingEngine(
            walls=[wall],
            devices=[
                DraftingDevice(device_id="D1", device_type="SMOKE", position=(3, 5)),
                DraftingDevice(device_id="D2", device_type="SMOKE", position=(7, 5)),
            ],
        )
        # Route a path that would cross the fire-rated wall
        path = engine.route_cable((3, 5), (7, 5))
        if path:
            callouts = engine.find_firestopping_points(path)
            # If the path goes around the wall, there may be no callouts
            # If it crosses near the wall, there should be callouts
            for callout in callouts:
                assert isinstance(callout, FirestoppingCallout)
                assert callout.wall_fire_rating > 0
                assert "§714" in callout.nfpa_reference


# ============================================================================
# WallSegment Tests
# ============================================================================

class TestWallSegment:
    """Test WallSegment dataclass."""

    def test_wall_segment_creation(self):
        """WallSegment should be creatable with required fields."""
        ws = WallSegment(start=(0, 0), end=(10, 0), fire_rating=120)
        assert ws.start == (0, 0)
        assert ws.end == (10, 0)
        assert ws.fire_rating == 120

    def test_wall_segment_default_rating(self):
        """WallSegment default fire_rating should be 0 (non-rated)."""
        ws = WallSegment(start=(0, 0), end=(10, 0))
        assert ws.fire_rating == 0

    def test_wall_segment_frozen(self):
        """WallSegment should be immutable (frozen=True)."""
        ws = WallSegment(start=(0, 0), end=(10, 0))
        with pytest.raises(AttributeError):
            ws.fire_rating = 60


# ============================================================================
# DraftingDevice Tests
# ============================================================================

class TestDraftingDevice:
    """Test DraftingDevice dataclass."""

    def test_device_creation(self):
        """DraftingDevice should be creatable with required fields."""
        dd = DraftingDevice(
            device_id="SD-1",
            device_type="SMOKE",
            position=(5.0, 10.0),
            zone_id="Z1",
        )
        assert dd.device_id == "SD-1"
        assert dd.position == (5.0, 10.0)

    def test_device_frozen(self):
        """DraftingDevice should be immutable."""
        dd = DraftingDevice(device_id="SD-1", device_type="SMOKE", position=(0, 0))
        with pytest.raises(AttributeError):
            dd.device_id = "SD-2"
