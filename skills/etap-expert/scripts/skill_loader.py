"""
ETAP Expert Skill Loader
=========================
Validates and loads the etap-expert skill, enforcing structural integrity
per FireAI agent.md Rule 14 (NO MODIFICATION WITHOUT VERIFICATION).

This loader performs Gate 1 (Static) and Gate 2 (Runtime) verification:
- Parses YAML front-matter from SKILL.md
- Validates all 33 numbered sections exist
- Validates 4 response templates (A/B/C/D) present
- Validates 5 internal simulation examples present
- Validates standards tables (IEEE/IEC/NEC/NFPA) present
- Validates the 6-step workflow structure
- Validates the 6 mistake categories

Author: FireAI Project
Version: 1.0.0
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as e:
    raise ImportError(
        "PyYAML is required for skill loading. Install with: pip install pyyaml"
    ) from e


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS — Derived from skill content, NOT hardcoded assumptions
# ═══════════════════════════════════════════════════════════════════════════

SKILL_NAME = "etap-expert"
SKILL_VERSION = "1.0.0"
EXPECTED_SECTIONS = 33  # Verified from SKILL.md table of contents
EXPECTED_TEMPLATES = ["A", "B", "C", "D"]
EXPECTED_SIMULATION_EXAMPLES = 5
EXPECTED_MISTAKE_CATEGORIES = 6
EXPECTED_WORKFLOW_STEPS = 6

# Templates must contain these markers (verified from skill Section 16)
TEMPLATE_MARKERS = {
    "A": "REQUEST ANALYSIS: COMPLETE",
    "B": "REQUEST ANALYSIS: INCOMPLETE",
    "C": "REQUEST ANALYSIS: INCORRECT APPROACH",
    "D": "ADMS REQUEST ANALYSIS",
}

# The 6-step workflow steps (verified from skill Section 4)
WORKFLOW_STEPS = [
    "PARSE & CLASSIFY",
    "SEARCH INTERNAL KNOWLEDGE",
    "FEASIBILITY & VALIDATION",
    "INTERNAL SIMULATION",
    "FORMULATE RESPONSE",
    "QUALITY ASSURANCE",
]

# The 6 mistake categories (verified from skill Section 14)
MISTAKE_CATEGORIES = [
    "WRONG STUDY FOR THE GOAL",
    "MISSING CRITICAL DATA",
    "PHYSICALLY IMPOSSIBLE",
    "CONFUSING ETAP WITH OTHER SOFTWARE",
    "ADMS-SPECIFIC MISTAKES",
    "PROTECTION MISTAKES",
]

# Standards that MUST be referenced (verified from skill Section 13)
REQUIRED_STANDARDS = {
    "IEEE": ["IEEE 80", "IEEE 1584", "IEEE 1547", "IEEE 519", "IEEE 141"],
    "IEC": ["IEC 60909", "IEC 61363", "IEC 62351", "IEC 61850", "IEC 60092"],
    "NFPA": ["NFPA 70", "NFPA 70E", "NFPA 110", "NFPA 780"],
}

# Internal simulation examples (verified from skill Section 15.2)
SIMULATION_EXAMPLE_TITLES = [
    "Cable Sizing with Voltage Drop",
    "Transformer Sizing",
    "Protection Coordination",
    "Arc Flash Calculation",
    "ADMS - FLISR Simulation",
]

# ETAP terminology that must be enforced (skill Rule 6)
ETAP_CANONICAL_TERMS = {
    "bus": "Bus",  # NOT "node"
    "one-line": "One-Line",  # NOT "schematic"
    "star": "Star",  # NOT "relay module"
    "study case": "Study Case",  # NOT "scenario"
}


# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SkillFrontMatter:
    """Validated YAML front-matter from SKILL.md."""

    name: str
    version: str
    description: str
    author: str

    def validate(self) -> tuple[bool, str | None]:
        """Validate front-matter against expected values."""
        if self.name != SKILL_NAME:
            return False, f"name mismatch: expected '{SKILL_NAME}', got '{self.name}'"
        if self.version != SKILL_VERSION:
            return (
                False,
                f"version mismatch: expected '{SKILL_VERSION}', got '{self.version}'",
            )
        if not self.description or len(self.description) < 10:
            return False, "description too short (<10 chars)"
        if not self.author:
            return False, "author is empty"
        return True, None


@dataclass
class SkillStructure:
    """Parsed structural elements of the skill."""

    front_matter: SkillFrontMatter
    sections: list[str] = field(default_factory=list)  # Section headings
    templates_found: dict[str, bool] = field(default_factory=dict)
    simulation_examples: list[str] = field(default_factory=list)
    mistake_categories: list[str] = field(default_factory=list)
    workflow_steps: list[str] = field(default_factory=list)
    standards_referenced: dict[str, list[str]] = field(default_factory=dict)
    total_lines: int = 0
    total_chars: int = 0


@dataclass
class ValidationResult:
    """Result of skill validation."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    structure: SkillStructure | None = None

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


