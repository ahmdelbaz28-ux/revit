"""Compliance check functions for each rule."""

from math import sqrt
from typing import List
from core.compliance_engine.rule_registry import get_rule_by_id


def check_detector_spacing(devices: list, max_spacing: float = 15.0) -> dict:
    violations = []
    for i, d1 in enumerate(devices):
        for j, d2 in enumerate(devices):
            if j <= i:
                continue
            dist = sqrt((d1.get("x", 0) - d2.get("x", 0))**2 + (d1.get("y", 0) - d2.get("y", 0))**2)
            if dist > max_spacing:
                violations.append({
                    "device_pair": (i, j),
                    "distance": round(dist, 1),
                    "max_allowed": max_spacing
                })

    rule = get_rule_by_id("NFPA72-17.6.3-SPACING")
    return {
        "rule_id": rule.rule_id,
        "passed": len(violations) == 0,
        "violations": violations,
        "source": rule.source,
        "version": rule.version,
        "severity": rule.severity,
        "rationale": rule.rationale
    }


def check_coverage(coverage: float, min_coverage: float = 0.90) -> dict:
    rule = get_rule_by_id("NFPA72-17.6.3.1-COVERAGE")
    return {
        "rule_id": rule.rule_id,
        "passed": coverage >= min_coverage,
        "current_coverage": round(coverage, 3),
        "min_required": min_coverage,
        "source": rule.source,
        "version": rule.version,
        "severity": rule.severity,
        "rationale": rule.rationale
    }


def check_redundancy(room: dict, devices: list) -> dict:
    rule = get_rule_by_id("NFPA72-17.7.1-REDUNDANCY")
    critical_types = ["electrical", "server", "control", "mechanical", "storage"]
    is_critical = room.get("type") in critical_types

    if not is_critical:
        return {
            "rule_id": rule.rule_id,
            "passed": True,
            "applicable": False,
            "reason": "Not a critical room type",
            "source": rule.source,
            "version": rule.version,
            "severity": rule.severity,
            "rationale": rule.rationale
        }

    room_devices = [d for d in devices if d.get("room_id") == room.get("id")]
    has_redundancy = len(room_devices) >= 2

    return {
        "rule_id": rule.rule_id,
        "passed": has_redundancy,
        "device_count": len(room_devices),
        "min_required": 2,
        "applicable": True,
        "source": rule.source,
        "version": rule.version,
        "severity": rule.severity,
        "rationale": rule.rationale
    }


def check_egress(room: dict) -> dict:
    rule = get_rule_by_id("OSHA-1910.36-EGRESS")
    exit_count = room.get("exit_count", 1)
    travel_distance = room.get("travel_distance", 20)

    violations = []
    if exit_count < 2:
        violations.append(f"Only {exit_count} exit(s) provided, minimum 2 required")
    if travel_distance > 30:
        violations.append(f"Travel distance {travel_distance}m exceeds 30m maximum")

    return {
        "rule_id": rule.rule_id,
        "passed": len(violations) == 0,
        "violations": violations,
        "exit_count": exit_count,
        "travel_distance": travel_distance,
        "source": rule.source,
        "version": rule.version,
        "severity": rule.severity,
        "rationale": rule.rationale
    }


def check_ceiling_height_adjustment(room: dict) -> dict:
    rule = get_rule_by_id("NFPA72-17.6.2-HEIGHT")
    height = room.get("height", 3.0)

    adjustment_needed = height > 6.0

    return {
        "rule_id": rule.rule_id,
        "passed": not adjustment_needed or room.get("density_adjusted", False),
        "ceiling_height": height,
        "adjustment_needed": adjustment_needed,
        "source": rule.source,
        "version": rule.version,
        "severity": rule.severity,
        "rationale": rule.rationale
    }


def check_manual_call_points(room: dict, devices: list) -> dict:
    rule = get_rule_by_id("NFPA72-17.14-MCP")
    has_mcp = any(d.get("type") == "manual_call_point" for d in devices)

    return {
        "rule_id": rule.rule_id,
        "passed": has_mcp or room.get("type") not in ["corridor", "exit_area"],
        "mcp_present": has_mcp,
        "source": rule.source,
        "version": rule.version,
        "severity": rule.severity,
        "rationale": rule.rationale
    }