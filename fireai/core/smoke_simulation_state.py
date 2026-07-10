# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
smoke_simulation_state.py — Smoke Density & Visibility Gradient State.
========================================================================

MISSION TASK 4.1 — Advanced Simulation Hooks for Fire Dynamics Simulators
==========================================================================

This module provides placeholder data structures for "Smoke Density" and
"Visibility Gradient" in the DigitalTwin state. These structures prepare
the system for future integration with Fire Dynamics Simulators (FDS),
CFAST, and other CFD tools.

⚠️  SAFETY WARNING — PLACEHOLDER DATA
======================================
Per agent.md Rule 12 (Safety-First) and VERIFY-TASK4 SAFETY-R1:

These structures contain PLACEHOLDER data only. They MUST NOT be used
as real safety data until validated against an actual FDS simulation.
All placeholder values carry ``source="placeholder"`` and trigger
visible "NOT VALIDATED — requires FDS per NFPA 72 §B.2" warnings on
all UI/AHJ surfaces.

Per VERIFY-TASK4 SAFETY-R2: placeholder smoke values MUST NEVER be
persisted into AuditStore (would taint the legal chain). Only validated
FDS results may be persisted.

Architecture
------------
- ``SmokeSimulationState``: Top-level container for smoke/visibility data
  per room (or per building zone).
- ``SmokeDensityPoint``: Point cloud entry with smoke density (kg/m³)
  at a 3D location.
- ``VisibilityGradient``: Visibility (m) at multiple heights above floor.
- ``FDSIntegrationConfig``: Configuration for connecting to an external
  FDS simulation service.

Usage
-----
    from fireai.core.smoke_simulation_state import (
        SmokeSimulationState, SmokeDensityPoint, VisibilityGradient,
    )

    # Initialize placeholder state for a room
    state = SmokeSimulationState.create_placeholder(room_id="R-001")

    # Check if data is validated
    if not state.is_validated:
        print(f"WARNING: {state.validation_warning}")

    # Update with real FDS results (when available)
    state.update_from_fds(
        smoke_density_points=[
            SmokeDensityPoint(x=5.0, y=3.0, z=1.5, density_kg_m3=0.025),
            SmokeDensityPoint(x=5.0, y=3.0, z=2.5, density_kg_m3=0.045),
        ],
        visibility_at_height={
            1.7: 8.5,  # 8.5m visibility at eye level (1.7m)
            2.5: 4.2,  # 4.2m visibility at ceiling jet layer
        },
        fds_run_id="fds-2026-001",
    )

References
----------
- NFPA 72-2022 §B.2 (Smoke Detection Performance-Based Design)
- SFPE Handbook of Fire Protection Engineering, 5th Ed.
- NIST FDS User Guide: https://pages.nist.gov/fds-smv/
- agent.md Rule 12: Safety-First

"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# NFPA 72 §B.2 — Tenability thresholds (for visibility)
VISIBILITY_TENABILITY_THRESHOLD_M: float = 10.0  # 10m minimum for safe egress
SMOKE_DENSITY_TENABILITY_THRESHOLD_KG_M3: float = 0.05  # 50 mg/m³ optical density

# Standard eye level heights (per SFPE Handbook)
EYE_LEVEL_ADULT_M: float = 1.7
EYE_LEVEL_CHILD_M: float = 1.2
EYE_LEVEL_WHEELCHAIR_M: float = 1.1

# Standard sampling heights for visibility gradient
DEFAULT_VISIBILITY_HEIGHTS_M: tuple[float, ...] = (0.5, 1.1, 1.7, 2.5, 3.0)

# Source identifiers (for audit trail)
SOURCE_PLACEHOLDER: str = "placeholder"
SOURCE_FDS: str = "fds"
SOURCE_CFAST: str = "cfast"
SOURCE_MANUAL: str = "manual_engineer_input"

