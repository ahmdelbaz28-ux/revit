#!/usr/bin/env python3
"""FireAI — Module Dependency Index Generator

Scans the codebase and generates a dependency graph to identify:
- Module layers and their dependencies
- Circular import risks
- Architecture violations
"""

from __future__ import annotations

# Run: python -m fireai.tools.dependency_indexer
# Output: fireai/DEPENDENCY_INDEX.md
import re
import subprocess
from collections import defaultdict
from pathlib import Path

# Known layer assignments (based on architecture analysis)
LAYER_1_MODULES = {
    "contracts",
    "nfpa72_models",
    "nfpa72_calculations",
    "unit_converter",
}

LAYER_2_MODULES = {
    "nfpa72_coverage",
    "nfpa72_engine",
    "nfpa72_schemas",
    "nfpa72_technology_dispatcher",
    "voltage_drop",
    "sequence_of_operations",
    "light_current",
}

LAYER_3_MODULES = {
    "qomn_kernel",
    "device_placement",
    "density_optimizer",
    "constraint_engine",
    "proof_certificate",
    "battery_aging_derating",
    "circuit_topology",
    "network_topology",
}

LAYER_4_MODULES = {
    "digital_twin",
    "digital_twin_interface",
    "floor_orchestrator",
    "multi_floor_orchestrator",
    "analysis_pipeline",
    "pipeline",
    "building_engine",
}


def get_module_layer(module_name: str) -> int:
    """Get the layer number for a module."""
    if module_name in LAYER_1_MODULES:
        return 1
    if module_name in LAYER_2_MODULES:
        return 2
    if module_name in LAYER_3_MODULES:
        return 3
    if module_name in LAYER_4_MODULES:
        return 4
    return 0  # Unknown layer


def extract_imports(file_path: Path, package_prefix: str) -> list[str]:
    """Extract all imports from a Python file."""
    content = file_path.read_text()
    imports = []

    # Match: from package.module import ...
    pattern = rf'from\s+{package_prefix}\.(\w+)\s+import'
    for match in re.finditer(pattern, content):
        module = match.group(1)
        if module not in imports:
            imports.append(module)

    return imports


def build_dependency_map(root: Path) -> dict:
    """Build a dependency map for all core modules."""
    core_dir = root / "fireai" / "core"
    deps = defaultdict(set)

    for py_file in core_dir.glob("*.py"):
        if py_file.name.startswith("_") or py_file.name.startswith("test_"):
            continue

        module_name = py_file.stem
        imports = extract_imports(py_file, "fireai.core")

        for imp in imports:
            deps[module_name].add(imp)

    return dict(deps)


def detect_circular_imports(deps: dict) -> list[list[str]]:
    """Detect circular import chains (excluding self-loops from lazy imports)."""
    circular = []

    def has_cycle(node: str, visited: set, path: list) -> bool:
        if node in path:
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            # Skip self-loops (module importing itself via lazy import)
            if len(cycle) == 2 and cycle[0] == cycle[1]:
                return False
            # Normalize cycle to avoid duplicates (rotate to smallest element)
            core = cycle[:-1]
            min_idx = core.index(min(core))
            normalized = core[min_idx:] + core[:min_idx] + [core[min_idx]]
            if normalized not in circular:
                circular.append(normalized)
            return True
        if node in visited:
            return False

        visited.add(node)
        path.append(node)

        for dep in deps.get(node, []):
            if dep in deps:  # Only check internal deps
                # Skip self-imports (lazy import pattern)
                if dep == node:
                    continue
                has_cycle(dep, visited, path.copy())

        return False

    for node in deps:
        has_cycle(node, set(), [])

    return circular


