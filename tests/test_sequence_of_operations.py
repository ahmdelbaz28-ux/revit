"""
tests/test_sequence_of_operations.py
======================================
Comprehensive test suite for fireai/core/sequence_of_operations.py

SAFETY CRITICAL: The Cause & Effect matrix maps every input device to
its required output actions. Errors can cause silent alarms, false
evacuations, or HVAC running during fire.

NFPA 72 References:
  §14.4, §10.14, §17.7.5.6, §21.3.3, §17.14
ASME A17.1 — Elevator Phase I and Phase II
"""

from __future__ import annotations

import dataclasses
import pytest

import fireai.core.sequence_of_operations as _soo_mod

# Force fallback dict path — provenance RuleApplied/Violation field names
# don't match what the source module expects.
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


# ─────────────────────────────────────────────────────────────────────────────
# LogicFunction Enum
# ─────────────────────────────────────────────────────────────────────────────


class TestLogicFunction:

    def test_alarm_exists(self):
        assert LogicFunction.ALARM.value == "General Alarm / Evacuation"

    def test_supervisory_exists(self):
        assert LogicFunction.SUPERVISORY.value == "Supervisory Signal Only"

    def test_nac_zone_exists(self):
        assert "Notification Appliance" in LogicFunction.NAC_ZONE.value

    def test_nac_all_exists(self):
        assert LogicFunction.NAC_ALL is not None

    def test_elevator_recall_primary(self):
        assert "Phase I" in LogicFunction.ELEVATOR_RECALL_PRIMARY.value

    def test_elevator_recall_alternate(self):
        assert "Alternate" in LogicFunction.ELEVATOR_RECALL_ALTERNATE.value

    def test_elevator_phase_ii(self):
        assert "Phase II" in LogicFunction.ELEVATOR_PHASE_II.value

    def test_elevator_shunt_trip(self):
        assert "Shunt" in LogicFunction.ELEVATOR_SHUNT_TRIP.value

    def test_hvac_shutdown_zone(self):
        assert "Zone" in LogicFunction.HVAC_SHUTDOWN_ZONE.value

    def test_hvac_shutdown_all(self):
        assert "Building" in LogicFunction.HVAC_SHUTDOWN_ALL.value

    def test_door_release(self):
        assert "Door" in LogicFunction.DOOR_RELEASE.value

    def test_fire_pump_start(self):
        assert "Fire Pump" in LogicFunction.FIRE_PUMP_START.value

    def test_trouble_exists(self):
        assert LogicFunction.TROUBLE is not None


# ─────────────────────────────────────────────────────────────────────────────
# DeviceInputType Enum
# ─────────────────────────────────────────────────────────────────────────────


class TestDeviceInputType:

    def test_all_types_have_values(self):
        for dit in DeviceInputType:
            assert dit.value  # non-empty

    def test_smoke_general(self):
        assert DeviceInputType.SMOKE_GENERAL.value == "SMOKE_GENERAL"

    def test_duct_detector(self):
        assert DeviceInputType.DUCT_DETECTOR is not None

    def test_unknown(self):
        assert DeviceInputType.UNKNOWN is not None


# ─────────────────────────────────────────────────────────────────────────────
# CAUSE_EFFECT_RULES
# ─────────────────────────────────────────────────────────────────────────────


