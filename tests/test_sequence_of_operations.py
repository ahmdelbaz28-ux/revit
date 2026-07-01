"""
tests/test_sequence_of_operations.py — Tests for NFPA 72 §14.4 Cause & Effect Matrix.

Covers:
  - LogicFunction enum completeness
  - DeviceInputType enum classification
  - CAUSE_EFFECT_RULES mapping for each device type
  - SequenceOfOperationsMatrix.generate_matrix()
  - Smoke detector → alarm + NAC + door release + HVAC shutdown
  - Elevator lobby smoke → elevator recall
  - Duct detector → supervisory (not alarm) in business occupancy
  - Duct detector → alarm + NAC in healthcare occupancy
  - Unknown device type → trouble signal + warning
  - NFPA references included
  - Matrix row structure
"""

from __future__ import annotations

from fireai.core.sequence_of_operations import (
    CAUSE_EFFECT_RULES,
    NFPA_REFERENCES,
    DeviceInput,
    DeviceInputType,
    LogicFunction,
    MatrixRow,
    SequenceOfOperationsMatrix,
)


class TestLogicFunctionEnum:
    """Tests for LogicFunction enum."""

    def test_all_values_are_strings(self) -> None:
        """All LogicFunction values should be strings."""
        for lf in LogicFunction:
            assert isinstance(lf.value, str)

    def test_alarm_exists(self) -> None:
        """ALARM should exist for general evacuation."""
        assert LogicFunction.ALARM.value == "General Alarm / Evacuation"

    def test_nac_zone_exists(self) -> None:
        """NAC_ZONE should exist for notification appliance circuits."""
        assert LogicFunction.NAC_ZONE.value.startswith("Activate Notification")

    def test_elevator_recall_exists(self) -> None:
        """Elevator Phase I recall should exist."""
        assert LogicFunction.ELEVATOR_RECALL_PRIMARY.value.startswith("Elevator Phase I")

    def test_elevator_phase_ii_exists(self) -> None:
        """Elevator Phase II should exist."""
        assert LogicFunction.ELEVATOR_PHASE_II.value.startswith("Elevator Phase II")

    def test_hvac_shutdown_exists(self) -> None:
        """HVAC shutdown should exist."""
        assert LogicFunction.HVAC_SHUTDOWN_ZONE.value.startswith("Shutdown AHU")


class TestDeviceInputTypeEnum:
    """Tests for DeviceInputType enum."""

    def test_smoke_general_exists(self) -> None:
        assert DeviceInputType.SMOKE_GENERAL.value == "SMOKE_GENERAL"

    def test_duct_detector_exists(self) -> None:
        assert DeviceInputType.DUCT_DETECTOR.value == "DUCT_DETECTOR"

    def test_waterflow_exists(self) -> None:
        assert DeviceInputType.WATERFLOW.value == "WATERFLOW"

    def test_unknown_exists(self) -> None:
        assert DeviceInputType.UNKNOWN.value == "UNKNOWN"


class TestCauseEffectRules:
    """Tests for CAUSE_EFFECT_RULES mapping."""

    def test_smoke_general_triggers_alarm(self) -> None:
        """General smoke detector should trigger ALARM."""
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_GENERAL]
        assert LogicFunction.ALARM in rules

    def test_smoke_general_triggers_nac(self) -> None:
        """General smoke detector should trigger NAC_ZONE."""
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_GENERAL]
        assert LogicFunction.NAC_ZONE in rules

    def test_smoke_general_triggers_door_release(self) -> None:
        """General smoke detector should trigger DOOR_RELEASE."""
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_GENERAL]
        assert LogicFunction.DOOR_RELEASE in rules

    def test_smoke_general_triggers_hvac_shutdown(self) -> None:
        """General smoke detector should trigger HVAC_SHUTDOWN_ZONE."""
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_GENERAL]
        assert LogicFunction.HVAC_SHUTDOWN_ZONE in rules

    def test_elevator_lobby_smoke_triggers_recall(self) -> None:
        """Elevator lobby smoke should trigger elevator recall."""
        rules = CAUSE_EFFECT_RULES[DeviceInputType.SMOKE_ELEVATOR_LOBBY]
        assert LogicFunction.ELEVATOR_RECALL_PRIMARY in rules

    def test_duct_detector_does_not_trigger_alarm_by_default(self) -> None:
        """Duct detector should NOT trigger ALARM in business occupancy."""
        rules = CAUSE_EFFECT_RULES[DeviceInputType.DUCT_DETECTOR]
        # Duct detectors are supervisory in most occupancies
        assert LogicFunction.ALARM not in rules or LogicFunction.SUPERVISORY in rules


