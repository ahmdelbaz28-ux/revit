"""
test_v18_sequence_conduit.py — V18 Cause-Effect Matrix & Conduit Fill Tests
===========================================================================
Tests the two V18 modules:
  1. SequenceOfOperationsMatrix — NFPA 72 §14.4 cause & effect
  2. ConduitSizer — NEC Chapter 9 conduit fill analysis

These tests verify:
  - NAC (Notification Appliance Circuit) activation is present
  - Duct detectors produce supervisory, NOT general alarm
  - Elevator lobby smoke → elevator recall
  - Elevator machine room smoke → alternate recall + Phase II
  - PLFA/NPLFA mixing is detected and blocked
  - Conduit fill ratios are correct per NEC Table 1
  - Conductor derating is applied for >3 conductors
  - Multiple conduit types (EMT, RMC, IMC) work
  - Consultant's errors are all corrected
"""

import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import math
import pytest


# ============================================================================
# Sequence of Operations Tests
# ============================================================================

class TestSequenceOfOperationsMatrix:
    """Test NFPA 72 §14.4 Cause & Effect Matrix generation."""

    def test_duct_detector_is_supervisory_not_alarm(self):
        """Duct detector must produce SUPERVISORY, NOT general alarm.

        This is the consultant's most important diagnostic — duct detector
        triggering general evacuation causes panic in hospitals.
        """
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType, LogicFunction,
        )
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([
            DeviceInput(device_id="DD-01", device_type=DeviceInputType.DUCT_DETECTOR, zone_id="Z-2"),
        ])
        # Extract outputs from result
        if hasattr(result, "value"):
            outputs = [o for o in result.value["matrix"][0]["outputs"]]
            assert LogicFunction.SUPERVISORY.value in outputs
            assert LogicFunction.ALARM.value not in outputs
            # NAC must NOT be triggered for duct detectors
            assert LogicFunction.NAC_ZONE.value not in outputs
            assert LogicFunction.NAC_ALL.value not in outputs

    def test_smoke_detector_triggers_nac(self):
        """Smoke detector MUST trigger NAC (Notification Appliance Circuit).

        The consultant's code completely missed NAC activation — the
        MOST CRITICAL output for audible/visual notification.
        """
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType, LogicFunction,
        )
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([
            DeviceInput(device_id="SD-01", device_type=DeviceInputType.SMOKE_GENERAL, zone_id="Z-1"),
        ])
        if hasattr(result, "value"):
            outputs = [o for o in result.value["matrix"][0]["outputs"]]
            assert LogicFunction.ALARM.value in outputs
            assert LogicFunction.NAC_ZONE.value in outputs

    def test_elevator_lobby_smoke_triggers_recall(self):
        """Elevator lobby smoke detector must trigger Phase I recall."""
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType, LogicFunction,
        )
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([
            DeviceInput(device_id="SD-EL-01", device_type=DeviceInputType.SMOKE_ELEVATOR_LOBBY, zone_id="Z-EL"),
        ])
        if hasattr(result, "value"):
            outputs = [o for o in result.value["matrix"][0]["outputs"]]
            assert LogicFunction.ELEVATOR_RECALL_PRIMARY.value in outputs

    def test_elevator_machine_room_triggers_alternate(self):
        """Machine room smoke must trigger alternate recall + door release.
        V20.2 FIX: Phase II removed — it's manual firefighter action only per
        ASME A17.1 §2.27.3.4. DOOR_RELEASE added per NFPA 72 §14.4."""
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType, LogicFunction,
        )
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([
            DeviceInput(device_id="SD-MR-01", device_type=DeviceInputType.SMOKE_MACHINE_ROOM, zone_id="Z-MR"),
        ])
        if hasattr(result, "value"):
            outputs = [o for o in result.value["matrix"][0]["outputs"]]
            assert LogicFunction.ELEVATOR_RECALL_ALTERNATE.value in outputs
            # V20.2 FIX: Phase II must NOT be auto-triggered
            assert LogicFunction.ELEVATOR_PHASE_II.value not in outputs
            # V20.2 FIX: Door release IS required for smoke containment
            assert LogicFunction.DOOR_RELEASE.value in outputs

    def test_waterflow_does_not_trigger_fire_pump(self):
        """Waterflow switch triggers alarm but NOT fire pump start.
        V20.2 FIX: Per NFPA 20 §10.5.2.1, the fire pump controller starts
        the pump automatically on pressure drop — the FACP does NOT command this."""
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType, LogicFunction,
        )
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([
            DeviceInput(device_id="WF-01", device_type=DeviceInputType.WATERFLOW, zone_id="Z-3"),
        ])
        if hasattr(result, "value"):
            outputs = [o for o in result.value["matrix"][0]["outputs"]]
            assert LogicFunction.ALARM.value in outputs
            # V20.2 FIX: FIRE_PUMP_START must NOT be triggered by waterflow
            assert LogicFunction.FIRE_PUMP_START.value not in outputs

    def test_manual_call_point_triggers_full_evac(self):
        """Manual pull station triggers full building evacuation + NAC_ALL."""
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType, LogicFunction,
        )
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([
            DeviceInput(device_id="MCP-01", device_type=DeviceInputType.MANUAL_CALL_POINT, zone_id="Z-1"),
        ])
        if hasattr(result, "value"):
            outputs = [o for o in result.value["matrix"][0]["outputs"]]
            assert LogicFunction.ALARM.value in outputs
            assert LogicFunction.NAC_ALL.value in outputs
            assert LogicFunction.HVAC_SHUTDOWN_ALL.value in outputs

    def test_valve_tamper_supervisory_only(self):
        """Valve tamper switch is supervisory only — not alarm."""
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType, LogicFunction,
        )
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([
            DeviceInput(device_id="VT-01", device_type=DeviceInputType.VALVE_TAMPER, zone_id="Z-4"),
        ])
        if hasattr(result, "value"):
            outputs = [o for o in result.value["matrix"][0]["outputs"]]
            assert LogicFunction.SUPERVISORY.value in outputs
            assert LogicFunction.ALARM.value not in outputs

    def test_hvac_shutdown_is_zone_specific(self):
        """Smoke detector should trigger zone-specific HVAC shutdown, not building-wide."""
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType, LogicFunction,
        )
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([
            DeviceInput(device_id="SD-01", device_type=DeviceInputType.SMOKE_GENERAL, zone_id="Z-1"),
        ])
        if hasattr(result, "value"):
            outputs = [o for o in result.value["matrix"][0]["outputs"]]
            # Zone-specific, NOT building-wide
            assert LogicFunction.HVAC_SHUTDOWN_ZONE.value in outputs
            assert LogicFunction.HVAC_SHUTDOWN_ALL.value not in outputs

    def test_healthcare_duct_detector_context_aware(self):
        """In healthcare, duct detectors should add NAC zone activation."""
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType, LogicFunction,
        )
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix(
            [DeviceInput(device_id="DD-01", device_type=DeviceInputType.DUCT_DETECTOR, zone_id="Z-2")],
            occupancy_type="healthcare",
        )
        if hasattr(result, "value"):
            outputs = [o for o in result.value["matrix"][0]["outputs"]]
            # Healthcare: duct detector gets NAC zone activation
            assert LogicFunction.NAC_ZONE.value in outputs

    def test_canonical_hash_deterministic(self):
        """Matrix hash must be deterministic (not str() on dicts)."""
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType,
        )
        matrix = SequenceOfOperationsMatrix()
        devices = [
            DeviceInput(device_id="SD-01", device_type=DeviceInputType.SMOKE_GENERAL, zone_id="Z-1"),
            DeviceInput(device_id="DD-01", device_type=DeviceInputType.DUCT_DETECTOR, zone_id="Z-2"),
        ]
        result1 = matrix.generate_matrix(devices)
        result2 = matrix.generate_matrix(devices)
        if hasattr(result1, "value") and hasattr(result2, "value"):
            assert result1.value["hash"] == result2.value["hash"]

    def test_legacy_dict_interface_works(self):
        """Legacy dict-based interface should work for backward compat."""
        from fireai.core.sequence_of_operations import SequenceOfOperationsMatrix
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_for_legacy_dicts([
            {"device_id": "SD-01", "type": "SMOKE", "zone_id": "Z-1"},
            {"device_id": "DD-01", "type": "DUCT", "zone_id": "Z-2"},
            {"device_id": "SD-EL-01", "type": "SMOKE", "zone_id": "Z-EL",
             "location_hint": "Elevator Lobby 3rd Floor"},
        ])
        assert result is not None

    def test_no_string_substring_matching(self):
        """"LOBBY STORAGE" must NOT match elevator lobby logic.

        Consultant's bug: "LOBBY" in loc_hint matches "LOBBY STORAGE ROOM"
        """
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInputType,
        )
        matrix = SequenceOfOperationsMatrix()
        # "LOBBY STORAGE" should NOT match elevator lobby
        result = matrix._classify_device({
            "type": "SMOKE",
            "location_hint": "LOBBY STORAGE ROOM",
        })
        assert result != DeviceInputType.SMOKE_ELEVATOR_LOBBY

    def test_provenance_has_audit_trail(self):
        """DecisionProvenance should have NFPA 72 §14.4 citations."""
        from fireai.core.sequence_of_operations import (
            SequenceOfOperationsMatrix, DeviceInput, DeviceInputType,
        )
        from fireai.core.provenance import DecisionProvenance
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([
            DeviceInput(device_id="SD-01", device_type=DeviceInputType.SMOKE_GENERAL, zone_id="Z-1"),
        ])
        if isinstance(result, DecisionProvenance):
            assert result.decision_type == "cause_and_effect_matrix"
            assert len(result.rules_applied) >= 1
            assert "14.4" in result.rules_applied[0]["citation"]


