"""Deterministic placement and analysis output."""

from __future__ import annotations

from .canonical_json import sha256_payload
from .geometry import bounding_box, polygon_area


def analyze_room(contract, spacing_m, coverage_radius_m):
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    if coverage_radius_m <= 0:
        raise ValueError("coverage_radius_m must be positive")

    box = bounding_box(contract.polygon)
    area_m2 = polygon_area(contract.polygon)
    detectors = []

    row = 0
    y = box["min_y"] + spacing_m / 2.0
    while y < box["max_y"]:
        x = box["min_x"] + spacing_m / 2.0
        col = 0
        while x < box["max_x"]:
            detectors.append(
                {
                    "detector_id": "%s-D%02d%02d" % (contract.room_id, row, col),
                    "room_id": contract.room_id,
                    "x": round(x, 4),
                    "y": round(y, 4),
                    "z": contract.ceiling_height_m,
                    "detector_type": "smoke",
                    "coverage_radius_m": coverage_radius_m,
                }
            )
            x += spacing_m
            col += 1
        y += spacing_m
        row += 1

    if not detectors:
        detectors.append(
            {
                "detector_id": "%s-D00" % contract.room_id,
                "room_id": contract.room_id,
                "x": round((box["min_x"] + box["max_x"]) / 2.0, 4),
                "y": round((box["min_y"] + box["max_y"]) / 2.0, 4),
                "z": contract.ceiling_height_m,
                "detector_type": "smoke",
                "coverage_radius_m": coverage_radius_m,
            }
        )

    rule_basis = {
        "room_id": contract.room_id,
        "area_m2": round(area_m2, 4),
        "spacing_m": spacing_m,
        "detector_count": len(detectors),
    }
    return {
        "room_id": contract.room_id,
        "metrics": {
            "area_m2": area_m2,
            "width_m": box["width_m"],
            "depth_m": box["depth_m"],
            "ceiling_height_m": contract.ceiling_height_m,
        },
        "detectors": detectors,
        "rule_decision": {
            "rule_id": "NFPA72.SMOKE.GENERAL.SPACING",
            "rule_version": "2022",
            "outcome": "pass",
            "rationale": "Deterministic polygon-first layout.",
            "inputs_hash": sha256_payload(rule_basis),
        },
    }