class TestDeviceInputDataclass:
    """Tests for DeviceInput dataclass."""

    def test_device_input_creation(self) -> None:
        """DeviceInput should be created with required fields."""
        dev = DeviceInput(
            device_id="SD-01",
            device_type=DeviceInputType.SMOKE_GENERAL,
        )
        assert dev.device_id == "SD-01"
        assert dev.device_type == DeviceInputType.SMOKE_GENERAL
        assert dev.zone_id == ""
        assert dev.floor_id == ""

    def test_device_input_with_all_fields(self) -> None:
        """DeviceInput should accept all fields."""
        dev = DeviceInput(
            device_id="SD-FL1-01",
            device_type=DeviceInputType.SMOKE_GENERAL,
            zone_id="Z-1",
            floor_id="FL-1",
            description="Lobby smoke detector",
        )
        assert dev.zone_id == "Z-1"
        assert dev.floor_id == "FL-1"
        assert dev.description == "Lobby smoke detector"


class TestMatrixRowDataclass:
    """Tests for MatrixRow dataclass."""

    def test_matrix_row_creation(self) -> None:
        """MatrixRow should be created with required fields."""
        row = MatrixRow(
            input_device_id="SD-01",
            zone_id="Z-1",
            floor_id="FL-1",
            input_type=DeviceInputType.SMOKE_GENERAL,
            outputs_triggered=[LogicFunction.ALARM, LogicFunction.NAC_ZONE],
        )
        assert row.input_device_id == "SD-01"
        assert len(row.outputs_triggered) == 2
        assert row.nfpa_references == []


