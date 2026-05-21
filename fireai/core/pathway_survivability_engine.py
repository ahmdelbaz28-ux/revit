"""pathway_survivability_engine.py — NFPA 72-2022 §12.4 Pathway Survivability

CRITICAL LIFE-SAFETY MODULE
============================
Determines the minimum fire-resistance rating for fire alarm wiring
based on building occupancy, height, and evacuation strategy.

WHY THIS MATTERS:
  A fire in a 20-storey hotel burns the unprotected SLC cable riser
  on floor 3.  Floors 4-20 lose ALL alarm capability instantly.
  People die because the pathway did not survive the fire.

  NFPA 72 §12.4 defines three survivability levels:
    Level 1: General wiring — OK only in fully-sprinklered buildings.
    Level 2: 2-hour rated — CI cable OR cable in 2-hour enclosure.
             Required for: partial evacuation, high-rise, voice evac.
    Level 3: 2-hour rated enclosure + CI cable — highest protection.
             Required for: staged evacuation in non-sprinklered.

  The logic here is deterministic from NFPA — no invention needed.
  The classification maps directly from occupancy + height + sprinklers.

Architecture:
  PathwaySurvivabilityEngine.classify(building_spec) -> SurvivabilityResult
  The result feeds into:
    - auto_drafting_engine.py (routing constraints)
    - boq_generator.py (cable type selection)
    - contracts.py (CableType enum for downstream consumers)

Thread-safety: zero module-level mutable state. All methods are pure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from fireai.core.contracts import (
    PathwaySurvivabilityLevel,
    CableType,
    OccupancyCategory,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BuildingSpec",
    "SurvivabilityResult",
    "CableRequirement",
    "PathwaySurvivabilityEngine",
]


# ============================================================================
# Data Structures
# ============================================================================

@dataclass(frozen=True)
class BuildingSpec:
    """Building specification for pathway survivability classification.

    Attributes:
        occupancy:       Building occupancy category.
        height_m:        Building height in metres (grade to roof).
        num_floors:      Total number of floors above grade.
        is_sprinklered:  Fully sprinklered throughout (NFPA 13/13R).
        has_voice_evac:  Voice evacuation system (NFPA 72 §24.4).
        evacuation_type: "full", "partial", or "staged".
        has_central_station: Monitored by central station (NFPA 72 §26.3).
        is_high_rise:    Building exceeds 23 m (75 ft) per IBC §403.
        has_detention:   Detention/correctional occupancy.
        zone_count:      Number of alarm zones.
    """
    occupancy: OccupancyCategory = OccupancyCategory.BUSINESS
    height_m: float = 12.0
    num_floors: int = 3
    is_sprinklered: bool = False
    has_voice_evac: bool = False
    evacuation_type: str = "full"      # "full", "partial", "staged"
    has_central_station: bool = False
    is_high_rise: bool = False
    has_detention: bool = False
    zone_count: int = 1

    def __post_init__(self) -> None:
        # Auto-detect high-rise if height > 23 m
        if self.height_m > 23.0 and not self.is_high_rise:
            object.__setattr__(self, "is_high_rise", True)
        # Auto-detect detention
        if self.occupancy == OccupancyCategory.DETENTION and not self.has_detention:
            object.__setattr__(self, "has_detention", True)


@dataclass(frozen=True)
class CableRequirement:
    """Cable requirement for a specific zone/route.

    Attributes:
        route_type:      "riser", "horizontal", "plenum", or "general".
        required_level:  Minimum pathway survivability level.
        cable_type:      Required cable type (FPL/FPLR/FPLP/CI).
        in_rated_enclosure: Whether cable must be in fire-rated enclosure.
        enclosure_rating_hr: Fire-resistance rating of enclosure (hours).
        nfpa_reference:  Applicable NFPA 72 section.
        notes:           Additional engineering notes.
    """
    route_type: str = "general"
    required_level: PathwaySurvivabilityLevel = PathwaySurvivabilityLevel.LEVEL_1
    cable_type: CableType = CableType.FPL
    in_rated_enclosure: bool = False
    enclosure_rating_hr: float = 0.0
    nfpa_reference: str = "NFPA 72-2022 §12.4"
    notes: str = ""


@dataclass
class SurvivabilityResult:
    """Complete pathway survivability classification result.

    Attributes:
        building_level:   Overall minimum survivability level for the building.
        cable_requirements: Per-route-type cable requirements.
        warnings:         Non-fatal advisories.
        errors:           Fatal issues.
        compliant:        True if all requirements are satisfiable.
        nfpa_version:     NFPA edition applied.
        classification_rationale: Step-by-step reasoning for audit trail.
    """
    building_level: PathwaySurvivabilityLevel = PathwaySurvivabilityLevel.LEVEL_1
    cable_requirements: List[CableRequirement] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    compliant: bool = True
    nfpa_version: str = "NFPA 72-2022"
    classification_rationale: List[str] = field(default_factory=list)


# ============================================================================
# Engine
# ============================================================================

class PathwaySurvivabilityEngine:
    """NFPA 72-2022 §12.4 Pathway Survivability Classification Engine.

    Classifies a building's fire alarm wiring requirements based on
    occupancy, height, sprinkler status, and evacuation strategy.

    The classification is deterministic — there is only one correct
    answer for any given building specification, defined by NFPA 72.

    Usage::

        engine = PathwaySurvivabilityEngine()
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=True,
            has_voice_evac=True,
        )
        result = engine.classify(spec)
        # result.building_level → LEVEL_2
    """

    # NFPA 72-2022 §12.4.2 survivability level determination rules
    # Ordered from most to least restrictive for correct escalation.

    def classify(self, spec: BuildingSpec) -> SurvivabilityResult:
        """Classify the pathway survivability requirements for a building.

        Args:
            spec: Building specification.

        Returns:
            SurvivabilityResult with classification and cable requirements.
        """
        result = SurvivabilityResult()
        rationale = result.classification_rationale

        # ── Step 1: Determine minimum survivability level ────────────────

        required_level = PathwaySurvivabilityLevel.LEVEL_1  # baseline

        # Rule: Staged evacuation in non-sprinklered → Level 3
        # NFPA 72 §12.4.2(3): Where staging is used and building is NOT
        # fully sprinklered, the highest level of protection is required.
        if spec.evacuation_type == "staged" and not spec.is_sprinklered:
            required_level = PathwaySurvivabilityLevel.LEVEL_3
            rationale.append(
                "§12.4.2(3): Staged evacuation + non-sprinklered → Level 3. "
                "CI cable in 2-hour rated enclosure required."
            )

        # Rule: Partial evacuation → Level 2 minimum
        # NFPA 72 §12.4.2(2): Where partial evacuation is used, at least
        # Level 2 survivability is required so that the non-evacuating
        # floors maintain alarm capability.
        elif spec.evacuation_type == "partial":
            required_level = PathwaySurvivabilityLevel.LEVEL_2
            rationale.append(
                "§12.4.2(2): Partial evacuation → Level 2 minimum. "
                "CI cable or 2-hour rated enclosure required."
            )

        # Rule: High-rise → Level 2 minimum
        # NFPA 72 §12.4.2(2): Buildings >23 m require Level 2 because
        # fire on a lower floor can disable upper-floor alarm circuits
        # if wiring is unprotected.
        if spec.is_high_rise:
            if required_level < PathwaySurvivabilityLevel.LEVEL_2:
                required_level = PathwaySurvivabilityLevel.LEVEL_2
            rationale.append(
                "§12.4.2(2): High-rise (>23 m) → Level 2 minimum. "
                "Unprotected riser cables are a single point of failure."
            )

        # Rule: Voice evacuation → Level 2 minimum
        # NFPA 72 §12.4.2(2): Voice evacuation systems require Level 2
        # because occupants depend on audible instructions, not just
        # horns/strobes. If the voice circuit fails, evacuation fails.
        if spec.has_voice_evac:
            if required_level < PathwaySurvivabilityLevel.LEVEL_2:
                required_level = PathwaySurvivabilityLevel.LEVEL_2
            rationale.append(
                "§12.4.2(2): Voice evacuation → Level 2 minimum. "
                "Voice circuits must survive to instruct occupants."
            )

        # Rule: Detention/correctional → Level 2 minimum
        # NFPA 101 §14/15: Detention occupancies use staged/defend-in-place
        # strategy — occupants cannot self-evacuate.
        if spec.has_detention or spec.occupancy == OccupancyCategory.DETENTION:
            if required_level < PathwaySurvivabilityLevel.LEVEL_2:
                required_level = PathwaySurvivabilityLevel.LEVEL_2
            rationale.append(
                "NFPA 101 §14/15: Detention occupancy → Level 2. "
                "Occupants cannot self-evacuate; alarm must survive."
            )

        # Rule: Health care → Level 2 minimum
        # NFPA 101 §18/19: Health care uses defend-in-place strategy.
        if spec.occupancy == OccupancyCategory.HEALTH_CARE:
            if required_level < PathwaySurvivabilityLevel.LEVEL_2:
                required_level = PathwaySurvivabilityLevel.LEVEL_2
            rationale.append(
                "NFPA 101 §18/19: Health care → Level 2. "
                "Defend-in-place strategy; patients cannot self-evacuate."
            )

        # Rule: Fully sprinklered + full evacuation → Level 1 permitted
        # NFPA 72 §12.4.2(1): In fully sprinklered buildings with
        # simultaneous full evacuation, general-purpose wiring is OK.
        if (spec.is_sprinklered
                and spec.evacuation_type == "full"
                and not spec.is_high_rise
                and not spec.has_voice_evac):
            if required_level > PathwaySurvivabilityLevel.LEVEL_1:
                # Higher level already determined — keep it
                pass
            else:
                required_level = PathwaySurvivabilityLevel.LEVEL_1
                rationale.append(
                    "§12.4.2(1): Fully sprinklered + full evacuation → "
                    "Level 1 sufficient. General-purpose wiring permitted."
                )

        # Rule: Central station monitoring → Level 1 minimum
        # NFPA 72 §12.4.2(1): Central station monitoring requires at
        # least Level 1 (which is always satisfied).
        if spec.has_central_station:
            rationale.append(
                "§12.4.2(1): Central station monitoring → Level 1 minimum "
                "(already satisfied by all levels)."
            )

        result.building_level = required_level

        # ── Step 2: Generate cable requirements per route type ───────────

        result.cable_requirements = self._generate_cable_requirements(
            spec, required_level
        )

        # ── Step 3: Warnings ────────────────────────────────────────────

        if not spec.is_sprinklered and required_level == PathwaySurvivabilityLevel.LEVEL_1:
            result.warnings.append(
                "Non-sprinklered building at Level 1 — verify evacuation "
                "strategy. Partial/staged evacuation requires Level 2+."
            )

        if spec.is_high_rise and not spec.has_voice_evac:
            result.warnings.append(
                "High-rise without voice evacuation — consider adding "
                "voice per NFPA 72 §24.4 for improved life safety."
            )

        if spec.num_floors > 10 and not spec.is_high_rise:
            result.warnings.append(
                f"Building has {spec.num_floors} floors — verify height "
                f"classification. If height >23 m, Level 2 is required."
            )

        # ── Step 4: Compliance check ────────────────────────────────────

        result.compliant = len(result.errors) == 0

        logger.info(
            "PathwaySurvivability: occupancy=%s height=%.1fm sprinklered=%s "
            "level=%s",
            spec.occupancy.value, spec.height_m, spec.is_sprinklered,
            required_level.value,
        )

        return result

    def _generate_cable_requirements(
        self,
        spec: BuildingSpec,
        level: PathwaySurvivabilityLevel,
    ) -> List[CableRequirement]:
        """Generate per-route-type cable requirements based on survivability level.

        Maps the survivability level to specific cable types and enclosure
        requirements for each route type (riser, horizontal, plenum, general).
        """
        requirements: List[CableRequirement] = []

        # ── Riser cables (vertical shafts between floors) ────────────────

        if level == PathwaySurvivabilityLevel.LEVEL_3:
            requirements.append(CableRequirement(
                route_type="riser",
                required_level=level,
                cable_type=CableType.CI,
                in_rated_enclosure=True,
                enclosure_rating_hr=2.0,
                nfpa_reference="NFPA 72-2022 §12.4.2(3)",
                notes="CI cable in 2-hour rated enclosure (highest protection).",
            ))
        elif level == PathwaySurvivabilityLevel.LEVEL_2:
            # Level 2: CI cable OR ordinary cable in 2-hour enclosure.
            # Engineering choice: CI cable is simpler and more reliable.
            requirements.append(CableRequirement(
                route_type="riser",
                required_level=level,
                cable_type=CableType.CI,
                in_rated_enclosure=False,
                enclosure_rating_hr=0.0,
                nfpa_reference="NFPA 72-2022 §12.4.2(2)",
                notes="CI cable satisfies Level 2 without rated enclosure. "
                      "Alternative: FPLR in 2-hour rated shaft.",
            ))
        else:
            requirements.append(CableRequirement(
                route_type="riser",
                required_level=level,
                cable_type=CableType.FPLR,
                in_rated_enclosure=False,
                enclosure_rating_hr=0.0,
                nfpa_reference="NFPA 72-2022 §12.4.2(1)",
                notes="Riser-rated cable (FPLR) sufficient for Level 1.",
            ))

        # ── Horizontal cables (on-floor distribution) ────────────────────

        if level == PathwaySurvivabilityLevel.LEVEL_3:
            requirements.append(CableRequirement(
                route_type="horizontal",
                required_level=level,
                cable_type=CableType.CI,
                in_rated_enclosure=True,
                enclosure_rating_hr=2.0,
                nfpa_reference="NFPA 72-2022 §12.4.2(3)",
                notes="CI cable in 2-hour rated enclosure on every floor.",
            ))
        elif level == PathwaySurvivabilityLevel.LEVEL_2:
            requirements.append(CableRequirement(
                route_type="horizontal",
                required_level=level,
                cable_type=CableType.CI,
                in_rated_enclosure=False,
                enclosure_rating_hr=0.0,
                nfpa_reference="NFPA 72-2022 §12.4.2(2)",
                notes="CI cable for horizontal distribution. "
                      "Alternative: FPL in 2-hour rated conduit.",
            ))
        else:
            requirements.append(CableRequirement(
                route_type="horizontal",
                required_level=level,
                cable_type=CableType.FPL,
                in_rated_enclosure=False,
                enclosure_rating_hr=0.0,
                nfpa_reference="NFPA 72-2022 §12.4.2(1)",
                notes="General-purpose fire alarm cable (FPL) sufficient.",
            ))

        # ── Plenum cables (return air spaces) ────────────────────────────
        # Plenum spaces ALWAYS require FPLP regardless of survivability
        # level, per NEC Article 760.  Additionally, Level 2/3 may
        # require CI protection in plenum spaces.

        plenum_cable = CableType.FPLP  # base requirement
        plenum_enclosure = False
        plenum_rating = 0.0
        plenum_notes = "FPLP required in plenum spaces per NEC Art. 760."

        if level >= PathwaySurvivabilityLevel.LEVEL_2:
            plenum_cable = CableType.CI
            plenum_notes = (
                "CI cable required in plenum spaces for Level 2+ survivability. "
                "FPLP alone does not provide circuit integrity."
            )
            if level == PathwaySurvivabilityLevel.LEVEL_3:
                plenum_enclosure = True
                plenum_rating = 2.0
                plenum_notes = (
                    "CI cable in 2-hour rated enclosure in plenum spaces. "
                    "Level 3 requires maximum protection."
                )

        requirements.append(CableRequirement(
            route_type="plenum",
            required_level=level,
            cable_type=plenum_cable,
            in_rated_enclosure=plenum_enclosure,
            enclosure_rating_hr=plenum_rating,
            nfpa_reference="NEC Art. 760 / NFPA 72 §12.4.2",
            notes=plenum_notes,
        ))

        # ── General cables (non-plenum, non-riser) ──────────────────────

        if level == PathwaySurvivabilityLevel.LEVEL_3:
            requirements.append(CableRequirement(
                route_type="general",
                required_level=level,
                cable_type=CableType.CI,
                in_rated_enclosure=True,
                enclosure_rating_hr=2.0,
                nfpa_reference="NFPA 72-2022 §12.4.2(3)",
                notes="CI cable in 2-hour rated enclosure throughout.",
            ))
        elif level == PathwaySurvivabilityLevel.LEVEL_2:
            requirements.append(CableRequirement(
                route_type="general",
                required_level=level,
                cable_type=CableType.CI,
                in_rated_enclosure=False,
                enclosure_rating_hr=0.0,
                nfpa_reference="NFPA 72-2022 §12.4.2(2)",
                notes="CI cable for general fire alarm circuits.",
            ))
        else:
            requirements.append(CableRequirement(
                route_type="general",
                required_level=level,
                cable_type=CableType.FPL,
                in_rated_enclosure=False,
                enclosure_rating_hr=0.0,
                nfpa_reference="NFPA 72-2022 §12.4.2(1)",
                notes="FPL cable sufficient for Level 1.",
            ))

        return requirements

    def get_required_cable_type(
        self,
        spec: BuildingSpec,
        route_type: str = "general",
    ) -> CableType:
        """Convenience: return the required cable type for a given route.

        Args:
            spec: Building specification.
            route_type: "riser", "horizontal", "plenum", or "general".

        Returns:
            CableType enum value.
        """
        result = self.classify(spec)
        for req in result.cable_requirements:
            if req.route_type == route_type:
                return req.cable_type
        return CableType.FPL  # safe default
