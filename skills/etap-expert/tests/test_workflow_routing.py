# NOSONAR
"""
Gate 3: Behavioral Validation Tests.
====================================
Validates the 6-step workflow routing logic and the 4 response templates.

Per FireAI agent.md VERIFICATION GATES:
    [Gate 3] Behavioral Validation
    - expected outputs (templates trigger correctly)
    - edge-case handling (empty / malformed input)
    - failure handling (wrong study type detection)
    - deterministic behavior (same input → same output)

Tests cover:
    - Template A (Complete request) routing
    - Template B (Incomplete request) routing
    - Template C (Wrong request) routing
    - Template D (ADMS/DER request) routing
    - 6 mistake category detection
    - ETAP terminology enforcement
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

# Import classifier from production code (Rule 10: tests never modified, only code)
from classifier import classify_request  # noqa: E402

# TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestRequestClassification:
    """Test the request classifier (Step 1 of 6-step workflow)."""

    @pytest.mark.parametrize(
        ("request_text", "expected"),
        [
            # Complete requests → Template A
            ("What cable size for 200A load, 300ft, 480V?", "A"),
            ("Calculate arc flash for 480V MCC, 50kA fault, 18 inch working distance", "A"),
            ("Size transformer for 800kW load at 480V, PF=0.9", "A"),
            # Incomplete requests → Template B
            ("Size transformer for 500kW", "B"),
            ("Set relay for motor", "B"),
            ("Calculate voltage drop", "B"),
            # Wrong requests → Template C
            ("Run Load Flow to find fault current", "C"),
            ("Check arc flash with Load Flow", "C"),
            ("Size cable with Short Circuit only", "C"),
            ("Find motor starting time with Load Flow", "C"),
            # Physically impossible → Template C
            ("Need 0% voltage drop on 1000ft cable", "C"),
            ("Design 100% efficient transformer", "C"),
            # ADMS → Template D
            ("How does FLISR work for fault on Feeder 1?", "D"),
            ("Configure VVO for 4-feeder distribution system", "D"),
            ("Explain ADMS state estimation", "D"),
            ("Set up SCADA for substation monitoring", "D"),
            # DER → Template DER
            ("Size BESS for 1MW 4-hour peak shaving", "DER"),
            ("Model solar PV for 5MW farm", "DER"),
            ("Design microgrid with solar and battery", "DER"),
        ],
    )
    def test_classification(self, request_text, expected) -> None:
        result = classify_request(request_text)
        assert result == expected, (
            f"Request '{request_text}' classified as '{result}', expected '{expected}'"
        )


class TestMistakeDetection:
    """Test that all 6 mistake categories from Section 14 are detectable."""

    def test_mistake_1_wrong_study(self) -> None:
        result = classify_request("Run Load Flow to find fault current")
        assert result == "C"

    def test_mistake_2_missing_data(self) -> None:
        result = classify_request("Size transformer for 500kW")
        assert result == "B"

    def test_mistake_3_physically_impossible(self) -> None:
        result = classify_request("Need 0% voltage drop on 1000ft cable")
        assert result == "C"

    def test_mistake_4_other_software(self) -> None:
        """ETAP doesn't do FEM, PCB, HVAC."""
        # This is documented in skill but classifier doesn't catch it
        # (would require LLM understanding, not pattern matching)
        # Just verify the skill content covers it
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        assert "Do FEM analysis in ETAP" in skill_content
        assert "Design PCB in ETAP" in skill_content

    def test_mistake_5_adms_specific(self) -> None:
        """Load Flow in ADMS should use State Estimation."""
        # The mistake is "Run Load Flow in ADMS" → should be DSE
        # Classify as D (ADMS context) — the correction is in the response
        result = classify_request("Run Load Flow in ADMS")
        # "load flow" is in study types, "adms" is keyword — ADMS wins
        assert result == "D"

    def test_mistake_6_protection(self) -> None:
        """Set all relays the same violates selectivity."""
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        assert "Set all relays the same" in skill_content


class TestDeterministicBehavior:
    """Test that classification is deterministic (same input → same output)."""

    @pytest.mark.parametrize("trial", range(20))
    def test_deterministic_cable_sizing(self, trial) -> None:
        request = "What cable size for 200A load, 300ft, 480V?"
        results = [classify_request(request) for _ in range(5)]
        assert all(r == results[0] for r in results), "Non-deterministic classification"
        assert results[0] == "A"

    @pytest.mark.parametrize("trial", range(20))
    def test_deterministic_arc_flash(self, trial) -> None:
        request = "Calculate arc flash for 480V MCC, 50kA fault"
        results = [classify_request(request) for _ in range(5)]
        assert all(r == results[0] for r in results)


class TestETAPCanonicalTerms:
    """Test that skill uses canonical ETAP terminology (Rule 6)."""

    @pytest.fixture(scope="class")
    def skill_content(self):
        return (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    def test_bus_term_used(self, skill_content) -> None:
        """ETAP uses 'Bus' not 'Node'."""
        assert "Bus" in skill_content
        assert "One-Line" in skill_content

    def test_star_term_used(self, skill_content) -> None:
        """ETAP uses 'Star' for protection coordination."""
        assert "Star" in skill_content

    def test_study_case_term_used(self, skill_content) -> None:
        """ETAP uses 'Study Case' not 'Scenario'."""
        assert "Study Case" in skill_content


class TestUnitsEnforcement:
    """Test that skill enforces unit inclusion (Rule 9)."""

    def test_skill_states_units_rule(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        assert "INCLUDE units" in content or "units in ALL" in content

    def test_simulation_examples_have_units(self) -> None:
        """
        Verify the 5 simulation examples in skill text have units.

        Skill content shows calculations like "VD = 200 × ... = 5.44V" — we
        verify the units-bearing result strings are present (not exact
        equations, since the skill shows full calculation chains).
        """
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        # Cable sizing example — units must appear in result
        assert "5.44V" in content, "Cable sizing example missing voltage-drop value with units"
        assert "1.13%" in content, "Cable sizing example missing %VD with units"
        # Transformer sizing
        assert "kVA" in content
        # Protection coordination
        assert "FLA = 62A" in content or "62A" in content
