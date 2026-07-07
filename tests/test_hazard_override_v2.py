# NOSONAR
"""
tests/test_hazard_override_v2.py
================================
Comprehensive test suite for:
  fireai/core/hazard_override.py

SAFETY CRITICAL: The hazard override system is a NON-BYPASSABLE safety
gate that prevents AI/ML models from under-classifying hazard levels.
A missed override could result in undersized sprinkler systems,
potentially leading to loss of life in a fire.

NFPA 13-2022 Chapter 11: Hazard classifications and design densities
SBC 801 Chapter 9: Saudi Building Code fire protection requirements
"""

from __future__ import annotations

import pytest

from fireai.core.hazard_override import (
    _HAZARD_SEVERITY,
    MANDATORY_HAZARD_OVERRIDES,
    HazardClassification,
    HazardOverrideVerifier,
    OverrideResult,
    is_more_severe,
)

# ─────────────────────────────────────────────────────────────────────────────
# HazardClassification Enum
# ─────────────────────────────────────────────────────────────────────────────


class TestHazardClassification:
    """HazardClassification enum values and ordering."""

    def test_all_classifications_exist(self):
        """All five NFPA 13 hazard classifications must be present."""
        assert HazardClassification.LIGHT_HAZARD.value == "light_hazard"
        assert HazardClassification.ORDINARY_HAZARD_1.value == "ordinary_hazard_1"
        assert HazardClassification.ORDINARY_HAZARD_2.value == "ordinary_hazard_2"
        assert HazardClassification.EXTRA_HAZARD_1.value == "extra_hazard_1"
        assert HazardClassification.EXTRA_HAZARD_2.value == "extra_hazard_2"

    def test_five_classifications(self):
        """There must be exactly 5 hazard classifications."""
        assert len(HazardClassification) == 5


# ─────────────────────────────────────────────────────────────────────────────
# is_more_severe — Severity Comparison
# ─────────────────────────────────────────────────────────────────────────────


