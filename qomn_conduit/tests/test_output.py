"""
qomn_conduit.tests.test_output — Output Format Validation Tests
================================================================

Tests Revit JSON, AutoCAD DXF entities, and schedule generators
for correct format, determinism, and completeness.

Reference: Autodesk Revit MEP API; AutoCAD DXF R2018; NEC 358.
"""

import hashlib
import json
import pytest

from qomn_conduit import (
    ConduitType, TradeSize, FittingType, Point3D, RoutePath,
    place_fittings, generate_revit_conduit, generate_autocad_entities,
    generate_schedules, ConduitRun,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: create a simple ConduitRun for testing
# ─────────────────────────────────────────────────────────────────────────────

def _make_simple_run() -> ConduitRun:
    """Create a simple ConduitRun with one elbow for output testing."""
    path = RoutePath(
        waypoints=(
            Point3D(0.0, 0.0, 3.0),
            Point3D(5.0, 0.0, 3.0),
            Point3D(5.0, 5.0, 3.0),
        ),
        total_length_m=10.0,
        bend_count=1,
        elevation_change_m=0.0,
    )
    result = place_fittings(path, ConduitType.EMT, TradeSize.HALF_INCH, run_id="TEST-RUN-001")
    assert result.is_ok()
    return result.value


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Revit JSON has all required parameters
# ─────────────────────────────────────────────────────────────────────────────

class TestRevitOutput:
    """Revit JSON output must contain all required fields."""

    def test_revit_json_has_required_keys(self):
        """Revit JSON must have run_id, segments, fittings, summary, sha256."""
        run = _make_simple_run()
        output = generate_revit_conduit(run)
        assert "run_id" in output
        assert "conduit_type" in output
        assert "trade_size" in output
        assert "segments" in output
        assert "fittings" in output
        assert "summary" in output
        assert "sha256" in output
        assert "is_compliant" in output

    def test_revit_segments_have_length_ft(self):
        """Each segment must have length_ft and length_m."""
        run = _make_simple_run()
        output = generate_revit_conduit(run)
        for seg in output["segments"]:
            assert "length_ft" in seg
            assert "length_m" in seg
            assert "start_ft" in seg
            assert "end_ft" in seg

    def test_revit_fittings_have_catalog_number(self):
        """Each fitting must have catalog_number and fitting_type."""
        run = _make_simple_run()
        output = generate_revit_conduit(run)
        for fit in output["fittings"]:
            assert "catalog_number" in fit
            assert "fitting_type" in fit


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: AutoCAD entities have correct layer names
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoCADOutput:
    """AutoCAD DXF entity output must have correct layer names and formats."""

    def test_entities_have_correct_layer(self):
        """EMT conduit → FA-CONDUIT-EMT layer."""
        run = _make_simple_run()
        entities = generate_autocad_entities(run)
        for ent in entities:
            if ent["entity_type"] == "LINE":
                assert ent["layer"] == "FA-CONDUIT-EMT"
            elif ent["entity_type"] in ("ARC", "POINT"):
                assert "FITTINGS" in ent["layer"]

    def test_entities_have_entity_type(self):
        """All entities must have entity_type field."""
        run = _make_simple_run()
        entities = generate_autocad_entities(run)
        for ent in entities:
            assert "entity_type" in ent
            assert ent["entity_type"] in ("LINE", "ARC", "POINT")

    def test_line_entities_have_coordinates(self):
        """LINE entities must have start_mm and end_mm."""
        run = _make_simple_run()
        entities = generate_autocad_entities(run)
        lines = [e for e in entities if e["entity_type"] == "LINE"]
        assert len(lines) >= 1
        for line in lines:
            assert "start_mm" in line
            assert "end_mm" in line


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Schedules sum to correct totals
# ─────────────────────────────────────────────────────────────────────────────

class TestScheduleOutput:
    """Schedule output must have correct totals and quantities."""

    def test_conduit_schedule_has_totals(self):
        """Conduit schedule must have total_length_m and stick_count."""
        run = _make_simple_run()
        schedules = generate_schedules(run)
        cs = schedules["conduit_schedule"]
        assert "total_length_m" in cs
        assert "total_length_ft" in cs
        assert "stick_count" in cs
        assert cs["total_length_m"] > 0

    def test_fitting_schedule_has_quantities(self):
        """Fitting schedule must aggregate quantities by catalog number."""
        run = _make_simple_run()
        schedules = generate_schedules(run)
        fs = schedules["fitting_schedule"]
        assert len(fs) >= 1
        for item in fs:
            assert "catalog_number" in item
            assert "quantity" in item
            assert item["quantity"] >= 1

    def test_summary_has_compliance_status(self):
        """Summary must include is_compliant and violation_count."""
        run = _make_simple_run()
        schedules = generate_schedules(run)
        summary = schedules["summary"]
        assert "is_compliant" in summary
        assert "violation_count" in summary
        assert "total_length_m" in summary
        assert "elbow_90_count" in summary


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Output is deterministic (same input → same output hash)
# ─────────────────────────────────────────────────────────────────────────────

class TestOutputDeterminism:
    """Same ConduitRun must always produce the same output."""

    def test_revit_sha256_deterministic(self):
        """SHA-256 of Revit output must be identical for the same run."""
        run = _make_simple_run()
        output1 = generate_revit_conduit(run)
        output2 = generate_revit_conduit(run)
        assert output1["sha256"] == output2["sha256"]

    def test_autocad_deterministic(self):
        """AutoCAD entities must be identical for the same run."""
        run = _make_simple_run()
        entities1 = generate_autocad_entities(run)
        entities2 = generate_autocad_entities(run)
        # Compare serialised forms
        assert json.dumps(entities1, sort_keys=True) == json.dumps(entities2, sort_keys=True)

    def test_schedules_deterministic(self):
        """Schedules must be identical for the same run."""
        run = _make_simple_run()
        sched1 = generate_schedules(run)
        sched2 = generate_schedules(run)
        assert json.dumps(sched1, sort_keys=True) == json.dumps(sched2, sort_keys=True)
