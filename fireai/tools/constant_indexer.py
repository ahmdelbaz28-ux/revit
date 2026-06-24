#!/usr/bin/env python3
"""FireAI — Constants Usage Index Generator

This script scans the codebase and generates a comprehensive index of:
1. Where each constant is DEFINED (canonical source)
2. Where each constant is USED (imports and references)
3. Any DRIFT detected (redefined values that differ from canonical)
"""

from __future__ import annotations

# Run: python -m fireai.tools.constant_indexer
# Output: fireai/CONSTANTS_USAGE_MAP.json
#
# PE SIGN-OFF REQUIRED for any changes to canonical constants.
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Canonical constants from fireai/constants/nfpa72.py
# These values MUST match exactly what's in the canonical source
CANONICAL_CONSTANTS = {
    # NFPA 72 Constants
    "SMOKE_MAX_SPACING_M": 9.1,
    "HEAT_MAX_SPACING_M": 6.10,
    "COVERAGE_RADIUS_FACTOR": 0.7,
    "SMOKE_COVERAGE_RADIUS_M": 6.37,
    "HEAT_COVERAGE_RADIUS_M": 4.27,
    "WALL_MIN_DISTANCE_M": 0.1016,
    "SMOKE_MAX_WALL_DISTANCE_M": 4.55,
    "HEAT_MAX_WALL_DISTANCE_M": 3.05,
    "SMOKE_MAX_CEILING_HEIGHT_M": 18.288,
    "HEAT_MAX_CEILING_HEIGHT_M": 15.24,
    "CEILING_HEIGHT_MIN_M": 3.0,
    "BATTERY_STANDBY_HOURS": 24.0,
    "BATTERY_ALARM_MINUTES": 5.0,
    "BATTERY_SAFETY_FACTOR": 1.25,
    "NAC_MIN_CD": 75,
    "NAC_SLEEPING_MIN_CD": 177,
    "PULL_STATION_HEIGHT_M": 1.219,
    "PULL_STATION_FROM_EXIT_M": 1.524,
    "RIDGE_ZONE_BUFFER_M": 0.90,
    "VOLTAGE_DROP_MAX_FRACTION": 0.10,
    # Non-NFPA Constants
    "GRAVITY_M_S2": 9.80665,
    "MOLAR_MASS_AIR": 0.0289644,
    "UNIVERSAL_GAS_CONSTANT": 8.31447,
    "DEFAULT_AQI": 100,
    "DEFAULT_PM25_UG_M3": 35.0,
    "DEFAULT_PM10_UG_M3": 50.0,
    "DEFAULT_LFL_VOL_PCT": 0.5,
    "DEFAULT_AUTO_IGNITION_C": 200.0,
    "NFPA72_MINIMUM_SAFETY_FACTOR": 1.20,
    "MAX_DEVICES_BETWEEN_ISOLATORS": 32,
    "MAX_SLC_DEVICES_DEFAULT": 250,
    "MIN_STAIRWELL_PRESSURIZATION_PA": 25.0,
    "MAX_PRESSURE_DIFFERENTIAL_PA": 133.0,
}

