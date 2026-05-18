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
# Minimal helpers
# ---------------------------------------------------------------------------

def _room_dict(
    room_id: str = "R-RT-01",
    width: float = 8.0,
    length: float = 6.0,
    ceiling_height: float = 3.0,
) -> Dict[str, Any]:
    return dict(
        room_id=room_id,
        width=width,
        length=length,
        ceiling_height=ceiling_height,
    )


def _floor_dict(rooms: List[Dict]) -> Dict[str, Any]:
    return {"floor_id": "F-RT-01", "rooms": rooms}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        spec = calculate_coverage_radius_from_height(rd["ceiling_height"], "smoke")
        layout1 = DensityOptimizer().optimize(room, coverage_radius=spec.radius)
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
        spec = calculate_coverage_radius_from_height(rd["ceiling_height"], "smoke")
        layout1 = DensityOptimizer().optimize(room, coverage_radius=spec.radius)
        exported = json.dumps(_layout_to_dict(layout1), default=str)

        imported = json.loads(exported)
        assert abs(imported["coverage_pct"] - layout1.coverage_pct) < 0.01

    def test_room_detectors_list_round_trips(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer, Room
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height

        rd = _room_dict(width=20.0, length=15.0)
        room = Room(
            name=rd["room_id"],
            width=rd["width"],
            length=rd["length"],
            ceiling_height=rd["ceiling_height"],
        )
        spec = calculate_coverage_radius_from_height(rd["ceiling_height"], "smoke")
        layout = DensityOptimizer().optimize(room, coverage_radius=spec.radius)
        exported = json.dumps(_layout_to_dict(layout), default=str)

        imported = json.loads(exported)
        assert len(imported["detectors"]) == layout.count


# ---------------------------------------------------------------------------
# Floor round-trip
# ---------------------------------------------------------------------------

class TestFloorRoundTrip:

    def test_floor_analyse_export_same_total_detectors(self):
        from fireai.core.floor_analyser import FloorAnalyser
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

        rooms = [
            {"room_id": "R1", "name": "Office",
             "polygon_coords": [(0,0),(10,0),(10,8),(0,8)],
             "ceiling_height": 3.0},
            {"room_id": "R2", "name": "Lobby",
             "polygon_coords": [(0,0),(12,0),(12,6),(0,6)],
             "ceiling_height": 3.0},
        ]
        opt = DensityOptimizer()
        analyser = FloorAnalyser(floor_id="F-RT", optimizer=opt)
        report = analyser.analyse(rooms)

        # Export summaries as JSON
        summaries = []
        for rs in report.room_summaries:
            summaries.append({
                "room_id":       rs.room_id,
                "detector_count": rs.detector_count,
                "coverage_pct":  rs.coverage_pct,
                "nfpa_valid":    rs.nfpa_valid,
                "proof_valid":   rs.proof_valid,
            })
        exported = json.dumps({"floor_id": report.floor_id,
                               "total_detectors": report.total_detectors,
                               "summaries": summaries}, default=str)

        # Re-import and verify
        imported = json.loads(exported)
        assert imported["total_detectors"] == report.total_detectors
        assert len(imported["summaries"]) == 2

    def test_floor_round_trip_preserves_compliance(self):
        from fireai.core.floor_analyser import FloorAnalyser
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer

        rooms = [
            {"room_id": "R1", "name": "Meeting",
             "polygon_coords": [(0,0),(6,0),(6,5),(0,5)],
             "ceiling_height": 3.0},
        ]
        opt = DensityOptimizer()
        analyser = FloorAnalyser(floor_id="F-COMP", optimizer=opt)
        report = analyser.analyse(rooms)

        exported = json.dumps({
            "fully_compliant": report.fully_compliant,
            "safe_to_submit":  report.safe_to_submit,
        })
        imported = json.loads(exported)
        assert imported["fully_compliant"] == report.fully_compliant
        assert imported["safe_to_submit"] == report.safe_to_submit


# ---------------------------------------------------------------------------
# JSON serialisation robustness
# ---------------------------------------------------------------------------

class TestJsonRobustness:

    def test_nan_and_inf_handled(self):
        """NaN and Infinity should not crash JSON serialisation."""
        import math
        data = {"value": float("nan"), "inf": float("inf")}
        result = json.dumps(data, default=str)
        assert isinstance(result, str)

    def test_tuple_serialises_as_list(self):
        """Detector positions (tuples) should round-trip as lists."""
        positions = [(1.5, 3.2), (4.0, 5.0)]
        exported = json.dumps(positions)
        imported = json.loads(exported)
        assert imported == [[1.5, 3.2], [4.0, 5.0]]
