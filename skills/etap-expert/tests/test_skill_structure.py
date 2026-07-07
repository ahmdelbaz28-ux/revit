# NOSONAR
"""
Gate 1: Static Validation Tests.
================================
Validates the structural integrity of the etap-expert SKILL.md file.

Per FireAI agent.md VERIFICATION GATES:
    [Gate 1] Static Validation
    - syntax (YAML front-matter)
    - lint (section structure)
    - typing (front-matter fields)
    - schema validation (manifest.yaml)

Tests:
    1. SKILL.md file exists and is non-empty
    2. YAML front-matter parses cleanly
    3. Front-matter fields match expected values
    4. All 33 numbered sections exist
    5. All 4 response templates (A/B/C/D) present
    6. All 5 simulation examples present
    7. All 6 mistake categories present
    8. All 6 workflow steps present
    9. Required IEEE/IEC/NFPA standards referenced
    10. manifest.yaml validates against skill_validator.py model
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Add skill scripts to path
SKILL_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from skill_loader import (  # noqa: E402
    EXPECTED_MISTAKE_CATEGORIES,
    EXPECTED_SECTIONS,
    EXPECTED_SIMULATION_EXAMPLES,
    EXPECTED_TEMPLATES,
    EXPECTED_WORKFLOW_STEPS,
    REQUIRED_STANDARDS,
    SKILL_NAME,
    SKILL_VERSION,
    load_skill,
)

SKILL_MD = SKILL_ROOT / "SKILL.md"
MANIFEST_YAML = SKILL_ROOT / "manifest.yaml"


# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def skill_content() -> str:
    """Read SKILL.md content once per session."""
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def skill_validation_result():
    """Run loader validation once per session."""
    return load_skill(SKILL_MD)


@pytest.fixture(scope="session")
def manifest_data():
    """Parse manifest.yaml once per session."""
    return yaml.safe_load(MANIFEST_YAML.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: File existence
# ═══════════════════════════════════════════════════════════════════════════


class TestSkillFileIntegrity:
    """Test that skill files exist and are non-empty."""

    def test_skill_md_exists(self) -> None:
        assert SKILL_MD.exists(), f"SKILL.md not found at {SKILL_MD}"

    def test_skill_md_non_empty(self, skill_content) -> None:
        assert len(skill_content) > 1000, "SKILL.md is suspiciously short"

    def test_skill_md_has_substantial_content(self, skill_content) -> None:
        # Expected ~4400+ lines based on source
        lines = skill_content.count("\n")
        assert lines >= 4000, f"SKILL.md has only {lines} lines, expected >= 4000"

    def test_manifest_yaml_exists(self) -> None:
        assert MANIFEST_YAML.exists(), f"manifest.yaml not found at {MANIFEST_YAML}"

    def test_readme_md_exists(self) -> None:
        assert (SKILL_ROOT / "README.md").exists()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Front-matter validation
# ═══════════════════════════════════════════════════════════════════════════


class TestFrontMatter:
    """Test YAML front-matter parsing and validation."""

    def test_loader_passes(self, skill_validation_result) -> None:
        """Skill loader must pass without errors."""
        assert skill_validation_result.is_valid, (
            "Loader failed with errors:\n"
            + "\n".join(f"  - {e}" for e in skill_validation_result.errors)
        )

    def test_skill_name(self, skill_validation_result) -> None:
        assert skill_validation_result.structure.front_matter.name == SKILL_NAME

    def test_skill_version(self, skill_validation_result) -> None:
        assert skill_validation_result.structure.front_matter.version == SKILL_VERSION

    def test_skill_author_non_empty(self, skill_validation_result) -> None:
        assert skill_validation_result.structure.front_matter.author

    def test_skill_description_non_empty(self, skill_validation_result) -> None:
        desc = skill_validation_result.structure.front_matter.description
        assert desc
        assert len(desc) > 20


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Section count
# ═══════════════════════════════════════════════════════════════════════════


class TestSectionStructure:
    """Test that all expected sections are present."""

    def test_section_count(self, skill_validation_result) -> None:
        sections = skill_validation_result.structure.sections
        assert len(sections) >= EXPECTED_SECTIONS, (
            f"Expected >= {EXPECTED_SECTIONS} sections, found {len(sections)}: "
            f"{sections}"
        )

    def test_core_sections_present(self, skill_validation_result) -> None:
        """Verify critical sections by name (substring match)."""
        sections_text = " ".join(skill_validation_result.structure.sections)
        required_sections = [
            "CORE IDENTITY",
            "ETAP MODULE DIRECTORY",
            "EXPERT WORKFLOW",
            "ADMS",
            "GIS INTEGRATION",
            "POWER SYSTEM ANALYSIS",
            "PROTECTION",
            "ARC FLASH",
            "TRANSIENT",
            "RENEWABLE",
            "MARINE",
            "TRACTION",
            "STANDARDS",
            "COMMON USER MISTAKES",
            "INTERNAL SIMULATION",
            "RESPONSE TEMPLATES",
            "CRITICAL RULES",
        ]
        for required in required_sections:
            assert required in sections_text.upper(), (
                f"Required section '{required}' not found in skill sections"
            )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Templates A/B/C/D
# ═══════════════════════════════════════════════════════════════════════════


class TestResponseTemplates:
    """Test that all 4 response templates are present."""

    def test_all_templates_present(self, skill_validation_result) -> None:
        templates = skill_validation_result.structure.templates_found
        for key in EXPECTED_TEMPLATES:
            assert templates.get(key, False), f"Template {key} not found in skill"

    def test_template_a_complete_request(self, skill_content) -> None:
        assert "REQUEST ANALYSIS: COMPLETE" in skill_content

    def test_template_b_incomplete_request(self, skill_content) -> None:
        assert "REQUEST ANALYSIS: INCOMPLETE" in skill_content

    def test_template_c_wrong_request(self, skill_content) -> None:
        assert "REQUEST ANALYSIS: INCORRECT APPROACH" in skill_content

    def test_template_d_adms_request(self, skill_content) -> None:
        assert "ADMS REQUEST ANALYSIS" in skill_content


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Simulation examples
# ═══════════════════════════════════════════════════════════════════════════


class TestSimulationExamples:
    """Test that all 5 simulation examples are present."""

    def test_simulation_count(self, skill_validation_result) -> None:
        examples = skill_validation_result.structure.simulation_examples
        assert len(examples) >= EXPECTED_SIMULATION_EXAMPLES, (
            f"Expected {EXPECTED_SIMULATION_EXAMPLES} simulations, found {len(examples)}: "
            f"{examples}"
        )

    def test_cable_sizing_example(self, skill_content) -> None:
        assert "Cable Sizing with Voltage Drop" in skill_content
        # Verify numerical anchors
        assert "200A" in skill_content
        assert "480V" in skill_content

    def test_transformer_sizing_example(self, skill_content) -> None:
        assert "Transformer Sizing" in skill_content
        assert "800kW" in skill_content or "800 kW" in skill_content

    def test_protection_coordination_example(self, skill_content) -> None:
        assert "Protection Coordination" in skill_content
        assert "500HP" in skill_content or "500 HP" in skill_content

    def test_arc_flash_example(self, skill_content) -> None:
        assert "Arc Flash Calculation" in skill_content
        assert "IEEE 1584" in skill_content

    def test_flisr_example(self, skill_content) -> None:
        assert "FLISR" in skill_content


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: Mistake categories
# ═══════════════════════════════════════════════════════════════════════════


class TestMistakeCategories:
    """Test that all 6 mistake categories are present."""

    def test_mistake_count(self, skill_validation_result) -> None:
        cats = skill_validation_result.structure.mistake_categories
        assert len(cats) >= EXPECTED_MISTAKE_CATEGORIES, (
            f"Expected {EXPECTED_MISTAKE_CATEGORIES} mistake categories, "
            f"found {len(cats)}: {cats}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: Workflow steps
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowSteps:
    """Test that all 6 workflow steps are present."""

    def test_workflow_count(self, skill_validation_result) -> None:
        steps = skill_validation_result.structure.workflow_steps
        assert len(steps) >= EXPECTED_WORKFLOW_STEPS, (
            f"Expected {EXPECTED_WORKFLOW_STEPS} workflow steps, found {len(steps)}: {steps}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: Standards referenced
# ═══════════════════════════════════════════════════════════════════════════


class TestStandardsReferenced:
    """Test that all required standards are referenced."""

    def test_ieee_standards(self, skill_validation_result) -> None:
        ieee_found = skill_validation_result.structure.standards_referenced.get("IEEE", [])
        for std in REQUIRED_STANDARDS["IEEE"]:
            assert std in ieee_found, f"Required IEEE standard '{std}' not referenced"

    def test_iec_standards(self, skill_validation_result) -> None:
        iec_found = skill_validation_result.structure.standards_referenced.get("IEC", [])
        for std in REQUIRED_STANDARDS["IEC"]:
            assert std in iec_found, f"Required IEC standard '{std}' not referenced"

    def test_nfpa_standards(self, skill_validation_result) -> None:
        nfpa_found = skill_validation_result.structure.standards_referenced.get("NFPA", [])
        for std in REQUIRED_STANDARDS["NFPA"]:
            assert std in nfpa_found, f"Required NFPA standard '{std}' not referenced"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9: Manifest validation
# ═══════════════════════════════════════════════════════════════════════════


class TestManifestValidation:
    """Test that manifest.yaml is structurally valid."""

    def test_manifest_has_required_fields(self, manifest_data) -> None:
        assert "metadata" in manifest_data
        assert "description" in manifest_data
        assert "requirements" in manifest_data

    def test_manifest_metadata_fields(self, manifest_data) -> None:
        meta = manifest_data["metadata"]
        assert meta["name"] == SKILL_NAME
        assert meta["version"] == SKILL_VERSION
        assert meta["author"]

    def test_manifest_description_fields(self, manifest_data) -> None:
        desc = manifest_data["description"]
        assert "short_description" in desc
        assert "trigger_words" in desc
        assert isinstance(desc["trigger_words"], list)
        assert len(desc["trigger_words"]) >= 10, (
            f"Expected >= 10 trigger words, got {len(desc['trigger_words'])}"
        )

    def test_manifest_requirements_fields(self, manifest_data) -> None:
        req = manifest_data["requirements"]
        assert "python_version" in req
        assert "permissions" in req
        assert "max_execution_time" in req

    def test_manifest_tags_present(self, manifest_data) -> None:
        tags = manifest_data.get("tags", [])
        assert len(tags) >= 5, f"Expected >= 5 tags, got {len(tags)}"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10: ETAP terminology enforcement
# ═══════════════════════════════════════════════════════════════════════════


class TestETAPTerminology:
    """Test that skill uses correct ETAP terminology (Rule 6)."""

    def test_uses_bus_not_node(self, skill_content) -> None:
        # Skill should use "Bus" extensively
        assert "Bus" in skill_content
        # "node" should appear far less frequently than "Bus"
        bus_count = skill_content.count("Bus")
        node_count = skill_content.lower().count("node")
        # Allow some "node" mentions in non-ETAP contexts
        assert bus_count > node_count, (
            f"Expected 'Bus' count > 'node' count, got Bus={bus_count}, node={node_count}"
        )

    def test_uses_one_line_not_schematic(self, skill_content) -> None:
        assert "One-Line" in skill_content

    def test_uses_star_module(self, skill_content) -> None:
        assert "Star" in skill_content  # Star module for protection

    def test_uses_study_case(self, skill_content) -> None:
        assert "Study Case" in skill_content
