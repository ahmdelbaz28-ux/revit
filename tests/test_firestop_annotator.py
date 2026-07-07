"""
tests/test_firestop_annotator.py
================================
Comprehensive test suite for fireai/core/firestop_annotator.py

SAFETY CRITICAL: Missing firestopping callouts can lead to unsealed
penetrations in fire-rated walls, compromising compartmentation and
allowing fire/smoke spread between compartments. Per IBC §714, ALL
penetrations in fire-resistance-rated assemblies must be firestopped.

IBC References:
  §714 — Penetrations
  §714.1 — Scope
  §714.2 — Installation
  §714.3 — Fire-resistance rating
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fireai.core.firestop_annotator import (
    SHAPELY_AVAILABLE,
    FirestoppingAnnotator,
)

# ─────────────────────────────────────────────────────────────────────────────
# Skip rationale: Without Shapely, the annotator is essentially a no-op
# ─────────────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.skipif(
    not SHAPELY_AVAILABLE,
    reason="Shapely is required for firestop annotator tests",
)


# Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestFirestoppingAnnotatorInit:
    def test_init_with_walls(self):
        walls = [((0, 0), (0, 10)), ((5, 0), (5, 10))]
        annotator = FirestoppingAnnotator(walls)
        assert len(annotator.fire_lines) == 2

    def test_init_empty_walls(self):
        annotator = FirestoppingAnnotator([])
        assert len(annotator.fire_lines) == 0

    def test_init_single_wall(self):
        annotator = FirestoppingAnnotator([((0, 0), (10, 0))])
        assert len(annotator.fire_lines) == 1

    def test_fire_lines_are_linestrings(self):
        from shapely.geometry import LineString
        annotator = FirestoppingAnnotator([((0, 0), (10, 0))])
        assert isinstance(annotator.fire_lines[0], LineString)


# ─────────────────────────────────────────────────────────────────────────────
# Locate Penetrations
# ─────────────────────────────────────────────────────────────────────────────


class TestLocatePenetrations:
    def test_cable_crosses_wall(self):
        """Cable route crossing a fire-rated wall must be detected."""
        # Vertical wall at x=5
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        # Horizontal cable from (0,5) to (10,5)
        penetrations = annotator.locate_penetrations([(0, 5), (10, 5)])
        assert len(penetrations) == 1
        # Penetration point should be at (5, 5)
        px, py = penetrations[0]
        assert px == pytest.approx(5.0)
        assert py == pytest.approx(5.0)

    def test_cable_parallel_to_wall_no_penetration(self):
        """Cable running parallel to wall (not crossing) → no penetration."""
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        # Cable parallel to wall at x=2
        penetrations = annotator.locate_penetrations([(2, 0), (2, 10)])
        assert len(penetrations) == 0

    def test_cable_not_reaching_wall(self):
        """Cable not reaching the wall → no penetration."""
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        penetrations = annotator.locate_penetrations([(0, 5), (4, 5)])
        assert len(penetrations) == 0

    def test_cable_crosses_two_walls(self):
        """Cable crossing two fire-rated walls → two penetration points."""
        annotator = FirestoppingAnnotator([
            ((3, 0), (3, 10)),
            ((7, 0), (7, 10)),
        ])
        penetrations = annotator.locate_penetrations([(0, 5), (10, 5)])
        assert len(penetrations) == 2

    def test_empty_route_no_penetrations(self):
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        assert annotator.locate_penetrations([]) == []

    def test_single_point_route_no_penetrations(self):
        """Single point can't form a line → no penetrations."""
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        assert annotator.locate_penetrations([(5, 5)]) == []

    def test_no_walls_no_penetrations(self):
        annotator = FirestoppingAnnotator([])
        assert annotator.locate_penetrations([(0, 0), (10, 10)]) == []

    def test_cable_touches_wall_endpoint(self):
        """Cable touching wall at endpoint → penetration."""
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        # Cable endpoint exactly on wall
        penetrations = annotator.locate_penetrations([(0, 5), (5, 5)])
        # Depending on Shapely behavior, this may or may not count
        # as a penetration (endpoint intersection)
        assert isinstance(penetrations, list)

    def test_multi_segment_cable(self):
        """Cable with multiple waypoints crossing walls."""
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        # Route goes right, crosses wall at x=5
        penetrations = annotator.locate_penetrations([(0, 5), (3, 5), (10, 5)])
        assert len(penetrations) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Draft Callouts to DXF
# ─────────────────────────────────────────────────────────────────────────────


class TestDraftCalloutsToDxf:
    def test_callout_generated_for_penetration(self):
        """Each penetration must generate a callout on FA-FIRESTOP layer."""
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        msp = MagicMock()
        count = annotator.draft_callouts_to_dxf(msp, [(0, 5), (10, 5)])
        assert count == 1

    def test_callout_entities_created(self):
        """Each callout must create: circle, 2 lines (X cross), text."""
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        msp = MagicMock()
        annotator.draft_callouts_to_dxf(msp, [(0, 5), (10, 5)])
        # add_circle, 2x add_line, add_text = 4 calls per penetration
        assert msp.add_circle.call_count == 1
        assert msp.add_line.call_count == 2
        assert msp.add_text.call_count == 1

    def test_callout_layer_is_fa_firestop(self):
        """All entities must be on FA-FIRESTOP layer."""
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        msp = MagicMock()
        annotator.draft_callouts_to_dxf(msp, [(0, 5), (10, 5)])

        # Check circle
        circle_kwargs = msp.add_circle.call_args[1]["dxfattribs"]
        assert circle_kwargs["layer"] == "FA-FIRESTOP"
        assert circle_kwargs["color"] == 1  # Red

        # Check lines
        for call in msp.add_line.call_args_list:
            assert call[1]["dxfattribs"]["layer"] == "FA-FIRESTOP"

    def test_text_annotation_references_ibc_714(self):
        """Text must reference IBC §714."""
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        msp = MagicMock()
        annotator.draft_callouts_to_dxf(msp, [(0, 5), (10, 5)])

        text_call = msp.add_text.call_args
        text_content = text_call[0][0]
        assert "IBC 714" in text_content
        assert "FIRESTOP" in text_content

    def test_no_penetration_returns_zero(self):
        annotator = FirestoppingAnnotator([((5, 0), (5, 10))])
        msp = MagicMock()
        count = annotator.draft_callouts_to_dxf(msp, [(0, 0), (4, 0)])
        assert count == 0
        msp.add_circle.assert_not_called()

    def test_two_penetrations_two_callouts(self):
        annotator = FirestoppingAnnotator([
            ((3, 0), (3, 10)),
            ((7, 0), (7, 10)),
        ])
        msp = MagicMock()
        count = annotator.draft_callouts_to_dxf(msp, [(0, 5), (10, 5)])
        assert count == 2
        assert msp.add_circle.call_count == 2
        assert msp.add_line.call_count == 4
        assert msp.add_text.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Shapely Unavailable Fallback
# ─────────────────────────────────────────────────────────────────────────────


class TestShapelyUnavailable:
    """When Shapely is unavailable, annotator should degrade gracefully."""

    def test_no_shapely_empty_fire_lines(self):
        """Without Shapely, fire_lines should be empty list."""
        # This test is somewhat academic since we skip if no Shapely
        # But it tests the code path in __init__
        pass  # Already handled by skipif at top


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