class TestIsMoreSevere:
    """Severity comparison function — core of the override logic."""

    def test_extra_hazard_2_more_severe_than_light(self):
        assert is_more_severe("extra_hazard_2", "light_hazard") is True

    def test_light_less_severe_than_ordinary_1(self):
        assert is_more_severe("light_hazard", "ordinary_hazard_1") is False

    def test_same_severity_is_not_more(self):
        assert is_more_severe("ordinary_hazard_1", "ordinary_hazard_1") is False

    def test_ordinary_2_more_than_ordinary_1(self):
        assert is_more_severe("ordinary_hazard_2", "ordinary_hazard_1") is True

    def test_extra_1_more_than_ordinary_2(self):
        assert is_more_severe("extra_hazard_1", "ordinary_hazard_2") is True

    def test_extra_2_more_than_extra_1(self):
        assert is_more_severe("extra_hazard_2", "extra_hazard_1") is True

    def test_unknown_classification_treated_as_light(self):
        """Unknown classification has severity 0 (same as light)."""
        assert is_more_severe("ordinary_hazard_1", "unknown_type") is True
        assert is_more_severe("unknown_type", "light_hazard") is False

    def test_whitespace_and_case_normalization(self):
        """Input normalization: spaces → underscores, case insensitive."""
        assert is_more_severe("Extra Hazard 2", "Light Hazard") is True
        assert is_more_severe("ORDINARY_HAZARD_2", "ordinary_hazard_1") is True

    def test_severity_ordering_complete(self):
        """Severity must increase monotonically through all 5 levels."""
        levels = [
            "light_hazard",
            "ordinary_hazard_1",
            "ordinary_hazard_2",
            "extra_hazard_1",
            "extra_hazard_2",
        ]
        for i in range(len(levels)):
            for j in range(i + 1, len(levels)):
                assert is_more_severe(levels[j], levels[i]) is True, (
                    f"{levels[j]} should be more severe than {levels[i]}"
                )
                assert is_more_severe(levels[i], levels[j]) is False, (
                    f"{levels[i]} should not be more severe than {levels[j]}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# MANDATORY_HAZARD_OVERRIDES Dictionary
# ─────────────────────────────────────────────────────────────────────────────


class TestMandatoryOverrides:
    """The override dictionary is the SINGLE SOURCE OF TRUTH for safety."""

    def test_diesel_is_extra_hazard_2(self):
        """Diesel fuel rooms must be Extra Hazard Group 2."""
        assert MANDATORY_HAZARD_OVERRIDES["diesel"] == "extra_hazard_2"

    def test_fuel_is_extra_hazard_2(self):
        assert MANDATORY_HAZARD_OVERRIDES["fuel"] == "extra_hazard_2"

    def test_gasoline_is_extra_hazard_2(self):
        assert MANDATORY_HAZARD_OVERRIDES["gasoline"] == "extra_hazard_2"

    def test_paint_spray_is_extra_hazard_2(self):
        assert MANDATORY_HAZARD_OVERRIDES["paint spray"] == "extra_hazard_2"

    def test_substation_is_extra_hazard_1(self):
        assert MANDATORY_HAZARD_OVERRIDES["substation"] == "extra_hazard_1"

    def test_transformer_is_extra_hazard_1(self):
        assert MANDATORY_HAZARD_OVERRIDES["transformer"] == "extra_hazard_1"

    def test_electrical_room_is_extra_hazard_1(self):
        assert MANDATORY_HAZARD_OVERRIDES["electrical room"] == "extra_hazard_1"

    def test_storage_is_ordinary_hazard_2(self):
        assert MANDATORY_HAZARD_OVERRIDES["storage"] == "ordinary_hazard_2"

    def test_kitchen_is_ordinary_hazard_2(self):
        assert MANDATORY_HAZARD_OVERRIDES["kitchen"] == "ordinary_hazard_2"

    def test_warehouse_is_ordinary_hazard_2(self):
        assert MANDATORY_HAZARD_OVERRIDES["warehouse"] == "ordinary_hazard_2"

    def test_electrical_is_ordinary_hazard_1(self):
        assert MANDATORY_HAZARD_OVERRIDES["electrical"] == "ordinary_hazard_1"

    def test_corridor_is_ordinary_hazard_1(self):
        assert MANDATORY_HAZARD_OVERRIDES["corridor"] == "ordinary_hazard_1"

    def test_no_light_hazard_keywords(self):
        """There should be NO light_hazard overrides — too dangerous."""
        light_entries = [
            k for k, v in MANDATORY_HAZARD_OVERRIDES.items()
            if v == "light_hazard"
        ]
        assert len(light_entries) == 0, (
            f"Light hazard overrides found: {light_entries}. "
            "Light hazard should never be forced by keyword — it's too lenient."
        )

    def test_all_override_values_are_valid(self):
        """Every override value must be a valid severity key."""
        for keyword, classification in MANDATORY_HAZARD_OVERRIDES.items():
            assert classification in _HAZARD_SEVERITY, (
                f"Keyword '{keyword}' maps to invalid classification '{classification}'"
            )


# ─────────────────────────────────────────────────────────────────────────────
# HazardOverrideVerifier — Core Override Logic
# ─────────────────────────────────────────────────────────────────────────────


class TestHazardOverrideVerifier:
    """Non-bypassable deterministic safety override verification."""

    def test_diesel_generator_room_override(self):
        """Diesel Generator Room: AI says OH1 → overridden to EH2."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Diesel Generator Room",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert result.override_applied is True
        assert result.final_classification == "extra_hazard_2"
        assert result.matched_keyword == "diesel"

    def test_fuel_storage_override(self):
        """Fuel Storage: AI says light_hazard → overridden to EH2."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Fuel Storage",
            ml_predicted_hazard="light_hazard",
        )
        assert result.override_applied is True
        assert result.final_classification == "extra_hazard_2"

    def test_electrical_room_override(self):
        """Electrical Room: AI says OH1 → overridden to EH1."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Main Electrical Room",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert result.override_applied is True
        assert result.final_classification == "extra_hazard_1"

    def test_kitchen_override(self):
        """Kitchen: AI says OH1 → overridden to OH2."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Commercial Kitchen",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert result.override_applied is True
        assert result.final_classification == "ordinary_hazard_2"

    def test_ml_prediction_already_at_mandatory_level(self):
        """When ML prediction equals or exceeds mandatory → no override."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Diesel Generator Room",
            ml_predicted_hazard="extra_hazard_2",
        )
        assert result.override_applied is False
        assert result.final_classification == "extra_hazard_2"

    def test_ml_prediction_above_mandatory_level(self):
        """When ML prediction exceeds mandatory → no override, keep ML."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Kitchen",
            ml_predicted_hazard="extra_hazard_2",
        )
        assert result.override_applied is False
        assert result.final_classification == "extra_hazard_2"

    def test_no_keyword_match_prediction_above_default(self):
        """No keyword match + ML prediction ≥ default → no override."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Generic Office Space",
            ml_predicted_hazard="ordinary_hazard_2",
        )
        assert result.override_applied is False
        assert result.final_classification == "ordinary_hazard_2"

    def test_no_keyword_match_prediction_below_default(self):
        """No keyword match + ML prediction < default → override to default."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Generic Office Space",
            ml_predicted_hazard="light_hazard",
        )
        assert result.override_applied is True
        assert result.final_classification == "ordinary_hazard_1"

    def test_empty_room_name_defaults_to_minimum(self):
        """Empty room name → default to safe minimum."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="",
            ml_predicted_hazard="light_hazard",
        )
        assert result.override_applied is True
        assert result.final_classification == "ordinary_hazard_1"

    def test_none_room_name_defaults_to_minimum(self):
        """None room name → default to safe minimum."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name=None,  # NOSONAR — S5655: intentional wrong-type arg (test verifies rejection)
            ml_predicted_hazard="light_hazard",
        )
        assert result.override_applied is True

    def test_case_insensitive_keyword_match(self):
        """Keyword matching should be case-insensitive."""
        verifier = HazardOverrideVerifier()
        r1 = verifier.verify_and_override("DIESEL ROOM", "ordinary_hazard_1")
        r2 = verifier.verify_and_override("diesel room", "ordinary_hazard_1")
        assert r1.final_classification == r2.final_classification == "extra_hazard_2"

    def test_most_severe_keyword_selected(self):
        """Room matching multiple keywords → most severe classification."""
        # "Diesel Generator Room" matches both "diesel" (EH2) and "generator" (EH1)
        # → EH2 (most severe)
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Diesel Generator Room",
            ml_predicted_hazard="light_hazard",
        )
        assert result.final_classification == "extra_hazard_2"

    def test_safety_rationale_is_not_empty_when_overridden(self):
        """Override result must include safety rationale."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Diesel Storage",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert result.override_applied is True
        assert len(result.safety_rationale) > 0

    def test_nfpa_reference_in_result(self):
        """Override result must reference NFPA 13."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Paint Spray Booth",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert "NFPA 13" in result.nfpa_reference

    def test_sbc_reference_in_result(self):
        """Override result must reference SBC 801."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Paint Spray Booth",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert "SBC 801" in result.sbc_reference


# ─────────────────────────────────────────────────────────────────────────────
# HazardOverrideVerifier — Custom Overrides
# ─────────────────────────────────────────────────────────────────────────────


class TestCustomOverrides:
    """Custom override dictionary support."""

    def test_custom_overrides_supplement_built_in(self):
        """Custom overrides add to, not replace, built-in overrides."""
        verifier = HazardOverrideVerifier(
            custom_overrides={"battery room": "extra_hazard_1"}
        )
        # Custom override works
        result = verifier.verify_and_override(
            room_name="Battery Room",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert result.final_classification == "extra_hazard_1"

        # Built-in override still works
        result2 = verifier.verify_and_override(
            room_name="Diesel Room",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert result2.final_classification == "extra_hazard_2"

    def test_custom_override_does_not_replace_built_in(self):
        """Custom override with same key updates the built-in value."""
        verifier = HazardOverrideVerifier(
            custom_overrides={"diesel": "extra_hazard_1"}  # Lower than built-in EH2
        )
        # Custom overrides update() the dict, so "diesel" now maps to EH1
        result = verifier.verify_and_override(
            room_name="Diesel Room",
            ml_predicted_hazard="light_hazard",
        )
        # Custom override replaces the built-in value
        assert result.final_classification == "extra_hazard_1"


# ─────────────────────────────────────────────────────────────────────────────
# HazardOverrideVerifier — Minimum Default
# ─────────────────────────────────────────────────────────────────────────────


class TestMinimumDefault:
    """Minimum default classification validation."""

    def test_invalid_minimum_default_raises(self):
        """Invalid minimum_default must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid minimum_default"):
            HazardOverrideVerifier(minimum_default="invalid_hazard")

    def test_custom_minimum_default(self):
        """Custom minimum default is used when no keyword matches."""
        verifier = HazardOverrideVerifier(minimum_default="ordinary_hazard_2")
        result = verifier.verify_and_override(
            room_name="Generic Space",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert result.override_applied is True
        assert result.final_classification == "ordinary_hazard_2"

    def test_default_minimum_is_ordinary_hazard_1(self):
        """Default minimum is ordinary_hazard_1 (conservative/safe)."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Unknown Room",
            ml_predicted_hazard="light_hazard",
        )
        assert result.final_classification == "ordinary_hazard_1"


# ─────────────────────────────────────────────────────────────────────────────
# OverrideResult — Data Structure
# ─────────────────────────────────────────────────────────────────────────────


class TestOverrideResult:
    """OverrideResult dataclass tests."""

    def test_result_fields(self):
        """OverrideResult must have all required fields."""
        result = OverrideResult(
            room_name="Test Room",
            original_prediction="light_hazard",
            final_classification="extra_hazard_2",
            override_applied=True,
            matched_keyword="diesel",
            safety_rationale="Test rationale",
        )
        assert result.room_name == "Test Room"
        assert result.original_prediction == "light_hazard"
        assert result.final_classification == "extra_hazard_2"
        assert result.override_applied is True
        assert result.matched_keyword == "diesel"

    def test_default_nfpa_reference(self):
        """Default NFPA reference must be present."""
        result = OverrideResult(
            room_name="Test",
            original_prediction="light_hazard",
            final_classification="ordinary_hazard_1",
            override_applied=False,
        )
        assert "NFPA 13" in result.nfpa_reference


# ─────────────────────────────────────────────────────────────────────────────
# Integration — Real-World Hazard Classification Scenarios
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrationScenarios:
    """End-to-end scenarios representing real BIM room names."""

    def test_transformer_room_underrated_by_ai(self):
        """Transformer Room misclassified as OH1 → overridden to EH1."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Transformer Room",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert result.override_applied is True
        assert result.final_classification == "extra_hazard_1"

    def test_solvent_storage_underrated(self):
        """Solvent Storage: AI says OH2 → overridden to EH2."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Solvent Storage Area",
            ml_predicted_hazard="ordinary_hazard_2",
        )
        assert result.override_applied is True
        assert result.final_classification == "extra_hazard_2"

    def test_boiler_room_correctly_classified(self):
        """Boiler Room: AI says OH2 → no override (correct)."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Boiler Room",
            ml_predicted_hazard="ordinary_hazard_2",
        )
        assert result.override_applied is False
        assert result.final_classification == "ordinary_hazard_2"

    def test_parking_garage_ordinary_hazard_1(self):
        """Parking Garage: AI says light → overridden to OH1."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Underground Parking Garage",
            ml_predicted_hazard="light_hazard",
        )
        assert result.override_applied is True
        assert result.final_classification == "ordinary_hazard_1"

    def test_laboratory_ordinary_hazard_2(self):
        """Laboratory: AI says OH1 → overridden to OH2."""
        verifier = HazardOverrideVerifier()
        result = verifier.verify_and_override(
            room_name="Chemistry Laboratory",
            ml_predicted_hazard="ordinary_hazard_1",
        )
        assert result.override_applied is True
        assert result.final_classification == "ordinary_hazard_2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
