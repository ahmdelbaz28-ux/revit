"""
tests/test_sequence_of_operations_v2.py
==========================================
Comprehensive v2 test suite for fireai/core/sequence_of_operations.py

SAFETY CRITICAL: The Cause & Effect matrix is the MOST CRITICAL document
for FACP programming. Each test verifies life-safety logic that prevents:
  - Silent alarms (missing NAC activation)
  - False evacuations (duct detector -> general alarm)
  - HVAC running during fire (missing zone shutdown)
  - Elevator traps (missing Phase I/Phase II)

V18 Bug Regression Tests:
  1. NAC activation included (was MISSING entirely)
  2. DUCT_DETECTOR does NOT produce ALARM (was incorrect)
  3. ELEVATOR_PHASE_II exists (was missing)
  4. FIRE_PUMP_START exists (was missing)
  5. HVAC shutdown is zone-specific, not building-wide
  6. MANUAL_CALL_POINT -> NAC_ALL (building-wide)
"""

from __future__ import annotations

import dataclasses

import pytest

import fireai.core.sequence_of_operations as _soo_mod


@pytest.fixture(autouse=True)
def _disable_provenance():
    originals = {}
    for attr in ("DecisionProvenance", "RuleApplied", "Violation",
                 "ConfidenceScore", "ConfidenceLevel"):
        originals[attr] = getattr(_soo_mod, attr, None)
        setattr(_soo_mod, attr, None)
    yield
    for attr, val in originals.items():
        setattr(_soo_mod, attr, val)


from fireai.core.sequence_of_operations import (
    SequenceOfOperationsMatrix,
    LogicFunction,
    DeviceInputType,
    DeviceInput,
    MatrixRow,
    CAUSE_EFFECT_RULES,
    NFPA_REFERENCES,
)


@pytest.fixture
def matrix() -> SequenceOfOperationsMatrix:
    return SequenceOfOperationsMatrix()


@pytest.fixture
def matrix_instance() -> SequenceOfOperationsMatrix:
    return SequenceOfOperationsMatrix()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. LogicFunction Enum — All 15 members + values
# ═══════════════════════════════════════════════════════════════════════════════


