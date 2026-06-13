#!/usr/bin/env python3
"""
FireAI — Constants Cross-Reference Index Generator

Tracks where each constant is used across the codebase.
Generates impact analysis for constant changes.

Run: python -m fireai.tools.crossref_indexer
Output: fireai/CROSSREF_INDEX.md
"""

import re
import subprocess
from collections import defaultdict
from pathlib import Path


# Canonical constants and their sources
CANONICAL_SOURCES = {
    # NFPA 72 Constants
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
    "BATTERY_STANDBY_HOURS": "fireai/constants/nfpa72.py",
    "BATTERY_ALARM_MINUTES": "fireai/constants/nfpa72.py",
    "BATTERY_SAFETY_FACTOR": "fireai/constants/nfpa72.py",
    "NAC_MIN_CD": "fireai/constants/nfpa72.py",
    "NAC_SLEEPING_MIN_CD": "fireai/constants/nfpa72.py",
    "PULL_STATION_HEIGHT_M": "fireai/constants/nfpa72.py",
    "PULL_STATION_FROM_EXIT_M": "fireai/constants/nfpa72.py",
    "VOLTAGE_DROP_MAX_FRACTION": "fireai/constants/nfpa72.py",
    # Service Constants
    "GRAVITY_M_S2": "backend/services/elevation_service.py",
    "MOLAR_MASS_AIR": "backend/services/elevation_service.py",
    "UNIVERSAL_GAS_CONSTANT": "backend/services/elevation_service.py",
    "DEFAULT_AQI": "backend/services/air_quality_service.py",
    "DEFAULT_PM25_UG_M3": "backend/services/air_quality_service.py",
    "DEFAULT_PM10_UG_M3": "backend/services/air_quality_service.py",
    "DEFAULT_LFL_VOL_PCT": "backend/services/hazmat_service.py",
    "DEFAULT_AUTO_IGNITION_C": "backend/services/hazmat_service.py",
}


def find_constant_usages(root: Path, constants: list[str]) -> dict:
    """Find all usages of each constant."""
    usages = defaultdict(list)
    
    pattern = rf'\b({"|".join(constants)})\b'
    
    for py_file in root.rglob("*.py"):
        if "__pycache__" in str(py_file) or "test_" in py_file.name:
            continue
        
        try:
            content = py_file.read_text()
            lines = content.split('\n')
            
            for i, line in enumerate(lines, 1):
                if line.strip().startswith('#'):
                    continue
                
                for match in re.finditer(pattern, line):
                    const_name = match.group(1)
                    rel_path = str(py_file.relative_to(root))
                    
                    usages[const_name].append({
                        "file": rel_path,
                        "line": i,
                        "context": line.strip()[:80],
                    })
        except Exception:
            pass
    
    return dict(usages)


def find_inline_definitions(root: Path) -> list[dict]:
    """Find constants defined inline (not from canonical source)."""
    drift_issues = []
    
    # Known drift patterns
    drift_patterns = [
        ("MIN_WALL_DISTANCE_M = 0.10", "core/nfpa72_models.py", 
         "Should be 0.1016 from fireai/constants/nfpa72.py"),
    ]
    
    for py_file in root.rglob("*.py"):
        if "__pycache__" in str(py_file) or "test_" in py_file.name:
            continue
        
        try:
            content = py_file.read_text()
            
            # Check for hardcoded values that should be imported
            if "MIN_WALL_DISTANCE_M = 0.10" in content:
                drift_issues.append({
                    "file": str(py_file.relative_to(root)),
                    "issue": "MIN_WALL_DISTANCE_M = 0.10",
                    "expected": "0.1016",
                    "fix": "Import from fireai.constants.nfpa72",
                })
            
            if "WALL_MIN_M = 0.1016" in content:
                # Check if it's actually an import or inline
                if "from fireai.constants" not in content:
                    drift_issues.append({
                        "file": str(py_file.relative_to(root)),
                        "issue": "WALL_MIN_M defined inline",
                        "expected": "Import from canonical",
                        "fix": "from fireai.constants.nfpa72 import WALL_MIN_DISTANCE_M",
                    })
        except Exception:
            pass
    
    return drift_issues


def generate_markdown(usages: dict, drift: list) -> str:
    """Generate Markdown documentation."""
    
    md = f"""# FireAI — Constants Cross-Reference Map

**Generated:** {subprocess.check_output(['date', '+%Y-%m-%d']).decode().strip()}
**Purpose:** Track constant usage across codebase

---

## 📊 Summary

| Metric | Count |
|--------|-------|
| Tracked constants | {len(usages)} |
| Total usages | {sum(len(v) for v in usages.values())} |
| Drift issues | {len(drift)} |

---

## 🔑 Constants Usage Map

"""
    
    for const, sources in sorted(usages.items()):
        canonical = CANONICAL_SOURCES.get(const, "Unknown")
        md += f"### `{const}`\n\n"
        md += f"**Canonical Source:** `{canonical}`\n\n"
        md += f"**Usages ({len(sources)}):**\n\n"
        
        for usage in sources[:10]:  # Limit to 10 per constant
            md += f"- `{usage['file']}`:{usage['line']}\n"
        
        if len(sources) > 10:
            md += f"- ... and {len(sources) - 10} more\n"
        
        md += "\n"
    
    if drift:
        md += "## ⚠️ Drift Issues\n\n"
        md += "| File | Issue | Expected | Fix |\n"
        md += "|------|-------|----------|-----|\n"
        for d in drift:
            md += f"| `{d['file']}` | {d['issue']} | {d['expected']} | {d['fix']} |\n"
        md += "\n"
    
    md += """
## ✅ Import Guidelines

```python
# ✅ CORRECT: Import from canonical source
from fireai.constants.nfpa72 import SMOKE_MAX_SPACING_M

# ❌ WRONG: Redefining inline
SMOKE_MAX_SPACING_M = 9.1

# ❌ WRONG: Using wrong value
WALL_MIN_DISTANCE_M = 0.10  # Should be 0.1016
```

---

*Auto-generated by `fireai/tools/crossref_indexer.py`*
"""
    
    return md


def main():
    root = Path(__file__).parent.parent.parent
    output_file = root / "fireai" / "CROSSREF_INDEX.md"
    
    constants = list(CANONICAL_SOURCES.keys())
    
    print("🔍 Finding constant usages...")
    usages = find_constant_usages(root, constants)
    
    print(f"📊 Found {sum(len(v) for v in usages.values())} usages across {len(usages)} constants")
    
    print("⚠️  Checking for drift issues...")
    drift = find_inline_definitions(root)
    print(f"   Drift issues: {len(drift)}")
    
    print(f"📝 Generating {output_file}...")
    md = generate_markdown(usages, drift)
    output_file.write_text(md)
    
    print(f"✅ Cross-Reference Index saved to: {output_file}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())