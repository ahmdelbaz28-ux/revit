"""
fireai/core/tests/test_analysis_pipeline.py — Tests for AnalysisPipeline input validation.

NFPA 72 Section 10.4: Input validation requirements for fire safety analysis.
All input data must be validated before engineering calculations are performed
to prevent dangerous design recommendations from garbage input.
"""

import pytest

from fireai.core.analysis_pipeline import AnalysisPipeline


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def pipeline() -> AnalysisPipeline:
    """Create an AnalysisPipeline instance for testing."""
    return AnalysisPipeline(generate_certificate=False, require_consensus=False)


@pytest.fixture
def valid_input() -> dict:
    """Create a valid input data dictionary."""
    return {
        "floor_plan": {"area": 1000, "exits": [1, 2, 3]},
        "detector_specs": {"type": "heat"},
        "occupancy_class": "B",
    }


# ── Validation Tests ─────────────────────────────────────────────────────


class TestPipelineValidation:
    """NFPA 72 Section 10.4: Input validation tests.

    These tests verify that the AnalysisPipeline.validate_input method
    correctly rejects invalid input data and accepts valid data. Input
    validation is a critical safety gate — invalid inputs could produce
    dangerous fire protection design recommendations.
    """

    def test_valid_input(self, pipeline: AnalysisPipeline, valid_input: dict):
        """Test valid input passes validation."""
        is_valid, errors = pipeline.validate_input(valid_input)
        assert is_valid is True
        assert errors == []

    def test_missing_required_field(self, pipeline: AnalysisPipeline):
        """Test missing required field is detected."""
        data = {
            "floor_plan": {"area": 1000, "exits": [1]},
            "detector_specs": {"type": "heat"},
            # Missing occupancy_class
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("occupancy_class" in e for e in errors)

    def test_missing_multiple_fields(self, pipeline: AnalysisPipeline):
        """Test multiple missing fields are all reported."""
        data = {}
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert len(errors) >= 3  # At least floor_plan, detector_specs, occupancy_class

    def test_invalid_floor_plan_area(self, pipeline: AnalysisPipeline):
        """Test negative floor plan area is rejected."""
        data = {
            "floor_plan": {"area": -100, "exits": [1]},
            "detector_specs": {"type": "heat"},
            "occupancy_class": "B",
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("positive" in e.lower() or "area" in e.lower() for e in errors)

    def test_floor_plan_no_exits(self, pipeline: AnalysisPipeline):
        """Test floor plan without exits is rejected."""
        data = {
            "floor_plan": {"area": 1000},
            "detector_specs": {"type": "heat"},
            "occupancy_class": "B",
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("exit" in e.lower() for e in errors)

    def test_floor_plan_empty_exits(self, pipeline: AnalysisPipeline):
        """Test floor plan with empty exits list is rejected."""
        data = {
            "floor_plan": {"area": 1000, "exits": []},
            "detector_specs": {"type": "heat"},
            "occupancy_class": "B",
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("exit" in e.lower() for e in errors)

    def test_invalid_detector_type(self, pipeline: AnalysisPipeline):
        """Test invalid detector type is rejected per NFPA 72 §17.6/§17.7."""
        data = {
            "floor_plan": {"area": 1000, "exits": [1]},
            "detector_specs": {"type": "invalid"},
            "occupancy_class": "B",
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("Invalid detector type" in e for e in errors)

    def test_missing_detector_type(self, pipeline: AnalysisPipeline):
        """Test missing detector type is reported."""
        data = {
            "floor_plan": {"area": 1000, "exits": [1]},
            "detector_specs": {},
            "occupancy_class": "B",
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("type" in e.lower() for e in errors)

    def test_valid_detector_types(self, pipeline: AnalysisPipeline):
        """Test all valid detector types are accepted."""
        for det_type in ["heat", "smoke", "multi", "beam"]:
            data = {
                "floor_plan": {"area": 1000, "exits": [1]},
                "detector_specs": {"type": det_type},
                "occupancy_class": "B",
            }
            is_valid, errors = pipeline.validate_input(data)
            assert is_valid is True, f"Detector type '{det_type}' should be valid, got errors: {errors}"

    def test_invalid_occupancy_class(self, pipeline: AnalysisPipeline):
        """Test invalid occupancy class is rejected per IBC/NFPA 101."""
        data = {
            "floor_plan": {"area": 1000, "exits": [1]},
            "detector_specs": {"type": "heat"},
            "occupancy_class": "INVALID",
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("Invalid occupancy class" in e for e in errors)

    def test_valid_occupancy_classes(self, pipeline: AnalysisPipeline):
        """Test common valid occupancy classes are accepted."""
        for occ_class in ["B", "E", "R-1", "A-3", "S-1", "H-2", "I-2"]:
            data = {
                "floor_plan": {"area": 1000, "exits": [1]},
                "detector_specs": {"type": "smoke"},
                "occupancy_class": occ_class,
            }
            is_valid, errors = pipeline.validate_input(data)
            assert is_valid is True, f"Occupancy class '{occ_class}' should be valid, got errors: {errors}"

    def test_floor_plan_not_dict(self, pipeline: AnalysisPipeline):
        """Test floor_plan as non-dict is rejected."""
        data = {
            "floor_plan": "not a dict",
            "detector_specs": {"type": "heat"},
            "occupancy_class": "B",
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("dictionary" in e.lower() for e in errors)

    def test_detector_specs_not_dict(self, pipeline: AnalysisPipeline):
        """Test detector_specs as non-dict is rejected."""
        data = {
            "floor_plan": {"area": 1000, "exits": [1]},
            "detector_specs": "not a dict",
            "occupancy_class": "B",
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("dictionary" in e.lower() for e in errors)

    def test_zero_area_rejected(self, pipeline: AnalysisPipeline):
        """Test zero area is rejected — NFPA 72 requires positive area."""
        data = {
            "floor_plan": {"area": 0, "exits": [1]},
            "detector_specs": {"type": "heat"},
            "occupancy_class": "B",
        }
        is_valid, errors = pipeline.validate_input(data)
        assert is_valid is False
        assert any("positive" in e.lower() or "area" in e.lower() for e in errors)
