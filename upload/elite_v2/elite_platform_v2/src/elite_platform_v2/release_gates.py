"""Release blocking policy as executable code."""

from __future__ import annotations


def evaluate_release(context):
    checks = {
        "canonical_geometry": bool(context.get("canonical_geometry")),
        "evidence_chain_valid": bool(context.get("evidence_chain_valid")),
        "connector_in_sync": bool(context.get("connector_in_sync")),
        "version_authority_valid": bool(context.get("version_authority_valid")),
        "stale_surfaces_removed": bool(context.get("stale_surfaces_removed")),
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "checks": checks,
        "blockers": blockers,
        "release_status": "blocked" if blockers else "green",
    }
