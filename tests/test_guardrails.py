"""
tests/test_guardrails.py
=========================
Tests for the tripwire-style guardrail system.

Adapted from the guardrail pattern in OpenAI's agents-python SDK
(src/agents/guardrail.py, MIT License, Copyright (c) 2025 OpenAI).
The tests verify the FireAI-specific adaptation, not the original.

V133 (2026-06-22): Initial implementation.
"""

from __future__ import annotations

import asyncio
import pytest

from fireai.core.guardrails import (
    TripwireResult,
    CalculationErrorSnapshot,
    input_guardrail,
    output_guardrail,
    run_guardrails,
)


# ─── TripwireResult ────────────────────────────────────────────────────

class TestTripwireResult:
    def test_not_triggered_by_default(self):
        r = TripwireResult(tripwire_triggered=False)
        assert r.tripwire_triggered is False
        assert r.output_info == {}

    def test_triggered_with_info(self):
        r = TripwireResult(
            tripwire_triggered=True,
            output_info={"check": "height", "severity": "critical"},
        )
        assert r.tripwire_triggered is True
        assert r.output_info["check"] == "height"
        assert r.output_info["severity"] == "critical"

    def test_output_info_must_be_dict(self):
        with pytest.raises(TypeError):
            TripwireResult(tripwire_triggered=False, output_info="not a dict")  # type: ignore

    def test_frozen(self):
        """TripwireResult should be immutable."""
        r = TripwireResult(tripwire_triggered=True)
        with pytest.raises(AttributeError):
            r.tripwire_triggered = False  # type: ignore


# ─── CalculationErrorSnapshot ──────────────────────────────────────────

class TestCalculationErrorSnapshot:
    def test_carries_full_context(self):
        """The exception must carry all calculation context for audit."""
        snapshot = CalculationErrorSnapshot(
            calculation_id="CALC-001",
            calculation_type="nfpa72_detector_placement",
            input_params={"room_width": 15.0, "room_depth": 20.0, "ceiling_height": 3.0},
            intermediate_steps=[
                {"step": "spacing", "value": 9.1},
                {"step": "count_width", "value": 2},
                {"step": "count_depth", "value": 3},
            ],
            guardrail_results=[
                TripwireResult(tripwire_triggered=False),
                TripwireResult(
                    tripwire_triggered=True,
                    output_info={"check": "wall_distance", "message": "Exceeds S/2"},
                ),
            ],
            error_message="Wall distance violation",
        )
        assert snapshot.calculation_id == "CALC-001"
        assert snapshot.calculation_type == "nfpa72_detector_placement"
        assert len(snapshot.intermediate_steps) == 3
        assert len(snapshot.guardrail_results) == 2
        assert snapshot.guardrail_results[1].tripwire_triggered is True

    def test_is_exception(self):
        """CalculationErrorSnapshot must be raiseable as an exception."""
        with pytest.raises(CalculationErrorSnapshot) as exc_info:
            raise CalculationErrorSnapshot(
                calculation_id="CALC-002",
                calculation_type="voltage_drop",
                input_params={"voltage": 24.0},
                intermediate_steps=[],
                guardrail_results=[],
                error_message="Drop exceeds 10%",
            )
        assert "CALC-002" in str(exc_info.value)
        assert "voltage_drop" in str(exc_info.value)

    def test_to_audit_dict(self):
        """to_audit_dict must produce a serializable audit record."""
        snapshot = CalculationErrorSnapshot(
            calculation_id="CALC-003",
            calculation_type="battery_capacity",
            input_params={"standby_current": 0.5},
            intermediate_steps=[{"step": "standby_ah", "value": 12.0}],
            guardrail_results=[
                TripwireResult(tripwire_triggered=True, output_info={"check": "min_24h"}),
            ],
            error_message="Standby < 24h",
        )
        d = snapshot.to_audit_dict()
        assert d["calculation_id"] == "CALC-003"
        assert d["input_params"]["standby_current"] == 0.5
        assert d["guardrail_results"][0]["tripwire_triggered"] is True
        # Must be JSON-serializable for audit trail
        import json
        json.dumps(d)

    def test_has_timestamp(self):
        """Every snapshot must have a UTC timestamp for audit correlation."""
        snapshot = CalculationErrorSnapshot(
            calculation_id="CALC-004",
            calculation_type="test",
            input_params={},
            intermediate_steps=[],
            guardrail_results=[],
            error_message="test",
        )
        assert snapshot.timestamp is not None
        assert "T" in snapshot.timestamp  # ISO format
        assert snapshot.timestamp.endswith("Z")  # UTC