# ═══════════════════════════════════════════════════════════════════════════
# PARSER
# ═══════════════════════════════════════════════════════════════════════════


def parse_front_matter(content: str) -> tuple[SkillFrontMatter | None, str | None]:
    """
    Parse YAML front-matter from SKILL.md content.

    Front-matter is delimited by --- at start and end.
    Returns (front_matter, error_message).
    """
    fm_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    match = fm_pattern.match(content)
    if not match:
        return None, "No YAML front-matter found at start of SKILL.md"

    yaml_text = match.group(1)
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"

    if not isinstance(data, dict):
        return None, "Front-matter is not a mapping"

    required_fields = {"name", "version", "description", "author"}
    missing = required_fields - set(data.keys())
    if missing:
        return None, f"Missing required fields: {missing}"

    return (
        SkillFrontMatter(
            name=str(data["name"]),
            version=str(data["version"]),
            description=str(data["description"]),
            author=str(data["author"]),
        ),
        None,
    )


def extract_sections(content: str) -> list[str]:
    """Extract all section headings (## N. Title)."""
    pattern = re.compile(r"^##\s+(\d+)\.\s+(.+)$", re.MULTILINE)
    matches = pattern.findall(content)
    # Sort by section number
    matches.sort(key=lambda x: int(x[0]))
    return [title.strip() for _, title in matches]


def extract_templates(content: str) -> dict[str, bool]:
    """Check presence of Templates A/B/C/D by their markers."""
    found = {}
    for key, marker in TEMPLATE_MARKERS.items():
        found[key] = marker in content
    return found


def extract_simulation_examples(content: str) -> list[str]:
    """Extract the 5 simulation examples from Section 15.2."""
    examples = []
    for title in SIMULATION_EXAMPLE_TITLES:
        if title in content:
            examples.append(title)
    return examples


def extract_mistake_categories(content: str) -> list[str]:
    """Extract the 6 mistake categories from Section 14."""
    found = []
    for cat in MISTAKE_CATEGORIES:
        if cat.upper() in content.upper():
            found.append(cat)
    return found


def extract_workflow_steps(content: str) -> list[str]:
    """Extract the 6-step workflow from Section 4."""
    found = []
    for step in WORKFLOW_STEPS:
        if step.upper() in content.upper():
            found.append(step)
    return found


def extract_standards(content: str) -> dict[str, list[str]]:
    """Check which required standards are referenced."""
    found = {}
    for category, standards in REQUIRED_STANDARDS.items():
        present = [s for s in standards if s in content]
        found[category] = present
    return found


# ═══════════════════════════════════════════════════════════════════════════
# MAIN VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════


