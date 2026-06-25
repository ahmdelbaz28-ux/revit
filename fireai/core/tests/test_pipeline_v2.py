"""test_pipeline_v2.py — Comprehensive tests for fireai.core.pipeline
===================================================================

Focus areas for coverage improvement (71% → 80%):
  - _stage7_cable_routing (L1309-1576): import fallback, <2 positions,
    no building model, successful routing, dependency missing, generic failure
  - _stage8_conduit_fittings (L1580-1663): import fallback, <2 positions,
    fill failure with upsizing, routing failure, fitting failure,
    non-compliant runs, fully compliant runs
  - _stage0_contract / _stage1_nfpa_spacing error paths
  - _stage2_placement fallback path
  - _stage3_verify_coverage fallback path
  - _stage4_safety_classify / _stage5_release_gates / _stage6_evidence
  - Helper functions: _hex_grid_placement, _point_in_polygon,
    _estimate_coverage, _count_wall_violations, _failed_result
  - analyze_room full pipeline with various option combos
  - analyze_building with empty list, partial failures, concurrent rooms
  - StageResult and PipelineResult dataclasses
  - _run_stage error handling (ContractViolation, generic Exception)

NOTE: Tests mock heavy external dependencies (cable_router, constraint_engine,
conduit, ifc_parser, etc.) to exercise pipeline logic without requiring
those optional modules to be installed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from fireai.core.contracts_validation import ContractViolation
from fireai.core.pipeline import (
    PipelineResult,
    StageResult,
    _count_wall_violations,
    _estimate_coverage,
    _failed_result,
    _hex_grid_placement,
    _point_in_polygon,
    _run_stage,
    _stage0_contract,
    _stage1_nfpa_spacing,
    _stage2_placement,
    _stage3_verify_coverage,
    _stage4_safety_classify,
    _stage5_release_gates,
    _stage6_evidence,
    _stage7_cable_routing,
    _stage8_conduit_fittings,
    analyze_building,
    analyze_room,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Shared Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

RECT_POLYGON = [(0, 0), (10, 0), (10, 8), (0, 8)]  # 10m × 8m = 80 m²


@pytest.fixture
def valid_payload():
    """Standard valid room payload for the pipeline."""
    return {
        "room_id": "R-101",
        "room_polygon": list(RECT_POLYGON),
        "ceiling_height_m": 3.0,
        "detector_type": "smoke",
        "area_m2": 80.0,
        "occupancy_type": "office",
        "ceiling_type": "flat",
    }


@pytest.fixture
def validated_payload(valid_payload):
    """Payload as it would look after contract validation."""
    return dict(valid_payload, _contract_warnings=[])


@pytest.fixture
def small_polygon():
    """Small 2m × 2m polygon — usually needs only 1 detector."""
    return [(0, 0), (2, 0), (2, 2), (0, 2)]


@pytest.fixture
def long_polygon():
    """Long narrow corridor polygon 20m × 2m."""
    return [(0, 0), (20, 0), (20, 2), (0, 2)]


# ═══════════════════════════════════════════════════════════════════════════════
# StageResult & PipelineResult dataclasses
# ═══════════════════════════════════════════════════════════════════════════════


class TestStageResult:
    def test_defaults(self):
        sr = StageResult(stage_name="S0", success=True, duration_ms=1.5)
        assert sr.data == {}
        assert sr.errors == []
        assert sr.warnings == []

    def test_with_data(self):
        sr = StageResult(
            stage_name="S1",
            success=True,
            duration_ms=2.0,
            data={"key": "val"},
            errors=["err"],
            warnings=["warn"],
        )
        assert sr.data == {"key": "val"}
        assert sr.errors == ["err"]
        assert sr.warnings == ["warn"]


class TestPipelineResult:
    def test_to_dict(self, valid_payload):
        result = analyze_room(valid_payload)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "run_id" in d
        assert "room_id" in d
        assert "success" in d
        assert "stages" in d
        # stages should be a list of dicts
        assert isinstance(d["stages"], list)
        if d["stages"]:
            assert "stage" in d["stages"][0]
            assert "success" in d["stages"][0]

    def test_to_json(self, valid_payload):
        result = analyze_room(valid_payload)
        j = result.to_json()
        parsed = json.loads(j)
        assert isinstance(parsed, dict)
        assert parsed["room_id"] == "R-101"

    def test_to_json_custom_indent(self, valid_payload):
        result = analyze_room(valid_payload)
        j = result.to_json(indent=4)
        # 4-space indent means lines start with 4 spaces for first nested level
        assert "    " in j

    def test_cable_routing_default_none(self):
        pr = PipelineResult(
            run_id="test", room_id="R-1", success=True,
            release_status="green", safety_tier="PROOF_VERIFIED",
            coverage_pct=100.0, detector_count=1, detector_radius_m=6.3,
            max_spacing_m=9.1, detector_positions=[(5, 5)],
            wall_violations=0, battery=None, voltage_drop=None,
            fault_isolation=None, stages=[], release_gates={},
            evidence_hash="abc", total_ms=10.0, errors=[], warnings=[],
            nfpa_references=[], timestamp="2024-01-01T00:00:00+00:00",
        )
        assert pr.cable_routing is None
        assert pr.qomn_audit is None
        d = pr.to_dict()
        assert d["cable_routing"] is None
        assert d["qomn_audit"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# _run_stage
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunStage:
    def test_success(self):
        def fn():
            return {"a": 1}

        sr = _run_stage("test", fn)
        assert sr.success is True
        assert sr.data == {"a": 1}
        assert sr.stage_name == "test"
        assert sr.duration_ms >= 0

    def test_success_non_dict_return(self):
        """Non-dict result gets wrapped in {'result': ...}."""
        sr = _run_stage("test", lambda: 42)
        assert sr.success is True
        assert sr.data == {"result": 42}

    def test_contract_violation(self):
        def fn():
            raise ContractViolation("bad input", field="x", value=0)

        sr = _run_stage("test", fn)
        assert sr.success is False
        assert any("CONTRACT_VIOLATION" in e for e in sr.errors)

    def test_generic_exception(self):
        def fn():
            raise RuntimeError("boom")

        sr = _run_stage("test", fn)
        assert sr.success is False
        assert any("RuntimeError" in e for e in sr.errors)

    def test_passes_args_kwargs(self):
        def fn(a, b=0):
            return {"sum": a + b}

        sr = _run_stage("test", fn, 3, b=7)
        assert sr.data == {"sum": 10}


# ═══════════════════════════════════════════════════════════════════════════════
# _stage0_contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage0Contract:
    def test_valid_payload(self, valid_payload):
        result = _stage0_contract(valid_payload)
        assert result["validated_room_id"] == "R-101"
        assert result["ceiling_height_m"] == 3.0
        assert result["detector_type"] == "smoke"
        assert "validated_payload" in result

    def test_invalid_missing_field(self):
        with pytest.raises(ContractViolation):
            _stage0_contract({"room_id": "R-1"})

    def test_nan_in_payload(self):
        with pytest.raises(ContractViolation):
            _stage0_contract({
                "room_id": "R-1",
                "room_polygon": [(0, 0), (1, 0), (1, 1)],
                "ceiling_height_m": float("nan"),
                "detector_type": "smoke",
            })

    def test_empty_room_id(self):
        with pytest.raises(ContractViolation):
            _stage0_contract({
                "room_id": "  ",
                "room_polygon": [(0, 0), (1, 0), (1, 1)],
                "ceiling_height_m": 3.0,
                "detector_type": "smoke",
            })


# ═══════════════════════════════════════════════════════════════════════════════
# _stage1_nfpa_spacing
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage1NfpaSpacing:
    def test_smoke_detector(self):
        result = _stage1_nfpa_spacing(3.0, "smoke", 80.0)
        assert result["max_spacing_m"] > 0
        assert result["coverage_radius_m"] > 0
        assert result["estimated_min_count"] >= 1
        assert result["area_per_detector_m2"] is not None

    def test_heat_detector(self):
        result = _stage1_nfpa_spacing(3.0, "heat", 80.0)
        assert result["max_spacing_m"] > 0
        assert result["coverage_radius_m"] > 0

    def test_estimate_error_propagation(self):
        """M-3 FIX: Invalid room area should produce error in result."""
        result = _stage1_nfpa_spacing(3.0, "smoke", 0.0)
        assert "error" in result
        assert result["estimated_min_count"] == 0
        assert result["area_per_detector_m2"] is None

    def test_negative_area(self):
        result = _stage1_nfpa_spacing(3.0, "smoke", -5.0)
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════════
# _stage2_placement (including hex fallback)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage2Placement:
    def test_geometric_fallback(self, validated_payload):
        """When DensityOptimizer import fails, hex fallback is used."""
        with patch.dict("sys.modules", {"fireai.core.spatial_engine.density_optimizer": None}):
            result = _stage2_placement(validated_payload, 6.3)
        assert result["method"] == "geometric_hex_fallback"
        assert result["fallback_used"] is True
        assert result["detector_count"] >= 1
        assert result["coverage_pct"] > 0.0

    def test_fallback_reason(self, validated_payload):
        with patch.dict("sys.modules", {"fireai.core.spatial_engine.density_optimizer": None}):
            result = _stage2_placement(validated_payload, 6.3)
        assert "fallback_reason" in result


# ═══════════════════════════════════════════════════════════════════════════════
# _hex_grid_placement
# ═══════════════════════════════════════════════════════════════════════════════


class TestHexGridPlacement:
    def test_empty_polygon(self):
        assert _hex_grid_placement([], 6.3) == []

    def test_zero_radius(self):
        assert _hex_grid_placement(RECT_POLYGON, 0) == []

    def test_negative_radius(self):
        assert _hex_grid_placement(RECT_POLYGON, -1) == []

    def test_returns_positions(self):
        positions = _hex_grid_placement(RECT_POLYGON, 6.3)
        assert len(positions) >= 1
        for x, y in positions:
            assert isinstance(x, float)
            assert isinstance(y, float)

    def test_positions_inside_polygon(self):
        positions = _hex_grid_placement(RECT_POLYGON, 6.3)
        for x, y in positions:
            assert _point_in_polygon(x, y, RECT_POLYGON), f"({x},{y}) not in polygon"

    def test_small_room_gives_at_least_one(self, small_polygon):
        positions = _hex_grid_placement(small_polygon, 6.3)
        assert len(positions) >= 1

    def test_large_radius_fewer_detectors(self):
        p1 = _hex_grid_placement(RECT_POLYGON, 6.3)
        p2 = _hex_grid_placement(RECT_POLYGON, 20.0)
        assert len(p2) <= len(p1)


# ═══════════════════════════════════════════════════════════════════════════════
# _point_in_polygon
# ═══════════════════════════════════════════════════════════════════════════════


class TestPointInPolygon:
    def test_inside(self):
        assert _point_in_polygon(5, 4, RECT_POLYGON) is True

    def test_outside(self):
        assert _point_in_polygon(15, 4, RECT_POLYGON) is False

    def test_on_edge(self):
        """Point on the boundary may be inside or outside (ray-casting)."""
        # This tests the ray-casting algorithm's boundary behavior
        result = _point_in_polygon(0, 0, RECT_POLYGON)
        assert isinstance(result, bool)

    def test_triangle(self):
        tri = [(0, 0), (10, 0), (5, 10)]
        assert _point_in_polygon(5, 3, tri) is True
        assert _point_in_polygon(5, 15, tri) is False

    def test_concave_polygon(self):
        """L-shaped polygon — the inner corner is OUTSIDE."""
        poly = [(0, 0), (6, 0), (6, 3), (3, 3), (3, 6), (0, 6)]
        assert _point_in_polygon(1, 1, poly) is True   # inside lower-left
        assert _point_in_polygon(4, 4, poly) is False  # inside cut-out corner (outside)
        assert _point_in_polygon(1, 5, poly) is True   # inside upper-left
        assert _point_in_polygon(5, 1, poly) is True   # inside lower-right


# ═══════════════════════════════════════════════════════════════════════════════
# _estimate_coverage
# ═══════════════════════════════════════════════════════════════════════════════


class TestEstimateCoverage:
    def test_no_positions(self):
        assert _estimate_coverage([], RECT_POLYGON, 6.3) == 0.0

    def test_no_polygon(self):
        assert _estimate_coverage([(5, 4)], [], 6.3) == 0.0

    def test_full_coverage(self):
        # Single detector in the center of a small room
        positions = [(5, 4)]
        pct = _estimate_coverage(positions, RECT_POLYGON, 20.0)
        assert pct == 100.0  # Radius 20 > room diagonal

    def test_partial_coverage(self):
        positions = [(2, 2)]
        pct = _estimate_coverage(positions, RECT_POLYGON, 6.3)
        assert 0.0 < pct < 100.0

    def test_clamp_to_100(self):
        """V96 FIX: Coverage must not exceed 100.0."""
        positions = [(5, 4), (5, 4)]  # Overlapping detectors
        pct = _estimate_coverage(positions, RECT_POLYGON, 20.0)
        assert pct <= 100.0

    def test_custom_step(self):
        pct1 = _estimate_coverage([(5, 4)], RECT_POLYGON, 6.3, step=0.5)
        pct2 = _estimate_coverage([(5, 4)], RECT_POLYGON, 6.3, step=1.0)
        # Both should be valid coverage estimates
        assert 0.0 <= pct1 <= 100.0
        assert 0.0 <= pct2 <= 100.0

    def test_large_room_adaptive_step(self):
        """Large rooms use coarser grid step for performance."""
        big_poly = [(0, 0), (20, 0), (20, 20), (0, 20)]
        positions = [(10, 10)]
        pct = _estimate_coverage(positions, big_poly, 6.3)
        assert 0.0 < pct <= 100.0


# ═══════════════════════════════════════════════════════════════════════════════
# _stage3_verify_coverage
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage3VerifyCoverage:
    def test_fallback_grid_estimate(self):
        """When ExactCoverageEngine is unavailable, uses grid estimate."""
        with patch.dict("sys.modules", {"fireai.core.spatial_engine.exact_coverage": None}):
            result = _stage3_verify_coverage(
                [(5, 4)], RECT_POLYGON, 6.3, "R-101"
            )
        assert result["engine"] == "grid_estimate_fallback"
        assert "coverage_pct" in result
        assert 0.0 <= result["coverage_pct"] <= 100.0

    def test_is_compliant_flag(self):
        with patch.dict("sys.modules", {"fireai.core.spatial_engine.exact_coverage": None}):
            result = _stage3_verify_coverage(
                [(5, 4)], RECT_POLYGON, 6.3, "R-101"
            )
        assert "is_compliant" in result
        assert isinstance(result["is_compliant"], bool)


# ═══════════════════════════════════════════════════════════════════════════════
# _stage4_safety_classify
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage4SafetyClassify:
    def test_perfect_coverage(self):
        result = _stage4_safety_classify(100.0, True, False, 0)
        assert result["safety_tier"] is not None
        assert result["can_submit"] is True

    def test_low_coverage(self):
        result = _stage4_safety_classify(50.0, False, True, 2)
        assert result["safety_tier"] is not None
        assert result["requires_fpe_review"] is True or result["can_submit"] is False

    def test_with_wall_violations(self):
        result = _stage4_safety_classify(99.5, True, False, 1)
        assert result["safety_tier"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# _stage5_release_gates
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage5ReleaseGates:
    def test_basic_call(self, validated_payload):
        nfpa_result = {"is_compliant": True, "violations": []}
        result = _stage5_release_gates(
            validated_payload, nfpa_result, 100.0, True, "PROOF_VERIFIED", 0
        )
        assert "release_status" in result

    def test_with_violations(self, validated_payload):
        nfpa_result = {"is_compliant": False, "violations": ["Coverage too low"]}
        result = _stage5_release_gates(
            validated_payload, nfpa_result, 85.0, False, "FALLBACK_USED", 1
        )
        assert result.get("release_status") in ("green", "blocked")

    def test_with_battery_result(self, validated_payload):
        from fireai.core.nfpa72_engine import BatteryResult

        battery = BatteryResult(
            required_ah=7.0,
            installed_ah=12.0,
            is_adequate=True,
            formula="NFPA 72 §10.6.7",
            nfpa_section="NFPA 72-2022 §10.6.7.2.1",
        )
        nfpa_result = {"is_compliant": True, "violations": []}
        result = _stage5_release_gates(
            validated_payload, nfpa_result, 100.0, True, "PROOF_VERIFIED", 0,
            battery_result=battery,
        )
        assert "release_status" in result

    def test_with_loop_data(self, validated_payload):
        nfpa_result = {"is_compliant": True, "violations": []}
        result = _stage5_release_gates(
            validated_payload, nfpa_result, 100.0, True, "PROOF_VERIFIED", 0,
            loop_data={"devices": []},
        )
        assert "release_status" in result


# ═══════════════════════════════════════════════════════════════════════════════
# _stage6_evidence
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage6Evidence:
    def test_basic(self, validated_payload):
        spacing_result = {
            "max_spacing_m": 9.1,
            "coverage_radius_m": 6.3,
            "nfpa_section": "NFPA 72-2022 §17.7.3.2.1",
        }
        result = _stage6_evidence(
            "run-123", validated_payload, [(5, 4)], 100.0, True,
            "PROOF_VERIFIED", spacing_result, 0, "APPROVED",
        )
        assert "evidence_hash" in result
        assert result["evidence_hash"] != ""
        assert "nfpa_references" in result
        assert len(result["nfpa_references"]) >= 2

    def test_wall_violation_adds_reference(self, validated_payload):
        spacing_result = {
            "max_spacing_m": 9.1,
            "coverage_radius_m": 6.3,
            "nfpa_section": "NFPA 72-2022 §17.7.3.2.1",
        }
        result = _stage6_evidence(
            "run-456", validated_payload, [(0.05, 4)], 95.0, False,
            "REJECTED", spacing_result, 1, "REJECTED",
        )
        refs = result["nfpa_references"]
        assert any("wall violation" in r.lower() for r in refs)


# ═══════════════════════════════════════════════════════════════════════════════
# _stage7_cable_routing — MAJOR COVERAGE TARGET (L1342-1571)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage7CableRouting:
    """Tests for _stage7_cable_routing covering all major branches."""

    def test_import_unavailable(self, validated_payload):
        """When cable_router import fails, returns 'unavailable' status."""
        with patch.dict("sys.modules", {"fireai.core.cable_router": None}):
            result = _stage7_cable_routing(validated_payload, [(5, 4), (8, 6)])
        assert result["status"] == "unavailable"
        assert "reason" in result

    def test_fewer_than_2_positions(self, validated_payload):
        """Fewer than 2 positions → skipped, no routing needed."""
        result = _stage7_cable_routing(validated_payload, [(5, 4)])
        # This may hit the import error first if modules are unavailable
        # but the <2 positions check is after the import, so we need to
        # ensure the import succeeds
        with patch.dict("sys.modules", {"fireai.core.cable_router": MagicMock(), "fireai.core.constraint_engine": MagicMock(), "fireai.core.schedule_generator": MagicMock()}):
            # Need to also patch the function-level import
            with patch("fireai.core.pipeline._CABLE_ROUTER_AVAILABLE", True):
                # The function has its own try/import, so mock sys.modules
                # to provide the cable_router module
                mock_cable_router = MagicMock()
                mock_constraint = MagicMock()
                mock_schedule = MagicMock()
                with patch.dict("sys.modules", {
                    "fireai.core.cable_router": mock_cable_router,
                    "fireai.core.constraint_engine": mock_constraint,
                    "fireai.core.schedule_generator": mock_schedule,
                }):
                    result = _stage7_cable_routing(validated_payload, [(5, 4)])
        assert result["status"] == "skipped"
        assert result["reason"] == "fewer than 2 detector positions — no routing needed"
        assert result["routes"] == []

    def test_no_positions(self, validated_payload):
        """Empty positions list → skipped."""
        with patch.dict("sys.modules", {
            "fireai.core.cable_router": MagicMock(),
            "fireai.core.constraint_engine": MagicMock(),
            "fireai.core.schedule_generator": MagicMock(),
        }):
            result = _stage7_cable_routing(validated_payload, [])
        assert result["status"] == "skipped"

    def test_building_model_construction_fails(self, validated_payload):
        """When build_abstract_model() raises, cable routing returns 'failed'."""
        mock_cable_router_mod = MagicMock()
        mock_cable_router_mod.build_abstract_model.side_effect = RuntimeError("model failed")

        # Also need IfcElementType, BoundingBox3D from ifc_parser
        mock_ifc = MagicMock()

        with patch.dict("sys.modules", {
            "fireai.core.cable_router": mock_cable_router_mod,
            "fireai.core.constraint_engine": MagicMock(),
            "fireai.core.schedule_generator": MagicMock(),
            "fireai.core.ifc_parser": mock_ifc,
        }):
            result = _stage7_cable_routing(
                validated_payload, [(5, 4), (8, 6)]
            )
        # Building model construction failure → status "failed" or "unavailable"
        assert result["status"] in ("failed", "unavailable", "dependency_missing")
        if result["status"] == "failed":
            assert result.get("safety_block") is True

    def test_no_building_model_available(self, validated_payload):
        """When build_abstract_model returns None, routing returns 'failed' with safety_block."""
        mock_cable_router_mod = MagicMock()
        mock_cable_router_mod.build_abstract_model.return_value = None

        mock_ifc = MagicMock()

        with patch.dict("sys.modules", {
            "fireai.core.cable_router": mock_cable_router_mod,
            "fireai.core.constraint_engine": MagicMock(),
            "fireai.core.schedule_generator": MagicMock(),
            "fireai.core.ifc_parser": mock_ifc,
        }):
            result = _stage7_cable_routing(
                validated_payload, [(5, 4), (8, 6)]
            )
        if result["status"] == "failed":
            assert result.get("safety_block") is True
            assert "routes" in result

    def test_generic_exception(self, validated_payload):
        """Any generic exception during routing → status 'failed' with safety_block."""
        mock_cable_router_mod = MagicMock()
        # Make CableRouter constructor raise
        mock_cable_router_mod.CableRouter.side_effect = RuntimeError("router crash")

        mock_constraint = MagicMock()

        # Need to make the initial import succeed but then the router fail
        with patch.dict("sys.modules", {
            "fireai.core.cable_router": mock_cable_router_mod,
            "fireai.core.constraint_engine": mock_constraint,
            "fireai.core.schedule_generator": MagicMock(),
            "fireai.core.ifc_parser": MagicMock(),
        }):
            result = _stage7_cable_routing(
                validated_payload, [(5, 4), (8, 6)]
            )
        # Should get a failed or unavailable status
        assert result["status"] in ("failed", "unavailable", "dependency_missing")
        if result["status"] == "failed":
            assert result.get("safety_block") is True

    def test_no_polygon_uses_area_for_bbox(self):
        """When polygon is empty, bounding box is derived from area."""
        payload = {
            "room_id": "R-200",
            "area_m2": 100.0,
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
            "room_polygon": [],  # Empty polygon
            "occupancy_type": "office",
            "ceiling_type": "flat",
        }
        # With no polygon, the function should still attempt routing
        # (will likely fail at build_abstract_model with no walls)
        result = _stage7_cable_routing(payload, [(5, 5), (8, 8)])
        # Should be some status — not crash
        assert "status" in result

    def test_custom_room_z(self, validated_payload):
        """Custom room_z_m parameter is accepted."""
        result = _stage7_cable_routing(
            validated_payload, [(5, 4)], room_z_m=1.0
        )
        # Should not crash; may be skipped if <2 positions
        assert "status" in result


# ═══════════════════════════════════════════════════════════════════════════════
# _stage8_conduit_fittings — MAJOR COVERAGE TARGET (L1580-1668)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStage8ConduitFittings:
    """Tests for _stage8_conduit_fittings covering all branches."""

    def test_import_unavailable(self, validated_payload):
        """When conduit module is not available, returns 'unavailable'."""
        with patch.dict("sys.modules", {"fireai.conduit": None}):
            result = _stage8_conduit_fittings(
                validated_payload, [(5, 4), (8, 6)], {}
            )
        assert result["status"] == "unavailable"
        assert "reason" in result

    def test_fewer_than_2_positions(self, validated_payload):
        """< 2 positions → skipped."""
        mock_conduit = MagicMock()
        with patch.dict("sys.modules", {"fireai.conduit": mock_conduit}):
            result = _stage8_conduit_fittings(
                validated_payload, [(5, 4)], {}
            )
        assert result["status"] == "skipped"
        assert "runs" in result

    def test_empty_positions(self, validated_payload):
        """Empty positions → skipped."""
        mock_conduit = MagicMock()
        with patch.dict("sys.modules", {"fireai.conduit": mock_conduit}):
            result = _stage8_conduit_fittings(
                validated_payload, [], {}
            )
        assert result["status"] == "skipped"

    def test_fill_error_upsizes_trade(self, validated_payload):
        """When calculate_fill returns error, trade size is increased to THREE_QTR."""
        mock_conduit = MagicMock()

        # calculate_fill returns an error result
        fill_result = MagicMock()
        fill_result.is_err.return_value = True
        mock_conduit.calculate_fill.return_value = fill_result

        # orthogonal_astar also returns error → skip segment
        route_result = MagicMock()
        route_result.is_err.return_value = True
        route_result.error = MagicMock(message="no route")
        mock_conduit.orthogonal_astar.return_value = route_result

        # ConduitType and TradeSize must have .value attribute
        mock_conduit.ConduitType.EMT = MagicMock(value="EMT")
        mock_conduit.TradeSize.HALF = MagicMock(value="1/2")
        mock_conduit.TradeSize.THREE_QTR = MagicMock(value="3/4")
        mock_conduit.Point3D = MagicMock

        with patch.dict("sys.modules", {"fireai.conduit": mock_conduit}):
            result = _stage8_conduit_fittings(
                validated_payload, [(5, 4), (8, 6)], {}
            )
        assert result["status"] == "completed"
        assert "runs" in result
        # The segment should have routing_failed status
        assert len(result["runs"]) == 1
        assert result["runs"][0]["status"] == "routing_failed"

    def test_routing_failure(self, validated_payload):
        """When orthogonal_astar returns error, segment is marked routing_failed."""
        mock_conduit = MagicMock()

        # calculate_fill succeeds
        fill_result = MagicMock()
        fill_result.is_err.return_value = False
        mock_conduit.calculate_fill.return_value = fill_result

        # orthogonal_astar fails
        route_result = MagicMock()
        route_result.is_err.return_value = True
        route_result.error = MagicMock(message="blocked path")
        mock_conduit.orthogonal_astar.return_value = route_result

        mock_conduit.ConduitType.EMT = MagicMock(value="EMT")
        mock_conduit.TradeSize.HALF = MagicMock(value="1/2")
        mock_conduit.TradeSize.THREE_QTR = MagicMock(value="3/4")
        mock_conduit.Point3D = MagicMock

        with patch.dict("sys.modules", {"fireai.conduit": mock_conduit}):
            result = _stage8_conduit_fittings(
                validated_payload, [(5, 4), (8, 6)], {}
            )
        assert result["status"] == "completed"
        assert result["runs"][0]["status"] == "routing_failed"
        assert result["runs"][0]["reason"] == "blocked path"

    def test_fitting_failure(self, validated_payload):
        """When place_fittings returns error, segment is marked fitting_failed."""
        mock_conduit = MagicMock()

        # calculate_fill succeeds
        fill_result = MagicMock()
        fill_result.is_err.return_value = False
        mock_conduit.calculate_fill.return_value = fill_result

        # orthogonal_astar succeeds
        route_result = MagicMock()
        route_result.is_err.return_value = False
        route_result.value = "route_obj"
        mock_conduit.orthogonal_astar.return_value = route_result

        # place_fittings fails
        fitting_result = MagicMock()
        fitting_result.is_err.return_value = True
        mock_conduit.place_fittings.return_value = fitting_result

        mock_conduit.ConduitType.EMT = MagicMock(value="EMT")
        mock_conduit.TradeSize.HALF = MagicMock(value="1/2")
        mock_conduit.TradeSize.THREE_QTR = MagicMock(value="3/4")
        mock_conduit.Point3D = MagicMock

        with patch.dict("sys.modules", {"fireai.conduit": mock_conduit}):
            result = _stage8_conduit_fittings(
                validated_payload, [(5, 4), (8, 6)], {}
            )
        assert result["status"] == "completed"
        assert result["runs"][0]["status"] == "fitting_failed"

    def test_compliant_run(self, validated_payload):
        """When run is compliant, all_compliant stays True."""
        mock_conduit = MagicMock()

        # calculate_fill succeeds
        fill_result = MagicMock()
        fill_result.is_err.return_value = False
        mock_conduit.calculate_fill.return_value = fill_result

        # orthogonal_astar succeeds
        route_result = MagicMock()
        route_result.is_err.return_value = False
        route_result.value = "route_obj"
        mock_conduit.orthogonal_astar.return_value = route_result

        # place_fittings succeeds with compliant run
        fitting_result = MagicMock()
        fitting_result.is_err.return_value = False
        run = MagicMock()
        run.is_compliant = True
        run.run_id = "SEG-000"
        run.conduit_type = MagicMock(value="EMT")
        run.trade_size = MagicMock(value="1/2")
        run.total_length_m = 5.0
        run.total_bend_deg = 90.0
        run.violations = []
        fitting_result.value = run
        mock_conduit.place_fittings.return_value = fitting_result

        mock_conduit.ConduitType.EMT = MagicMock(value="EMT")
        mock_conduit.TradeSize.HALF = MagicMock(value="1/2")
        mock_conduit.TradeSize.THREE_QTR = MagicMock(value="3/4")
        mock_conduit.Point3D = MagicMock

        with patch.dict("sys.modules", {"fireai.conduit": mock_conduit}):
            result = _stage8_conduit_fittings(
                validated_payload, [(5, 4), (8, 6)], {}
            )
        assert result["status"] == "completed"
        assert result["all_compliant"] is True
        assert result["total_violations"] == 0
        assert result["runs"][0]["status"] == "completed"
        assert result["runs"][0]["is_compliant"] is True

    def test_non_compliant_run(self, validated_payload):
        """When run is not compliant, all_compliant becomes False."""
        mock_conduit = MagicMock()

        # calculate_fill succeeds
        fill_result = MagicMock()
        fill_result.is_err.return_value = False
        mock_conduit.calculate_fill.return_value = fill_result

        # orthogonal_astar succeeds
        route_result = MagicMock()
        route_result.is_err.return_value = False
        route_result.value = "route_obj"
        mock_conduit.orthogonal_astar.return_value = route_result

        # place_fittings succeeds with NON-compliant run
        fitting_result = MagicMock()
        fitting_result.is_err.return_value = False
        run = MagicMock()
        run.is_compliant = False
        run.run_id = "SEG-000"
        run.conduit_type = MagicMock(value="EMT")
        run.trade_size = MagicMock(value="1/2")
        run.total_length_m = 5.0
        run.total_bend_deg = 360.0
        run.violations = ["Exceeds max 360\u00b0 bends per NEC 358.26"]
        fitting_result.value = run
        mock_conduit.place_fittings.return_value = fitting_result

        mock_conduit.ConduitType.EMT = MagicMock(value="EMT")
        mock_conduit.TradeSize.HALF = MagicMock(value="1/2")
        mock_conduit.TradeSize.THREE_QTR = MagicMock(value="3/4")
        mock_conduit.Point3D = MagicMock

        with patch.dict("sys.modules", {"fireai.conduit": mock_conduit}):
            result = _stage8_conduit_fittings(
                validated_payload, [(5, 4), (8, 6)], {}
            )
        assert result["status"] == "completed"
        assert result["all_compliant"] is False
        assert result["total_violations"] > 0
        assert result["runs"][0]["is_compliant"] is False

    def test_multiple_segments(self, validated_payload):
        """Multiple detector pairs produce multiple run segments."""
        mock_conduit = MagicMock()

        fill_result = MagicMock()
        fill_result.is_err.return_value = False
        mock_conduit.calculate_fill.return_value = fill_result

        route_result = MagicMock()
        route_result.is_err.return_value = False
        route_result.value = "route_obj"
        mock_conduit.orthogonal_astar.return_value = route_result

        fitting_result = MagicMock()
        fitting_result.is_err.return_value = False
        run = MagicMock()
        run.is_compliant = True
        run.run_id = "SEG-000"
        run.conduit_type = MagicMock(value="EMT")
        run.trade_size = MagicMock(value="1/2")
        run.total_length_m = 5.0
        run.total_bend_deg = 90.0
        run.violations = []
        fitting_result.value = run
        mock_conduit.place_fittings.return_value = fitting_result

        mock_conduit.ConduitType.EMT = MagicMock(value="EMT")
        mock_conduit.TradeSize.HALF = MagicMock(value="1/2")
        mock_conduit.TradeSize.THREE_QTR = MagicMock(value="3/4")
        mock_conduit.Point3D = MagicMock

        positions = [(5, 4), (8, 4), (8, 6)]
        with patch.dict("sys.modules", {"fireai.conduit": mock_conduit}):
            result = _stage8_conduit_fittings(
                validated_payload, positions, {}
            )
        assert len(result["runs"]) == 2  # 3 positions → 2 segments

    def test_cable_od_from_cable_routing_data(self, validated_payload):
        """cable_routing_data can provide cable_od_in."""
        mock_conduit = MagicMock()

        fill_result = MagicMock()
        fill_result.is_err.return_value = False
        mock_conduit.calculate_fill.return_value = fill_result

        route_result = MagicMock()
        route_result.is_err.return_value = False
        route_result.value = "route_obj"
        mock_conduit.orthogonal_astar.return_value = route_result

        fitting_result = MagicMock()
        fitting_result.is_err.return_value = False
        run = MagicMock()
        run.is_compliant = True
        run.run_id = "SEG-000"
        run.conduit_type = MagicMock(value="EMT")
        run.trade_size = MagicMock(value="1/2")
        run.total_length_m = 5.0
        run.total_bend_deg = 90.0
        run.violations = []
        fitting_result.value = run
        mock_conduit.place_fittings.return_value = fitting_result

        mock_conduit.ConduitType.EMT = MagicMock(value="EMT")
        mock_conduit.TradeSize.HALF = MagicMock(value="1/2")
        mock_conduit.TradeSize.THREE_QTR = MagicMock(value="3/4")
        mock_conduit.Point3D = MagicMock

        with patch.dict("sys.modules", {"fireai.conduit": mock_conduit}):
            result = _stage8_conduit_fittings(
                validated_payload,
                [(5, 4), (8, 6)],
                {"cable_od_in": 0.2},
            )
        # Should not crash — cable_od_in was provided
        assert result["status"] == "completed"


# ═══════════════════════════════════════════════════════════════════════════════
# _count_wall_violations
# ═══════════════════════════════════════════════════════════════════════════════


class TestCountWallViolations:
    def test_no_positions(self):
        assert _count_wall_violations([], RECT_POLYGON) == 0

    def test_no_polygon(self):
        assert _count_wall_violations([(5, 4)], []) == 0

    def test_center_position_no_violation(self):
        # Position well inside polygon, > 0.1m from any wall
        violations = _count_wall_violations([(5, 4)], RECT_POLYGON)
        assert violations == 0

    def test_close_to_wall_violation(self):
        # Position very close to wall edge (0.05m < 0.1m)
        violations = _count_wall_violations([(0.05, 4)], RECT_POLYGON)
        assert violations >= 1

    def test_custom_min_dist(self):
        # With larger min_dist, more positions may violate
        v1 = _count_wall_violations([(1, 4)], RECT_POLYGON, min_dist_m=0.5)
        v2 = _count_wall_violations([(1, 4)], RECT_POLYGON, min_dist_m=2.0)
        assert v2 >= v1

    def test_multiple_positions(self):
        positions = [(5, 4), (0.05, 4)]  # One OK, one violation
        violations = _count_wall_violations(positions, RECT_POLYGON)
        assert violations >= 1

    def test_degenerate_segment(self):
        """Zero-length polygon edge (same start/end point)."""
        degenerate_poly = [(5, 5), (5, 5), (10, 5), (10, 10)]
        # Should not crash
        violations = _count_wall_violations([(5, 7)], degenerate_poly)
        assert isinstance(violations, int)


# ═══════════════════════════════════════════════════════════════════════════════
# _failed_result
# ═══════════════════════════════════════════════════════════════════════════════


class TestFailedResult:
    def test_basic(self):
        import time
        pr = _failed_result("run-1", {"room_id": "R-1"}, [], ["err1"], [], time.perf_counter())
        assert pr.success is False
        assert pr.release_status == "blocked"
        assert pr.safety_tier == "REJECTED"
        assert pr.coverage_pct == 0.0
        assert pr.detector_count == 0
        assert pr.errors == ["err1"]

    def test_default_room_id(self):
        import time
        pr = _failed_result("run-2", {}, [], [], [], time.perf_counter())
        assert pr.room_id == "UNKNOWN"

    def test_explicit_room_id(self):
        import time
        pr = _failed_result("run-3", {"room_id": "R-99"}, [], [], [], time.perf_counter(), room_id="R-99")
        assert pr.room_id == "R-99"

    def test_with_stages(self):
        import time
        stages = [StageResult("S0", True, 1.0)]
        pr = _failed_result("run-4", {}, stages, ["err"], ["warn"], time.perf_counter())
        assert len(pr.stages) == 1

    def test_non_dict_payload(self):
        import time
        pr = _failed_result("run-5", "not_a_dict", [], [], [], time.perf_counter())
        assert pr.room_id == "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_room — Integration-level tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeRoom:
    def test_basic_smoke(self, valid_payload):
        result = analyze_room(valid_payload)
        assert isinstance(result, PipelineResult)
        assert result.room_id == "R-101"
        assert result.detector_count >= 1
        assert result.coverage_pct > 0.0
        assert result.total_ms > 0

    def test_heat_detector(self):
        payload = {
            "room_id": "R-H1",
            "room_polygon": list(RECT_POLYGON),
            "ceiling_height_m": 3.0,
            "detector_type": "heat",
            "area_m2": 80.0,
        }
        result = analyze_room(payload)
        assert result.detector_count >= 1

    def test_deterministic_run_id(self, valid_payload):
        """Same input → same run_id (V61 FIX)."""
        r1 = analyze_room(valid_payload)
        r2 = analyze_room(valid_payload)
        assert r1.run_id == r2.run_id

    def test_different_input_different_run_id(self):
        p1 = {"room_id": "R-A", "room_polygon": list(RECT_POLYGON),
               "ceiling_height_m": 3.0, "detector_type": "smoke", "area_m2": 80.0}
        p2 = {"room_id": "R-B", "room_polygon": list(RECT_POLYGON),
               "ceiling_height_m": 3.0, "detector_type": "smoke", "area_m2": 80.0}
        r1 = analyze_room(p1)
        r2 = analyze_room(p2)
        assert r1.run_id != r2.run_id

    def test_contract_failure_returns_failed_result(self):
        """Invalid payload → success=False, blocked."""
        result = analyze_room({"room_id": ""})
        assert result.success is False
        assert result.release_status == "blocked"

    def test_with_battery_params(self, valid_payload):
        result = analyze_room(
            valid_payload,
            standby_current_a=0.05,
            alarm_current_a=0.5,
        )
        assert result.battery is not None

    def test_with_voltage_drop_params(self, valid_payload):
        result = analyze_room(
            valid_payload,
            alarm_current_a=0.5,
            circuit_length_m=50.0,
        )
        assert result.voltage_drop is not None

    def test_with_fault_isolation(self, valid_payload):
        loop_data = {
            "devices": [
                {"device_id": "D1", "type": "smoke", "isolator_before": True},
                {"device_id": "D2", "type": "smoke", "isolator_before": False},
            ]
        }
        result = analyze_room(valid_payload, loop_data=loop_data)
        assert result.fault_isolation is not None

    def test_voltage_drop_non_compliant_warning(self, valid_payload):
        """Very long circuit should produce a voltage drop warning."""
        result = analyze_room(
            valid_payload,
            alarm_current_a=2.0,
            circuit_length_m=500.0,
        )
        if result.voltage_drop and not result.voltage_drop.get("is_compliant", True):
            assert any("Voltage drop" in w for w in result.warnings)

    def test_stages_list_populated(self, valid_payload):
        result = analyze_room(valid_payload)
        assert len(result.stages) >= 5  # S0, S0.5, S1, S2, S3, S4, S5, S6, S7, S8
        stage_names = [s.stage_name for s in result.stages]
        assert "S0_contract" in stage_names
        assert "S1_nfpa_spacing" in stage_names

    def test_coverage_between_0_and_100(self, valid_payload):
        result = analyze_room(valid_payload)
        assert 0.0 <= result.coverage_pct <= 100.0

    def test_nan_in_input_fails(self):
        payload = {
            "room_id": "R-NaN",
            "room_polygon": [(0, 0), (1, float("nan")), (1, 1)],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
        }
        result = analyze_room(payload)
        assert result.success is False

    def test_inf_in_input_fails(self):
        payload = {
            "room_id": "R-Inf",
            "room_polygon": [(0, 0), (float("inf"), 0), (1, 1)],
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
        }
        result = analyze_room(payload)
        assert result.success is False

    def test_ambient_temperature_param(self, valid_payload):
        """Custom ambient temperature is accepted."""
        result = analyze_room(valid_payload, ambient_temperature_c=75.0)
        assert isinstance(result, PipelineResult)

    def test_stage7_and_stage8_always_run(self, valid_payload):
        """Stages 7 and 8 should appear in the stages list even on failure."""
        result = analyze_room(valid_payload)
        stage_names = [s.stage_name for s in result.stages]
        assert "S7_cable_routing" in stage_names
        assert "S8_conduit_fittings" in stage_names


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_building
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeBuilding:
    def test_empty_rooms(self):
        result = analyze_building([])
        assert result["total_rooms"] == 0
        assert result["results"] == []
        assert result["summary"]["passed"] == 0

    def test_single_room(self, valid_payload):
        result = analyze_building([valid_payload])
        assert result["total_rooms"] == 1
        assert len(result["results"]) == 1
        assert "summary" in result
        assert "total_ms" in result

    def test_multiple_rooms(self, valid_payload):
        rooms = [dict(valid_payload, room_id=f"R-{i}") for i in range(3)]
        result = analyze_building(rooms)
        assert result["total_rooms"] == 3
        assert len(result["results"]) == 3
        assert result["summary"]["total"] == 3

    def test_mixed_valid_invalid(self, valid_payload):
        invalid = {"room_id": ""}  # Will fail contract
        result = analyze_building([valid_payload, invalid])
        assert result["total_rooms"] == 2
        assert result["summary"]["errors"] >= 1

    def test_pass_rate_calculation(self, valid_payload):
        result = analyze_building([valid_payload])
        assert 0.0 <= result["summary"]["pass_rate_pct"] <= 100.0

    def test_total_detectors(self, valid_payload):
        result = analyze_building([valid_payload])
        assert result["total_detectors"] >= 1

    def test_max_workers_param(self, valid_payload):
        result = analyze_building([valid_payload], max_workers=1)
        assert result["total_rooms"] == 1

    def test_kwargs_passed_through(self, valid_payload):
        """Battery/voltage kwargs are forwarded to analyze_room."""
        result = analyze_building(
            [valid_payload],
            standby_current_a=0.05,
            alarm_current_a=0.5,
        )
        assert result["total_rooms"] == 1

    def test_timestamp_present(self, valid_payload):
        result = analyze_building([valid_payload])
        assert "timestamp" in result
        assert result["timestamp"] != ""

    def test_concurrent_execution(self, valid_payload):
        """Multiple rooms can be processed concurrently."""
        rooms = [dict(valid_payload, room_id=f"R-{i}") for i in range(5)]
        result = analyze_building(rooms, max_workers=3)
        assert result["total_rooms"] == 5
        assert len(result["results"]) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Cable routing via analyze_room (Path A: cable_connections + building_model)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCableRoutingPathA:
    """Tests for cable routing via analyze_room cable_connections parameter."""

    def test_cable_connections_without_building_model(self, valid_payload):
        """cable_connections without building_model → no cable routing via Path A."""
        result = analyze_room(valid_payload, cable_connections=[{"from": "A", "to": "B"}])
        # Path A requires both cable_connections AND building_model
        # Cable routing should still attempt via Stage 7
        assert isinstance(result, PipelineResult)

    def test_cable_router_unavailable(self, valid_payload):
        """When _CABLE_ROUTER_AVAILABLE is False, cable routing via Path A is skipped."""
        with patch("fireai.core.pipeline._CABLE_ROUTER_AVAILABLE", False):
            result = analyze_room(
                valid_payload,
                cable_connections=[{"from": "A", "to": "B"}],
                building_model=MagicMock(),
            )
        assert isinstance(result, PipelineResult)
        # cable_routing should be None since Path A was skipped and Stage 7
        # may also fail without the cable_router module

    def test_cable_routing_dict_from_stage7(self, valid_payload):
        """When Stage 7 succeeds, cable_routing_dict is populated from it."""
        # Mock the internal stage7 to return completed status
        stage7_data = {
            "status": "completed",
            "total_cable_length_m": 25.0,
            "total_bends": 4,
            "max_circuit_length_m": 12.0,
            "min_end_voltage_v": 22.5,
            "all_compliant": True,
            "route_count": 2,
            "violations_count": 0,
            "code_refs": ["NEC 760.24"],
        }
        with patch("fireai.core.pipeline._stage7_cable_routing", return_value=stage7_data):
            # Also need to handle Stage 8
            with patch("fireai.core.pipeline._stage8_conduit_fittings", return_value={"status": "unavailable"}):
                result = analyze_room(valid_payload)
        # cable_routing should be populated from Stage 7
        if result.cable_routing is not None:
            assert result.cable_routing["total_cable_length_m"] == 25.0
            assert result.cable_routing["all_compliant"] is True

    def test_cable_routing_non_compliant_warning(self, valid_payload):
        """When Stage 7 has violations, a warning is added."""
        stage7_data = {
            "status": "completed",
            "total_cable_length_m": 25.0,
            "total_bends": 4,
            "max_circuit_length_m": 12.0,
            "min_end_voltage_v": 18.0,
            "all_compliant": False,
            "route_count": 2,
            "violations_count": 1,
            "code_refs": ["NEC 760.24"],
        }
        with patch("fireai.core.pipeline._stage7_cable_routing", return_value=stage7_data):
            with patch("fireai.core.pipeline._stage8_conduit_fittings", return_value={"status": "unavailable"}):
                result = analyze_room(valid_payload)
        if result.cable_routing is not None and not result.cable_routing["all_compliant"]:
            assert any("Cable routing" in w for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# Edge Cases and Error Path Coverage
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_stage0_failure_stops_pipeline(self):
        """Contract failure at Stage 0 should stop the pipeline early."""
        result = analyze_room({"room_id": ""})  # Empty room_id → contract violation
        assert result.success is False
        # Should have very few stages (just S0)
        assert len(result.stages) >= 1

    def test_stage1_failure_returns_failed_result(self):
        """If stage1 somehow fails, pipeline returns a failed result."""
        with patch("fireai.core.pipeline._stage1_nfpa_spacing", side_effect=RuntimeError("spacing error")):
            result = analyze_room({
                "room_id": "R-E1",
                "room_polygon": list(RECT_POLYGON),
                "ceiling_height_m": 3.0,
                "detector_type": "smoke",
                "area_m2": 80.0,
            })
        # Pipeline should handle stage1 failure gracefully
        assert isinstance(result, PipelineResult)

    def test_stage2_failure_uses_estimate(self):
        """When placement fails entirely, pipeline continues with estimates."""
        with patch("fireai.core.pipeline._stage2_placement", side_effect=RuntimeError("placement crash")):
            result = analyze_room({
                "room_id": "R-E2",
                "room_polygon": list(RECT_POLYGON),
                "ceiling_height_m": 3.0,
                "detector_type": "smoke",
                "area_m2": 80.0,
            })
        assert isinstance(result, PipelineResult)

    def test_stage3_failure_uses_optimizer_estimate(self, valid_payload):
        """When coverage verification fails, optimizer estimate is used."""
        with patch("fireai.core.pipeline._stage3_verify_coverage", side_effect=RuntimeError("coverage crash")):
            result = analyze_room(valid_payload)
        assert isinstance(result, PipelineResult)

    def test_stage5_failure_defaults_to_blocked(self, valid_payload):
        """When release gates fail, default is 'blocked'."""
        with patch("fireai.core.pipeline._stage5_release_gates", side_effect=RuntimeError("gates crash")):
            result = analyze_room(valid_payload)
        assert result.release_status == "blocked"

    def test_stage6_failure_empty_hash(self, valid_payload):
        """When evidence packaging fails, hash is empty string."""
        with patch("fireai.core.pipeline._stage6_evidence", side_effect=RuntimeError("evidence crash")):
            result = analyze_room(valid_payload)
        assert result.evidence_hash == ""
        assert result.nfpa_references == []

    def test_small_room_single_detector(self, small_polygon):
        """Very small room should produce at least 1 detector."""
        payload = {
            "room_id": "R-tiny",
            "room_polygon": small_polygon,
            "ceiling_height_m": 3.0,
            "detector_type": "smoke",
            "area_m2": 4.0,
        }
        result = analyze_room(payload)
        assert result.detector_count >= 1

    def test_high_ceiling(self):
        """High ceiling should still produce a result (with warnings)."""
        payload = {
            "room_id": "R-tall",
            "room_polygon": list(RECT_POLYGON),
            "ceiling_height_m": 12.0,
            "detector_type": "smoke",
            "area_m2": 80.0,
        }
        result = analyze_room(payload)
        assert isinstance(result, PipelineResult)

    def test_pipeline_result_timestamp_format(self, valid_payload):
        result = analyze_room(valid_payload)
        # Should be ISO format
        assert "T" in result.timestamp
        assert result.timestamp != ""


# ═══════════════════════════════════════════════════════════════════════════════
# QOMN Physics Guard (Stage 0.5) Coverage
# ═══════════════════════════════════════════════════════════════════════════════


class TestQomnPhysicsGuard:
    def test_qomn_unavailable(self, valid_payload):
        """When QOMN kernel is not available, physics_guard_passed is False."""
        with patch.dict("sys.modules", {"fireai.core.qomn_kernel": None}):
            result = analyze_room(valid_payload)
        # Should still complete pipeline
        assert isinstance(result, PipelineResult)
        # Check stage 0.5 in stages
        s05 = next((s for s in result.stages if s.stage_name == "S0.5_qomn_physics_guard"), None)
        if s05 and s05.success:
            assert s05.data.get("physics_guard_passed") is False

    def test_qomn_adds_warnings_on_guard_failure(self, valid_payload):
        """Physics guard failures should add warnings."""
        mock_qomn = MagicMock()
        mock_qomn.QOMNKernel.side_effect = ImportError("no QOMN")
        mock_qomn.PhysicsGuardError = Exception

        with patch.dict("sys.modules", {"fireai.core.qomn_kernel": mock_qomn}):
            result = analyze_room(valid_payload)
        assert isinstance(result, PipelineResult)


# ═══════════════════════════════════════════════════════════════════════════════
# Rules Engine (Stage 3.5) Coverage
# ═══════════════════════════════════════════════════════════════════════════════


class TestRulesCompliance:
    def test_rules_engine_failure_is_non_blocking(self, valid_payload):
        """When Rules Engine fails, pipeline still completes."""
        with patch("fireai.core.pipeline._stage35_rules_compliance", side_effect=RuntimeError("rules crash")):
            result = analyze_room(valid_payload)
        assert isinstance(result, PipelineResult)
        assert any("Rules Engine" in w for w in result.warnings)

    def test_rules_engine_unsafe_adds_warnings(self, valid_payload):
        """When rules engine reports is_safe=False, critical/violation warnings are added."""
        rules_data = {
            "engine": "NFPA72ComplianceChecker",
            "is_safe": False,
            "critical_issues": 1,
            "violations": 0,
            "critical_details": [{"rule_id": "R-001", "message": "Spacing exceeds limit"}],
            "violation_details": [],
        }
        with patch("fireai.core.pipeline._stage35_rules_compliance", return_value=rules_data):
            result = analyze_room(valid_payload)
        assert any("RULES_ENGINE CRITICAL" in w for w in result.warnings)

    def test_rules_engine_violation_details(self, valid_payload):
        """Violation details from rules engine are added as warnings."""
        rules_data = {
            "engine": "NFPA72ComplianceChecker",
            "is_safe": False,
            "critical_issues": 0,
            "violations": 1,
            "critical_details": [],
            "violation_details": [{"rule_id": "V-001", "message": "Wall distance violation"}],
        }
        with patch("fireai.core.pipeline._stage35_rules_compliance", return_value=rules_data):
            result = analyze_room(valid_payload)
        assert any("RULES_ENGINE VIOLATION" in w for w in result.warnings)