# ─── Input Guardrail Decorator ─────────────────────────────────────────

class TestInputGuardrail:
    def test_sync_guardrail_passes(self):
        @input_guardrail(name="height_positive")
        def check_height(params: dict) -> TripwireResult:
            h = params.get("ceiling_height_m", 0)
            if h <= 0:
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={"check": "height_positive", "message": f"Height {h} <= 0"},
                )
            return TripwireResult(tripwire_triggered=False)

        result = check_height({"ceiling_height_m": 3.0})
        assert result.tripwire_triggered is False

    def test_sync_guardrail_triggers(self):
        @input_guardrail(name="height_positive")
        def check_height(params: dict) -> TripwireResult:
            h = params.get("ceiling_height_m", 0)
            if h <= 0:
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={"check": "height_positive", "message": f"Height {h} <= 0"},
                )
            return TripwireResult(tripwire_triggered=False)

        result = check_height({"ceiling_height_m": -1.0})
        assert result.tripwire_triggered is True
        assert result.output_info["check"] == "height_positive"

    def test_guardrail_crash_returns_triggered(self):
        """If a guardrail function crashes, it should return triggered=True."""
        @input_guardrail(name="crashy")
        def check(params: dict) -> TripwireResult:
            raise ValueError("Internal error in guardrail")

        result = check({})
        assert result.tripwire_triggered is True
        assert "crashed" in result.output_info["message"].lower()
        assert result.output_info["exception"] == "ValueError"

    def test_guardrail_metadata_attached(self):
        @input_guardrail(name="my_check")
        def check(params: dict) -> TripwireResult:
            return TripwireResult(tripwire_triggered=False)

        assert check.is_guardrail is True
        assert check.guardrail_name == "my_check"

    def test_default_name_is_function_name(self):
        @input_guardrail()
        def my_custom_check(params: dict) -> TripwireResult:
            return TripwireResult(tripwire_triggered=False)

        assert my_custom_check.guardrail_name == "my_custom_check"


# ─── Output Guardrail ──────────────────────────────────────────────────

class TestOutputGuardrail:
    def test_output_guardrail_works(self):
        @output_guardrail(name="count_reasonable")
        def check_count(result: dict) -> TripwireResult:
            count = result.get("total_detectors", 0)
            if count > 1000:
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={"check": "count_reasonable", "count": count},
                )
            return TripwireResult(tripwire_triggered=False)

        assert check_count({"total_detectors": 6}).tripwire_triggered is False
        assert check_count({"total_detectors": 2000}).tripwire_triggered is True

    def test_output_guardrail_has_metadata(self):
        @output_guardrail(name="my_output_check")
        def check(result: dict) -> TripwireResult:
            return TripwireResult(tripwire_triggered=False)

        assert check.is_guardrail is True
        assert check.guardrail_name == "my_output_check"


# ─── Guardrail Runner ──────────────────────────────────────────────────

class TestRunGuardrails:
    def _make_guardrails(self):
        @input_guardrail(name="check_a")
        def check_a(params: dict) -> TripwireResult:
            if params.get("a") == "bad":
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={"check": "check_a"},
                )
            return TripwireResult(tripwire_triggered=False)

        @input_guardrail(name="check_b")
        def check_b(params: dict) -> TripwireResult:
            if params.get("b") == "bad":
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={"check": "check_b"},
                )
            return TripwireResult(tripwire_triggered=False)

        return [check_a, check_b]

    def test_all_pass(self):
        results = run_guardrails(self._make_guardrails(), {"a": "good", "b": "good"})
        assert len(results) == 2
        assert all(not r.tripwire_triggered for r in results)

    def test_stop_on_first_trigger(self):
        results = run_guardrails(
            self._make_guardrails(),
            {"a": "bad", "b": "good"},
            stop_on_first_trigger=True,
        )
        assert len(results) == 1  # Stopped after first trigger
        assert results[0].tripwire_triggered is True
        assert results[0].output_info["check"] == "check_a"

    def test_run_all_no_stop(self):
        results = run_guardrails(
            self._make_guardrails(),
            {"a": "bad", "b": "bad"},
            stop_on_first_trigger=False,
        )
        assert len(results) == 2  # Ran all guardrails
        assert all(r.tripwire_triggered for r in results)

    def test_empty_guardrail_list(self):
        results = run_guardrails([], {})
        assert results == []


