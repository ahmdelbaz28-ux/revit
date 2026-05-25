from math import sqrt

RULE_METADATA = {
    "NFPA-SPACING-001": {
        "source": "NFPA 72",
        "version": "2022",
        "section": "17.6.3",
        "description": "Maximum detector spacing",
        "severity": "HIGH"
    },
    "NFPA-COVERAGE-001": {
        "source": "NFPA 72",
        "version": "2022",
        "section": "17.6.3.1",
        "description": "Minimum coverage percentage",
        "severity": "CRITICAL"
    },
    "NFPA-REDUNDANCY-001": {
        "source": "NFPA 72",
        "version": "2022",
        "section": "17.7.1",
        "description": "Redundancy for critical areas",
        "severity": "HIGH"
    },
    "OSHA-EGRESS-001": {
        "source": "OSHA 1910.36",
        "version": "2023",
        "section": "1910.36(d)",
        "description": "Exit route requirements",
        "severity": "CRITICAL"
    }
}

def check_spacing_compliance(devices: list, max_spacing: float = 15.0) -> list:
    violations = []
    for i, d1 in enumerate(devices):
        for j, d2 in enumerate(devices):
            if j <= i:
                continue
            dist = sqrt((d1["x"] - d2["x"])**2 + (d1["y"] - d2["y"])**2)
            if dist > max_spacing:
                violations.append({
                    "rule": "NFPA-SPACING-001",
                    "status": "FAIL",
                    "reason": f"Detector spacing {dist:.1f}m exceeds {max_spacing}m",
                    "severity": RULE_METADATA["NFPA-SPACING-001"]["severity"]
                })
    return violations

def check_coverage_compliance(coverage: float, min_coverage: float = 0.90) -> list:
    if coverage < min_coverage:
        return [{
            "rule": "NFPA-COVERAGE-001",
            "status": "FAIL",
            "reason": f"Coverage {coverage:.1%} below {min_coverage:.0%}",
            "severity": RULE_METADATA["NFPA-COVERAGE-001"]["severity"]
        }]
    return []

def check_egress_compliance(room: dict) -> list:
    violations = []
    exit_count = room.get("exit_count", 1)
    if exit_count < 2:
        violations.append({
            "rule": "OSHA-EGRESS-001",
            "status": "FAIL",
            "reason": f"Room {room.get('id')} has only {exit_count} exit(s)",
            "severity": RULE_METADATA["OSHA-EGRESS-001"]["severity"]
        })
    return violations

def run_compliance_check(rooms: list, devices: list, coverage: float) -> dict:
    all_violations = []

    spacing_violations = check_spacing_compliance(devices)
    all_violations.extend(spacing_violations)

    coverage_violations = check_coverage_compliance(coverage)
    all_violations.extend(coverage_violations)

    for room in rooms:
        egress_violations = check_egress_compliance(room)
        all_violations.extend(egress_violations)

    critical_failures = [v for v in all_violations if v["severity"] == "CRITICAL"]
    high_failures = [v for v in all_violations if v["severity"] == "HIGH"]
    total_violations = len(all_violations)

    passed = total_violations == 0

    return {
        "passed": passed,
        "total_violations": total_violations,
        "critical_failures": len(critical_failures),
        "high_failures": len(high_failures),
        "violations": all_violations,
        "rule_metadata": RULE_METADATA
    }