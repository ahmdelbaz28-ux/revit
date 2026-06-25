"""Static analysis tool — scans ALL .py files for numeric constant mismatches.
Prevents Bug #25-class issues where mw_air or DETECTOR_RADIUS diverge silently.

Run:  python -m fireai.tools.constant_consistency_checker
      python -m fireai.tools.constant_consistency_checker --root /path/to/project

Exit codes:
  0 = PASS (no canonical mismatches, no inconsistent multi-definitions)
  1 = FAIL (canonical mismatches or inconsistent multi-definitions found)

This tool is CI-ready: add to your pipeline as a static analysis gate.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Canonical constants we track explicitly ───────────────────────────────────
# Format: name → (canonical_value, canonical_module_pattern, nfpa_reference)
# Values verified against actual project source code (V30).
CANONICAL_CONSTANTS: Dict[str, Tuple[float, str, str]] = {
    # density_optimizer.py — NFPA 72 detector spacing
    "DETECTOR_RADIUS": (6.37, "density_optimizer", "NFPA 72 §17.7.4.2.3.1 — 0.7S Rule"),
    "MAX_SPACING_M": (9.1, "density_optimizer", "NFPA 72 §17.6.3.1.1"),
    "WALL_MIN_M": (0.1016, "density_optimizer", "NFPA 72 §17.6.3.1.1"),
    "VERIFY_STEP": (0.20, "density_optimizer", "internal — proof resolution"),
    "COARSE_STEP": (1.00, "density_optimizer", "internal — coarse grid step"),
    "PLACEMENT_MARGIN": (0.1414, "density_optimizer", "internal — δ-conservative"),
    # digital_twin.py — duplicate of MAX_SPACING_M
    "NFPA72_MAX_SPACING_M": (9.1, "digital_twin", "NFPA 72 Table 17.6.3.1.1"),
    # models_v21.py — molecular weight of dry air (CRC Handbook, 97th Ed.)
    "_MW_AIR": (28.96, "models_v21", "CRC Handbook — dry air MW"),
    # semi_cfast_engine.py — aligned to 28.96 (CRC Handbook, same as _MW_AIR)
    "AIR_MOLAR_MASS_G_MOL": (28.96, "semi_cfast_engine", "CRC Handbook — dry air MW (aligned with _MW_AIR)"),
    # Gravity
    "GRAVITY": (9.81, "", "SI standard (local approx)"),
    "GRAVITY_M_S2": (9.81, "", "SI standard (local approx)"),
    # Standard conditions
    "STD_TEMP_C": (20.0, "", "NFPA standard conditions"),
    "STD_TEMP_K": (293.15, "", "NFPA standard conditions"),
    # Duct detector spacing
    "_DUCT_DETECTOR_MAX_SPACING_M": (10.0, "nfpa72_calculations", "NFPA 72 §17.7.5.4.2"),
    "NFPA_DUCT_MAX_SPACING_M": (3.05, "duct_detector", "NFPA 72 §17.7.5 — 10ft"),
}

# Float literals that are suspicious raw numbers (should be a named constant)
SUSPICIOUS_LITERALS: Dict[float, str] = {
    6.37: "DETECTOR_RADIUS",
    9.1: "MAX_SPACING_M",
    9.14: "MAX_SPACING_M (feet conversion variant)",
    0.10: "WALL_MIN_M",
    0.1414: "PLACEMENT_MARGIN",
    28.96: "mw_air / MW_AIR / _MW_AIR / AIR_MOLAR_MASS_G_MOL",
    9.81: "GRAVITY",
    4.27: "NFPA72_HEAT_RADIUS_M",
    5.3: "NFPA72_HEAT_RADIUS_25FT_M",
}

# Cross-module consistency groups: names that MUST agree on the same value
# Each group represents the SAME physical constant defined in multiple modules.
CONSISTENCY_GROUPS: Dict[str, List[str]] = {
    "max_spacing": [
        "MAX_SPACING_M",  # density_optimizer
        "NFPA72_MAX_SPACING_M",  # digital_twin
    ],
    "mw_air": [
        "_MW_AIR",  # models_v21 = 28.96
        "AIR_MOLAR_MASS_G_MOL",  # semi_cfast_engine = 28.96 (aligned with _MW_AIR)
    ],
    "gravity": [
        "GRAVITY",  # twin/semi_cfast_engine, twin/fire_physics
        "GRAVITY_M_S2",  # fireai/core/semi_cfast_engine
    ],
}

# Explicit cross-module value checks: physical constants that appear as raw
# literals in dict constructors (e.g., PHYSICAL_CONSTANTS = {"KEY": 28.97}).
# These are NOT captured by ast.Assign because they are dict values, not top-level vars.
# Format: (dict_key, expected_value, canonical_source)
DICT_CONSTANT_CHECKS: List[Tuple[str, float, str]] = [
    ("AIR_MOLAR_MASS_G_MOL", 28.96, "_MW_AIR in models_v21.py (CRC Handbook)"),
    ("GRAVITY_M_S2", 9.81, "SI standard"),
    ("AMBIENT_TEMP_K", 293.15, "NFPA standard conditions"),
]

# Names that are typically try/except fallback patterns (True/False) — NOT real
# constant inconsistencies. Filtered from multi-definition checks.
TRY_EXCEPT_BOOLEAN_NAMES: set = {
    "HAS_PULP",
    "HAS_SHAPELY",
    "HAS_FITZ",
    "HAS_ECDSA",
    "HAS_EZDXF",
    "HAS_FLOOR_ORCHESTRATOR",
    "HAS_DXF_PARSER",
    "PULP_AVAILABLE",
    "EZDXF_AVAILABLE",
    "IFC_AVAILABLE",
    "NX_AVAILABLE",
    "GEOM_AVAILABLE",
    "CRYPTO_AVAILABLE",
    "HAS_SHAPELY_VORONOI",
    "SHAPELY_AVAILABLE",
}

TOLERANCE = 1e-4  # float comparison tolerance


@dataclass
class ConstantOccurrence:
    file: Path
    line: int
    name: str
    value: float
    context: str  # surrounding line text


@dataclass
class SuspiciousLiteral:
    file: Path
    line: int
    value: float
    hint: str
    context: str


@dataclass
class DictConstantOccurrence:
    """A constant defined inside a dict literal (e.g., PHYSICAL_CONSTANTS["KEY"] = 28.97)."""

    file: Path
    line: int
    key: str
    value: float
    context: str


@dataclass
class ConsistencyReport:
    consistent: List[str] = field(default_factory=list)
    inconsistent: List[str] = field(default_factory=list)
    suspicious: List[SuspiciousLiteral] = field(default_factory=list)
    registry: Dict[str, List[ConstantOccurrence]] = field(default_factory=lambda: defaultdict(list))
    cross_module_issues: List[str] = field(default_factory=list)
    dict_constant_issues: List[str] = field(default_factory=list)


class ConstantCollector(ast.NodeVisitor):
    """AST visitor that extracts named constant assignments, dict constants, and float literals."""

    def __init__(self, filepath: Path, source_lines: List[str]) -> None:
        self.filepath = filepath
        self.source_lines = source_lines
        self.assignments: List[ConstantOccurrence] = []
        self.literals: List[SuspiciousLiteral] = []
        self.dict_constants: List[DictConstantOccurrence] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        """Capture: CONSTANT_NAME = <float>"""
        val = self._extract_float(node.value)
        if val is None:
            # Check for dict assignment like PHYSICAL_CONSTANTS = {...}
            self._scan_dict_literal(node)
            self.generic_visit(node)
            return
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                ctx = self._ctx(node.lineno)
                occ = ConstantOccurrence(
                    file=self.filepath,
                    line=node.lineno,
                    name=name,
                    value=val,
                    context=ctx,
                )
                self.assignments.append(occ)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Capture: CONSTANT_NAME: float = <float>"""
        if node.value is None:
            return
        val = self._extract_float(node.value)
        if val is None:
            # Check for dict assignment like PHYSICAL_CONSTANTS: Dict = {...}
            self._scan_dict_literal_ann(node)
            self.generic_visit(node)
            return
        if isinstance(node.target, ast.Name):
            name = node.target.id
            self.assignments.append(
                ConstantOccurrence(
                    file=self.filepath,
                    line=node.lineno,
                    name=name,
                    value=val,
                    context=self._ctx(node.lineno),
                )
            )

    def visit_Constant(self, node: ast.Constant) -> None:
        """Catch raw float literals that match suspicious values."""
        if not isinstance(node.value, float):
            self.generic_visit(node)
            return
        val = node.value
        for known_val, hint in SUSPICIOUS_LITERALS.items():
            if abs(val - known_val) < TOLERANCE:
                self.literals.append(
                    SuspiciousLiteral(
                        file=self.filepath,
                        line=node.lineno,
                        value=val,
                        hint=hint,
                        context=self._ctx(node.lineno),
                    )
                )
                break
        self.generic_visit(node)

    def _scan_dict_literal(self, node: ast.Assign) -> None:
        """Scan dict literal assignments for known constant keys with float values.

        Catches patterns like:
            PHYSICAL_CONSTANTS = {
                "AIR_MOLAR_MASS_G_MOL": 28.97,
                "GRAVITY_M_S2": 9.81,
            }
        """
        if not isinstance(node.value, ast.Dict):
            return
        for key_node, val_node in zip(node.value.keys, node.value.values, strict=False):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            key_str = key_node.value
            # Check if this key matches any DICT_CONSTANT_CHECKS
            val = self._extract_float(val_node)
            if val is not None:
                self.dict_constants.append(
                    DictConstantOccurrence(
                        file=self.filepath,
                        line=key_node.lineno,
                        key=key_str,
                        value=val,
                        context=self._ctx(key_node.lineno),
                    )
                )

    def _scan_dict_literal_ann(self, node: ast.AnnAssign) -> None:
        """Scan annotated dict literal assignments (e.g., PHYSICAL_CONSTANTS: Dict = {...})."""
        if not isinstance(node.value, ast.Dict):
            return
        for key_node, val_node in zip(node.value.keys, node.value.values, strict=False):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            key_str = key_node.value
            val = self._extract_float(val_node)
            if val is not None:
                self.dict_constants.append(
                    DictConstantOccurrence(
                        file=self.filepath,
                        line=key_node.lineno,
                        key=key_str,
                        value=val,
                        context=self._ctx(key_node.lineno),
                    )
                )

    @staticmethod
    def _extract_float(node: ast.expr) -> Optional[float]:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = ConstantCollector._extract_float(node.operand)
            if inner is not None:
                return -inner
        # Handle expressions like 0.7 * 9.1 if both operands are constant
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            left = ConstantCollector._extract_float(node.left)
            right = ConstantCollector._extract_float(node.right)
            if left is not None and right is not None:
                return left * right
        return None

    def _ctx(self, lineno: int) -> str:
        idx = lineno - 1
        if 0 <= idx < len(self.source_lines):
            return self.source_lines[idx].strip()[:120]
        return ""


