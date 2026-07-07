#!/usr/bin/env python3
# NOSONAR
"""
ETAP Expert Skill — Stress Test Runner (Orchestrator).
=======================================================
Runs all 5 gates of verification per FireAI agent.md VERIFICATION GATES:

    [Gate 1] Static Validation      — test_skill_structure.py
    [Gate 2] Runtime Validation     — test_skill_loader.py
    [Gate 3] Behavioral Validation  — test_workflow_routing.py
    [Gate 4] Regression Validation  — test_internal_simulations.py
    [Gate 5] Adversarial Audit      — test_property_based.py

Usage:
    python skills/etap-expert/scripts/stress_test_runner.py
    python skills/etap-expert/scripts/stress_test_runner.py --gate 4
    python skills/etap-expert/scripts/stress_test_runner.py --verbose

Exit code:
    0 = all gates passed
    1 = one or more gates failed

Author: FireAI Project
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).parent.parent
PROJECT_ROOT = SKILL_ROOT.parent.parent  # /home/z/my-project/revit/
TESTS_DIR = SKILL_ROOT / "tests"


# ═══════════════════════════════════════════════════════════════════════════
# GATE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class GateResult:
    """Result of running one gate."""

    gate_number: int
    gate_name: str
    test_file: str
    passed: bool
    duration_s: float
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    errors: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


GATES = [
    (1, "Static Validation", "test_skill_structure.py"),
    (2, "Runtime Validation", "test_skill_loader.py"),
    (3, "Behavioral Validation", "test_workflow_routing.py"),
    (4, "Regression Validation", "test_internal_simulations.py"),
    (5, "Adversarial Audit (Property-Based)", "test_property_based.py"),
]


# RUNNER
# ═══════════════════════════════════════════════════════════════════════════


def run_gate(gate_num: int, gate_name: str, test_file: str, verbose: bool = False) -> GateResult:  # NOSONAR - python:S3776
    """Run a single test gate using pytest."""
    test_path = TESTS_DIR / test_file
    if not test_path.exists():
        return GateResult(
            gate_number=gate_num,
            gate_name=gate_name,
            test_file=test_file,
            passed=False,
            duration_s=0.0,
            errors=[f"Test file not found: {test_path}"],
        )

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_path),
        "--tb=short" if verbose else "--tb=line",
        "--json-report",
        "--json-report-file=-",  # stdout
        "-q",
    ]

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 min max per gate (TOOL TIMEOUT safety)
            cwd=str(PROJECT_ROOT),
        )
        duration = time.perf_counter() - start
    except subprocess.TimeoutExpired:
        return GateResult(
            gate_number=gate_num,
            gate_name=gate_name,
            test_file=test_file,
            passed=False,
            duration_s=180.0,
            errors=["Test gate timed out after 180s"],
        )

    # Parse pytest output for pass/fail counts
    output = proc.stdout + proc.stderr
    tests_run = 0
    tests_passed = 0
    tests_failed = 0
    errors = []
    failures = []

    # Try to parse JSON report (embedded in output)
    try:
        # pytest-json-report outputs JSON to stdout; find the JSON object
        json_match = output.rfind("\n{")
        if json_match >= 0:
            json_str = output[json_match + 1 :]
            data = json.loads(json_str)
            tests_run = data.get("summary", {}).get("total", 0)
            tests_passed = data.get("summary", {}).get("passed", 0)
            tests_failed = data.get("summary", {}).get("failed", 0)
            for test in data.get("tests", []):
                if test.get("outcome") == "failed":
                    failures.append(f"{test.get('nodeid')}: {test.get('call', {}).get('longrepr', '')[:200]}")
    except (json.JSONDecodeError, ValueError):  # NOSONAR - python:S5713
        # Fallback: parse plain text
        if "passed" in output:
            import re

            m = re.search(r"(\d+) passed", output)  # NOSONAR - python:S8786
            if m:
                tests_passed = int(m.group(1))
            m = re.search(r"(\d+) failed", output)  # NOSONAR - python:S8786
            if m:
                tests_failed = int(m.group(1))
            tests_run = tests_passed + tests_failed

    # Capture error lines if any
    if proc.returncode != 0:
        for line in output.split("\n"):
            if "ERROR" in line or "FAILED" in line:
                errors.append(line.strip()[:200])

    return GateResult(
        gate_number=gate_num,
        gate_name=gate_name,
        test_file=test_file,
        passed=(proc.returncode == 0),
        duration_s=duration,
        tests_run=tests_run,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        errors=errors[:5],  # cap
        failures=failures[:5],
    )


def run_all_gates(verbose: bool = False, only_gate: int | None = None) -> list[GateResult]:  # NOSONAR - python:S3776
    """Run all (or one) gate(s) and return results."""
    results = []
    for gate_num, gate_name, test_file in GATES:
        if only_gate is not None and gate_num != only_gate:
            continue
        print(f"\n{'═' * 70}")
        print(f"  GATE {gate_num}: {gate_name}")
        print(f"  Test file: {test_file}")
        print(f"{'═' * 70}")

        result = run_gate(gate_num, gate_name, test_file, verbose=verbose)
        results.append(result)

        status = "✅ PASSED" if result.passed else "❌ FAILED"
        print(f"\n  Status: {status}")
        print(f"  Duration: {result.duration_s:.2f}s")
        print(f"  Tests: {result.tests_passed}/{result.tests_run} passed, {result.tests_failed} failed")

        if result.failures and verbose:
            print("\n  Failures:")
            for f in result.failures:
                print(f"    - {f[:150]}")

        if result.errors and verbose:
            print("\n  Errors:")
            for e in result.errors:
                print(f"    - {e[:150]}")

    return results


def print_summary(results: list[GateResult]) -> dict[str, Any]:
    """Print final summary and return report dict."""
    print(f"\n{'═' * 70}")
    print("  FINAL SUMMARY — ETAP EXPERT SKILL STRESS TEST")
    print(f"{'═' * 70}")

    total_passed = sum(1 for r in results if r.passed)
    total_gates = len(results)
    total_tests = sum(r.tests_run for r in results)
    total_tests_passed = sum(r.tests_passed for r in results)
    total_tests_failed = sum(r.tests_failed for r in results)
    total_duration = sum(r.duration_s for r in results)

    print(f"\n  Gates: {total_passed}/{total_gates} passed")
    print(f"  Tests: {total_tests_passed}/{total_tests} passed, {total_tests_failed} failed")
    print(f"  Total duration: {total_duration:.2f}s")

    print("\n  Per-gate breakdown:")
    print(f"  {'Gate':<6} {'Name':<40} {'Status':<10} {'Tests':<15} {'Duration':<10}")
    print(f"  {'─' * 6} {'─' * 40} {'─' * 10} {'─' * 15} {'─' * 10}")
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        tests_str = f"{r.tests_passed}/{r.tests_run}"
        print(f"  {r.gate_number:<6} {r.gate_name:<40} {status:<10} {tests_str:<15} {r.duration_s:.2f}s")

    overall_pass = total_passed == total_gates and total_tests_failed == 0
    print(f"\n  Overall: {'✅ ALL GATES PASSED' if overall_pass else '❌ SOME GATES FAILED'}")

    return {
        "overall_pass": overall_pass,
        "gates_passed": total_passed,
        "gates_total": total_gates,
        "tests_passed": total_tests_passed,
        "tests_total": total_tests,
        "tests_failed": total_tests_failed,
        "duration_s": total_duration,
        "gate_results": [asdict(r) for r in results],
    }


# MAIN
# ═══════════════════════════════════════════════════════════════════════════


def main() -> int:
    parser = argparse.ArgumentParser(description="ETAP Expert Skill Stress Test Runner")
    parser.add_argument("--gate", type=int, choices=[1, 2, 3, 4, 5],
                        help="Run only specified gate (1-5)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output (show failure details)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON report (in addition to text)")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Write JSON report to file")
    args = parser.parse_args()

    results = run_all_gates(verbose=args.verbose, only_gate=args.gate)
    report = print_summary(results)

    if args.json or args.output:
        json_str = json.dumps(report, indent=2, default=str)
        if args.json:
            print(f"\n{'─' * 70}\nJSON REPORT:\n{'─' * 70}")
            print(json_str)
        if args.output:
            args.output.write_text(json_str, encoding="utf-8")
            print(f"\nJSON report written to: {args.output}")

    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
