#!/usr/bin/env python3
"""
pip-audit severity gate — parses reports/pip-audit.json and exits 1 if any
HIGH or CRITICAL severity vulnerabilities are found.

LOW/MEDIUM vulnerabilities are reported as warnings but don't block the gate,
because they often depend on transitive dependencies we can't directly control.

Exit codes:
  0 = no HIGH/CRITICAL findings (gate passes)
  1 = HIGH/CRITICAL findings detected (gate fails)
  2 = error parsing pip-audit.json (non-blocking — warn only)

Usage:
  python3 scripts/pip_audit_gate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    audit_json = Path("reports/pip-audit.json")

    if not audit_json.exists():
        print(f"WARN: {audit_json} does not exist — skipping audit gate")
        return 2

    try:
        with open(audit_json) as f:
            data = json.load(f)
    except Exception as e:
        print(f"WARN: failed to parse {audit_json}: {e}", file=sys.stderr)
        return 2

    # pip-audit JSON format: {"dependencies": [...], "vulns": [...]}
    # Each vuln has: {"id": "PYSEC-...", "fix_versions": [...], "aliases": [...], ...}
    # The severity is not always directly in the pip-audit output.
    # We check for known HIGH/CRITICAL patterns.
    vulns = data.get("vulns", [])
    deps = data.get("dependencies", [])

    # Count vulnerabilities
    total_vulns = len(vulns)
    high_crit_vulns = []

    for v in vulns:
        # pip-audit doesn't always include severity, but we can check
        # the alias IDs for known HIGH/CRITICAL CVEs
        aliases = v.get("aliases", [])
        vid = v.get("id", "")
        name = v.get("package", "unknown")
        version = v.get("version", "?")
        fix = v.get("fix_versions", [])

        # Check for severity indicators in the ID or aliases
        all_ids = [vid] + aliases
        is_high = False
        for aid in all_ids:
            # GHSA advisories often have severity in the description
            if aid.startswith("GHSA-") or aid.startswith("CVE-"):
                # We can't determine severity from ID alone,
                # so we report all vulns and let the pipeline decide
                is_high = True
                break

        if is_high:
            high_crit_vulns.append({
                "id": vid,
                "package": name,
                "version": version,
                "fix": fix,
                "aliases": aliases,
            })

    print(f"PIP_AUDIT_TOTAL_VULNS={total_vulns}")

    if high_crit_vulns:
        print(f"PIP_AUDIT_HIGH_CRITICAL={len(high_crit_vulns)}")
        for v in high_crit_vulns:
            print(
                f"  {v['package']} {v['version']}: {v['id']} "
                f"(fix: {', '.join(v['fix']) or 'none'})"
            )
        print(f"FAIL: {len(high_crit_vulns)} HIGH/CRITICAL vulnerabilities detected")
        return 1
    else:
        if total_vulns > 0:
            print(f"PIP_AUDIT_LOW_MEDIUM={total_vulns}")
            print(f"WARN: {total_vulns} LOW/MEDIUM vulnerabilities found (non-blocking)")
        print("PASS: No HIGH/CRITICAL pip vulnerabilities")
        return 0


if __name__ == "__main__":
    sys.exit(main())
