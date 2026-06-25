"""v17_core/acoustic_calculator.py — NFPA 72 §18.4 Audible Notification Compliance
=================================================================================
CRITICAL LIFE-SAFETY MODULE — Part of the V17 Critical Trilogy

Wrapper around the physics-correct AcousticSPLCalculator from
fireai.core.acoustic_calculator, adding DecisionProvenance audit trails
for AHJ submittal packages.

The consultant's proposed code had these errors (all fixed in fireai.core):
  1. WRONG FORMULA: 20*log10(dist_m) assumes 1m reference distance.
     Speaker specs are at 3m (10ft). Correct: 20*log10(dist_m / 3.0).
     This overestimated attenuation by ~9.5 dB.
  2. 2D ONLY: Used math.hypot(x1-x2, y1-y2), ignoring height (z).
     A ceiling speaker at 3m height to a listener at 1.5m has 1.5m
     vertical distance that 2D would miss entirely.
  3. behind_closed_door ON SPEAKER: Put the barrier flag on the speaker
     object. Barriers are between speaker and listener, not on the speaker.
     Replaced with proper Barrier dataclass system.
  4. WRONG IMPORT: fireai.v8_core.decision_provenance → fireai.core.provenance

NFPA 72 References:
  - §18.4.3.1: Public mode — minimum 15 dB above average ambient
  - §18.4.4:   Private mode — minimum 10 dB above ambient
  - §18.4.2:   Sleeping areas — minimum 75 dBA at pillow
  - §18.4.1.2: Maximum 110 dBA at minimum distance from source

Usage:
    from fireai.v17_core import AcousticSPLCalculator

    calc = AcousticSPLCalculator(room_ambient_noise={"business": 55.0})
    provenance = calc.calculate_room_spl(
        room_id="R-101",
        occ_type="business",
        speakers=[{"x": 5, "y": 5, "z": 2.8, "rating_db_3m": 95}],
        check_points=[{"x": 1, "y": 1, "z": 1.5}],
    )
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Import the correct provenance shim (not the consultant's fireai.v8_core path)
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]

# Import the physics-correct implementation from fireai.core
from fireai.core.acoustic_calculator import (
    AMBIENT_NOISE_LEVELS,
    AUDIBLE_REQUIREMENTS,
    DEFAULT_REF_DISTANCE_M,
    Barrier,
    CheckPoint,
    RoomAcousticResult,
    Speaker,
)
from fireai.core.acoustic_calculator import (
    AcousticSPLCalculator as _CoreAcousticSPLCalculator,
)


class AcousticSPLCalculator:
    """V17 Acoustic SPL Calculator with DecisionProvenance audit trail.

    Wraps the physics-correct AcousticSPLCalculator from fireai.core and
    produces DecisionProvenance objects for AHJ submittal packages.

    The consultant's interface used dict-based speakers and check_points.
    This implementation accepts BOTH dict-based (consultant-compatible) and
    object-based (fireai.core) inputs, converting dicts to proper objects.

    Key corrections from consultant's code:
      - 2D → 3D distance calculation (includes z/height)
      - 20*log10(dist_m) → 20*log10(dist_m / ref_distance_m)
      - behind_closed_door flag → proper Barrier system
      - fireai.v8_core import → fireai.core.provenance

    NFPA 72 §18.4.3.1: Public-mode audible alarm must be ≥15 dB above
    the average ambient sound level.
    """

    def __init__(
        self,
        room_ambient_noise: Optional[Dict[str, float]] = None,
    ) -> None:
        """Initialize with ambient noise levels per occupancy type.

        Args:
            room_ambient_noise: Dict mapping occupancy types to ambient
                noise levels in dBA. Merged with defaults from
                NFPA 72 Table A.18.4.3.

        """
        # Start with NFPA 72 Table A.18.4.3 defaults
        self.ambient_levels: Dict[str, float] = dict(AMBIENT_NOISE_LEVELS)
        if room_ambient_noise:
            self.ambient_levels.update(room_ambient_noise)

        # Also store the simple NFPA 72 Table A.18.4.3 defaults
        # that the consultant's interface expected
        self._simple_ambient = {
            "business": 55.0,
            "mechanical": 85.0,
            "industrial": 80.0,
            "residential": 45.0,
        }
        self.ambient_levels.update(self._simple_ambient)

    def _convert_speakers(self, speakers: List[dict]) -> List[Speaker]:
        """Convert dict-based speaker specs to Speaker objects.

        The consultant's interface used dicts with keys like:
            {"x": 5, "y": 5, "z": 2.8, "rating_db_3m": 95}
        We convert these to proper Speaker dataclasses.
        """
        result = []
        for spkr in speakers:
            # Consultant used "rating_db_3m", our core uses "rating_dba"
            rating = spkr.get("rating_db_3m", spkr.get("rating_dba", 95.0))
            ref_dist = spkr.get("ref_distance_m", DEFAULT_REF_DISTANCE_M)
            result.append(
                Speaker(
                    x=float(spkr.get("x", 0)),
                    y=float(spkr.get("y", 0)),
                    z=float(spkr.get("z", 2.8)),  # Default ceiling mount height
                    rating_dba=float(rating),
                    ref_distance_m=float(ref_dist),
                    speaker_id=spkr.get("speaker_id", spkr.get("id", "")),
                )
            )
        return result

    def _convert_check_points(self, check_points: List[dict]) -> List[CheckPoint]:
        """Convert dict-based check points to CheckPoint objects.

        The consultant's interface used dicts with keys like:
            {"x": 1, "y": 1, "z": 1.5}
        """
        result = []
        for pt in check_points:
            result.append(
                CheckPoint(
                    x=float(pt.get("x", 0)),
                    y=float(pt.get("y", 0)),
                    z=float(pt.get("z", 1.5)),  # Default: typical ear height
                    label=pt.get("label", ""),
                )
            )
        return result

    def _convert_barriers(
        self,
        speakers: List[dict],
    ) -> List[Barrier]:
        """Extract barrier information from consultant-style speaker dicts.

        The consultant used 'behind_closed_door' flag on speakers.
        We convert this to proper Barrier objects.
        """
        barriers = []
        for spkr in speakers:
            if spkr.get("behind_closed_door", False):
                barriers.append(
                    Barrier(
                        barrier_type="standard_door",
                        label=f"Closed door for speaker {spkr.get('id', 'unknown')}",
                    )
                )
        return barriers

    def calculate_room_spl(
        self,
        room_id: str,
        occ_type: str,
        speakers: List[dict],
        check_points: List[dict],
        barriers: Optional[List[dict]] = None,
        mode: str = "public",
        room_absorption_m2: Optional[float] = None,
    ) -> Any:
        """Calculate SPL at all check points from all speakers in a room.

        Produces a DecisionProvenance audit trail for AHJ submittal.

        For each check point:
          1. Calculate 3D distance to each speaker (NOT 2D like consultant's code)
          2. Apply inverse square law: Lp(d) = Lp(ref) - 20*log10(d/d_ref)
             (NOT 20*log10(d) like consultant's code)
          3. Apply barrier attenuation if barriers exist
          4. Sum SPL contributions from all speakers (logarithmic addition)
          5. Add reverberant field contribution if room absorption provided
          6. Check against NFPA 72 §18.4.3.1 requirements (+15 dB above ambient)

        Args:
            room_id: Room identifier.
            occ_type: Occupancy type (e.g., "business", "mechanical").
            speakers: List of speaker dicts. Each must have "x", "y" and
                optionally "z", "rating_db_3m" (or "rating_dba"),
                "ref_distance_m", "behind_closed_door".
            check_points: List of check point dicts. Each must have "x", "y"
                and optionally "z", "label".
            barriers: Optional list of barrier dicts. Each may have
                "barrier_type", "attenuation_dba", "label".
            mode: "public", "private", or "sleeping" per NFPA 72 §18.4.
            room_absorption_m2: Room absorption in m² Sabine.

        Returns:
            DecisionProvenance with compliance status, or dict if
            provenance is unavailable.

        """
        # Convert consultant-style dicts to proper objects
        speaker_objs = self._convert_speakers(speakers)
        point_objs = self._convert_check_points(check_points)

        # Extract barriers from consultant-style inputs
        barrier_objs = self._convert_barriers(speakers)
        if barriers:
            for b in barriers:
                barrier_objs.append(
                    Barrier(
                        barrier_type=b.get("barrier_type", "standard_door"),
                        attenuation_dba=b.get("attenuation_dba"),
                        label=b.get("label", ""),
                    )
                )

        # Use the core physics-correct calculator
        core_calc = _CoreAcousticSPLCalculator(
            room_ambient_noise=self.ambient_levels,
        )
        result: RoomAcousticResult = core_calc.calculate_room_spl(
            room_id=room_id,
            occ_type=occ_type,
            speakers=speaker_objs,
            check_points=point_objs,
            barriers=barrier_objs if barrier_objs else None,
            mode=mode,
            room_absorption_m2=room_absorption_m2,
        )

        # Get ambient level used
        ambient_dba = self.ambient_levels.get(
            occ_type.lower(),
            self._simple_ambient.get(occ_type.lower(), 55.0),
        )
        # Try matching with core calculator's logic
        for key, val in self.ambient_levels.items():
            if occ_type.lower() in key.lower():
                ambient_dba = val
                break

        # Build DecisionProvenance if available
        if DecisionProvenance is not None:
            violations = []
            for v in result.violations:
                severity = "WARNING" if v.get("code") == "ACOUSTIC-EXCESSIVE" else "CRITICAL"
                violations.append(
                    Violation(
                        severity=severity,
                        citation="NFPA 72-2022 §18.4.3.1",
                        description=v.get("message", str(v)),
                        location=v.get("point"),
                    )
                )

            if mode not in AUDIBLE_REQUIREMENTS:
                mode = "public"
            min_above_ambient = AUDIBLE_REQUIREMENTS[mode][0]
            nfpa_section = AUDIBLE_REQUIREMENTS[mode][2]

            rules = [
                RuleApplied(
                    citation=f"NFPA 72-2022 {nfpa_section}",
                    constant_id="SPL_PUB_MODE",
                    value_used=float(min_above_ambient),
                    unit="dBA",
                ),
            ]

            has_violations = len(result.violations) > 0
            conf_level = ConfidenceLevel.MEDIUM if has_violations else ConfidenceLevel.HIGH
            conf = ConfidenceScore(
                input_quality_score=0.9,
                rule_coverage=1.0,
                geometry_certainty=0.85,
                overall=conf_level,
            )

            return DecisionProvenance.new(
                decision_type="audibility_compliance",
                value={
                    "min_spl_achieved": result.worst_point_spl,
                    "required_dba": result.required_dba,
                    "margin_dba": result.margin_dba,
                    "pass": result.compliant,
                    "room_id": room_id,
                },
                inputs={
                    "speakers": len(speakers),
                    "check_pts": len(check_points),
                    "ambient_dba": ambient_dba,
                    "occ_type": occ_type,
                    "mode": mode,
                },
                rules_applied=rules,
                algorithm={
                    "name": "InverseSquareSPLAccumulator",
                    "version": "v17",
                    "corrections": [
                        "3D distance (not 2D)",
                        "20*log10(d/d_ref) not 20*log10(d)",
                        "Proper Barrier system (not behind_closed_door flag)",
                    ],
                },
                confidence=conf,
                selected_because=(
                    f"Logarithmic sum across {len(speakers)} speaker arrays projected over room space with 3D physics"
                ),
                violations=violations,
            )

        # Fallback: return result dict if provenance unavailable
        return {
            "room_id": result.room_id,
            "compliant": result.compliant,
            "worst_point_spl": result.worst_point_spl,
            "required_dba": result.required_dba,
            "margin_dba": result.margin_dba,
            "violations": result.violations,
            "point_results": result.point_results,
        }
