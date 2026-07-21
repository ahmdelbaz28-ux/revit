#!/usr/bin/env python3
"""
MyPy regression gate — runs mypy and fails if the error count exceeds
a configurable baseline. This allows pre-existing type errors to coexist
with CI while preventing new regressions from slipping in.

Usage:
    python scripts/mypy_regression_gate.py [--baseline N] [--target PATHS...]

The script runs mypy with the same flags as the CI step, counts errors,
and exits:
  0 = error count <= baseline (gate passes)
  1 = error count > baseline (regression detected)
  2 = script error (mypy not found, etc.)

To update the baseline after fixing a batch of type errors:
  1. Run: python scripts/mypy_regression_gate.py --baseline 0
  2. Note the error count in the output
  3. Update --baseline in ci.yml to the new count
"""
from __future__ import annotations

import subprocess
import sys
import re


def main() -> int:
    # Parse simple args
    baseline = 434  # Current baseline (V140): 434 pre-existing errors
    targets = ["backend/", "fireai/", "core/"]
    mypy_args = [
        "--ignore-missing-imports",
        "--no-strict-optional",
        "--exclude", r".*test.*",
        "--python-version", "3.12",
    ]

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--baseline" and i + 1 < len(sys.argv):
            baseline = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--target":
            targets = [sys.argv[i + 1]]
            i += 2
        else:
            i += 1

    cmd = ["mypy"] + targets + mypy_args
    print(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute timeout
        )
    except FileNotFoundError:
        print("ERROR: mypy not found. Install with: pip install mypy", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("ERROR: mypy timed out after 300 seconds", file=sys.stderr)
        return 2

    # Count errors from mypy output
    # mypy outputs lines like "file.py:42: error: message [error-code]"
    error_pattern = re.compile(r":\d+: error:")
    error_count = sum(
        1 for line in result.stdout.splitlines() if error_pattern.search(line)
    )

    # Also check the summary line mypy prints
    summary_pattern = re.compile(r"Found (\d+) error")
    for line in result.stdout.splitlines():
        m = summary_pattern.search(line)
        if m:
            error_count = int(m.group(1))
            break

    print(f"MYPY_ERROR_COUNT={error_count}")
    print(f"MYPY_BASELINE={baseline}")
    print(f"MYPY_DELTA={error_count - baseline:+d}")

    if error_count > baseline:
        print(f"")
        print(f"FAIL: mypy error count ({error_count}) exceeds baseline ({baseline})")
        print(f"  New errors introduced: {error_count - baseline}")
        print(f"  Fix the new errors or update the baseline in ci.yml")
        # Print the last 20 errors for visibility
        error_lines = [
            line for line in result.stdout.splitlines() if error_pattern.search(line)
        ]
        if error_lines:
            print(f"\nLast {min(20, len(error_lines))} errors:")
            for line in error_lines[-20:]:
                print(f"  {line}")
        return 1
    elif error_count < baseline:
        print(f"")
        print(f"INFO: mypy error count ({error_count}) is BELOW baseline ({baseline})")
        print(f"  Consider updating --baseline to {error_count} in ci.yml")
        print(f"  This is not a failure — just a suggestion to tighten the gate")
        return 0
    else:
        print(f"")
        print(f"PASS: mypy error count matches baseline ({baseline})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
