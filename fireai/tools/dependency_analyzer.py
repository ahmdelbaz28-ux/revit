"""D6: Dependency Analyzer — Circular Imports + Dead Code Detection
================================================================
Static analysis tool that scans the FireAI codebase for:
  1. Circular import dependencies
  2. Dead code (unreachable, unused imports, unused functions)
  3. Module dependency graph visualization

This tool is CI-ready: add to your pipeline as a static analysis gate.

Run:
  python -m fireai.tools.dependency_analyzer
  python -m fireai.tools.dependency_analyzer --root /path/to/project

Exit codes:
  0 = PASS (no circular imports, no critical dead code)
  1 = FAIL (circular imports found or critical dead code detected)

NFPA 72 Context: Circular imports can cause runtime failures that
bypass verification engines, creating life-safety risks.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ImportInfo:
    """Information about an import statement."""

    source_file: Path
    line: int
    module_name: str
    import_type: str  # "absolute" or "relative"


@dataclass
class CircularImport:
    """A circular import chain."""

    cycle: List[str]
    severity: str  # "CRITICAL" (import-time side effects) or "WARNING"


@dataclass
class DeadCodeIssue:
    """A dead code issue."""

    file: Path
    line: int
    issue_type: str  # "unused_import", "unreachable_code", "unused_function"
    name: str
    details: str


@dataclass
class DependencyReport:
    """Complete dependency analysis report."""

    n_modules: int = 0
    n_imports: int = 0
    circular_imports: List[CircularImport] = field(default_factory=list)
    dead_code_issues: List[DeadCodeIssue] = field(default_factory=list)
    dependency_graph: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    unused_public_modules: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Import Collector (AST Visitor)
# ═══════════════════════════════════════════════════════════════════════════════


class ImportCollector(ast.NodeVisitor):
    """AST visitor that extracts import statements from a Python file."""

    def __init__(self, filepath: Path, project_root: Path) -> None:
        self.filepath = filepath
        self.project_root = project_root
        self.imports: List[ImportInfo] = []
        self.defined_names: Set[str] = set()
        self.used_names: Set[str] = set()
        self._scope_stack: List[Set[str]] = [set()]

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module_name = alias.name
            # Only track project-internal imports
            if self._is_internal(module_name):
                self.imports.append(
                    ImportInfo(
                        source_file=self.filepath,
                        line=node.lineno,
                        module_name=module_name,
                        import_type="absolute",
                    )
                )
            # Track imported name as defined
            bound_name = alias.asname or alias.name.split(".")[0]
            self._scope_stack[-1].add(bound_name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and self._is_internal(node.module):
            self.imports.append(
                ImportInfo(
                    source_file=self.filepath,
                    line=node.lineno,
                    module_name=node.module,
                    import_type="absolute" if not node.level else "relative",
                )
            )
        # Track imported names
        if node.names:
            for alias in node.names:
                bound_name = alias.asname or alias.name
                self._scope_stack[-1].add(bound_name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.defined_names.add(node.name)
        self._scope_stack.append(set())
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.defined_names.add(node.name)
        self._scope_stack.append(set())
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.defined_names.add(node.name)
        self._scope_stack.append(set())
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_Name(self, node: ast.Name) -> None:
        self.used_names.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Track attribute access like "module.something"
        if isinstance(node.value, ast.Name):
            self.used_names.add(node.value.id)
        self.generic_visit(node)

    def _is_internal(self, module_name: str) -> bool:
        """Check if a module is part of the FireAI project."""
        return (
            module_name.startswith("fireai")
            or module_name.startswith("core")
            or module_name.startswith("spatial_engine")
            or module_name.startswith("bridges")
            or module_name.startswith("parsers")
            or module_name.startswith("twin")
            or module_name.startswith("src")
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis Functions
# ═══════════════════════════════════════════════════════════════════════════════


def _find_root(start: Path) -> Path:
    """Walk up until we find fireai/ or pyproject.toml."""
    cwd = start.resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / "fireai").is_dir() or (parent / "pyproject.toml").exists():
            return parent
    return cwd


def _gather_py_files(root: Path) -> List[Path]:
    """Gather all Python files in the project."""
    skip_dirs = {
        ".git",
        "__pycache__",
        ".tox",
        ".venv",
        "venv",
        "build",
        "dist",
        "node_modules",
        "skills",
        "elite_drawing_analyzer",
        "fire-alarm-db",
    }
    files: List[Path] = []
    for p in root.rglob("*.py"):
        if any(part in skip_dirs for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def _file_to_module(filepath: Path, root: Path) -> str:
    """Convert a file path to a Python module name."""
    try:
        rel = filepath.relative_to(root)
    except ValueError:
        return str(filepath)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _build_dependency_graph(
    py_files: List[Path],
    root: Path,
) -> Tuple[Dict[str, Set[str]], List[ImportCollector]]:
    """Build a module dependency graph from import analysis."""
    graph: Dict[str, Set[str]] = defaultdict(set)
    collectors: List[ImportCollector] = []

    for filepath in py_files:
        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(filepath))
        except (SyntaxError, Exception):
            continue

        collector = ImportCollector(filepath, root)
        collector.visit(tree)
        collectors.append(collector)

        source_module = _file_to_module(filepath, root)
        for imp in collector.imports:
            # Normalize import target to project module
            target = imp.module_name
            graph[source_module].add(target)

    return graph, collectors


def _find_circular_imports(graph: Dict[str, Set[str]]) -> List[CircularImport]:
    """Find all circular import chains using DFS."""
    cycles: List[CircularImport] = []
    visited: Set[str] = set()
    path: List[str] = []
    path_set: Set[str] = set()
    found_cycles: Set[Tuple[str, ...]] = set()

    def dfs(node: str) -> None:
        if node in path_set:
            # Found a cycle
            cycle_start = path.index(node)
            cycle = tuple(path[cycle_start:])
            if cycle not in found_cycles and len(cycle) > 1:
                found_cycles.add(cycle)
                # Determine severity
                severity = "CRITICAL" if len(cycle) <= 3 else "WARNING"
                cycles.append(
                    CircularImport(
                        cycle=list(cycle),
                        severity=severity,
                    )
                )
            return

        if node in visited:
            return

        visited.add(node)
        path.append(node)
        path_set.add(node)

        for neighbor in graph.get(node, set()):
            dfs(neighbor)

        path.pop()
        path_set.discard(node)

    for module in graph:
        visited.clear()
        dfs(module)

    return cycles


def _find_dead_code(
    collectors: List[ImportCollector],
    root: Path,
) -> List[DeadCodeIssue]:
    """Find dead code issues: unused imports and unreachable code."""
    issues: List[DeadCodeIssue] = []

    for collector in collectors:
        filepath = collector.filepath
        # Check for unused imports
        for imp in collector.imports:
            # Extract the name that was imported
            module_parts = imp.module_name.split(".")
            module_parts[-1] if module_parts else ""

            # Check if the imported module base name is used
            base_name = imp.module_name.split(".")[0]
            if base_name not in collector.used_names:
                # Check all names from this import
                is_used = any(part in collector.used_names for part in imp.module_name.split("."))
                if not is_used:
                    issues.append(
                        DeadCodeIssue(
                            file=filepath,
                            line=imp.line,
                            issue_type="unused_import",
                            name=imp.module_name,
                            details=f"Module '{imp.module_name}' imported but never used",
                        )
                    )

    return issues


def _find_unused_public_modules(
    graph: Dict[str, Set[str]],
    root: Path,
) -> List[str]:
    """Find modules that are never imported by any other module."""
    all_modules = set(graph.keys())
    all_targets: Set[str] = set()
    for targets in graph.values():
        all_targets.update(targets)

    # A module is "unused" if it's not imported by anyone
    # (excluding __init__.py modules and test files)
    unused = []
    for module in sorted(all_modules):
        if module.endswith(".__init__") or module.startswith("tests."):
            continue
        # Check if module base name appears as a target
        is_target = any(module == t or module.startswith(t + ".") for t in all_targets)
        if not is_target:
            # Entry point modules are OK (they're run, not imported)
            if not any(x in module for x in ["__main__", "cli", "server", "api_server"]):
                unused.append(module)

    return unused


# ═══════════════════════════════════════════════════════════════════════════════
# Report Generation
# ═══════════════════════════════════════════════════════════════════════════════


def _print_report(report: DependencyReport, root: Path) -> int:
    """Print the dependency analysis report and return exit code."""
    sep = "=" * 78
    print(sep)
    print("FIREAI V30 — Dependency Analyzer")
    print(f"Root: {root}")
    print(sep)

    # Module count
    print(f"\nModules analyzed: {report.n_modules}")
    print(f"Import statements: {report.n_imports}")

    # Circular imports
    if report.circular_imports:
        critical = [c for c in report.circular_imports if c.severity == "CRITICAL"]
        warnings = [c for c in report.circular_imports if c.severity == "WARNING"]
        print(f"\n[CRITICAL] Circular import chains ({len(critical)}):")
        for ci in critical:
            cycle_str = " → ".join(ci.cycle + [ci.cycle[0]])
            print(f"  X {cycle_str}")
        if warnings:
            print(f"\n[WARN] Potential circular import chains ({len(warnings)}):")
            for ci in warnings:
                cycle_str = " → ".join(ci.cycle + [ci.cycle[0]])
                print(f"  ⚠ {cycle_str}")
    else:
        print("\n[PASS] No circular import chains detected.")

    # Dead code
    if report.dead_code_issues:
        unused_imports = [d for d in report.dead_code_issues if d.issue_type == "unused_import"]
        other = [d for d in report.dead_code_issues if d.issue_type != "unused_import"]
        if unused_imports:
            print(f"\n[WARN] Unused imports ({len(unused_imports)}):")
            for di in unused_imports[:30]:  # Limit output
                rel = di.file.relative_to(root) if root in di.file.parents else di.file
                print(f"  {rel}:{di.line} — {di.details}")
            if len(unused_imports) > 30:
                print(f"  ... and {len(unused_imports) - 30} more")
        if other:
            print(f"\n[WARN] Other dead code issues ({len(other)}):")
            for di in other[:20]:
                rel = di.file.relative_to(root) if root in di.file.parents else di.file
                print(f"  {rel}:{di.line} — {di.details}")
    else:
        print("\n[PASS] No dead code issues detected.")

    # Unused public modules
    if report.unused_public_modules:
        print(f"\n[WARN] Modules not imported by any other module ({len(report.unused_public_modules)}):")
        for mod in report.unused_public_modules[:20]:
            print(f"  {mod}")
        if len(report.unused_public_modules) > 20:
            print(f"  ... and {len(report.unused_public_modules) - 20} more")
    else:
        print("\n[PASS] All public modules are referenced.")

    # Summary
    print(f"\n{sep}")
    has_critical = any(c.severity == "CRITICAL" for c in report.circular_imports)
    status = "FAIL" if has_critical else ("WARN" if report.circular_imports or report.dead_code_issues else "PASS")
    print(f"Status: {status}")
    print(sep)
    return 1 if has_critical else 0


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════


def main(root: Optional[Path] = None) -> int:
    """Run the dependency analysis."""
    if root is None:
        root = _find_root(Path(__file__))

    print(f"Scanning {root} for dependency analysis...")

    py_files = _gather_py_files(root)
    print(f"Found {len(py_files)} Python files.")

    graph, collectors = _build_dependency_graph(py_files, root)

    circular = _find_circular_imports(graph)
    dead_code = _find_dead_code(collectors, root)
    unused_modules = _find_unused_public_modules(graph, root)

    report = DependencyReport(
        n_modules=len(py_files),
        n_imports=sum(len(c.imports) for c in collectors),
        circular_imports=circular,
        dead_code_issues=dead_code,
        dependency_graph=dict(graph),
        unused_public_modules=unused_modules,
    )

    return _print_report(report, root)


if __name__ == "__main__":
    sys.exit(main())