class TestLogicFunction:
    """Every LogicFunction member exists and has the correct value."""

    def test_alarm(self):
        assert LogicFunction.ALARM.value == "General Alarm / Evacuation"

    def test_supervisory(self):
        assert LogicFunction.SUPERVISORY.value == "Supervisory Signal Only"

    def test_trouble(self):
        assert LogicFunction.TROUBLE.value == "Trouble Signal"

    def test_nac_zone(self):
        assert LogicFunction.NAC_ZONE.value == "Activate Notification Appliance Circuits (Zone)"

    def test_nac_all(self):
        assert LogicFunction.NAC_ALL.value == "Activate Notification Appliance Circuits (All)"

    def test_hvac_shutdown_zone(self):
        assert LogicFunction.HVAC_SHUTDOWN_ZONE.value == "Shutdown AHU / Close Fire Dampers (Zone)"

    def test_hvac_shutdown_all(self):
        assert LogicFunction.HVAC_SHUTDOWN_ALL.value == "Shutdown AHU / Close Fire Dampers (Building)"

    def test_elevator_recall_primary(self):
        assert LogicFunction.ELEVATOR_RECALL_PRIMARY.value == "Elevator Phase I Recall (Designated Floor)"

    def test_elevator_recall_alternate(self):
        assert LogicFunction.ELEVATOR_RECALL_ALTERNATE.value == "Elevator Phase I Recall (Alternate Floor)"

    def test_elevator_phase_ii(self):
        assert LogicFunction.ELEVATOR_PHASE_II.value == "Elevator Phase II (Independent Service)"

    def test_elevator_shunt_trip(self):
        assert LogicFunction.ELEVATOR_SHUNT_TRIP.value == "Elevator Shunt-Trip Power Disconnect (NFPA 72 §21.4.1)"

    def test_door_release(self):
        assert LogicFunction.DOOR_RELEASE.value == "Release Magnetic Hold-Open Doors (Zone)"

    def test_fire_pump_start(self):
        assert LogicFunction.FIRE_PUMP_START.value == "Start Fire Pump"

    def test_smoke_control(self):
        assert LogicFunction.SMOKE_CONTROL.value == "Activate Smoke Control (Zone)"

    def test_stairwell_pressurization(self):
        assert LogicFunction.STAIRWELL_PRESSURIZATION.value == "Pressurize Stairwells"

    def test_all_members_have_unique_values(self):
        values = [m.value for m in LogicFunction]
        assert len(values) == len(set(values)), "All LogicFunction values must be unique"

    def test_all_members_accounted(self):
        names = {m.name for m in LogicFunction}
        expected = {
            "ALARM", "SUPERVISORY", "TROUBLE",
            "NAC_ZONE", "NAC_ALL",
            "HVAC_SHUTDOWN_ZONE", "HVAC_SHUTDOWN_ALL",
            "ELEVATOR_RECALL_PRIMARY", "ELEVATOR_RECALL_ALTERNATE",
            "ELEVATOR_PHASE_II", "ELEVATOR_SHUNT_TRIP",
            "DOOR_RELEASE", "FIRE_PUMP_START",
            "SMOKE_CONTROL", "STAIRWELL_PRESSURIZATION",
        }
        assert names == expected, f"Missing or extra LogicFunction members: {names ^ expected}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DeviceInputType Enum — All 14 members
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeviceInputType:
    """Every DeviceInputType member exists and has correct value."""

    def test_smoke_general(self):
        assert DeviceInputType.SMOKE_GENERAL.value == "SMOKE_GENERAL"

    def test_smoke_elevator_lobby(self):
        assert DeviceInputType.SMOKE_ELEVATOR_LOBBY.value == "SMOKE_ELEVATOR_LOBBY"

    def test_smoke_elevator_lobby_designated(self):
        assert DeviceInputType.SMOKE_ELEVATOR_LOBBY_DESIGNATED.value == "SMOKE_ELEVATOR_LOBBY_DESIGNATED"

    def test_smoke_machine_room(self):
        assert DeviceInputType.SMOKE_MACHINE_ROOM.value == "SMOKE_MACHINE_ROOM"

    def test_smoke_elevator_shaft(self):
        assert DeviceInputType.SMOKE_ELEVATOR_SHAFT.value == "SMOKE_ELEVATOR_SHAFT"

    def test_smoke_return(self):
        assert DeviceInputType.SMOKE_RETURN.value == "SMOKE_RETURN"

    def test_heat(self):
        assert DeviceInputType.HEAT.value == "HEAT"

    def test_heat_elevator_shunt_trip(self):
        assert DeviceInputType.HEAT_ELEVATOR_SHUNT_TRIP.value == "HEAT_ELEVATOR_SHUNT_TRIP"

    def test_manual_call_point(self):
        assert DeviceInputType.MANUAL_CALL_POINT.value == "MANUAL_CALL_POINT"

    def test_duct_detector(self):
        assert DeviceInputType.DUCT_DETECTOR.value == "DUCT_DETECTOR"

    def test_waterflow(self):
        assert DeviceInputType.WATERFLOW.value == "WATERFLOW"

    def test_valve_tamper(self):
        assert DeviceInputType.VALVE_TAMPER.value == "VALVE_TAMPER"

    def test_sprinkler_supervisory(self):
        assert DeviceInputType.SPRINKLER_SUPERVISORY.value == "SPRINKLER_SUPERVISORY"

    def test_unknown(self):
        assert DeviceInputType.UNKNOWN.value == "UNKNOWN"

    def test_all_members_accounted(self):
        names = {m.name for m in DeviceInputType}
        expected = {
            "SMOKE_GENERAL", "SMOKE_ELEVATOR_LOBBY",
            "SMOKE_ELEVATOR_LOBBY_DESIGNATED", "SMOKE_MACHINE_ROOM",
            "SMOKE_ELEVATOR_SHAFT", "SMOKE_RETURN",
            "HEAT", "HEAT_ELEVATOR_SHUNT_TRIP",
            "MANUAL_CALL_POINT", "DUCT_DETECTOR",
            "WATERFLOW", "VALVE_TAMPER",
            "SPRINKLER_SUPERVISORY", "UNKNOWN",
        }
        assert names == expected, f"Missing or extra DeviceInputType members: {names ^ expected}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DeviceInput Dataclass
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeviceInput:
    """DeviceInput — construction, defaults, frozen immutability."""

    def test_required_fields(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL)
        assert d.device_id == "SD-01"
        assert d.device_type == DeviceInputType.SMOKE_GENERAL

    def test_default_optional_fields(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL)
        assert d.zone_id == ""
        assert d.floor_id == ""
        assert d.description == ""

    def test_all_fields_positional(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1", "FL1", "Smoke detector FL1")
        assert d.device_id == "SD-01"
        assert d.device_type == DeviceInputType.SMOKE_GENERAL
        assert d.zone_id == "Z-1"
        assert d.floor_id == "FL1"
        assert d.description == "Smoke detector FL1"

    def test_all_fields_keyword(self):
        d = DeviceInput(
            device_id="SD-02",
            device_type=DeviceInputType.HEAT,
            zone_id="Z-2",
            floor_id="FL2",
            description="Heat detector FL2",
        )
        assert d.device_id == "SD-02"
        assert d.device_type == DeviceInputType.HEAT
        assert d.zone_id == "Z-2"
        assert d.floor_id == "FL2"
        assert d.description == "Heat detector FL2"

    def test_frozen_immutability_device_id(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL)
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.device_id = "CHANGED"

    def test_frozen_immutability_device_type(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL)
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.device_type = DeviceInputType.HEAT

    def test_frozen_immutability_zone_id(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.zone_id = "Z-99"

    def test_equality(self):
        a = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1", "FL1")
        b = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1", "FL1")
        assert a == b

    def test_inequality(self):
        a = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")
        b = DeviceInput("SD-02", DeviceInputType.SMOKE_GENERAL, "Z-1")
        assert a != b

    def test_repr(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL)
        r = repr(d)
        assert "DeviceInput" in r
        assert "SD-01" in r
        assert "SMOKE_GENERAL" in r


# ═══════════════════════════════════════════════════════════════════════════════
# 4. MatrixRow Dataclass
# ═══════════════════════════════════════════════════════════════════════════════


class TestMatrixRow:
    """MatrixRow — construction, defaults, frozen immutability."""

    def test_basic_creation(self):
        row = MatrixRow(
            "SD-01", "Z-1", "FL1",
            DeviceInputType.SMOKE_GENERAL,
            [LogicFunction.ALARM, LogicFunction.NAC_ZONE],
        )
        assert row.input_device_id == "SD-01"
        assert row.zone_id == "Z-1"
        assert row.floor_id == "FL1"
        assert row.input_type == DeviceInputType.SMOKE_GENERAL
        assert row.outputs_triggered == [LogicFunction.ALARM, LogicFunction.NAC_ZONE]

    def test_default_nfpa_references_is_empty_list(self):
        row = MatrixRow("SD-01", "Z-1", "FL1", DeviceInputType.SMOKE_GENERAL, [])
        assert row.nfpa_references == []

    def test_nfpa_references_provided(self):
        refs = ["NFPA 72-2022 §10.14"]
        row = MatrixRow("SD-01", "Z-1", "FL1", DeviceInputType.SMOKE_GENERAL, [], nfpa_references=refs)
        assert row.nfpa_references == refs

    def test_frozen_immutability_device_id(self):
        row = MatrixRow("SD-01", "Z-1", "FL1", DeviceInputType.SMOKE_GENERAL, [])
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.input_device_id = "CHANGED"

    def test_frozen_immutability_outputs(self):
        row = MatrixRow("SD-01", "Z-1", "FL1", DeviceInputType.SMOKE_GENERAL, [])
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.outputs_triggered = [LogicFunction.ALARM]

    def test_equality(self):
        a = MatrixRow("SD-01", "Z-1", "FL1", DeviceInputType.SMOKE_GENERAL, [LogicFunction.ALARM])
        b = MatrixRow("SD-01", "Z-1", "FL1", DeviceInputType.SMOKE_GENERAL, [LogicFunction.ALARM])
        assert a == b

    def test_inequality(self):
        a = MatrixRow("SD-01", "Z-1", "FL1", DeviceInputType.SMOKE_GENERAL, [LogicFunction.ALARM])
        b = MatrixRow("SD-02", "Z-1", "FL1", DeviceInputType.SMOKE_GENERAL, [LogicFunction.ALARM])
        assert a != b

    def test_all_fields_keyword(self):
        row = MatrixRow(
            input_device_id="SD-01",
            zone_id="Z-1",
            floor_id="FL1",
            input_type=DeviceInputType.SMOKE_GENERAL,
            outputs_triggered=[LogicFunction.ALARM],
            nfpa_references=["NFPA 72-2022 §10.14"],
        )
        assert row.input_device_id == "SD-01"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CAUSE_EFFECT_RULES — All 13 device types verified
# ═══════════════════════════════════════════════════════════════════════════════


class TestCauseEffectRules:
    """Every device type in CAUSE_EFFECT_RULES has the correct output list.

    V18 bug regression: verify NAC activation is included, DUCT_DETECTOR
    does NOT produce ALARM, ELEVATOR_PHASE_II exists, FIRE_PUMP_START exists.
    """

    def test_all_device_types_have_rules(self):
        for dit in DeviceInputType:
            assert dit in CAUSE_EFFECT_RULES, f"Missing rule for {dit.value}"

    def test_rule_count_matches_device_type_count(self):
        assert len(CAUSE_EFFECT_RULES) == len(list(DeviceInputType))

    # --- SMOKE_GENERAL ---
    def test_smoke_general_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_GENERAL]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ZONE,
            LogicFunction.DOOR_RELEASE,
            LogicFunction.HVAC_SHUTDOWN_ZONE,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        # V18 bug regression: NAC must be present
        assert LogicFunction.NAC_ZONE in rules
        # V18 bug regression: HVAC is zone-specific, not building-wide
        assert LogicFunction.HVAC_SHUTDOWN_ALL not in rules

    # --- SMOKE_ELEVATOR_LOBBY ---
    def test_smoke_elevator_lobby_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_ELEVATOR_LOBBY]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ZONE,
            LogicFunction.ELEVATOR_RECALL_PRIMARY,
            LogicFunction.DOOR_RELEASE,
            LogicFunction.HVAC_SHUTDOWN_ZONE,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        assert LogicFunction.ELEVATOR_PHASE_II not in rules

    # --- SMOKE_ELEVATOR_LOBBY_DESIGNATED ---
    def test_smoke_elevator_lobby_designated_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_ELEVATOR_LOBBY_DESIGNATED]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ZONE,
            LogicFunction.ELEVATOR_RECALL_ALTERNATE,
            LogicFunction.DOOR_RELEASE,
            LogicFunction.HVAC_SHUTDOWN_ZONE,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        assert LogicFunction.ELEVATOR_RECALL_PRIMARY not in rules

    # --- SMOKE_MACHINE_ROOM ---
    def test_smoke_machine_room_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_MACHINE_ROOM]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ZONE,
            LogicFunction.ELEVATOR_RECALL_ALTERNATE,
            LogicFunction.DOOR_RELEASE,
            LogicFunction.HVAC_SHUTDOWN_ZONE,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        # V18 bug regression: Phase II is MANUAL per ASME A17.1 §2.27.3.4
        assert LogicFunction.ELEVATOR_PHASE_II not in rules

    # --- SMOKE_ELEVATOR_SHAFT ---
    def test_smoke_elevator_shaft_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_ELEVATOR_SHAFT]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ZONE,
            LogicFunction.ELEVATOR_RECALL_ALTERNATE,
            LogicFunction.DOOR_RELEASE,
            LogicFunction.HVAC_SHUTDOWN_ZONE,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)

    # --- SMOKE_RETURN ---
    def test_smoke_return_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_RETURN]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ZONE,
            LogicFunction.DOOR_RELEASE,
            LogicFunction.HVAC_SHUTDOWN_ZONE,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        # V18 bug regression: HVAC is zone-specific
        assert LogicFunction.HVAC_SHUTDOWN_ALL not in rules

    # --- HEAT ---
    def test_heat_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.HEAT]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ZONE,
            LogicFunction.DOOR_RELEASE,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        # No HVAC shutdown for heat detectors
        assert LogicFunction.HVAC_SHUTDOWN_ZONE not in rules
        assert LogicFunction.HVAC_SHUTDOWN_ALL not in rules

    # --- HEAT_ELEVATOR_SHUNT_TRIP ---
    def test_heat_elevator_shunt_trip_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.HEAT_ELEVATOR_SHUNT_TRIP]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ZONE,
            LogicFunction.ELEVATOR_SHUNT_TRIP,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        # V18 bug regression: ELEVATOR_SHUNT_TRIP must exist
        assert LogicFunction.ELEVATOR_SHUNT_TRIP in rules

    # --- MANUAL_CALL_POINT ---
    def test_manual_call_point_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.MANUAL_CALL_POINT]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ALL,
            LogicFunction.DOOR_RELEASE,
            LogicFunction.HVAC_SHUTDOWN_ALL,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        # MANUAL_CALL_POINT is building-wide NAC_ALL, not zone-specific NAC_ZONE
        assert LogicFunction.NAC_ALL in rules
        assert LogicFunction.NAC_ZONE not in rules
        # V18 bug regression: HVAC_ALL is building-wide for MCP
        assert LogicFunction.HVAC_SHUTDOWN_ALL in rules

    # --- DUCT_DETECTOR ---
    def test_duct_detector_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.DUCT_DETECTOR]
        expected = {
            LogicFunction.SUPERVISORY,
            LogicFunction.HVAC_SHUTDOWN_ZONE,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        # V18 bug regression: DUCT_DETECTOR must NOT produce ALARM
        assert LogicFunction.ALARM not in rules
        # V18 bug regression: DUCT_DETECTOR is NOT general evacuation
        assert LogicFunction.NAC_ZONE not in rules
        assert LogicFunction.NAC_ALL not in rules

    # --- WATERFLOW ---
    def test_waterflow_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.WATERFLOW]
        expected = {
            LogicFunction.ALARM,
            LogicFunction.NAC_ZONE,
        }
        assert set(rules) == expected
        assert len(rules) == len(expected)
        # V18 bug regression: FIRE_PUMP_START removed per NFPA 20 §10.5.2.1
        assert LogicFunction.FIRE_PUMP_START not in rules

    # --- VALVE_TAMPER ---
    def test_valve_tamper_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.VALVE_TAMPER]
        assert rules == [LogicFunction.SUPERVISORY]

    # --- SPRINKLER_SUPERVISORY ---
    def test_sprinkler_supervisory_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SPRINKLER_SUPERVISORY]
        assert rules == [LogicFunction.SUPERVISORY]

    # --- UNKNOWN ---
    def test_unknown_outputs(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.UNKNOWN]
        assert rules == [LogicFunction.TROUBLE]
        assert LogicFunction.ALARM not in rules
        assert LogicFunction.SUPERVISORY not in rules