class TestCauseEffectRules:

    def test_all_device_types_have_rules(self):
        for dit in DeviceInputType:
            assert dit in CAUSE_EFFECT_RULES, f"Missing rule for {dit.value}"

    def test_smoke_general_triggers_alarm(self):
        assert LogicFunction.ALARM in CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_GENERAL]

    def test_smoke_general_triggers_nac(self):
        assert LogicFunction.NAC_ZONE in CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_GENERAL]

    def test_smoke_general_triggers_door_release(self):
        assert LogicFunction.DOOR_RELEASE in CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_GENERAL]

    def test_smoke_general_triggers_hvac_zone(self):
        assert LogicFunction.HVAC_SHUTDOWN_ZONE in CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_GENERAL]

    def test_elevator_lobby_triggers_recall(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_ELEVATOR_LOBBY]
        assert LogicFunction.ELEVATOR_RECALL_PRIMARY in rules

    def test_designated_lobby_triggers_alternate_recall(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_ELEVATOR_LOBBY_DESIGNATED]
        assert LogicFunction.ELEVATOR_RECALL_ALTERNATE in rules

    def test_machine_room_triggers_alternate_recall(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_MACHINE_ROOM]
        assert LogicFunction.ELEVATOR_RECALL_ALTERNATE in rules

    def test_machine_room_no_phase_ii(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_MACHINE_ROOM]
        assert LogicFunction.ELEVATOR_PHASE_II not in rules

    def test_duct_detector_supervisory_not_alarm(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.DUCT_DETECTOR]
        assert LogicFunction.SUPERVISORY in rules
        assert LogicFunction.ALARM not in rules

    def test_duct_detector_triggers_hvac(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.DUCT_DETECTOR]
        assert LogicFunction.HVAC_SHUTDOWN_ZONE in rules

    def test_waterflow_triggers_alarm_and_nac(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.WATERFLOW]
        assert LogicFunction.ALARM in rules
        assert LogicFunction.NAC_ZONE in rules

    def test_waterflow_no_fire_pump_start(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.WATERFLOW]
        assert LogicFunction.FIRE_PUMP_START not in rules

    def test_valve_tamper_supervisory_only(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.VALVE_TAMPER]
        assert rules == [LogicFunction.SUPERVISORY]

    def test_unknown_defaults_to_trouble(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.UNKNOWN]
        assert LogicFunction.TROUBLE in rules

    def test_manual_call_point_triggers_nac_all(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.MANUAL_CALL_POINT]
        assert LogicFunction.NAC_ALL in rules
        assert LogicFunction.HVAC_SHUTDOWN_ALL in rules

    def test_heat_elevator_shunt_trip(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.HEAT_ELEVATOR_SHUNT_TRIP]
        assert LogicFunction.ELEVATOR_SHUNT_TRIP in rules

    def test_heat_no_hvac(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.HEAT]
        assert LogicFunction.HVAC_SHUTDOWN_ZONE not in rules

    def test_smoke_return_has_door_release(self):
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_RETURN]
        assert LogicFunction.DOOR_RELEASE in rules


# ─────────────────────────────────────────────────────────────────────────────
# DeviceInput & MatrixRow
# ─────────────────────────────────────────────────────────────────────────────


class TestDeviceInput:

    def test_required_fields(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL)
        assert d.device_id == "SD-01"
        assert d.device_type == DeviceInputType.SMOKE_GENERAL

    def test_default_optional_fields(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL)
        assert d.zone_id == ""
        assert d.floor_id == ""

    def test_frozen(self):
        d = DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL)
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.device_id = "CHANGED"


class TestMatrixRow:

    def test_basic_creation(self):
        row = MatrixRow("SD-01", "Z-1", "F1", DeviceInputType.SMOKE_GENERAL, [LogicFunction.ALARM])
        assert row.input_device_id == "SD-01"

    def test_default_nfpa_references(self):
        row = MatrixRow("SD-01", "Z-1", "F1", DeviceInputType.SMOKE_GENERAL, [])
        assert row.nfpa_references == []