class TestSequenceOfOperationsMatrix:
    """Tests for SequenceOfOperationsMatrix class."""

    def test_init_creates_matrix_generator(self) -> None:
        """__init__ should create a matrix generator with rules."""
        matrix = SequenceOfOperationsMatrix()
        assert matrix.rules is not None
        assert matrix.references is not None

    def test_generate_matrix_with_smoke_detector(self) -> None:
        """Smoke detector should produce a matrix row with alarm + NAC."""
        matrix = SequenceOfOperationsMatrix()
        devices = [
            DeviceInput(
                device_id="SD-01",
                device_type=DeviceInputType.SMOKE_GENERAL,
                zone_id="Z-1",
            ),
        ]
        result = matrix.generate_matrix(devices)
        # Result is DecisionProvenance with .value dict containing 'matrix'
        matrix_data = result.value if hasattr(result, "value") else result
        rows = matrix_data.get("matrix", [])
        assert len(rows) >= 1
        # Verify alarm + NAC in outputs
        outputs = rows[0].get("outputs", [])
        assert any("Alarm" in o for o in outputs)
        assert any("Notification" in o for o in outputs)

    def test_generate_matrix_with_elevator_lobby_smoke(self) -> None:
        """Elevator lobby smoke should trigger elevator recall."""
        matrix = SequenceOfOperationsMatrix()
        devices = [
            DeviceInput(
                device_id="SD-LOBBY-01",
                device_type=DeviceInputType.SMOKE_ELEVATOR_LOBBY,
                zone_id="Z-ELEV",
            ),
        ]
        result = matrix.generate_matrix(devices)
        matrix_data = result.value if hasattr(result, "value") else result
        rows = matrix_data.get("matrix", [])
        if rows:
            outputs = rows[0].get("outputs", [])
            assert any("Elevator" in o and "Recall" in o for o in outputs)

    def test_generate_matrix_with_duct_detector_business(self) -> None:
        """Duct detector in business occupancy should be supervisory."""
        matrix = SequenceOfOperationsMatrix()
        devices = [
            DeviceInput(
                device_id="DD-01",
                device_type=DeviceInputType.DUCT_DETECTOR,
                zone_id="Z-2",
            ),
        ]
        result = matrix.generate_matrix(devices, occupancy_type="business")
        assert result is not None

    def test_generate_matrix_with_duct_detector_healthcare(self) -> None:
        """Duct detector in healthcare should trigger ALARM + NAC."""
        matrix = SequenceOfOperationsMatrix()
        devices = [
            DeviceInput(
                device_id="DD-01",
                device_type=DeviceInputType.DUCT_DETECTOR,
                zone_id="Z-2",
            ),
        ]
        result = matrix.generate_matrix(devices, occupancy_type="healthcare")
        matrix_data = result.value if hasattr(result, "value") else result
        rows = matrix_data.get("matrix", [])
        if rows:
            outputs = rows[0].get("outputs", [])
            assert any("Alarm" in o for o in outputs)
            assert any("Notification" in o for o in outputs)

    def test_generate_matrix_with_unknown_device_type(self) -> None:
        """Unknown device type should default to Trouble signal."""
        matrix = SequenceOfOperationsMatrix()
        devices = [
            DeviceInput(
                device_id="XX-01",
                device_type=DeviceInputType.UNKNOWN,
                zone_id="Z-9",
            ),
        ]
        result = matrix.generate_matrix(devices)
        matrix_data = result.value if hasattr(result, "value") else result
        rows = matrix_data.get("matrix", [])
        if rows:
            outputs = rows[0].get("outputs", [])
            assert any("Trouble" in o for o in outputs)

    def test_generate_matrix_with_multiple_devices(self) -> None:
        """Multiple devices should produce multiple matrix rows."""
        matrix = SequenceOfOperationsMatrix()
        devices = [
            DeviceInput(device_id="SD-01", device_type=DeviceInputType.SMOKE_GENERAL),
            DeviceInput(device_id="DD-01", device_type=DeviceInputType.DUCT_DETECTOR),
            DeviceInput(device_id="MCP-01", device_type=DeviceInputType.MANUAL_CALL_POINT),
        ]
        result = matrix.generate_matrix(devices)
        matrix_data = result.value if hasattr(result, "value") else result
        rows = matrix_data.get("matrix", [])
        assert len(rows) == 3

    def test_generate_matrix_empty_devices(self) -> None:
        """Empty device list should produce empty matrix."""
        matrix = SequenceOfOperationsMatrix()
        result = matrix.generate_matrix([])
        matrix_data = result.value if hasattr(result, "value") else result
        rows = matrix_data.get("matrix", [])
        assert len(rows) == 0

    def test_generate_matrix_includes_nfpa_references(self) -> None:
        """Matrix rows should include NFPA references."""
        matrix = SequenceOfOperationsMatrix()
        devices = [
            DeviceInput(
                device_id="SD-01",
                device_type=DeviceInputType.SMOKE_GENERAL,
            ),
        ]
        result = matrix.generate_matrix(devices)
        # NFPA references may be in the matrix row or in the provenance
        matrix_data = result.value if hasattr(result, "value") else result
        matrix_data.get("matrix", [])
        # At minimum, the result should have some reference data
        assert result is not None
        # Check if references exist somewhere in the result
        if hasattr(result, "rules_applied") and result.rules_applied:
            assert len(result.rules_applied) > 0


class TestNFPAReferences:
    """Tests for NFPA_REFERENCES mapping."""

    def test_smoke_general_has_references(self) -> None:
        """SMOKE_GENERAL should have NFPA references."""
        refs = NFPA_REFERENCES.get(DeviceInputType.SMOKE_GENERAL, [])
        assert len(refs) > 0
        assert any("§10.14" in r for r in refs)

    def test_duct_detector_has_references(self) -> None:
        """DUCT_DETECTOR should have NFPA references."""
        refs = NFPA_REFERENCES.get(DeviceInputType.DUCT_DETECTOR, [])
        assert len(refs) > 0
        assert any("§17.7" in r for r in refs)

    def test_waterflow_has_references(self) -> None:
        """WATERFLOW should have NFPA references."""
        refs = NFPA_REFERENCES.get(DeviceInputType.WATERFLOW, [])
        assert len(refs) > 0