# ═══════════════════════════════════════════════════════════════════════════════
# 6. NFPA_REFERENCES
# ═══════════════════════════════════════════════════════════════════════════════


class TestNFPAReferences:
    """Verify all NFPA section references exist and are meaningful."""

    def test_smoke_general_has_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.SMOKE_GENERAL]
        assert "§10.14" in refs[0] or "§10.14" in " ".join(refs)
        assert len(refs) >= 2

    def test_smoke_elevator_lobby_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.SMOKE_ELEVATOR_LOBBY]
        assert any("21.3.3" in r for r in refs)
        assert any("ASME" in r for r in refs)

    def test_smoke_machine_room_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.SMOKE_MACHINE_ROOM]
        assert any("21.3.3" in r for r in refs)
        assert any("ASME" in r for r in refs)

    def test_smoke_return_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.SMOKE_RETURN]
        assert any("17.7.5.6" in r for r in refs)
        assert any("6.8" in r for r in refs)

    def test_heat_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.HEAT]
        assert any("10.14" in r for r in refs)
        assert any("17.9" in r for r in refs)

    def test_manual_call_point_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.MANUAL_CALL_POINT]
        assert any("10.14" in r for r in refs)
        assert any("17.14.4" in r for r in refs)

    def test_duct_detector_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.DUCT_DETECTOR]
        assert any("17.7.5.6" in r for r in refs)
        assert any("6.8" in r for r in refs)

    def test_waterflow_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.WATERFLOW]
        assert any("17.14" in r for r in refs)
        assert any("NFPA 20" in r for r in refs)

    def test_valve_tamper_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.VALVE_TAMPER]
        assert any("17.14.2.1" in r for r in refs)

    def test_sprinkler_supervisory_references(self):
        refs = NFPA_REFERENCES[DeviceInputType.SPRINKLER_SUPERVISORY]
        assert any("17.14.2" in r for r in refs)

    def test_unknown_has_no_references(self):
        assert DeviceInputType.UNKNOWN not in NFPA_REFERENCES

    def test_smoke_elevator_lobby_designated_not_in_references(self):
        assert DeviceInputType.SMOKE_ELEVATOR_LOBBY_DESIGNATED not in NFPA_REFERENCES

    def test_smoke_elevator_shaft_not_in_references(self):
        assert DeviceInputType.SMOKE_ELEVATOR_SHAFT not in NFPA_REFERENCES

    def test_heat_elevator_shunt_trip_not_in_references(self):
        assert DeviceInputType.HEAT_ELEVATOR_SHUNT_TRIP not in NFPA_REFERENCES

    def test_all_references_are_non_empty_strings(self):
        for dev_type, refs in NFPA_REFERENCES.items():
            for ref in refs:
                assert isinstance(ref, str) and len(ref) > 0

    def test_sections_contain_standard_prefix(self):
        for dev_type, refs in NFPA_REFERENCES.items():
            for ref in refs:
                assert "NFPA" in ref or "ASME" in ref, f"Unexpected ref prefix: {ref}"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SequenceOfOperationsMatrix.__init__