def _scan_file(
    filepath: Path,
) -> Tuple[List[ConstantOccurrence], List[SuspiciousLiteral], List[DictConstantOccurrence]]:
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
        lines = source.splitlines()
        col = ConstantCollector(filepath, lines)
        col.visit(tree)
        return col.assignments, col.literals, col.dict_constants
    except SyntaxError as exc:
        print(f"  [WARN] Syntax error in {filepath}: {exc}", file=sys.stderr)
        return [], [], []
    except Exception as exc:
        print(f"  [WARN] Cannot parse {filepath}: {exc}", file=sys.stderr)
        return [], [], []


def _find_root(start: Path) -> Path:
    """Walk up until we find a directory containing fireai/ or pyproject.toml."""
    cwd = start.resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / "fireai").is_dir() or (parent / "pyproject.toml").exists():
            return parent
    return cwd


def _gather_py_files(root: Path) -> List[Path]:
    skip_dirs = {".git", "__pycache__", ".tox", ".venv", "venv", "build", "dist", "node_modules"}
    files: List[Path] = []
    for p in root.rglob("*.py"):
        if any(part in skip_dirs for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def _build_registry(
    all_occurrences: List[ConstantOccurrence],
) -> Dict[str, List[ConstantOccurrence]]:
    reg: Dict[str, List[ConstantOccurrence]] = defaultdict(list)
    for occ in all_occurrences:
        reg[occ.name].append(occ)
    return reg


def _check_consistency(
    registry: Dict[str, List[ConstantOccurrence]],
) -> Tuple[List[str], List[str]]:
    """Check for multi-definition inconsistencies, filtering out try/except booleans."""
    consistent: List[str] = []
    inconsistent: List[str] = []

    for name, occs in sorted(registry.items()):
        if len(occs) < 2:
            continue

        # Filter: skip try/except boolean patterns (HAS_X = True / HAS_X = False)
        if name in TRY_EXCEPT_BOOLEAN_NAMES:
            continue

        # Filter: if all values are only 0.0 and 1.0 (boolean True/False pattern)
        values = [o.value for o in occs]
        if all(v in (0.0, 1.0) for v in values):
            continue

        if all(abs(v - values[0]) < TOLERANCE for v in values):
            consistent.append(name)
        else:
            inconsistent.append(name)

    return consistent, inconsistent


def _check_cross_module_consistency(
    registry: Dict[str, List[ConstantOccurrence]],
) -> List[str]:
    """Check that names in the same CONSISTENCY_GROUP agree on value."""
    issues: List[str] = []
    for group_name, names in CONSISTENCY_GROUPS.items():
        values: Dict[float, List[str]] = defaultdict(list)
        for name in names:
            if name in registry:
                for occ in registry[name]:
                    values[round(occ.value, 4)].append(f"{occ.file.name}:{occ.line} ({name}={occ.value})")
        if len(values) > 1:
            details = " | ".join(f"{v}: {locs}" for v, locs in sorted(values.items()))
            issues.append(
                f"CROSS-MODULE INCONSISTENCY [{group_name}]: same physical constant has different values — {details}"
            )
    return issues


def _check_dict_constants(
    dict_constants: List[DictConstantOccurrence],
) -> List[str]:
    """Check dict-literal constants against their expected canonical values.

    This catches constants defined inside PHYSICAL_CONSTANTS-style dicts
    that the AST visitor's visit_Assign would miss (since the dict key is
    a string, not a variable name).
    """
    issues: List[str] = []
    for dc in dict_constants:
        for key, expected_val, source in DICT_CONSTANT_CHECKS:
            if dc.key == key and abs(dc.value - expected_val) > TOLERANCE:
                issues.append(
                    f"DICT CONSTANT MISMATCH: {dc.key} = {dc.value} "
                    f"(expected {expected_val} per {source}) "
                    f"in {dc.file.name}:{dc.line}"
                )
    return issues


def _filter_suspicious(
    all_literals: List[SuspiciousLiteral],
    all_occurrences: List[ConstantOccurrence],
) -> List[SuspiciousLiteral]:
    """Remove false positives: a literal on the SAME line as its named constant
    assignment is not suspicious (it IS the definition).
    """
    definition_lines: set = set()
    for occ in all_occurrences:
        if occ.name in CANONICAL_CONSTANTS:
            definition_lines.add((str(occ.file), occ.line))

    return [lit for lit in all_literals if (str(lit.file), lit.line) not in definition_lines]


def _canonical_mismatch_check(
    registry: Dict[str, List[ConstantOccurrence]],
) -> List[str]:
    """Check: known canonical constants against their expected values.
    Returns list of CRITICAL mismatch descriptions.
    """
    critical: List[str] = []
    for name, (expected_val, _, nfpa_ref) in CANONICAL_CONSTANTS.items():
        if name not in registry:
            continue
        for occ in registry[name]:
            if abs(occ.value - expected_val) > TOLERANCE:
                critical.append(
                    f"CANONICAL MISMATCH: {name} = {occ.value} "
                    f"(expected {expected_val}) "
                    f"in {occ.file.name}:{occ.line} [{nfpa_ref}]"
                )
    return critical


def _print_report(report: ConsistencyReport, root: Path) -> int:
    """Print report and return exit code (0=clean, 1=issues found)."""
    sep = "=" * 78
    print(sep)
    print("FIREAI V30 — Constant Consistency Checker")
    print(f"Root: {root}")
    print(sep)

    # Canonical mismatches (highest severity)
    canonical_issues = _canonical_mismatch_check(report.registry)
    if canonical_issues:
        print(f"\n[CRITICAL] Canonical constant mismatches ({len(canonical_issues)}):")
        for msg in canonical_issues:
            print(f"  X {msg}")
    else:
        print("\n[PASS] No canonical constant mismatches found.")

    # Dict constant mismatches (e.g., PHYSICAL_CONSTANTS dict values)
    if report.dict_constant_issues:
        print(f"\n[CRITICAL] Dict-literal constant mismatches ({len(report.dict_constant_issues)}):")
        for msg in report.dict_constant_issues:
            print(f"  X {msg}")
    else:
        print("\n[PASS] No dict-literal constant mismatches found.")

    # Cross-module consistency group issues
    if report.cross_module_issues:
        print(f"\n[CRITICAL] Cross-module consistency group violations ({len(report.cross_module_issues)}):")
        for msg in report.cross_module_issues:
            print(f"  X {msg}")
    else:
        print("\n[PASS] All cross-module consistency groups are aligned.")

    # Inconsistent multi-definitions (try/except boolean patterns filtered out)
    if report.inconsistent:
        print(f"\n[CRITICAL] Inconsistent multi-definitions ({len(report.inconsistent)}):")
        for name in report.inconsistent:
            occs = report.registry[name]
            print(f"\n  {name}:")
            for occ in occs:
                rel = occ.file.relative_to(root) if root in occ.file.parents else occ.file
                print(f"    {rel}:{occ.line}  = {occ.value}  # {occ.context}")
    else:
        print("\n[PASS] No inconsistent multi-definitions found.")

    # Suspicious raw literals
    if report.suspicious:
        seen: set = set()
        unique_sus: List[SuspiciousLiteral] = []
        for lit in report.suspicious:
            key = (str(lit.file), lit.line)
            if key not in seen:
                seen.add(key)
                unique_sus.append(lit)
        print(f"\n[WARN] Suspicious raw literals ({len(unique_sus)}):")
        print("   (These should use a named constant instead of a raw number)")
        for lit in sorted(unique_sus, key=lambda l: (str(l.file), l.line)):
            rel = lit.file.relative_to(root) if root in lit.file.parents else lit.file
            print(f"  {rel}:{lit.line}  value={lit.value}  should be {lit.hint}")
            print(f"    context: {lit.context}")
    else:
        print("\n[PASS] No suspicious raw literals found.")

    # Consistent
    if report.consistent:
        print(f"\n[PASS] Consistent constants ({len(report.consistent)}): {', '.join(report.consistent)}")

    print(f"\n{sep}")
    has_issues = bool(
        canonical_issues or report.inconsistent or report.cross_module_issues or report.dict_constant_issues
    )
    status = "FAIL" if has_issues else ("WARN" if report.suspicious else "PASS")
    print(f"Status: {status}")
    print(sep)
    return 1 if has_issues else 0


def main(root: Optional[Path] = None) -> int:
    if root is None:
        root = _find_root(Path(__file__))

    print(f"Scanning {root} ...")
    py_files = _gather_py_files(root)
    print(f"Found {len(py_files)} Python files.")

    all_occs: List[ConstantOccurrence] = []
    all_literals: List[SuspiciousLiteral] = []
    all_dict_consts: List[DictConstantOccurrence] = []

    for f in py_files:
        occs, lits, dcs = _scan_file(f)
        all_occs.extend(occs)
        all_literals.extend(lits)
        all_dict_consts.extend(dcs)

    registry = _build_registry(all_occs)
    consistent, inconsistent = _check_consistency(registry)
    suspicious = _filter_suspicious(all_literals, all_occs)
    cross_module = _check_cross_module_consistency(registry)
    dict_issues = _check_dict_constants(all_dict_consts)

    report = ConsistencyReport(
        consistent=consistent,
        inconsistent=inconsistent,
        suspicious=suspicious,
        registry=registry,
        cross_module_issues=cross_module,
        dict_constant_issues=dict_issues,
    )
    return _print_report(report, root)


if __name__ == "__main__":
    sys.exit(main())