# Known canonical sources for constants
CANONICAL_SOURCES = {
    "SMOKE_MAX_SPACING_M": "fireai/constants/nfpa72.py",
    "HEAT_MAX_SPACING_M": "fireai/constants/nfpa72.py",
    "COVERAGE_RADIUS_FACTOR": "fireai/constants/nfpa72.py",
    "SMOKE_COVERAGE_RADIUS_M": "fireai/constants/nfpa72.py",
    "HEAT_COVERAGE_RADIUS_M": "fireai/constants/nfpa72.py",
    "WALL_MIN_DISTANCE_M": "fireai/constants/nfpa72.py",
    "SMOKE_MAX_WALL_DISTANCE_M": "fireai/constants/nfpa72.py",
    "HEAT_MAX_WALL_DISTANCE_M": "fireai/constants/nfpa72.py",
    "SMOKE_MAX_CEILING_HEIGHT_M": "fireai/constants/nfpa72.py",
    "HEAT_MAX_CEILING_HEIGHT_M": "fireai/constants/nfpa72.py",
    "GRAVITY_M_S2": "backend/services/elevation_service.py",
    "MOLAR_MASS_AIR": "backend/services/elevation_service.py",
    "UNIVERSAL_GAS_CONSTANT": "backend/services/elevation_service.py",
    "NFPA72_MINIMUM_SAFETY_FACTOR": "fireai/core/battery_aging_derating.py",
    "MAX_DEVICES_BETWEEN_ISOLATORS": "fireai/core/circuit_topology.py",
    "MAX_SLC_DEVICES_DEFAULT": "fireai/core/circuit_topology.py",
}


def find_constant_definitions(root_path: Path) -> dict[str, list[dict]]:
    """Find where constants are defined (not imported)."""
    definitions = defaultdict(list)

    # Pattern to find constant definitions like: CONSTANT_NAME = value
    pattern = re.compile(r'^([A-Z][A-Z0-9_]*)\s*=\s*(.+)', re.MULTILINE)

    for py_file in root_path.rglob("*.py"):
        if "__pycache__" in str(py_file) or "test_" in py_file.name:
            continue

        try:
            content = py_file.read_text()
            for match in pattern.finditer(content):
                const_name = match.group(1)
                const_value = match.group(2).strip()

                # Check if this looks like a numeric constant
                if any(c.isdigit() for c in const_value[:10]):
                    definitions[const_name].append({
                        "file": str(py_file.relative_to(root_path)),
                        "line": content[:match.start()].count('\n') + 1,
                        "value": const_value[:50],  # Truncate for readability
                    })
        except Exception as e:
            logger.warning("Error scanning %s for constant definitions: %s", py_file, e)

    return dict(definitions)


def find_constant_usages(root_path: Path, constants: list[str]) -> dict[str, list[dict]]:
    """Find where constants are imported or used."""
    usages = defaultdict(list)
    seen_positions: set[tuple[str, int]] = set()  # (file, line) — O(1) duplicate check

    # Pattern to find imports
    import_pattern = re.compile(r'from\s+[\w.]+\s+import\s+.*?\b(' + '|'.join(constants) + r')\b')

    # Pattern to find usage (after import)
    use_pattern = re.compile(r'\b(' + '|'.join(constants) + r')\b')

    for py_file in root_path.rglob("*.py"):
        if "__pycache__" in str(py_file) or "test_" in py_file.name:
            continue

        try:
            content = py_file.read_text()
            lines = content.split('\n')

            for i, line in enumerate(lines, 1):
                # Skip comments
                if line.strip().startswith('#'):
                    continue

                rel_path = str(py_file.relative_to(root_path))
                pos = (rel_path, i)

                for match in import_pattern.finditer(line):
                    const_name = match.group(1)
                    if pos not in seen_positions:
                        seen_positions.add(pos)
                        usages[const_name].append({
                            "file": rel_path,
                            "line": i,
                            "type": "import",
                            "context": line.strip()[:80],
                        })

                for match in use_pattern.finditer(line):
                    const_name = match.group(1)
                    # Avoid counting the same line twice (import already counted)
                    if pos not in seen_positions:
                        seen_positions.add(pos)
                        usages[const_name].append({
                            "file": rel_path,
                            "line": i,
                            "type": "usage",
                            "context": line.strip()[:80],
                        })
        except Exception as e:
            logger.warning("Error scanning %s for constant usages: %s", py_file, e)

    return dict(usages)