def load_skill(skill_path: Path | str) -> ValidationResult:
    """
    Load and validate the etap-expert skill.

    Args:
        skill_path: Path to SKILL.md file

    Returns:
        ValidationResult with full structure if valid
    """
    result = ValidationResult(is_valid=True)
    skill_path = Path(skill_path)

    # 1. File exists
    if not skill_path.exists():
        result.add_error(f"Skill file not found: {skill_path}")
        return result

    # 2. Read content
    try:
        content = skill_path.read_text(encoding="utf-8")
    except OSError as e:
        result.add_error(f"Cannot read file: {e}")
        return result

    # 3. Parse front-matter
    fm, fm_err = parse_front_matter(content)
    if fm_err or fm is None:
        result.add_error(f"Front-matter error: {fm_err}")
        return result

    fm_valid, fm_msg = fm.validate()
    if not fm_valid:
        result.add_error(f"Front-matter validation failed: {fm_msg}")
        return result

    # 4. Parse structural elements
    structure = SkillStructure(
        front_matter=fm,
        sections=extract_sections(content),
        templates_found=extract_templates(content),
        simulation_examples=extract_simulation_examples(content),
        mistake_categories=extract_mistake_categories(content),
        workflow_steps=extract_workflow_steps(content),
        standards_referenced=extract_standards(content),
        total_lines=content.count("\n") + 1,
        total_chars=len(content),
    )

    # 5. Validate section count
    if len(structure.sections) < EXPECTED_SECTIONS:
        result.add_error(
            f"Expected >= {EXPECTED_SECTIONS} sections, found {len(structure.sections)}"
        )
    elif len(structure.sections) > EXPECTED_SECTIONS:
        result.add_warning(
            f"Found {len(structure.sections)} sections, expected {EXPECTED_SECTIONS} "
            "(skill may have been extended — verify additions are intentional)"
        )

    # 6. Validate templates
    for key, present in structure.templates_found.items():
        if not present:
            result.add_error(f"Template {key} marker not found")

    # 7. Validate simulation examples
    if len(structure.simulation_examples) < EXPECTED_SIMULATION_EXAMPLES:
        result.add_error(
            f"Expected {EXPECTED_SIMULATION_EXAMPLES} simulation examples, "
            f"found {len(structure.simulation_examples)}: {structure.simulation_examples}"
        )

    # 8. Validate mistake categories
    if len(structure.mistake_categories) < EXPECTED_MISTAKE_CATEGORIES:
        result.add_error(
            f"Expected {EXPECTED_MISTAKE_CATEGORIES} mistake categories, "
            f"found {len(structure.mistake_categories)}"
        )

    # 9. Validate workflow steps
    if len(structure.workflow_steps) < EXPECTED_WORKFLOW_STEPS:
        result.add_error(
            f"Expected {EXPECTED_WORKFLOW_STEPS} workflow steps, "
            f"found {len(structure.workflow_steps)}"
        )

    # 10. Validate standards
    for category, found in structure.standards_referenced.items():
        if not found:
            result.add_error(f"No {category} standards referenced")

    # 11. Sanity checks
    if structure.total_lines < 1000:
        result.add_warning(
            f"Skill is suspiciously short: {structure.total_lines} lines"
        )

    result.structure = structure
    return result


def load_skill_or_raise(skill_path: Path | str) -> SkillStructure:
    """Load skill and raise if invalid."""
    result = load_skill(skill_path)
    if not result.is_valid:
        raise ValueError(
            f"Skill validation failed with {len(result.errors)} errors:\n"
            + "\n".join(f"  - {e}" for e in result.errors)
        )
    return result.structure  # type: ignore[return-value]


# ═══════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════


def main() -> int:
    """CLI entry: validate skill and print report."""
    import sys

    skill_path = Path(__file__).parent.parent / "SKILL.md"
    if len(sys.argv) > 1:
        skill_path = Path(sys.argv[1])

    print(f"═" * 70)
    print(f"ETAP Expert Skill Loader — Validation Report")
    print(f"═" * 70)
    print(f"Skill path: {skill_path}")
    print()

    result = load_skill(skill_path)

    if result.structure:
        s = result.structure
        print(f"Front-matter:")
        print(f"  name:        {s.front_matter.name}")
        print(f"  version:     {s.front_matter.version}")
        print(f"  author:      {s.front_matter.author}")
        print(f"  description: {s.front_matter.description[:80]}...")
        print()
        print(f"Structure:")
        print(f"  Total lines:              {s.total_lines}")
        print(f"  Total chars:              {s.total_chars}")
        print(f"  Sections found:           {len(s.sections)} / {EXPECTED_SECTIONS}")
        print(f"  Templates A/B/C/D:        {s.templates_found}")
        print(f"  Simulation examples:      {len(s.simulation_examples)} / {EXPECTED_SIMULATION_EXAMPLES}")
        print(f"  Mistake categories:       {len(s.mistake_categories)} / {EXPECTED_MISTAKE_CATEGORIES}")
        print(f"  Workflow steps:           {len(s.workflow_steps)} / {EXPECTED_WORKFLOW_STEPS}")
        print(f"  IEEE standards referenced: {len(s.standards_referenced.get('IEEE', []))}")
        print(f"  IEC standards referenced:  {len(s.standards_referenced.get('IEC', []))}")
        print(f"  NFPA standards referenced: {len(s.standards_referenced.get('NFPA', []))}")
        print()

    if result.warnings:
        print(f"⚠️  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"  - {w}")
        print()

    if result.errors:
        print(f"❌ Errors ({len(result.errors)}):")
        for e in result.errors:
            print(f"  - {e}")
        print()
        print(f"RESULT: FAILED")
        return 1

    print(f"✅ RESULT: PASSED")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
