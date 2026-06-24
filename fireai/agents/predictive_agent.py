"""fireai/agents/predictive_agent.py — Anticipatory Recommendations Agent
========================================================================
Analyzes future compliance state given design changes, suggests optimal
detector placement, and performs what-if analysis for design alternatives.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fireai.agents.learning_agent import LearningAgent
from fireai.analytics.ml_pipeline import DesignData, MLPipeline, RoomDesignData
from fireai.analytics.predictive_analytics import (
    PredictiveAnalyticsEngine,
)

logger = logging.getLogger(__name__)


# ── data classes ──────────────────────────────────────────────────────────────


@dataclass
class RoomData:
    room_id: str
    width: float
    length: float
    height: float
    area: float
    ceiling_type: str = "flat"
    obstruction_count: int = 0
    existing_detector_count: int = 0


@dataclass
class PlacementSuggestion:
    suggestion_id: str = ""
    room_id: str = ""
    detector_type: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    confidence: float = 0.0
    rationale: str = ""
    expected_coverage_improvement: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


@dataclass
class DesignChange:
    description: str = ""
    changes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FutureState:
    design_id: str = ""
    current_coverage: float = 0.0
    projected_coverage: float = 0.0
    compliance_status: str = "unknown"
    projected_compliance: str = "unknown"
    risks: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    confidence: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


@dataclass
class WhatIfResult:
    scenario: str = ""
    baseline: FutureState = field(default_factory=FutureState)
    projected: FutureState = field(default_factory=FutureState)
    delta_coverage: float = 0.0
    delta_compliance: str = "no_change"
    recommendation: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, indent=2)


# ── PredictiveAgent ──────────────────────────────────────────────────────────


class PredictiveAgent:
    """Anticipatory recommendations and future-state analysis:
    - Suggests optimal detector placement before user asks
    - Analyzes future compliance state given design changes
    - What-if analysis for design alternatives
    """

    def __init__(
        self,
        analytics_engine: Optional[PredictiveAnalyticsEngine] = None,
        ml_pipeline: Optional[MLPipeline] = None,
        learning_agent: Optional[LearningAgent] = None,
    ):
        self.analytics = analytics_engine or PredictiveAnalyticsEngine()
        self.ml_pipeline = ml_pipeline or MLPipeline()
        self.learning_agent = learning_agent or LearningAgent()

    def suggest_placement(self, room: RoomData) -> List[PlacementSuggestion]:
        suggestions: List[PlacementSuggestion] = []

        # Retrieve similar experiences for guidance
        similar = self.learning_agent.retrieve_similar(
            {
                "area": room.area,
                "width": room.width,
                "length": room.length,
                "ceiling_height": room.height,
                "ceiling_type": room.ceiling_type,
                "obstruction_count": room.obstruction_count,
            },
            top_k=3,
        )

        avg_detectors = 0.0
        if similar:
            avg_detectors = sum(e.detector_count for e in similar) / len(similar)
        else:
            avg_detectors = max(1, math.ceil(room.area / 100.0))

        suggested_count = max(1, round(avg_detectors))
        spacing_x = room.width / max(suggested_count, 1)
        spacing_y = room.length / max(suggested_count, 1)

        for i in range(suggested_count):
            for j in range(suggested_count):
                x = spacing_x * 0.5 + i * spacing_x
                y = spacing_y * 0.5 + j * spacing_y
                if x > room.width or y > room.length:
                    continue
                obs_factor = max(0.0, 1.0 - room.obstruction_count * 0.05)
                confidence = min(0.9, 0.5 + avg_detectors * 0.05) * obs_factor
                suggestions.append(
                    PlacementSuggestion(
                        suggestion_id=f"sug_{room.room_id}_{i}_{j}",
                        room_id=room.room_id,
                        detector_type="smoke",
                        x=round(x, 2),
                        y=round(y, 2),
                        z=room.height,
                        confidence=round(confidence, 4),
                        rationale=f"grid placement ({(i+1)}, {(j+1)} of {suggested_count}x{suggested_count})",
                        expected_coverage_improvement=round(min(0.95, 0.75 + suggested_count * 0.05), 4),
                    )
                )
                if len(suggestions) >= 20:
                    break
            if len(suggestions) >= 20:
                break

        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions[:10]

    def analyze_future_state(self, design: DesignData, changes: DesignChange) -> FutureState:
        current_coverage = sum(r.coverage_pct for r in design.rooms) / max(len(design.rooms), 1)

        projected_rooms: List[RoomDesignData] = []
        for room in design.rooms:
            room_dict = {"area": room.area, "ceiling_height": room.ceiling_height, "detector_count": room.detector_count, "obstruction_count": room.obstruction_count, "beam_depth_ratio": room.beam_depth_ratio, "wall_proximity_min": room.wall_proximity_min, "hvac_proximity_min": room.hvac_proximity_min, "coverage_pct": room.coverage_pct}
            updated = dict(room_dict)
            for key, val in changes.changes.items():
                if key in room_dict:
                    updated[key] = val
                elif key == "add_detectors" and isinstance(val, (int, float)):
                    updated["detector_count"] = room.detector_count + int(val)
                    updated["coverage_pct"] = min(0.99, room.coverage_pct + int(val) * 0.03)
            projected_rooms.append(
                RoomDesignData(
                    room_id=room.room_id,
                    area=float(updated["area"]),
                    ceiling_height=float(updated["ceiling_height"]),
                    detector_count=int(updated["detector_count"]),
                    obstruction_count=int(updated["obstruction_count"]),
                    beam_depth_ratio=float(updated["beam_depth_ratio"]),
                    wall_proximity_min=float(updated["wall_proximity_min"]),
                    hvac_proximity_min=float(updated["hvac_proximity_min"]),
                    coverage_pct=float(updated["coverage_pct"]),
                )
            )

        projected_design = DesignData(building_id=design.building_id, rooms=projected_rooms)
        projected_coverage = sum(r.coverage_pct for r in projected_design.rooms) / max(len(projected_design.rooms), 1)

        compliance = "compliant" if current_coverage >= 0.85 else "non_compliant"
        projected_comp = "compliant" if projected_coverage >= 0.85 else "non_compliant"

        risks: List[str] = []
        if projected_coverage < 0.85:
            risks.append("Projected coverage below 85% threshold")
        for r in projected_design.rooms:
            if r.wall_proximity_min < 0.1:
                risks.append(f"Room {r.room_id}: wall proximity violation")
            if r.beam_depth_ratio > 0.1:
                risks.append(f"Room {r.room_id}: beam depth ratio exceeds 0.1")

        recs: List[str] = []
        if projected_coverage < 0.90:
            recs.append(f"Add detectors to improve coverage from {projected_coverage:.1%} to >= 90%")
        if risks:
            recs.append("Address identified risks before finalizing design")

        confidence = min(0.95, 0.5 + len(projected_rooms) * 0.05)

        return FutureState(
            design_id=design.building_id,
            current_coverage=round(current_coverage, 4),
            projected_coverage=round(projected_coverage, 4),
            compliance_status=compliance,
            projected_compliance=projected_comp,
            risks=risks,
            recommendations=recs,
            confidence=round(confidence, 4),
        )

    def what_if(self, design: DesignData, scenario: str) -> WhatIfResult:
        baseline = self.analyze_future_state(design, DesignChange(description="baseline", changes={}))

        scenario_map: Dict[str, Dict[str, Any]] = {
            "add_detectors": {"add_detectors": 2},
            "remove_detectors": {"add_detectors": -1},
            "reduce_obstructions": {"obstruction_count": 0},
            "increase_ceiling": {"ceiling_height": 6.0},
            "improve_coverage": {"coverage_pct": 0.95},
            "optimize_placement": {"wall_proximity_min": 0.3, "hvac_proximity_min": 0.5},
        }
        scenario_changes = scenario_map.get(scenario, {})

        projected = self.analyze_future_state(design, DesignChange(description=scenario, changes=scenario_changes))

        delta_cov = projected.projected_coverage - baseline.projected_coverage
        if delta_cov > 0.02:
            delta_comp = "improved"
        elif delta_cov < -0.02:
            delta_comp = "worsened"
        else:
            delta_comp = "no_change"

        rec = f"Scenario '{scenario}': coverage {delta_cov:+.1%}, compliance {projected.projected_compliance}"
        if delta_comp == "improved":
            rec += " — recommended for implementation"
        elif delta_comp == "worsened":
            rec += " — review before proceeding"

        return WhatIfResult(
            scenario=scenario,
            baseline=baseline,
            projected=projected,
            delta_coverage=round(delta_cov, 4),
            delta_compliance=delta_comp,
            recommendation=rec,
        )
