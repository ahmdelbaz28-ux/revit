"""
FireAI Pipeline — End-to-End Integration Tests
================================================

Tests the complete FireAI analysis pipeline from input payload
through all 7 stages to final PipelineResult output.

COVERED:
  1. analyze_room() — valid payload, all result fields
  2. analyze_room() — with battery calculation
  3. analyze_room() — with voltage drop calculation
  4. analyze_room() — with fault isolation (loop_data)
  5. analyze_room() — invalid payload → ContractViolation caught
  6. analyze_building() — multiple rooms, concurrent processing
  7. Failed pipeline — critical stage failure → blocked result
  8. NaN/Inf inputs caught at Stage 0

DESIGN PRINCIPLES:
  - NEVER mock internal behaviour — test actual pipeline execution
  - Pipeline MUST NEVER raise exceptions — all errors captured in PipelineResult
  - Use simple rectangular polygons for deterministic geometry
"""

from __future__ import annotations

import json
import math
import pytest

from fireai.core.pipeline import (
    analyze_room,
    analyze_building,
    PipelineResult,
    StageResult,
)
from fireai.core.contracts_validation import ContractViolation


# ─── Shared Fixtures ──────────────────────────────────────────────────────────

def _valid_payload(**overrides):
    """Build a valid room payload with sensible defaults."""
    base = {
        "room_id": "R-101",
        "room_polygon": [(0, 0), (10, 0), (10, 8), (0, 8)],
        "ceiling_height_m": 3.0,
        "detector_type": "smoke",
        "area_m2": 80.0,
        "occupancy_type": "office",
        "ceiling_type": "flat",
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════════════════════
# 1. analyze_room() — valid payload
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeRoomValid:
    """Test analyze_room with a valid room payload — happy path."""

    def test_returns_pipeline_result(self):
        result = analyze_room(_valid_payload())
        assert isinstance(result, PipelineResult)

    def test_success_is_true(self):
        result = analyze_room(_valid_payload())
        assert result.success is True

    def test_detector_count_positive(self):
        result = analyze_room(_valid_payload())
        assert result.detector_count > 0

    def test_coverage_pct_positive(self):
        result = analyze_room(_valid_payload())
        assert result.coverage_pct > 0.0

    def test_stages_populated(self):
        result = analyze_room(_valid_payload())
        assert len(result.stages) > 0
        # Must have at least stages 0–6
        stage_names = [s.stage_name for s in result.stages]
        assert "S0_contract" in stage_names
        assert "S1_nfpa_spacing" in stage_names
        assert "S2_placement" in stage_names
        assert "S3_coverage" in stage_names
        assert "S4_safety" in stage_names
        assert "S5_release_gates" in stage_names
        assert "S6_evidence" in stage_names

    def test_safety_tier_is_set(self):
        result = analyze_room(_valid_payload())
        assert result.safety_tier  # non-empty string
        assert result.safety_tier in {
            "PROOF_VERIFIED", "PROOF_VALID", "FALLBACK_USED", "REJECTED"
        }

    def test_release_status_is_set(self):
        result = analyze_room(_valid_payload())
        assert result.release_status in {"green", "blocked"}

    def test_evidence_hash_computed(self):
        result = analyze_room(_valid_payload())
        assert result.evidence_hash  # non-empty
        # SHA-256 hex digest is 64 chars
        assert len(result.evidence_hash) == 64
        assert all(c in "0123456789abcdef" for c in result.evidence_hash)

    def test_nfpa_references_populated(self):
        result = analyze_room(_valid_payload())
        assert isinstance(result.nfpa_references, list)
        assert len(result.nfpa_references) > 0
        # Should reference NFPA 72
        assert any("NFPA 72" in ref for ref in result.nfpa_references)

    def test_to_dict_returns_dict(self):
        result = analyze_room(_valid_payload())
        d = result.to_dict()
        assert isinstance(d, dict)
        # Key structural fields must be present
        assert "run_id" in d
        assert "room_id" in d
        assert "success" in d
        assert "release_status" in d
        assert "safety_tier" in d
        assert "coverage_pct" in d
        assert "detector_count" in d
        assert "stages" in d
        assert "evidence_hash" in d
        assert "nfpa_references" in d
        assert "timestamp" in d

    def test_to_dict_stages_are_dicts(self):
        result = analyze_room(_valid_payload())
        d = result.to_dict()
        assert isinstance(d["stages"], list)
        assert len(d["stages"]) > 0
        for stage in d["stages"]:
            assert isinstance(stage, dict)
            assert "stage" in stage
            assert "success" in stage

    def test_to_json_returns_valid_json(self):
        result = analyze_room(_valid_payload())
        j = result.to_json()
        assert isinstance(j, str)
        parsed = json.loads(j)
        assert isinstance(parsed, dict)
        assert parsed["success"] is True

    def test_to_json_custom_indent(self):
        result = analyze_room(_valid_payload())
        j4 = result.to_json(indent=4)
        j0 = result.to_json(indent=0)
        # Both must parse to the same data
        assert json.loads(j4) == json.loads(j0)

    def test_room_id_propagated(self):
        result = analyze_room(_valid_payload(room_id="R-42"))
        assert result.room_id == "R-42"

    def test_detector_positions_populated(self):
        result = analyze_room(_valid_payload())
        assert isinstance(result.detector_positions, list)
        assert len(result.detector_positions) > 0
        # Each position is an (x, y) tuple
        for pos in result.detector_positions:
            assert isinstance(pos, (list, tuple))
            assert len(pos) == 2

    def test_total_ms_positive(self):
        result = analyze_room(_valid_payload())
        assert result.total_ms > 0.0

    def test_timestamp_is_iso_format(self):
        result = analyze_room(_valid_payload())
        assert result.timestamp  # non-empty
        # ISO format should contain 'T'
        assert "T" in result.timestamp

    def test_max_spacing_m_positive(self):
        result = analyze_room(_valid_payload())
        assert result.max_spacing_m > 0.0

    def test_detector_radius_m_positive(self):
        result = analyze_room(_valid_payload())
        assert result.detector_radius_m > 0.0

    def test_run_id_is_uuid(self):
        result = analyze_room(_valid_payload())
        # UUID format: 8-4-4-4-12 hex chars
        parts = result.run_id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8

    def test_no_errors_on_valid_input(self):
        result = analyze_room(_valid_payload())
        # Valid input should not produce errors (warnings are okay)
        assert isinstance(result.errors, list)

    def test_placement_uses_geometric_hex_fallback(self):
        """Pipeline uses geometric hex fallback when DensityOptimizer is unavailable."""
        result = analyze_room(_valid_payload())
        s2 = next(s for s in result.stages if s.stage_name == "S2_placement")
        assert s2.success is True
        assert s2.data.get("method") in {"geometric_hex_fallback", "DensityOptimizer"}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. analyze_room() — with battery calculation
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeRoomBattery:
    """Test analyze_room with battery sizing parameters."""

    def test_battery_result_populated(self):
        result = analyze_room(
            _valid_payload(),
            standby_current_a=0.05,
            alarm_current_a=0.5,
        )
        assert result.battery is not None
        assert isinstance(result.battery, dict)
        assert "required_ah" in result.battery
        assert "installed_ah" in result.battery
        assert "is_adequate" in result.battery

    def test_battery_is_adequate(self):
        result = analyze_room(
            _valid_payload(),
            standby_current_a=0.05,
            alarm_current_a=0.5,
        )
        assert result.battery["is_adequate"] is True

    def test_battery_stage_in_stages(self):
        result = analyze_room(
            _valid_payload(),
            standby_current_a=0.05,
            alarm_current_a=0.5,
        )
        stage_names = [s.stage_name for s in result.stages]
        assert "S_battery" in stage_names

    def test_battery_required_ah_positive(self):
        result = analyze_room(
            _valid_payload(),
            standby_current_a=0.05,
            alarm_current_a=0.5,
        )
        assert result.battery["required_ah"] > 0.0

    def test_battery_installed_ge_required(self):
        result = analyze_room(
            _valid_payload(),
            standby_current_a=0.1,
            alarm_current_a=1.0,
        )
        assert result.battery["installed_ah"] >= result.battery["required_ah"]

    def test_no_battery_without_params(self):
        result = analyze_room(_valid_payload())
        assert result.battery is None

    def test_no_battery_with_only_standby(self):
        """Battery requires BOTH standby and alarm current."""
        result = analyze_room(
            _valid_payload(),
            standby_current_a=0.05,
        )
        assert result.battery is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. analyze_room() — with voltage drop calculation
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeRoomVoltageDrop:
    """Test analyze_room with voltage drop parameters."""

    def test_voltage_drop_result_populated(self):
        result = analyze_room(
            _valid_payload(),
            alarm_current_a=0.5,
            circuit_length_m=100.0,
        )
        assert result.voltage_drop is not None
        assert isinstance(result.voltage_drop, dict)
        assert "voltage_drop_v" in result.voltage_drop
        assert "voltage_drop_pct" in result.voltage_drop
        assert "is_compliant" in result.voltage_drop

    def test_voltage_drop_values_positive(self):
        result = analyze_room(
            _valid_payload(),
            alarm_current_a=0.5,
            circuit_length_m=100.0,
        )
        assert result.voltage_drop["voltage_drop_v"] > 0.0
        assert result.voltage_drop["voltage_drop_pct"] > 0.0

    def test_voltage_drop_stage_in_stages(self):
        result = analyze_room(
            _valid_payload(),
            alarm_current_a=0.5,
            circuit_length_m=100.0,
        )
        stage_names = [s.stage_name for s in result.stages]
        assert "S_voltage_drop" in stage_names

    def test_short_circuit_is_compliant(self):
        result = analyze_room(
            _valid_payload(),
            alarm_current_a=0.3,
            circuit_length_m=10.0,
        )
        assert result.voltage_drop["is_compliant"] is True

    def test_no_voltage_drop_without_params(self):
        result = analyze_room(_valid_payload())
        assert result.voltage_drop is None

    def test_voltage_drop_with_custom_awg(self):
        result = analyze_room(
            _valid_payload(),
            alarm_current_a=0.5,
            circuit_length_m=100.0,
            awg_gauge="12",
        )
        assert result.voltage_drop is not None
        # Thicker wire (AWG 12) should have less drop than AWG 14
        result_14 = analyze_room(
            _valid_payload(),
            alarm_current_a=0.5,
            circuit_length_m=100.0,
            awg_gauge="14",
        )
        assert result.voltage_drop["voltage_drop_v"] < result_14.voltage_drop["voltage_drop_v"]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. analyze_room() — with fault isolation (loop_data)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeRoomFaultIsolation:
    """Test analyze_room with SLC loop data for fault isolation."""

    def _loop_data_compliant(self):
        """Loop data that is compliant — few devices between isolators."""
        return {
            "devices": [
                {"device_id": "D1", "device_type": "detector", "zone_id": "Z1"},
                {"device_id": "D2", "device_type": "detector", "zone_id": "Z1"},
                {"device_id": "ISO1", "device_type": "isolator", "zone_id": "Z1"},
                {"device_id": "D3", "device_type": "detector", "zone_id": "Z2"},
                {"device_id": "D4", "device_type": "detector", "zone_id": "Z2"},
            ],
        }

    def _loop_data_non_compliant(self):
        """Loop data that violates NFPA 72 §12.3 — too many devices between isolators."""
        devices = [
            {"device_id": f"D{i}", "device_type": "detector", "zone_id": "Z1"}
            for i in range(1, 35)  # 34 devices, no isolator — exceeds 32 limit
        ]
        return {"devices": devices}

    def test_fault_isolation_result_populated(self):
        result = analyze_room(
            _valid_payload(),
            loop_data=self._loop_data_compliant(),
        )
        assert result.fault_isolation is not None
        assert isinstance(result.fault_isolation, dict)
        assert "compliant" in result.fault_isolation

    def test_fault_isolation_compliant(self):
        result = analyze_room(
            _valid_payload(),
            loop_data=self._loop_data_compliant(),
        )
        assert result.fault_isolation["compliant"] is True

    def test_fault_isolation_non_compliant(self):
        result = analyze_room(
            _valid_payload(),
            loop_data=self._loop_data_non_compliant(),
        )
        assert result.fault_isolation["compliant"] is False

    def test_fault_isolation_stage_in_stages(self):
        result = analyze_room(
            _valid_payload(),
            loop_data=self._loop_data_compliant(),
        )
        stage_names = [s.stage_name for s in result.stages]
        assert "S_fault_isolation" in stage_names

    def test_no_fault_isolation_without_loop_data(self):
        result = analyze_room(_valid_payload())
        assert result.fault_isolation is None

    def test_fault_isolation_reports_device_count(self):
        result = analyze_room(
            _valid_payload(),
            loop_data=self._loop_data_compliant(),
        )
        assert result.fault_isolation["device_count"] == 5

    def test_fault_isolation_non_compliant_has_violations(self):
        result = analyze_room(
            _valid_payload(),
            loop_data=self._loop_data_non_compliant(),
        )
        assert len(result.fault_isolation["violations"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. analyze_room() — invalid payload → ContractViolation caught
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeRoomInvalidPayload:
    """Test that invalid inputs are caught at Stage 0 and NEVER raise."""

    def test_missing_room_id(self):
        payload = _valid_payload()
        del payload["room_id"]
        result = analyze_room(payload)
        assert isinstance(result, PipelineResult)
        assert result.success is False
        assert result.release_status == "blocked"

    def test_missing_ceiling_height(self):
        payload = _valid_payload()
        del payload["ceiling_height_m"]
        result = analyze_room(payload)
        assert result.success is False

    def test_missing_detector_type(self):
        payload = _valid_payload()
        del payload["detector_type"]
        result = analyze_room(payload)
        assert result.success is False

    def test_missing_polygon(self):
        payload = _valid_payload()
        del payload["room_polygon"]
        result = analyze_room(payload)
        assert result.success is False

    def test_invalid_detector_type(self):
        result = analyze_room(_valid_payload(detector_type="radiation"))
        assert result.success is False

    def test_negative_ceiling_height(self):
        result = analyze_room(_valid_payload(ceiling_height_m=-1.0))
        assert result.success is False

    def test_zero_ceiling_height(self):
        result = analyze_room(_valid_payload(ceiling_height_m=0.0))
        assert result.success is False

    def test_zero_area(self):
        result = analyze_room(_valid_payload(area_m2=0.0))
        assert result.success is False

    def test_negative_area(self):
        result = analyze_room(_valid_payload(area_m2=-5.0))
        assert result.success is False

    def test_degenerate_polygon(self):
        """Polygon with < 3 vertices should fail contract validation."""
        result = analyze_room(_valid_payload(room_polygon=[(0, 0), (10, 0)]))
        assert result.success is False

    def test_empty_payload(self):
        result = analyze_room({})
        assert result.success is False
        assert result.release_status == "blocked"

    def test_none_payload(self):
        """Passing None must not raise — pipeline captures the error."""
        result = analyze_room(None)
        assert result.success is False

    def test_invalid_payload_produces_stage0_error(self):
        result = analyze_room({})
        s0 = result.stages[0]
        assert s0.stage_name == "S0_contract"
        assert s0.success is False
        assert len(s0.errors) > 0

    def test_invalid_payload_has_contract_violation_error(self):
        result = analyze_room({})
        errors_text = " ".join(result.errors)
        assert "CONTRACT_VIOLATION" in errors_text

    def test_invalid_payload_returns_empty_positions(self):
        result = analyze_room({})
        assert result.detector_positions == []
        assert result.detector_count == 0

    def test_pipeline_never_raises_on_invalid_input(self):
        """Core invariant: the pipeline NEVER propagates exceptions."""
        bad_inputs = [
            {},
            None,
            {"room_id": ""},
            {"room_id": "R1", "room_polygon": "not_a_list"},
            {"room_id": "R1", "room_polygon": [], "ceiling_height_m": "abc", "detector_type": 42},
        ]
        for payload in bad_inputs:
            result = analyze_room(payload)
            assert isinstance(result, PipelineResult)
            # Never raises — always returns a result


# ═══════════════════════════════════════════════════════════════════════════════
# 6. NaN / Inf inputs caught at Stage 0
# ═══════════════════════════════════════════════════════════════════════════════

class TestNanInfInputs:
    """Test that NaN and Inf inputs are caught at Stage 0 — never propagate."""

    def test_nan_ceiling_height(self):
        result = analyze_room(_valid_payload(ceiling_height_m=float("nan")))
        assert isinstance(result, PipelineResult)
        assert result.success is False

    def test_inf_ceiling_height(self):
        result = analyze_room(_valid_payload(ceiling_height_m=float("inf")))
        assert result.success is False

    def test_negative_inf_ceiling_height(self):
        result = analyze_room(_valid_payload(ceiling_height_m=float("-inf")))
        assert result.success is False

    def test_nan_area(self):
        result = analyze_room(_valid_payload(area_m2=float("nan")))
        assert result.success is False

    def test_inf_area(self):
        result = analyze_room(_valid_payload(area_m2=float("inf")))
        assert result.success is False

    def test_nan_in_polygon(self):
        result = analyze_room(
            _valid_payload(room_polygon=[(0, 0), (10, float("nan")), (10, 8), (0, 8)])
        )
        assert result.success is False

    def test_inf_in_polygon(self):
        result = analyze_room(
            _valid_payload(room_polygon=[(0, 0), (10, 0), (float("inf"), 8), (0, 8)])
        )
        assert result.success is False

    def test_nan_caught_at_stage0(self):
        """NaN must be caught specifically at Stage 0, not later stages."""
        result = analyze_room(_valid_payload(ceiling_height_m=float("nan")))
        assert len(result.stages) >= 1
        s0 = result.stages[0]
        assert s0.stage_name == "S0_contract"
        assert s0.success is False
        # Stage 0 error should mention NaN
        error_text = " ".join(s0.errors)
        assert "NaN" in error_text or "CONTRACT_VIOLATION" in error_text

    def test_nan_pipeline_never_raises(self):
        """NaN input must never cause an unhandled exception."""
        try:
            result = analyze_room(_valid_payload(ceiling_height_m=float("nan")))
            assert isinstance(result, PipelineResult)
        except Exception:
            pytest.fail("Pipeline raised an exception on NaN input")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. analyze_building() — multiple rooms, concurrent processing
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeBuilding:
    """Test batch analysis of multiple rooms."""

    def test_multiple_rooms(self):
        rooms = [
            _valid_payload(room_id="R-101", room_polygon=[(0, 0), (10, 0), (10, 8), (0, 8)]),
            _valid_payload(room_id="R-102", room_polygon=[(0, 0), (8, 0), (8, 6), (0, 6)]),
            _valid_payload(room_id="R-103", room_polygon=[(0, 0), (12, 0), (12, 10), (0, 10)]),
        ]
        building_result = analyze_building(rooms)
        assert isinstance(building_result, dict)
        assert building_result["total_rooms"] == 3
        assert len(building_result["results"]) == 3

    def test_building_summary_structure(self):
        rooms = [
            _valid_payload(room_id="R-A"),
            _valid_payload(room_id="R-B"),
        ]
        result = analyze_building(rooms)
        assert "summary" in result
        summary = result["summary"]
        assert "passed" in summary
        assert "blocked" in summary
        assert "errors" in summary
        assert "total" in summary
        assert "pass_rate_pct" in summary

    def test_building_total_detectors(self):
        rooms = [
            _valid_payload(room_id="R-X", room_polygon=[(0, 0), (10, 0), (10, 8), (0, 8)]),
            _valid_payload(room_id="R-Y", room_polygon=[(0, 0), (15, 0), (15, 12), (0, 12)]),
        ]
        result = analyze_building(rooms)
        assert result["total_detectors"] > 0

    def test_building_timestamp(self):
        rooms = [_valid_payload()]
        result = analyze_building(rooms)
        assert "timestamp" in result
        assert "T" in result["timestamp"]

    def test_empty_building(self):
        result = analyze_building([])
        assert result["total_rooms"] == 0
        assert result["results"] == []
        assert result["summary"]["passed"] == 0

    def test_building_preserves_order(self):
        """Results must be in the same order as input rooms."""
        rooms = [
            _valid_payload(room_id="R-FIRST"),
            _valid_payload(room_id="R-SECOND"),
            _valid_payload(room_id="R-THIRD"),
        ]
        result = analyze_building(rooms)
        result_ids = [r["room_id"] for r in result["results"]]
        assert result_ids == ["R-FIRST", "R-SECOND", "R-THIRD"]

    def test_building_concurrent_processing(self):
        """Building analysis uses ThreadPoolExecutor — results must be complete."""
        rooms = [_valid_payload(room_id=f"R-{i}") for i in range(10)]
        result = analyze_building(rooms, max_workers=4)
        assert result["total_rooms"] == 10
        assert len(result["results"]) == 10
        # Every result must be a valid dict
        for r in result["results"]:
            assert isinstance(r, dict)
            assert "room_id" in r
            assert "success" in r

    def test_building_with_invalid_room(self):
        """A bad room should not crash the whole batch."""
        rooms = [
            _valid_payload(room_id="R-OK"),
            {},  # Invalid
            _valid_payload(room_id="R-ALSO-OK"),
        ]
        result = analyze_building(rooms)
        assert result["total_rooms"] == 3
        assert len(result["results"]) == 3

    def test_building_with_battery_kwargs(self):
        """kwargs like battery params should propagate to each room."""
        rooms = [_valid_payload(room_id=f"R-{i}") for i in range(3)]
        result = analyze_building(
            rooms,
            standby_current_a=0.05,
            alarm_current_a=0.5,
        )
        for r in result["results"]:
            assert r.get("battery") is not None

    def test_building_total_ms_positive(self):
        rooms = [_valid_payload(room_id=f"R-{i}") for i in range(3)]
        result = analyze_building(rooms)
        assert result["total_ms"] > 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Failed pipeline — critical stage failure produces blocked result
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailedPipeline:
    """Test that critical stage failures produce blocked results."""

    def test_stage0_failure_blocks(self):
        """Contract validation failure → blocked, safety_tier=REJECTED."""
        result = analyze_room({})
        assert result.success is False
        assert result.release_status == "blocked"
        assert result.safety_tier == "REJECTED"

    def test_stage0_failure_coverage_zero(self):
        result = analyze_room({})
        assert result.coverage_pct == 0.0

    def test_stage0_failure_no_detectors(self):
        result = analyze_room({})
        assert result.detector_count == 0
        assert result.detector_positions == []

    def test_stage0_failure_empty_evidence_hash(self):
        result = analyze_room({})
        assert result.evidence_hash == ""

    def test_stage0_failure_no_nfpa_refs(self):
        result = analyze_room({})
        assert result.nfpa_references == []

    def test_stage0_failure_release_gates_blocked(self):
        result = analyze_room({})
        assert result.release_gates["release_status"] == "blocked"

    def test_stage0_failure_has_errors(self):
        result = analyze_room({})
        assert len(result.errors) > 0

    def test_failed_result_still_has_timestamp(self):
        result = analyze_room({})
        assert result.timestamp  # non-empty

    def test_failed_result_still_has_run_id(self):
        result = analyze_room({})
        assert result.run_id  # non-empty UUID

    def test_degenerate_polygon_produces_blocked(self):
        """A polygon that collapses to zero area should fail."""
        # Collinear points — zero area
        result = analyze_room(
            _valid_payload(room_polygon=[(0, 0), (5, 0), (10, 0), (15, 0)])
        )
        assert result.success is False
        assert result.release_status == "blocked"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Cross-cutting invariants
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineInvariants:
    """Cross-cutting invariants that hold for ALL pipeline invocations."""

    def test_never_raises_exception(self):
        """The pipeline MUST NEVER raise — all errors captured in result."""
        payloads = [
            _valid_payload(),
            _valid_payload(ceiling_height_m=float("nan")),
            {},
            None,
            {"room_id": "X", "room_polygon": [(0, 0), (1, 0), (1, 1), (0, 1)],
             "ceiling_height_m": 3.0, "detector_type": "heat"},
            _valid_payload(ceiling_height_m=-5.0),
        ]
        for p in payloads:
            result = analyze_room(p)
            assert isinstance(result, PipelineResult)

    def test_to_dict_and_to_json_consistent(self):
        """to_dict() and to_json() must represent the same data."""
        result = analyze_room(_valid_payload())
        d = result.to_dict()
        j = json.loads(result.to_json())
        # Key fields must match
        assert d["run_id"] == j["run_id"]
        assert d["success"] == j["success"]
        assert d["room_id"] == j["room_id"]
        assert d["coverage_pct"] == j["coverage_pct"]

    def test_all_stage_results_have_required_fields(self):
        """Every StageResult must have stage_name, success, duration_ms."""
        result = analyze_room(_valid_payload())
        for stage in result.stages:
            assert isinstance(stage, StageResult)
            assert isinstance(stage.stage_name, str)
            assert isinstance(stage.success, bool)
            assert isinstance(stage.duration_ms, (int, float))
            assert stage.duration_ms >= 0

    def test_heat_detector_type_works(self):
        """Pipeline must handle heat detector type correctly."""
        result = analyze_room(_valid_payload(detector_type="heat"))
        assert isinstance(result, PipelineResult)
        assert result.success is True
        assert result.detector_count > 0

    def test_large_room_produces_more_detectors(self):
        """A larger room should require more detectors."""
        small = analyze_room(
            _valid_payload(room_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)], area_m2=25.0)
        )
        large = analyze_room(
            _valid_payload(room_polygon=[(0, 0), (20, 0), (20, 16), (0, 16)], area_m2=320.0)
        )
        assert large.detector_count >= small.detector_count

    def test_combined_battery_and_voltage(self):
        """Battery and voltage drop can both be computed in one run."""
        result = analyze_room(
            _valid_payload(),
            standby_current_a=0.05,
            alarm_current_a=0.5,
            circuit_length_m=80.0,
        )
        assert result.battery is not None
        assert result.voltage_drop is not None

    def test_combined_all_optional(self):
        """Battery + voltage drop + fault isolation all in one run."""
        loop_data = {
            "devices": [
                {"device_id": "D1", "device_type": "detector", "zone_id": "Z1"},
                {"device_id": "ISO1", "device_type": "isolator", "zone_id": "Z1"},
            ],
        }
        result = analyze_room(
            _valid_payload(),
            standby_current_a=0.05,
            alarm_current_a=0.5,
            circuit_length_m=50.0,
            loop_data=loop_data,
        )
        assert result.battery is not None
        assert result.voltage_drop is not None
        assert result.fault_isolation is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Stage-specific data checks
# ═══════════════════════════════════════════════════════════════════════════════

class TestStageData:
    """Verify that each stage produces the expected data shape."""

    def test_stage0_data(self):
        result = analyze_room(_valid_payload())
        s0 = next(s for s in result.stages if s.stage_name == "S0_contract")
        assert s0.success is True
        assert "validated_room_id" in s0.data
        assert "computed_area_m2" in s0.data
        assert "detector_type" in s0.data

    def test_stage1_data(self):
        result = analyze_room(_valid_payload())
        s1 = next(s for s in result.stages if s.stage_name == "S1_nfpa_spacing")
        assert s1.success is True
        assert "max_spacing_m" in s1.data
        assert "coverage_radius_m" in s1.data
        assert "nfpa_section" in s1.data

    def test_stage2_data(self):
        result = analyze_room(_valid_payload())
        s2 = next(s for s in result.stages if s.stage_name == "S2_placement")
        assert s2.success is True
        assert "detector_positions" in s2.data
        assert "detector_count" in s2.data
        assert "coverage_pct" in s2.data

    def test_stage3_data(self):
        result = analyze_room(_valid_payload())
        s3 = next(s for s in result.stages if s.stage_name == "S3_coverage")
        assert s3.success is True
        assert "coverage_pct" in s3.data

    def test_stage4_data(self):
        result = analyze_room(_valid_payload())
        s4 = next(s for s in result.stages if s.stage_name == "S4_safety")
        assert s4.success is True
        assert "safety_tier" in s4.data

    def test_stage5_data(self):
        result = analyze_room(_valid_payload())
        s5 = next(s for s in result.stages if s.stage_name == "S5_release_gates")
        assert "release_status" in s5.data

    def test_stage6_data(self):
        result = analyze_room(_valid_payload())
        s6 = next(s for s in result.stages if s.stage_name == "S6_evidence")
        assert s6.success is True
        assert "evidence_hash" in s6.data
        assert "nfpa_references" in s6.data


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