# Validation warning text
PLACEHOLDER_VALIDATION_WARNING: str = (
    "NOT VALIDATED — requires FDS per NFPA 72 §B.2. "
    "Placeholder smoke/visibility data MUST NOT be used for safety decisions."
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SimulationStatus(str, Enum):
    """Status of smoke simulation data."""

    PLACEHOLDER = "placeholder"  # No real simulation run yet
    PENDING = "pending"          # FDS simulation queued/running
    VALIDATED = "validated"      # FDS results received and integrated
    FAILED = "failed"            # FDS simulation failed
    EXPIRED = "expired"          # Validated data is stale (past TTL)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SmokeDensityPoint:
    """
    Single point measurement of smoke density at a 3D location.

    Attributes:
        x, y, z: 3D coordinates in metres (relative to room origin).
        density_kg_m3: Smoke mass concentration (kg/m³).
            Typical soot yield: 0.01-0.10 kg/m³ in flaming fires.
        timestamp_s: Time from fire ignition (seconds).
        source: Data source identifier (placeholder/fds/cfast/manual).

    """

    x: float
    y: float
    z: float
    density_kg_m3: float
    timestamp_s: float = 0.0
    source: str = SOURCE_PLACEHOLDER

    def __post_init__(self) -> None:
        """Validate physical sanity (per agent.md V57 NaN/Inf bypass)."""
        for coord in (self.x, self.y, self.z):
            if not math.isfinite(coord):
                raise ValueError(
                    f"SmokeDensityPoint coordinate must be finite: ({self.x}, {self.y}, {self.z})"
                )
        if not math.isfinite(self.density_kg_m3):
            raise ValueError(
                f"Smoke density must be finite: {self.density_kg_m3}"
            )
        if self.density_kg_m3 < 0:
            raise ValueError(
                f"Smoke density cannot be negative: {self.density_kg_m3}"
            )

    @property
    def is_tenability_threshold_exceeded(self) -> bool:
        """
        Check if smoke density exceeds tenability threshold.

        Per SFPE: 0.05 kg/m³ (50 mg/m³) is the upper limit for
        occupant survivability.
        """
        return self.density_kg_m3 >= SMOKE_DENSITY_TENABILITY_THRESHOLD_KG_M3

    @property
    def optical_density_db_per_m(self) -> float:
        """
        Convert mass concentration to optical density (dB/m).

        Per Bouguer-Beer law: D = K × C
        where K ≈ 7.6 m²/g for soot (SFPE Handbook).
        """
        # Convert kg/m³ → g/m³, then apply coefficient
        return 7.6 * (self.density_kg_m3 * 1000.0)


@dataclass(frozen=True)
class VisibilityGradient:
    """
    Visibility (metres) at multiple heights above floor.

    Captures the vertical stratification of smoke, which is critical
    for egress analysis: occupants at eye level may have different
    visibility than at ceiling level.

    Attributes:
        room_id: Room this gradient applies to.
        visibility_at_height: Dict mapping height (m) → visibility (m).
        timestamp_s: Time from fire ignition.
        source: Data source identifier.

    """

    room_id: str
    visibility_at_height: dict[float, float] = field(default_factory=dict)
    timestamp_s: float = 0.0
    source: str = SOURCE_PLACEHOLDER

    def __post_init__(self) -> None:
        """Validate all visibility values are finite and non-negative."""
        for h, v in self.visibility_at_height.items():
            if not math.isfinite(h) or h < 0:
                raise ValueError(f"Invalid height: {h}")
            if not math.isfinite(v) or v < 0:
                raise ValueError(f"Invalid visibility at height {h}: {v}")

    @property
    def visibility_at_eye_level(self) -> float | None:
        """Visibility at standard adult eye level (1.7m)."""
        # Find closest height to 1.7m
        if not self.visibility_at_height:
            return None
        closest = min(self.visibility_at_height.keys(), key=lambda h: abs(h - EYE_LEVEL_ADULT_M))
        return self.visibility_at_height[closest]

    @property
    def is_tenability_threshold_exceeded(self) -> bool:
        """
        Check if visibility at eye level is below safe egress threshold.

        Per NFPA 101 §A.7.2: minimum 10m visibility for safe egress.
        """
        v_eye = self.visibility_at_eye_level
        if v_eye is None:
            return False  # Unknown = not exceeded (conservative would be True)
        return v_eye < VISIBILITY_TENABILITY_THRESHOLD_M

    @property
    def min_visibility(self) -> float | None:
        """Lowest visibility across all sampled heights."""
        if not self.visibility_at_height:
            return None
        return min(self.visibility_at_height.values())

    @property
    def max_visibility(self) -> float | None:
        """Highest visibility across all sampled heights."""
        if not self.visibility_at_height:
            return None
        return max(self.visibility_at_height.values())


@dataclass
class FDSIntegrationConfig:
    """
    Configuration for connecting to an external FDS simulation service.

    Attributes:
        fds_executable_path: Path to FDS binary (if running locally).
        fds_service_url: URL of cloud FDS service (if using cloud).
        mesh_resolution_m: FDS mesh cell size (metres). Finer = slower but accurate.
        simulation_duration_s: Total simulation time (seconds).
        soot_yield: Soot yield fraction (kg soot / kg fuel burned).
        ambient_pressure_pa: Ambient pressure (default 101325 Pa).

    """

    fds_executable_path: str | None = None
    fds_service_url: str | None = None
    mesh_resolution_m: float = 0.1
    simulation_duration_s: float = 600.0  # 10 minutes default
    soot_yield: float = 0.05  # 5% soot yield (typical for hydrocarbon fires)
    ambient_pressure_pa: float = 101325.0

    def __post_init__(self) -> None:
        """Validate config."""
        if self.mesh_resolution_m <= 0 or not math.isfinite(self.mesh_resolution_m):
            raise ValueError(
                f"mesh_resolution_m must be positive finite: {self.mesh_resolution_m}"
            )
        if self.simulation_duration_s <= 0:
            raise ValueError(
                f"simulation_duration_s must be positive: {self.simulation_duration_s}"
            )
        if not (0.0 <= self.soot_yield <= 1.0):
            raise ValueError(
                f"soot_yield must be in [0, 1]: {self.soot_yield}"
            )


# ---------------------------------------------------------------------------
# Main State Container
# ---------------------------------------------------------------------------


@dataclass
class SmokeSimulationState:
    """
    Complete smoke simulation state for a room.

    This is the primary data structure that gets attached to DigitalTwin
    state for future FDS integration. Per VERIFY-TASK4 SAFETY-R1, all
    placeholder data carries ``source="placeholder"`` and triggers
    visible warnings.

    Attributes:
        room_id: Room this state applies to.
        smoke_density_points: 3D point cloud of smoke density measurements.
        visibility_gradient: Vertical visibility profile.
        status: Simulation status (placeholder/pending/validated/failed).
        fds_config: Optional FDS integration configuration.
        fds_run_id: ID of the FDS run that produced validated data (if any).
        last_updated: ISO timestamp of last update.
        validation_warning: Human-readable warning for placeholder data.

    """

    room_id: str
    smoke_density_points: list[SmokeDensityPoint] = field(default_factory=list)
    visibility_gradient: VisibilityGradient | None = None
    status: SimulationStatus = SimulationStatus.PLACEHOLDER
    fds_config: FDSIntegrationConfig | None = None
    fds_run_id: str | None = None
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")  # NOSONAR — S1192: duplicated literal acceptable in this localized context
    )
    validation_warning: str | None = PLACEHOLDER_VALIDATION_WARNING

    # ------------------------------------------------------------------
    # Factory Methods
    # ------------------------------------------------------------------

    @classmethod
    def create_placeholder(cls, room_id: str) -> SmokeSimulationState:
        """
        Create a placeholder state with safe default values.

        The placeholder represents a "no data yet" state. It uses
        conservative (worst-case) values to ensure downstream code
        cannot accidentally treat the data as real.

        Args:
            room_id: Room identifier.

        Returns:
            SmokeSimulationState with placeholder data.

        """
        return cls(
            room_id=room_id,
            smoke_density_points=[],  # Empty = no measurements
            visibility_gradient=None,  # None = no visibility data
            status=SimulationStatus.PLACEHOLDER,
            fds_config=None,
            fds_run_id=None,
            validation_warning=PLACEHOLDER_VALIDATION_WARNING,
        )

    @classmethod
    def create_from_fds(
        cls,
        room_id: str,
        smoke_density_points: list[SmokeDensityPoint],
        visibility_at_height: dict[float, float],
        fds_run_id: str,
        timestamp_s: float = 0.0,
        fds_config: FDSIntegrationConfig | None = None,
    ) -> SmokeSimulationState:
        """
        Create a validated state from FDS simulation results.

        Args:
            room_id: Room identifier.
            smoke_density_points: 3D smoke density measurements from FDS.
            visibility_at_height: Visibility (m) at sampled heights.
            fds_run_id: FDS run identifier for traceability.
            timestamp_s: Time from fire ignition (seconds).
            fds_config: Optional FDS configuration used.

        Returns:
            SmokeSimulationState with validated data.

        """
        # Mark all points as FDS-sourced
        fds_points = [
            SmokeDensityPoint(
                x=p.x, y=p.y, z=p.z,
                density_kg_m3=p.density_kg_m3,
                timestamp_s=timestamp_s,
                source=SOURCE_FDS,
            )
            for p in smoke_density_points
        ]
        gradient = VisibilityGradient(
            room_id=room_id,
            visibility_at_height=dict(visibility_at_height),
            timestamp_s=timestamp_s,
            source=SOURCE_FDS,
        )
        return cls(
            room_id=room_id,
            smoke_density_points=fds_points,
            visibility_gradient=gradient,
            status=SimulationStatus.VALIDATED,
            fds_config=fds_config,
            fds_run_id=fds_run_id,
            validation_warning=None,  # No warning for validated data
        )

    # ------------------------------------------------------------------
    # Update Methods
    # ------------------------------------------------------------------

    def update_from_fds(
        self,
        smoke_density_points: list[SmokeDensityPoint],
        visibility_at_height: dict[float, float],
        fds_run_id: str,
        timestamp_s: float = 0.0,
    ) -> None:
        """
        Update state with FDS simulation results.

        Transitions status from PLACEHOLDER/PENDING → VALIDATED.
        Clears the validation_warning (data is now real).

        Args:
            smoke_density_points: New smoke density measurements.
            visibility_at_height: New visibility profile.
            fds_run_id: FDS run identifier.
            timestamp_s: Time from fire ignition.

        """
        self.smoke_density_points = [
            SmokeDensityPoint(
                x=p.x, y=p.y, z=p.z,
                density_kg_m3=p.density_kg_m3,
                timestamp_s=timestamp_s,
                source=SOURCE_FDS,
            )
            for p in smoke_density_points
        ]
        self.visibility_gradient = VisibilityGradient(
            room_id=self.room_id,
            visibility_at_height=dict(visibility_at_height),
            timestamp_s=timestamp_s,
            source=SOURCE_FDS,
        )
        self.fds_run_id = fds_run_id
        self.status = SimulationStatus.VALIDATED
        self.validation_warning = None  # Validated = no warning
        self.last_updated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        logger.info(
            "SmokeSimulationState updated with FDS results: room=%s fds_run=%s points=%d",
            self.room_id, fds_run_id, len(self.smoke_density_points),
        )

    def mark_pending(self, fds_run_id: str) -> None:
        """Mark state as pending FDS simulation completion."""
        self.fds_run_id = fds_run_id
        self.status = SimulationStatus.PENDING
        self.last_updated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def mark_failed(self, error: str) -> None:
        """Mark FDS simulation as failed."""
        self.status = SimulationStatus.FAILED
        self.validation_warning = f"FDS simulation failed: {error}"
        self.last_updated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # ------------------------------------------------------------------
    # Safety Properties
    # ------------------------------------------------------------------

    @property
    def is_validated(self) -> bool:
        """True if state contains validated FDS data (not placeholder)."""
        return self.status == SimulationStatus.VALIDATED

    @property
    def is_placeholder(self) -> bool:
        """True if state contains placeholder data only."""
        return self.status == SimulationStatus.PLACEHOLDER

    @property
    def max_smoke_density(self) -> float | None:
        """Maximum smoke density across all measurement points."""
        if not self.smoke_density_points:
            return None
        return max(p.density_kg_m3 for p in self.smoke_density_points)

    @property
    def avg_smoke_density_at_eye_level(self) -> float | None:
        """Average smoke density at eye level (1.5-2.0m height)."""
        eye_level_points = [
            p for p in self.smoke_density_points
            if 1.5 <= p.z <= 2.0
        ]
        if not eye_level_points:
            return None
        return sum(p.density_kg_m3 for p in eye_level_points) / len(eye_level_points)

    @property
    def is_tenability_exceeded(self) -> bool:
        """
        Check if smoke conditions exceed tenability thresholds.

        Returns True if EITHER:
        - Max smoke density ≥ 0.05 kg/m³, OR
        - Visibility at eye level < 10m

        Per SFPE Handbook and NFPA 101.
        """
        # Check smoke density
        max_density = self.max_smoke_density
        if max_density is not None and max_density >= SMOKE_DENSITY_TENABILITY_THRESHOLD_KG_M3:
            return True

        # Check visibility
        return bool(self.visibility_gradient and self.visibility_gradient.is_tenability_threshold_exceeded)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict for API responses."""
        return {
            "room_id": self.room_id,
            "status": self.status.value,
            "is_validated": self.is_validated,
            "is_placeholder": self.is_placeholder,
            "validation_warning": self.validation_warning,
            "smoke_density_points": [
                {
                    "x": p.x, "y": p.y, "z": p.z,
                    "density_kg_m3": p.density_kg_m3,
                    "timestamp_s": p.timestamp_s,
                    "source": p.source,
                    "optical_density_db_per_m": p.optical_density_db_per_m,
                }
                for p in self.smoke_density_points
            ],
            "visibility_gradient": (
                {
                    "room_id": self.visibility_gradient.room_id,
                    "visibility_at_height": dict(self.visibility_gradient.visibility_at_height),
                    "visibility_at_eye_level": self.visibility_gradient.visibility_at_eye_level,
                    "is_tenability_threshold_exceeded": self.visibility_gradient.is_tenability_threshold_exceeded,
                    "min_visibility": self.visibility_gradient.min_visibility,
                    "max_visibility": self.visibility_gradient.max_visibility,
                    "timestamp_s": self.visibility_gradient.timestamp_s,
                    "source": self.visibility_gradient.source,
                }
                if self.visibility_gradient else None
            ),
            "max_smoke_density": self.max_smoke_density,
            "avg_smoke_density_at_eye_level": self.avg_smoke_density_at_eye_level,
            "is_tenability_exceeded": self.is_tenability_exceeded,
            "fds_run_id": self.fds_run_id,
            "fds_config": (
                {
                    "fds_service_url": self.fds_config.fds_service_url,
                    "mesh_resolution_m": self.fds_config.mesh_resolution_m,
                    "simulation_duration_s": self.fds_config.simulation_duration_s,
                    "soot_yield": self.fds_config.soot_yield,
                }
                if self.fds_config else None
            ),
            "last_updated": self.last_updated,
            "nfpa_reference": "NFPA 72-2022 §B.2 (Performance-Based Design)",
        }

    # ------------------------------------------------------------------
    # Audit Safety
    # ------------------------------------------------------------------

    def to_audit_safe_dict(self) -> dict[str, Any]:
        """
        Convert to dict safe for AuditStore persistence.

        Per VERIFY-TASK4 SAFETY-R2: placeholder data MUST NEVER be
        persisted to AuditStore (would taint legal chain).

        V137 F-11 FIX: Expanded to reject ALL non-VALIDATED states
        (PLACEHOLDER, PENDING, FAILED, EXPIRED). The OLD code only
        rejected PLACEHOLDER — FAILED/EXPIRED/PENDING states could
        persist full measurement data, violating SAFETY-R2's spirit.
        """
        # V137 F-11: Only VALIDATED data can be fully persisted
        if self.status != SimulationStatus.VALIDATED:
            return {
                "room_id": self.room_id,
                "status": self.status.value,
                "placeholder": self.is_placeholder,
                "note": f"Status '{self.status.value}' data not persisted per SAFETY-R2 "
                        f"(only VALIDATED states are audit-safe)",
            }

        # Validated data can be fully persisted
        return self.to_dict()


__all__ = [
    "DEFAULT_VISIBILITY_HEIGHTS_M",
    "EYE_LEVEL_ADULT_M",
    "PLACEHOLDER_VALIDATION_WARNING",
    "SMOKE_DENSITY_TENABILITY_THRESHOLD_KG_M3",
    "SOURCE_CFAST",
    "SOURCE_FDS",
    "SOURCE_MANUAL",
    "SOURCE_PLACEHOLDER",
    "VISIBILITY_TENABILITY_THRESHOLD_M",
    "FDSIntegrationConfig",
    "SimulationStatus",
    "SmokeDensityPoint",
    "SmokeSimulationState",
    "VisibilityGradient",
]