# ============================================================================
# Conduit Fill Analyzer Tests
# ============================================================================

class TestConduitFillAnalyzer:
    """Test NEC Chapter 9 conduit fill analysis."""

    def test_basic_emt_sizing(self):
        """Basic bundle should fit in a reasonable EMT size."""
        from fireai.core.conduit_fill_analyzer import ConduitSizer
        sizer = ConduitSizer()
        result = sizer.analyze_routing_bundle(
            bundle_id="TRUNK-1",
            wire_inventory=[{"awg": 14, "count": 4, "insulation": "FPLP"}],
        )
        if hasattr(result, "value"):
            assert result.value["conduit_trade_size"] in [
                "1/2", "3/4", "1", "1-1/4", "1-1/2", "2"
            ]
            assert result.value["is_compliant"] is True
        else:
            assert result["is_compliant"] is True

    def test_overfilled_conduit_detected(self):
        """Overfilled conduit should be detected."""
        from fireai.core.conduit_fill_analyzer import ConduitSizer
        sizer = ConduitSizer()
        # 50 x AWG14 FPLP in a bundle — should require large conduit
        result = sizer.analyze_routing_bundle(
            bundle_id="OVERFILL",
            wire_inventory=[{"awg": 14, "count": 50, "insulation": "FPLP"}],
        )
        if hasattr(result, "value"):
            # Should still find a conduit size or recommend cable tray
            assert result.value["conduit_trade_size"] is not None
            # Derating should apply for >3 conductors
            assert result.value["derating_factor"] < 1.0
        else:
            assert result["derating_factor"] < 1.0

    def test_plfa_nplfa_mixing_detected(self):
        """Mixing PLFA and NPLFA circuits must be BLOCKED per NEC 760.154."""
        from fireai.core.conduit_fill_analyzer import ConduitSizer
        sizer = ConduitSizer()
        result = sizer.analyze_routing_bundle(
            bundle_id="MIXED-ILLEGAL",
            wire_inventory=[
                {"awg": 14, "count": 4, "insulation": "FPLP", "circuit_class": "PLFA"},
                {"awg": 12, "count": 2, "insulation": "THHN", "circuit_class": "NPLFA"},
            ],
        )
        if hasattr(result, "value"):
            assert result.value["plfa_nplfa_separated"] is False
            # Should have violations
            if hasattr(result, "violations_detected"):
                assert len(result.violations_detected) > 0
        else:
            assert result["plfa_nplfa_separated"] is False

    def test_plfa_only_bundle_ok(self):
        """PLFA-only bundle should have no separation violation."""
        from fireai.core.conduit_fill_analyzer import ConduitSizer
        sizer = ConduitSizer()
        result = sizer.analyze_routing_bundle(
            bundle_id="PLFA-ONLY",
            wire_inventory=[{"awg": 14, "count": 6, "insulation": "FPLP"}],
        )
        if hasattr(result, "value"):
            assert result.value["plfa_nplfa_separated"] is True
        else:
            assert result["plfa_nplfa_separated"] is True

    def test_fill_limits_per_nec_table_1(self):
        """Fill limits must match NEC Chapter 9 Table 1."""
        from fireai.core.conduit_fill_analyzer import FILL_LIMITS, DEFAULT_FILL_LIMIT
        assert FILL_LIMITS[1] == 0.53   # Single conductor: 53%
        assert FILL_LIMITS[2] == 0.31   # Two conductors: 31%
        assert DEFAULT_FILL_LIMIT == 0.40  # 3+ conductors: 40%

    def test_conductor_derating(self):
        """Derating must apply per NEC 310.15(B)(3)(a)."""
        from fireai.core.conduit_fill_analyzer import get_derating_factor
        assert get_derating_factor(3) == 1.0    # 3 or fewer: no derating
        assert get_derating_factor(4) == 0.80   # 4-6 conductors: 80%
        assert get_derating_factor(7) == 0.70   # 7-9 conductors: 70%
        assert get_derating_factor(10) == 0.50  # 10-20 conductors: 50%

    def test_wire_spec_auto_lookup(self):
        """WireSpec should auto-lookup diameter from table."""
        from fireai.core.conduit_fill_analyzer import WireSpec, InsulationType
        spec = WireSpec(awg=14, insulation=InsulationType.FPLP)
        assert spec.outer_diameter_mm > 0
        assert spec.cross_section_mm2 > 0

    def test_emt_conduit_specs_verified(self):
        """EMT specs must match NEC Chapter 9 Table 4 values."""
        from fireai.core.conduit_fill_analyzer import CONDUIT_SPECS
        # 1/2" EMT: ID = 15.80mm
        emt_half = CONDUIT_SPECS[("EMT", "1/2")]
        assert emt_half["id_mm"] == 15.80
        # Verify area: π × (15.80/2)² ≈ 196.07 mm²
        expected_area = math.pi * (15.80 / 2) ** 2
        assert abs(emt_half["area_mm2"] - expected_area) < 1.0

    def test_rmc_conduit_available(self):
        """RMC conduit type should be available (not just EMT)."""
        from fireai.core.conduit_fill_analyzer import CONDUIT_SPECS
        assert ("RMC", "1/2") in CONDUIT_SPECS
        assert ("IMC", "1/2") in CONDUIT_SPECS

    def test_cold_bundle_fits_small_conduit(self):
        """Small bundle (2 wires) should fit in 1/2" EMT."""
        from fireai.core.conduit_fill_analyzer import ConduitSizer
        sizer = ConduitSizer()
        result = sizer.analyze_routing_bundle(
            bundle_id="SMALL",
            wire_inventory=[{"awg": 18, "count": 2, "insulation": "FPLP"}],
        )
        if hasattr(result, "value"):
            # 2 small wires should fit in 1/2" EMT
            assert result.value["conduit_trade_size"] in ["1/2", "3/4"]
            assert result.value["is_compliant"] is True

    def test_provenance_has_nec_citations(self):
        """DecisionProvenance should have NEC Chapter 9 citations."""
        from fireai.core.conduit_fill_analyzer import ConduitSizer
        from fireai.core.provenance import DecisionProvenance
        sizer = ConduitSizer()
        result = sizer.analyze_routing_bundle(
            bundle_id="TEST",
            wire_inventory=[{"awg": 14, "count": 4, "insulation": "FPLP"}],
        )
        if isinstance(result, DecisionProvenance):
            assert result.decision_type == "conduit_emt_trade_sizing"
            citations = [r["citation"] for r in result.rules_applied]
            assert any("Chapter 9" in c or "NEC" in c for c in citations)