# ─── Integration: NFPA 72-style guardrails ─────────────────────────────

class TestNFPA72Guardrails:
    """Integration tests simulating real NFPA 72 calculation guardrails."""

    def test_ceiling_height_guardrail(self):
        @input_guardrail(name="nfpa72_ceiling_height")
        def check_ceiling_height(params: dict) -> TripwireResult:
            """NFPA 72: ceiling height must be positive and ≤ 12.2m (table max)."""
            h = params.get("ceiling_height_m", 0)
            if h <= 0:
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={
                        "check": "ceiling_height_positive",
                        "message": f"Height {h}m must be positive",
                        "severity": "critical",
                        "nfpa_ref": "NFPA 72 §17.6.3.1.1",
                    },
                )
            if h > 12.2:
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={
                        "check": "ceiling_height_table_max",
                        "message": f"Height {h}m exceeds NFPA 72 table max (12.2m)",
                        "severity": "warning",
                        "nfpa_ref": "NFPA 72 §17.6.3.1.1",
                    },
                )
            return TripwireResult(tripwire_triggered=False)

        # Valid height
        assert check_ceiling_height({"ceiling_height_m": 3.0}).tripwire_triggered is False

        # Negative height
        r = check_ceiling_height({"ceiling_height_m": -1.0})
        assert r.tripwire_triggered is True
        assert r.output_info["severity"] == "critical"

        # Height beyond table
        r = check_ceiling_height({"ceiling_height_m": 15.0})
        assert r.tripwire_triggered is True
        assert r.output_info["severity"] == "warning"

    def test_awg_guardrail(self):
        @output_guardrail(name="nec_awg_minimum")
        def check_awg(result: dict) -> TripwireResult:
            """NEC 760.71: minimum AWG 14 for fire alarm circuits.

            AWG numbering is INVERTED: smaller number = thicker wire.
            AWG 14 is the thinnest permitted. AWG 16, 18 are illegal
            (thinner than 14). AWG 12, 10 are legal (thicker than 14).
            """
            awg = result.get("selected_awg")
            if awg is not None and awg > 14:
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={
                        "check": "nec_awg_minimum",
                        "message": f"AWG {awg} > 14 — illegal (too thin) for FA circuits",
                        "severity": "critical",
                        "nec_ref": "NEC Art. 760.71",
                    },
                )
            return TripwireResult(tripwire_triggered=False)

        # Valid AWG (14 = thinnest legal, 12 and 10 = thicker = legal)
        assert check_awg({"selected_awg": 14}).tripwire_triggered is False
        assert check_awg({"selected_awg": 12}).tripwire_triggered is False
        assert check_awg({"selected_awg": 10}).tripwire_triggered is False

        # Illegal AWG (16, 18 = thinner than 14 = illegal)
        r = check_awg({"selected_awg": 18})
        assert r.tripwire_triggered is True
        assert r.output_info["severity"] == "critical"
        assert "NEC Art. 760.71" in r.output_info["nec_ref"]

        r = check_awg({"selected_awg": 16})
        assert r.tripwire_triggered is True

    def test_full_calculation_with_snapshot(self):
        """Simulate a full NFPA 72 calculation with guardrails + error snapshot."""
        @input_guardrail(name="room_dimensions")
        def check_dims(params: dict) -> TripwireResult:
            w = params.get("width_m", 0)
            d = params.get("depth_m", 0)
            if w <= 0 or d <= 0:
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={"check": "room_dimensions", "severity": "critical"},
                )
            return TripwireResult(tripwire_triggered=False)

        # Run guardrails on valid input
        results = run_guardrails(
            [check_dims],
            {"width_m": 15.0, "depth_m": 20.0},
        )
        assert all(not r.tripwire_triggered for r in results)

        # Run on invalid input → trigger → create snapshot
        results = run_guardrails(
            [check_dims],
            {"width_m": -5.0, "depth_m": 20.0},
        )
        triggered = [r for r in results if r.tripwire_triggered]
        assert len(triggered) == 1

        snapshot = CalculationErrorSnapshot(
            calculation_id="NFPA72-DET-001",
            calculation_type="detector_placement",
            input_params={"width_m": -5.0, "depth_m": 20.0},
            intermediate_steps=[],
            guardrail_results=results,
            error_message="Input validation failed",
        )

        audit = snapshot.to_audit_dict()
        assert audit["calculation_id"] == "NFPA72-DET-001"
        assert audit["guardrail_results"][0]["tripwire_triggered"] is True
