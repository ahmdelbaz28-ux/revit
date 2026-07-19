#!/usr/bin/env python3
"""
Bandit severity gate — parses reports/bandit.json and exits 1 if any HIGH
severity findings exist. Writes reports/bandit_high_summary.txt when HIGH
findings are found (so the CI step can cat the file for visibility).

V293 FIX: This script was extracted from the inline python3 -c "..." in
.github/workflows/ci.yml because the inline version was failing silently
with 2>/dev/null swallowing all errors. Using a separate file makes the
script testable and debuggable.

Exit codes:
  0 = no HIGH findings (gate passes)
  1 = HIGH findings detected (gate fails) — summary file written
  2 = error parsing bandit.json (gate fails — fail-safe)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    bandit_json = Path("reports/bandit.json")
    summary_file = Path("reports/bandit_high_summary.txt")

    if not bandit_json.exists():
        print(f"ERROR: {bandit_json} does not exist", file=sys.stderr)
        return 2

    try:
        with open(bandit_json) as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: failed to parse {bandit_json}: {e}", file=sys.stderr)
        return 2

    results = data.get("results", [])
    high = [r for r in results if r.get("issue_severity") == "HIGH"]

    print(f"BANDIT_TOTAL={len(results)}")
    print(f"BANDIT_HIGH={len(high)}")

    for r in high:
        fname = r.get("filename", "")
        lineno = r.get("line_number", "")
        text = r.get("issue_text", "")
        test = r.get("test_name", "")
        print(f"HIGH::{fname}:{lineno}::{text}::[{test}]")

    if high:
        with open(summary_file, "w") as out:
            out.write(f"Bandit HIGH severity findings ({len(high)} total):\n")
            out.write("=" * 70 + "\n")
            for r in high:
                fname = r.get("filename", "")
                lineno = r.get("line_number", "")
                text = r.get("issue_text", "")
                test = r.get("test_name", "")
                cwe_obj = r.get("issue_cwe")
                cwe_link = cwe_obj.get("link", "") if isinstance(cwe_obj, dict) else ""
                out.write(f"{fname}:{lineno}\n")
                out.write(f"  Issue: {text}\n")
                out.write(f"  Test:  {test}\n")
                out.write(f"  CWE:   {cwe_link}\n")
                out.write("\n")
        print(f"Wrote {summary_file} ({len(high)} HIGH findings)")
        return 1
    else:
        print("No HIGH findings — gate will pass")
        return 0


if __name__ == "__main__":
    sys.exit(main())