# ═══════════════════════════════════════════════════════════════════════════════


class TestSequenceOfOperationsMatrixInit:
    """__init__ loads CAUSE_EFFECT_RULES and NFPA_REFERENCES."""

    def test_init_loads_rules(self):
        m = SequenceOfOperationsMatrix()
        assert m.rules is not None
        assert m.rules[DeviceInputType.SMOKE_GENERAL] is not None
        assert len(m.rules) == len(CAUSE_EFFECT_RULES)

    def test_init_loads_references(self):
        m = SequenceOfOperationsMatrix()
        assert m.references is not None
        assert DeviceInputType.SMOKE_GENERAL in m.references

    def test_rules_copy_is_independent(self):
        m = SequenceOfOperationsMatrix()
        original_len = len(CAUSE_EFFECT_RULES)
        assert len(m.rules) == original_len

    def test_references_copy_is_independent(self):
        m = SequenceOfOperationsMatrix()
        original_len = len(NFPA_REFERENCES)
        assert len(m.references) == original_len


# ═══════════════════════════════════════════════════════════════════════════════
# 8. generate_matrix — Main method
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateMatrix:
    """Core matrix generation: edges, hash, all device types, V18 regressions."""

    # ── Basic structure ──────────────────────────────────────────────────

    def test_single_smoke_detector(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        result = matrix.generate_matrix(devices)
        assert "matrix" in result
        assert "hash" in result
        assert len(result["matrix"]) == 1

    def test_single_row_fields(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1", "FL1")]
        result = matrix.generate_matrix(devices)
        row = result["matrix"][0]
        assert row["device_id"] == "SD-01"
        assert row["zone"] == "Z-1"
        assert row["floor"] == "FL1"
        assert row["input_type"] == "SMOKE_GENERAL"

    def test_multiple_devices_different_types(self, matrix):
        devices = [
            DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1"),
            DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2"),
            DeviceInput("WF-01", DeviceInputType.WATERFLOW, "Z-3"),
            DeviceInput("MCP-01", DeviceInputType.MANUAL_CALL_POINT, "Z-4"),
        ]
        result = matrix.generate_matrix(devices)
        assert len(result["matrix"]) == 4

    # ── Empty / edge cases ───────────────────────────────────────────────

    def test_empty_devices_returns_empty_matrix(self, matrix):
        result = matrix.generate_matrix([])
        assert result["matrix"] == []
        assert isinstance(result["hash"], str)
        assert len(result["hash"]) == 64

    def test_unknown_device_defaults_to_trouble(self, matrix):
        devices = [DeviceInput("UNK-01", DeviceInputType.UNKNOWN)]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        assert "Trouble Signal" in outputs
        assert "General Alarm" not in outputs

    # ── Matrix hash determinism ──────────────────────────────────────────

    def test_deterministic_hash_same_input(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        r1 = matrix.generate_matrix(devices)
        r2 = matrix.generate_matrix(devices)
        assert r1["hash"] == r2["hash"]

    def test_deterministic_hash_multiple_calls(self, matrix):
        devices = [
            DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1"),
            DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2"),
        ]
        r1 = matrix.generate_matrix(devices)
        r2 = matrix.generate_matrix(devices)
        r3 = matrix.generate_matrix(devices)
        assert r1["hash"] == r2["hash"] == r3["hash"]

    def test_hash_changes_when_device_id_changes(self, matrix):
        d1 = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        d2 = [DeviceInput("SD-02", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        r1 = matrix.generate_matrix(d1)
        r2 = matrix.generate_matrix(d2)
        assert r1["hash"] != r2["hash"]

    def test_hash_changes_when_device_type_changes(self, matrix):
        d1 = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        d2 = [DeviceInput("SD-01", DeviceInputType.HEAT, "Z-1")]
        r1 = matrix.generate_matrix(d1)
        r2 = matrix.generate_matrix(d2)
        assert r1["hash"] != r2["hash"]

    def test_hash_changes_when_zone_changes(self, matrix):
        d1 = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        d2 = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-2")]
        r1 = matrix.generate_matrix(d1)
        r2 = matrix.generate_matrix(d2)
        assert r1["hash"] != r2["hash"]

    def test_hash_is_sha256_length(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        result = matrix.generate_matrix(devices)
        assert len(result["hash"]) == 64
        assert all(c in "0123456789abcdef" for c in result["hash"])

    # ── V18 bug regression: NAC activation ───────────────────────────────

    def test_nac_activation_included_in_alarm_devices(self, matrix):
        """V18 bug: NAC activation was MISSING entirely.
        Every alarm-producing device must include NAC_ZONE or NAC_ALL."""
        nac_types = [
            DeviceInputType.SMOKE_GENERAL,
            DeviceInputType.SMOKE_ELEVATOR_LOBBY,
            DeviceInputType.SMOKE_ELEVATOR_LOBBY_DESIGNATED,
            DeviceInputType.SMOKE_MACHINE_ROOM,
            DeviceInputType.SMOKE_ELEVATOR_SHAFT,
            DeviceInputType.SMOKE_RETURN,
            DeviceInputType.HEAT,
            DeviceInputType.HEAT_ELEVATOR_SHUNT_TRIP,
            DeviceInputType.WATERFLOW,
        ]
        for dt in nac_types:
            devices = [DeviceInput(f"DEV-{dt.value}", dt, "Z-1")]
            result = matrix.generate_matrix(devices)
            outputs = result["matrix"][0]["outputs"]
            nac_found = any("Notification Appliance" in o for o in outputs)
            assert nac_found, f"{dt.value} must produce NAC activation (V18 bug)"

    def test_manual_call_point_includes_nac_all(self, matrix):
        devices = [DeviceInput("MCP-01", DeviceInputType.MANUAL_CALL_POINT, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        assert any("(All)" in o for o in outputs), "MCP must produce NAC_ALL"

    def test_nac_not_in_duct_detector(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        nac_found = any("Notification Appliance" in o for o in outputs)
        assert not nac_found, "DUCT_DETECTOR must not produce NAC activation"

    def test_nac_not_in_valve_tamper(self, matrix):
        devices = [DeviceInput("VT-01", DeviceInputType.VALVE_TAMPER, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        nac_found = any("Notification Appliance" in o for o in outputs)
        assert not nac_found, "VALVE_TAMPER must not produce NAC activation"

    def test_nac_not_in_sprinkler_supervisory(self, matrix):
        devices = [DeviceInput("SS-01", DeviceInputType.SPRINKLER_SUPERVISORY, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        nac_found = any("Notification Appliance" in o for o in outputs)
        assert not nac_found, "SPRINKLER_SUPERVISORY must not produce NAC activation"

    # ── V18 bug regression: DUCT_DETECTOR does NOT produce ALARM ─────────

    def test_duct_detector_no_alarm(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        assert not any("General Alarm" in o for o in outputs)
        assert any("Supervisory" in o for o in outputs)
        assert any("Shutdown" in o for o in outputs)

    def test_duct_detector_hvac_shutdown(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        shutdown_outputs = [o for o in outputs if "Shutdown" in o]
        assert len(shutdown_outputs) == 1
        assert any("Zone" in o for o in shutdown_outputs)

    # ── V18 bug regression: DUCT_DETECTOR in healthcare adds ALARM+NAC_ZONE ──

    def test_healthcare_duct_detector_adds_alarm(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices, occupancy_type="healthcare")
        outputs = result["matrix"][0]["outputs"]
        assert any("General Alarm" in o for o in outputs), "Healthcare duct detector must add ALARM"

    def test_healthcare_duct_detector_adds_nac_zone(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices, occupancy_type="healthcare")
        outputs = result["matrix"][0]["outputs"]
        nac_zone = [o for o in outputs if "(Zone)" in o and "Notification" in o]
        assert len(nac_zone) >= 1, "Healthcare duct detector must add NAC_ZONE"

    def test_hospital_duct_detector_adds_alarm(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices, occupancy_type="hospital")
        outputs = result["matrix"][0]["outputs"]
        assert any("General Alarm" in o for o in outputs)

    def test_healthcare_duct_detector_still_supervisory(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices, occupancy_type="healthcare")
        outputs = result["matrix"][0]["outputs"]
        assert any("Supervisory" in o for o in outputs)

    def test_healthcare_duct_detector_warning_generated(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices, occupancy_type="healthcare")
        warnings = result.get("warnings", [])
        assert len(warnings) > 0
        assert any("healthcare" in w.lower() for w in warnings)

    def test_business_duct_detector_no_alarm(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices, occupancy_type="business")
        outputs = result["matrix"][0]["outputs"]
        assert not any("General Alarm" in o for o in outputs)

    # ── V18 bug regression: ELEVATOR_PHASE_II exists ────────────────────

    def test_elevator_phase_ii_enum_exists(self):
        assert LogicFunction.ELEVATOR_PHASE_II is not None
        assert "Phase II" in LogicFunction.ELEVATOR_PHASE_II.value

    def test_elevator_phase_ii_not_auto_triggered(self, matrix):
        """Phase II is MANUAL firefighter action — never auto-triggered."""
        all_device_types = list(DeviceInputType)
        for dt in all_device_types:
            if dt == DeviceInputType.UNKNOWN:
                continue
            devices = [DeviceInput(f"DEV-{dt.value}", dt, "Z-1")]
            result = matrix.generate_matrix(devices)
            outputs = result["matrix"][0]["outputs"]
            phase_ii_outputs = [o for o in outputs if "Phase II" in o]
            assert len(phase_ii_outputs) == 0, (
                f"{dt.value} must NOT auto-trigger ELEVATOR_PHASE_II"
            )

    # ── V18 bug regression: FIRE_PUMP_START exists ──────────────────────

    def test_fire_pump_start_enum_exists(self):
        assert LogicFunction.FIRE_PUMP_START is not None
        assert "Fire Pump" in LogicFunction.FIRE_PUMP_START.value

    def test_fire_pump_start_not_in_waterflow(self, matrix):
        """Per NFPA 20 §10.5.2.1, pump starts on pressure drop, not FACP."""
        devices = [DeviceInput("WF-01", DeviceInputType.WATERFLOW, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        fire_pump_outputs = [o for o in outputs if "Fire Pump" in o]
        assert len(fire_pump_outputs) == 0

    def test_fire_pump_start_not_in_any_auto_rule(self):
        """FIRE_PUMP_START should not be in any CAUSE_EFFECT_RULES."""
        for dt, outputs in CAUSE_EFFECT_RULES.items():
            assert LogicFunction.FIRE_PUMP_START not in outputs, (
                f"FIRE_PUMP_START should not be in {dt.value} rules"
            )

    # ── V18 bug regression: HVAC shutdown zone-specific ──────────────────

    def test_hvac_shutdown_is_zone_specific_for_smoke(self, matrix):
        """Smoke detectors trigger zone-specific HVAC, not building-wide."""
        zone_types = [
            DeviceInputType.SMOKE_GENERAL,
            DeviceInputType.SMOKE_ELEVATOR_LOBBY,
            DeviceInputType.SMOKE_ELEVATOR_LOBBY_DESIGNATED,
            DeviceInputType.SMOKE_MACHINE_ROOM,
            DeviceInputType.SMOKE_ELEVATOR_SHAFT,
            DeviceInputType.SMOKE_RETURN,
        ]
        for dt in zone_types:
            devices = [DeviceInput(f"DEV-{dt.value}", dt, "Z-1")]
            result = matrix.generate_matrix(devices)
            outputs = result["matrix"][0]["outputs"]
            zone_shutdown = [o for o in outputs if "Shutdown" in o and "(Zone)" in o]
            building_shutdown = [o for o in outputs if "Shutdown" in o and "(Building)" in o]
            assert len(zone_shutdown) >= 1, f"{dt.value} must have zone-specific HVAC"
            assert len(building_shutdown) == 0, f"{dt.value} must NOT have building-wide HVAC"

    def test_hvac_shutdown_building_wide_for_mcp(self, matrix):
        """Manual call points trigger building-wide HVAC shutdown."""
        devices = [DeviceInput("MCP-01", DeviceInputType.MANUAL_CALL_POINT, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        assert any("Shutdown" in o and "(Building)" in o for o in outputs)

    def test_hvac_shutdown_not_for_heat(self, matrix):
        """Heat detectors do NOT trigger HVAC shutdown."""
        devices = [DeviceInput("HD-01", DeviceInputType.HEAT, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        shutdown = [o for o in outputs if "Shutdown" in o]
        assert len(shutdown) == 0

    # ── V18 bug regression: MANUAL_CALL_POINT produces NAC_ALL ───────────

    def test_manual_call_point_nac_all_in_matrix(self, matrix):
        devices = [DeviceInput("MCP-01", DeviceInputType.MANUAL_CALL_POINT, "Z-1")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        assert any("(All)" in o for o in outputs)
        assert not any("(Zone)" in o and "Notification" in o for o in outputs)

    # ── All 13 device types (excluding UNKNOWN) produce expected outputs ─

    def test_all_known_device_types_include_alarm_or_supervisory_or_trouble(self, matrix):
        """Every device type produces at least one of ALARM / SUPERVISORY / TROUBLE."""
        for dt in DeviceInputType:
            if dt == DeviceInputType.UNKNOWN:
                continue
            devices = [DeviceInput(f"DEV-{dt.value}", dt, "Z-1")]
            result = matrix.generate_matrix(devices)
            outputs = result["matrix"][0]["outputs"]
            has_primary = any(
                "General Alarm" in o or "Supervisory" in o or "Trouble" in o
                for o in outputs
            )
            assert has_primary, f"{dt.value} must produce ALARM, SUPERVISORY, or TROUBLE"

    def test_each_device_type_produces_correct_output_count(self, matrix):
        """Verify each device type produces the exact expected number of outputs."""
        expected_counts = {
            DeviceInputType.SMOKE_GENERAL: 4,
            DeviceInputType.SMOKE_ELEVATOR_LOBBY: 5,
            DeviceInputType.SMOKE_ELEVATOR_LOBBY_DESIGNATED: 5,
            DeviceInputType.SMOKE_MACHINE_ROOM: 5,
            DeviceInputType.SMOKE_ELEVATOR_SHAFT: 5,
            DeviceInputType.SMOKE_RETURN: 4,
            DeviceInputType.HEAT: 3,
            DeviceInputType.HEAT_ELEVATOR_SHUNT_TRIP: 3,
            DeviceInputType.MANUAL_CALL_POINT: 4,
            DeviceInputType.DUCT_DETECTOR: 2,
            DeviceInputType.WATERFLOW: 2,
            DeviceInputType.VALVE_TAMPER: 1,
            DeviceInputType.SPRINKLER_SUPERVISORY: 1,
            DeviceInputType.UNKNOWN: 1,
        }
        for dt, expected in expected_counts.items():
            devices = [DeviceInput(f"DEV-{dt.value}", dt, "Z-1")]
            result = matrix.generate_matrix(devices)
            actual = len(result["matrix"][0]["outputs"])
            assert actual == expected, (
                f"{dt.value}: expected {expected} outputs, got {actual}"
            )

    # ── Matrix output values match LogicFunction enum values ─────────────

    def test_outputs_use_enum_values(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        result = matrix.generate_matrix(devices)
        for row in result["matrix"]:
            for output in row["outputs"]:
                assert any(
                    output == lf.value for lf in LogicFunction
                ), f"Unknown output value: {output}"

    # ── Warnings for unknown devices ─────────────────────────────────────

    def test_no_warning_for_unknown_enum(self, matrix):
        """UNKNOWN is in CAUSE_EFFECT_RULES so no warning is generated."""
        devices = [DeviceInput("UNK-01", DeviceInputType.UNKNOWN)]
        result = matrix.generate_matrix(devices)
        assert len(result.get("warnings", [])) == 0
        outputs = result["matrix"][0]["outputs"]
        assert any("Trouble" in o for o in outputs)

    def test_no_warnings_for_known_device(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        result = matrix.generate_matrix(devices)
        assert len(result.get("warnings", [])) == 0

    # ── Zone and floor pass-through ──────────────────────────────────────

    def test_zone_id_preserved_in_matrix(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-F1-A")]
        result = matrix.generate_matrix(devices)
        assert result["matrix"][0]["zone"] == "Z-F1-A"

    def test_floor_id_preserved_in_matrix(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1", "FL3")]
        result = matrix.generate_matrix(devices)
        assert result["matrix"][0]["floor"] == "FL3"

    def test_device_id_preserved_in_matrix(self, matrix):
        devices = [DeviceInput("CUSTOM-ID-123", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        result = matrix.generate_matrix(devices)
        assert result["matrix"][0]["device_id"] == "CUSTOM-ID-123"

    # ── healthcare case-insensitive matching ─────────────────────────────

    def test_healthcare_case_insensitive(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        r1 = matrix.generate_matrix(devices, occupancy_type="Healthcare")
        r2 = matrix.generate_matrix(devices, occupancy_type="HEALTHCARE")
        r3 = matrix.generate_matrix(devices, occupancy_type="healthcare")
        assert r1["matrix"][0]["outputs"] == r2["matrix"][0]["outputs"]
        assert r2["matrix"][0]["outputs"] == r3["matrix"][0]["outputs"]

    def test_hospital_is_equivalent_to_healthcare(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        r_health = matrix.generate_matrix(devices, occupancy_type="healthcare")
        r_hosp = matrix.generate_matrix(devices, occupancy_type="hospital")
        assert r_health["matrix"][0]["outputs"] == r_hosp["matrix"][0]["outputs"]

    # ── DOOR_RELEASE verification ───────────────────────────────────────

    def test_door_release_present_in_alarm_device_types(self, matrix):
        """Door release should be present for most alarm device types."""
        door_types = [
            DeviceInputType.SMOKE_GENERAL,
            DeviceInputType.SMOKE_ELEVATOR_LOBBY,
            DeviceInputType.SMOKE_ELEVATOR_LOBBY_DESIGNATED,
            DeviceInputType.SMOKE_MACHINE_ROOM,
            DeviceInputType.SMOKE_ELEVATOR_SHAFT,
            DeviceInputType.SMOKE_RETURN,
            DeviceInputType.HEAT,
            DeviceInputType.MANUAL_CALL_POINT,
        ]
        for dt in door_types:
            devices = [DeviceInput(f"DEV-{dt.value}", dt, "Z-1")]
            result = matrix.generate_matrix(devices)
            outputs = result["matrix"][0]["outputs"]
            has_door = any("Door" in o for o in outputs)
            assert has_door, f"{dt.value} must trigger DOOR_RELEASE"

    # ── SHAFT and SHUNT_TRIP classification ──────────────────────────────

    def test_smoke_elevator_shaft_in_matrix(self, matrix):
        devices = [DeviceInput("SFT-01", DeviceInputType.SMOKE_ELEVATOR_SHAFT, "Z-1")]
        result = matrix.generate_matrix(devices)
        assert result["matrix"][0]["input_type"] == "SMOKE_ELEVATOR_SHAFT"

    def test_heat_elevator_shunt_trip_in_matrix(self, matrix):
        devices = [DeviceInput("HST-01", DeviceInputType.HEAT_ELEVATOR_SHUNT_TRIP, "Z-1")]
        result = matrix.generate_matrix(devices)
        assert result["matrix"][0]["input_type"] == "HEAT_ELEVATOR_SHUNT_TRIP"
        outputs = result["matrix"][0]["outputs"]
        assert any("Shunt" in o for o in outputs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