def check_constant_consistency(root_path: Path) -> list[dict]:
    """Check for constant drift (different values in different places)."""
    drift_issues = []

    definitions = find_constant_definitions(root_path)

    for const_name, canonical_value in CANONICAL_CONSTANTS.items():
        if const_name not in definitions:
            continue

        for def_info in definitions[const_name]:
            # Extract numeric value from the definition
            value_str = def_info["value"]
            try:
                # Try to extract number
                match = re.search(r'[\d.]+', value_str)
                if match:
                    defined_value = float(match.group())
                    if abs(defined_value - canonical_value) > 0.0001:
                        drift_issues.append({
                            "constant": const_name,
                            "canonical_value": canonical_value,
                            "defined_value": defined_value,
                            "file": def_info["file"],
                            "line": def_info["line"],
                            "issue": f"Value {defined_value} differs from canonical {canonical_value}",
                        })
            except (ValueError, AttributeError) as e:
                logger.debug("Cannot extract numeric value for drift check: %s", e)

    return drift_issues


def generate_report(root_path: Path) -> dict[str, Any]:
    """Generate comprehensive constants index report."""
    constants_list = list(CANONICAL_CONSTANTS.keys())
    definitions = find_constant_definitions(root_path)
    usages = find_constant_usages(root_path, constants_list)
    drift_issues = check_constant_consistency(root_path)

    report = {
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "canonicals": CANONICAL_CONSTANTS,
        "definitions": definitions,
        "usages": usages,
        "drift_issues": drift_issues,
        "summary": {
            "total_constants": len(CANONICAL_CONSTANTS),
            "total_definitions": sum(len(v) for v in definitions.values()),
            "total_usages": sum(len(v) for v in usages.values()),
            "drift_count": len(drift_issues),
        },
    }

    return report


def main():
    root = Path(__file__).parent.parent.parent
    output_file = root / "fireai" / "CONSTANTS_USAGE_MAP.json"

    print("🔍 Scanning codebase for constant definitions and usages...")
    report = generate_report(root)

    print("\n📊 Constants Index Report")
    print("=" * 60)
    print(f"Total canonical constants: {report['summary']['total_constants']}")
    print(f"Total definitions found:   {report['summary']['total_definitions']}")
    print(f"Total usages found:        {report['summary']['total_usages']}")
    print(f"⚠️  Drift issues detected:  {report['summary']['drift_count']}")

    if report['drift_issues']:
        print("\n🚨 DRIFT ISSUES (MUST FIX):")
        for issue in report['drift_issues']:
            print(f"  - {issue['constant']}: {issue['issue']}")
            print(f"    File: {issue['file']}:{issue['line']}")

    # Write JSON report
    output_file.write_text(json.dumps(report, indent=2))
    print(f"\n✅ Full report saved to: {output_file}")

    # Write Markdown summary
    md_file = root / "fireai" / "CONSTANTS_USAGE_REPORT.md"
    with open(md_file, 'w') as f:
        f.write("# FireAI Constants Usage Report\n\n")
        f.write(f"Generated: {report['generated_at']}\n\n")
        f.write("## Summary\n\n")
        f.write(f"- Canonical constants: {report['summary']['total_constants']}\n")
        f.write(f"- Definitions found: {report['summary']['total_definitions']}\n")
        f.write(f"- Usages found: {report['summary']['total_usages']}\n")
        f.write(f"- Drift issues: {report['summary']['drift_count']}\n\n")

        if report['drift_issues']:
            f.write("## 🚨 Drift Issues (MUST FIX)\n\n")
            for issue in report['drift_issues']:
                f.write(f"### {issue['constant']}\n")
                f.write(f"- Canonical value: `{issue['canonical_value']}`\n")
                f.write(f"- Defined value: `{issue['defined_value']}`\n")
                f.write(f"- File: `{issue['file']}`:{issue['line']}\n")
                f.write(f"- Issue: {issue['issue']}\n\n")
        else:
            f.write("## ✅ No Drift Issues Detected\n\n")

    print(f"✅ Markdown report saved to: {md_file}")

    return 0 if report['summary']['drift_count'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