def check_layer_violations(deps: dict) -> list[dict]:
    """Check for layer violations (higher layer importing lower layer)."""
    violations = []

    for module, imports in deps.items():
        module_layer = get_module_layer(module)

        for imp in imports:
            imp_layer = get_module_layer(imp)

            # Layer N can only import from Layer N or lower
            if imp_layer > module_layer and imp_layer > 0:
                violations.append({
                    "module": module,
                    "imports": imp,
                    "module_layer": module_layer,
                    "imports_layer": imp_layer,
                    "violation": f"Layer {module_layer} imports Layer {imp_layer}",
                })

    return violations


def generate_markdown(deps: dict, circular: list, violations: list) -> str:
    """Generate Markdown documentation."""
    total_modules = len(deps)
    layer_counts = {
        1: len([m for m in deps if get_module_layer(m) == 1]),
        2: len([m for m in deps if get_module_layer(m) == 2]),
        3: len([m for m in deps if get_module_layer(m) == 3]),
        4: len([m for m in deps if get_module_layer(m) == 4]),
    }

    md = f"""# FireAI — Module Dependency Index

**Generated:** {subprocess.check_output(['date', '+%Y-%m-%d']).decode().strip()}
**Purpose:** Map module dependencies to prevent circular imports

---

## 📊 Summary

| Metric | Count |
|--------|-------|
| Total core modules | {total_modules} |
| Layer 1 (Foundation) | {layer_counts[1]} |
| Layer 2 (Standards) | {layer_counts[2]} |
| Layer 3 (Engineering) | {layer_counts[3]} |
| Layer 4 (Integration) | {layer_counts[4]} |
| Circular imports | {len(circular)} |
| Layer violations | {len(violations)} |

---

## 🏗️ Architecture Layers

```
Layer 4 (Integration):    digital_twin, floor_orchestrator, analysis_pipeline
        │
Layer 3 (Engineering):    qomn_kernel, device_placement, density_optimizer
        │
Layer 2 (Standards):      nfpa72_coverage, nfpa72_engine, voltage_drop
        │
Layer 1 (Foundation):     contracts, nfpa72_models, nfpa72_calculations
```

"""

    if circular:
        md += "\n## 🚨 Circular Import Chains\n\n"
        for i, cycle in enumerate(circular[:10], 1):  # Limit to 10
            md += f"{i}. `{'` → `'.join(cycle)}`\n"
        md += "\n"

    if violations:
        md += "\n## ⚠️ Layer Violations\n\n"
        md += "| Module | Imports | Violation |\n"
        md += "|--------|---------|----------|\n"
        for v in violations[:20]:  # Limit to 20
            md += f"| `{v['module']}` | `{v['imports']}` | {v['violation']} |\n"
        md += "\n"

    md += """
## 📦 Module Dependencies

| Module | Layer | Imports |
|--------|-------|---------|
"""

    for module in sorted(deps.keys()):
        layer = get_module_layer(module)
        imports = ", ".join(sorted(deps[module])) if deps[module] else "None"
        md += f"| `{module}` | {layer} | {imports} |\n"

    md += """
---

## 🚫 Circular Import Prevention Rules

1. **Never** import from `fireai/core/__init__.py` inside core modules
2. **Always** import from specific modules: `from fireai.core.nfpa72_models import ...`
3. **Avoid** importing services in models - use dependency injection
4. **Keep** `contracts.py` free of implementation dependencies

---

*Auto-generated by `fireai/tools/dependency_indexer.py`*
"""

    return md


def main():
    root = Path(__file__).parent.parent.parent
    output_file = root / "fireai" / "DEPENDENCY_INDEX.md"

    print("🔍 Building dependency map...")
    deps = build_dependency_map(root)

    print(f"📊 Found {len(deps)} modules with dependencies")

    print("🔎 Checking for circular imports...")
    circular = detect_circular_imports(deps)
    print(f"   Circular chains: {len(circular)}")

    print("⚠️  Checking layer violations...")
    violations = check_layer_violations(deps)
    print(f"   Violations: {len(violations)}")

    print(f"📝 Generating {output_file}...")
    md = generate_markdown(deps, circular, violations)
    output_file.write_text(md)

    print(f"✅ Dependency Index saved to: {output_file}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