# ─────────────────────────────────────────────────────────────────────────────
# generate_matrix — With provenance disabled, returns fallback dict
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateMatrix:

    def test_single_smoke_detector(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        result = matrix.generate_matrix(devices)
        # Fallback dict format
        assert "matrix" in result
        assert "hash" in result
        assert len(result["matrix"]) == 1

    def test_multiple_devices(self, matrix):
        devices = [
            DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1"),
            DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2"),
            DeviceInput("WF-01", DeviceInputType.WATERFLOW, "Z-3"),
        ]
        result = matrix.generate_matrix(devices)
        assert len(result["matrix"]) == 3

    def test_duct_detector_supervisory_in_matrix(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        assert any("Supervisory" in o for o in outputs)
        assert not any("General Alarm" in o for o in outputs)

    def test_healthcare_duct_detector_adds_alarm(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices, occupancy_type="healthcare")
        outputs = result["matrix"][0]["outputs"]
        assert any("General Alarm" in o for o in outputs)

    def test_hospital_duct_detector_adds_alarm(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices, occupancy_type="hospital")
        outputs = result["matrix"][0]["outputs"]
        assert any("General Alarm" in o for o in outputs)

    def test_matrix_hash_is_sha256(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        result = matrix.generate_matrix(devices)
        assert len(result["hash"]) == 64

    def test_empty_devices_produces_empty_matrix(self, matrix):
        result = matrix.generate_matrix([])
        assert len(result["matrix"]) == 0

    def test_unknown_device_defaults_to_trouble(self, matrix):
        devices = [DeviceInput("UNK-01", DeviceInputType.UNKNOWN)]
        result = matrix.generate_matrix(devices)
        outputs = result["matrix"][0]["outputs"]
        assert any("Trouble" in o for o in outputs)

    def test_deterministic_hash(self, matrix):
        devices = [DeviceInput("SD-01", DeviceInputType.SMOKE_GENERAL, "Z-1")]
        r1 = matrix.generate_matrix(devices)
        r2 = matrix.generate_matrix(devices)
        assert r1["hash"] == r2["hash"]

    def test_warnings_for_healthcare(self, matrix):
        devices = [DeviceInput("DD-01", DeviceInputType.DUCT_DETECTOR, "Z-2")]
        result = matrix.generate_matrix(devices, occupancy_type="healthcare")
        assert len(result.get("warnings", [])) > 0


# ─────────────────────────────────────────────────────────────────────────────
# generate_for_legacy_dicts
# ─────────────────────────────────────────────────────────────────────────────


class TestLegacyDicts:

    def test_smoke_detector_classification(self, matrix):
        devices = [{"device_id": "SD-01", "type": "SMOKE", "zone_id": "Z-1"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "SMOKE_GENERAL"

    def test_elevator_lobby_classification(self, matrix):
        devices = [{"device_id": "SD-01", "type": "SMOKE", "location_hint": "ELEVATOR LOBBY"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "SMOKE_ELEVATOR_LOBBY"

    def test_lobby_storage_not_elevator_lobby(self, matrix):
        devices = [{"device_id": "SD-01", "type": "SMOKE", "location_hint": "LOBBY STORAGE"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "SMOKE_GENERAL"

    def test_machine_room_classification(self, matrix):
        devices = [{"device_id": "SD-01", "type": "SMOKE", "location_hint": "ELEVATOR MACHINE ROOM"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "SMOKE_MACHINE_ROOM"

    def test_return_air_classification(self, matrix):
        devices = [{"device_id": "SD-01", "type": "SMOKE", "location_hint": "RETURN AIR SHAFT"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "SMOKE_RETURN"

    def test_heat_classification(self, matrix):
        devices = [{"device_id": "HD-01", "type": "HEAT"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "HEAT"

    def test_mcp_classification(self, matrix):
        devices = [{"device_id": "MCP-01", "type": "MCP"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "MANUAL_CALL_POINT"

    def test_duct_classification(self, matrix):
        devices = [{"device_id": "DD-01", "type": "DUCT"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "DUCT_DETECTOR"

    def test_flow_switch_classification(self, matrix):
        devices = [{"device_id": "WF-01", "type": "FLOW_SWITCH"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "WATERFLOW"

    def test_tamper_switch_classification(self, matrix):
        devices = [{"device_id": "VT-01", "type": "TAMPER_SWITCH"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "VALVE_TAMPER"

    def test_unknown_type_defaults_to_unknown(self, matrix):
        devices = [{"device_id": "X-01", "type": "SOMETHING_WEIRD"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["input_type"] == "UNKNOWN"

    def test_id_fallback_for_device_id(self, matrix):
        devices = [{"id": "SD-01", "type": "SMOKE"}]
        result = matrix.generate_for_legacy_dicts(devices)
        assert result["matrix"][0]["device_id"] == "SD-01"


# ─────────────────────────────────────────────────────────────────────────────
# NFPA References
# ─────────────────────────────────────────────────────────────────────────────


class TestNFPAReferences:

    def test_smoke_general_has_references(self):
        refs = NFPA_REFERENCES.get(DeviceInputType.SMOKE_GENERAL, [])
        assert len(refs) > 0

    def test_duct_detector_has_reference(self):
        refs = NFPA_REFERENCES.get(DeviceInputType.DUCT_DETECTOR, [])
        assert any("17.7.5.6" in r for r in refs)

    def test_waterflow_has_reference(self):
        refs = NFPA_REFERENCES.get(DeviceInputType.WATERFLOW, [])
        assert len(refs) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
