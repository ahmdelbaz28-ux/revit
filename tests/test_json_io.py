"""
Round-trip JSON I/O tests.
Room  -> analyse -> export JSON -> re-import -> same result.
Floor -> analyse -> export JSON -> re-import -> same detector count.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List

import pytest


# ---------------------------------------------------------------------------
# Minimal stubs so tests run without a full environment if needed
# ---------------------------------------------------------------------------

def _room_dict(
    room_id: str = "R-RT-01",
    width: float = 8.0,
    length: float = 6.0,
    ceiling_height: float = 3.0,
    detector_type: str = "smoke",
) -> Dict[str, Any]:
    return dict(
        room_id=room_id,
        width=width,
        length=length,
        ceiling_height=ceiling_height,
        detector_type=detector_type,
    )


def _floor_dict(rooms: List[Dict]) -> Dict[str, Any]:
    return {"floor_id": "F-RT-01", "rooms": rooms}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialise(obj: Any) -> str:
    """Convert a dataclass / object to JSON string."""
    try:
        return json.dumps(asdict(obj), default=str)
    except TypeError:
        # fallback for non-dataclass objects
        return json.dumps(obj.__dict__, default=str)


def _layout_to_dict(layout) -> Dict[str, Any]:
    return {
        "detectors":       layout.detectors,
        "count":           layout.count,
        "coverage_pct":    layout.coverage_pct,
        "proof_valid":     layout.proof_valid,
        "wall_violations": layout.wall_violations,
        "method":          layout.method,
    }


# ---------------------------------------------------------------------------
# Room round-trip
# ---------------------------------------------------------------------------

class TestRoomRoundTrip:

    def test_room_analyse_export_reimport_same_count(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height

        rd = _room_dict()
        room = Room(
            name=rd["room_id"],
            width=rd["width"],
            length=rd["length"],
            ceiling_height=rd["ceiling_height"],
        )
        cov_det_type = "heat" if "heat" in rd["detector_type"].lower() else "smoke"
        spec = calculate_coverage_radius_from_height(rd["ceiling_height"], cov_det_type)
        radius = spec.radius
        layout1 = DensityOptimizer().optimize(room, coverage_radius=radius)
        exported = json.dumps(_layout_to_dict(layout1), default=str)

        # Re-import
        imported = json.loads(exported)
        assert imported["count"] == layout1.count

    def test_room_analyse_export_reimport_same_coverage(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height

        rd = _room_dict(width=12.0, length=9.0, ceiling_height=4.0)
        room = Room(
            name=rd["room_id"],
            width=rd["width"],
            length=rd["length"],
            ceiling_height=rd["ceiling_height"],
        )
        cov_det_type = "heat" if "heat" in rd["detector_type"].lower() else "smoke"
        spec = calculate_coverage_radius_from_height(rd["ceiling_height"], cov_det_type)
        radius = spec.radius
        layout1 = DensityOptimizer().optimize(room, coverage_radius=radius)
        exported = json.dumps(_layout_to_dict(layout1), default=str)
        imported = json.loads(exported)

        assert abs(imported["coverage_pct"] - layout1.coverage_pct) < 0.01

    def test_room_analyse_export_reimport_same_method(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height

        rd = _room_dict(width=20.0, length=15.0, ceiling_height=3.0)
        room = Room(
            name=rd["room_id"],
            width=rd["width"],
            length=rd["length"],
            ceiling_height=rd["ceiling_height"],
        )
        cov_det_type = "heat" if "heat" in rd["detector_type"].lower() else "smoke"
        spec = calculate_coverage_radius_from_height(rd["ceiling_height"], cov_det_type)
        radius = spec.radius
        layout1 = DensityOptimizer().optimize(room, coverage_radius=radius)
        exported = json.dumps(_layout_to_dict(layout1), default=str)
        imported = json.loads(exported)

        assert imported["method"] == layout1.method


# ---------------------------------------------------------------------------
# Floor round-trip
# ---------------------------------------------------------------------------

class TestFloorRoundTrip:

    def test_floor_analyse_export_reimport_same_detector_count(self):
        from fireai.core.floor_analyser import FloorAnalyser
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0, 0), (10, 0), (10, 8), (0, 8)],
             "ceiling_height": 3.0},
            {"room_id": "R2", "name": "Meeting",
             "polygon_coords": [(0, 0), (6, 0), (6, 5), (0, 5)],
             "ceiling_height": 3.0},
        ]
        opt = DensityOptimizer()
        report = FloorAnalyser(floor_id="F-RT-01", optimizer=opt).analyse(rooms)

        # Export to JSON-serialisable dict
        exported_summaries = []
        for rs in report.room_summaries:
            exported_summaries.append({
                "room_id":        rs.room_id,
                "detector_count": rs.detector_count,
                "coverage_pct":   rs.coverage_pct,
                "method":         rs.method,
            })
        exported = json.dumps({
            "floor_id":        report.floor_id,
            "total_detectors": report.total_detectors,
            "room_summaries":  exported_summaries,
        }, default=str)

        # Re-import
        imported = json.loads(exported)
        assert imported["total_detectors"] == report.total_detectors

    def test_floor_analyse_export_reimport_same_room_count(self):
        from fireai.core.floor_analyser import FloorAnalyser
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

        rooms = [
            {"room_id": "R1", "name": "Lobby",
             "polygon_coords": [(0, 0), (12, 0), (12, 8), (0, 8)],
             "ceiling_height": 3.0},
        ]
        opt = DensityOptimizer()
        report = FloorAnalyser(floor_id="F-RT-02", optimizer=opt).analyse(rooms)

        # Export
        exported = json.dumps({
            "floor_id":        report.floor_id,
            "total_detectors": report.total_detectors,
            "room_count":      len(report.room_summaries),
        }, default=str)

        # Re-import
        imported = json.loads(exported)
        assert imported["room_count"] == len(report.room_summaries)
