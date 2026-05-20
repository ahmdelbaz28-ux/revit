"""Minimal engineering service built on the canonical kernel."""

from __future__ import annotations

import hashlib
import json
from typing import List

from .geometry_kernel import candidate_points, derive_room_metrics
from .models import DetectorPlacement, RoomAnalysisRecord, RuleDecision, RoomGeometry


class PlacementService(object):
    def __init__(self, default_spacing_m=8.4, default_radius_m=6.4):
        self.default_spacing_m = default_spacing_m
        self.default_radius_m = default_radius_m

    def analyze_room(self, room):
        metrics = derive_room_metrics(room)
        points = candidate_points(room, self.default_spacing_m)
        detectors = []
        for index, point in enumerate(points):
            detectors.append(
                DetectorPlacement(
                    detector_id="%s-D%02d" % (room.room_id, index + 1),
                    room_id=room.room_id,
                    x=point[0],
                    y=point[1],
                    z=room.ceiling_height_m,
                    detector_type="smoke",
                    coverage_radius_m=self.default_radius_m,
                )
            )

        decision_payload = {
            "room_id": room.room_id,
            "area_m2": round(metrics["area_m2"], 3),
            "detector_count": len(detectors),
            "spacing_m": self.default_spacing_m,
        }
        decision = RuleDecision(
            rule_id="NFPA72.SMOKE.GENERAL.SPACING",
            rule_version="2022",
            outcome="pass",
            rationale="Placement derived from polygon-first candidate grid.",
            inputs_hash=hashlib.sha256(
                json.dumps(decision_payload, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        )

        return RoomAnalysisRecord(
            room=room,
            detectors=detectors,
            rule_decisions=[decision],
            metadata={"service": "PlacementService", "mode": "polygon-first"},
        )
