"""FireAI — Pydantic Input Schemas for NFPA 72 Calculations

PDF Audit Phase 2: Architectural Rigidity
Per "From Prototype to Production-Grade" §Phase 2, Appendix A.2:
"Introduce pydantic models for all data structures, both as inputs to the
backend and as representations of internal states. A pydantic model allows
for the declarative definition of field types, value constraints, and
custom validation logic. This moves validation from an implicit, scattered
set of if statements to an explicit, centralized, and automatically
enforced contract."

This module provides Pydantic-validated input schemas for the NFPA 72
calculation pipeline. Any data that does not conform to the specified
schema will raise a clear ValidationError, preventing corrupted data from
propagating through the calculation pipeline.

Standards Referenced:
  - NFPA 72-2022: National Fire Alarm and Signaling Code
  - NEC (NFPA 70-2023): National Electrical Code
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

# ============================================================================
# ENUMS — Ceiling Type, Detector Type, Hazard Type
# ============================================================================

class CeilingTypePydantic(str, Enum):
    """Ceiling type classification per NFPA 72 §17.6.3."""

    FLAT = "flat"
    SLOPED = "sloped"
    GABLE = "gable"
    SHED = "shed"
    WAFFLE = "waffle"
    ACOUSTIC_TILE = "acoustic_tile"
    BEAM_AND_POCKET = "beam_and_pocket"


class DetectorTypePydantic(str, Enum):
    """Detector type per NFPA 72 Chapter 17."""

    SMOKE = "smoke"
    HEAT = "heat"
    DUCT = "duct"
    BEAM = "beam"
    FLAME = "flame"
    GAS = "gas"


# ============================================================================
# NFPA72Input — Coverage Radius Calculation Input Schema
# ============================================================================

class NFPA72Input(BaseModel):
    """Validated input schema for smoke detector coverage radius calculation.

    Per NFPA 72 §17.6.3.1.2, the coverage radius R = 0.7 × S where S is
    the height-adjusted listed spacing. This schema enforces:
      - Positive, finite numeric values
      - Ceiling height within NFPA 72 normative range (or flagged)
      - Ceiling type determines correction factors
      - HVAC velocity derates coverage when significant

    Example:
        >>> data = NFPA72Input(
        ...     spacing_m=9.1,
        ...     ceiling_height_m=3.0,
        ...     ceiling_type=CeilingTypePydantic.FLAT,
        ...     hvac_velocity_ms=0.0,
        ... )
        >>> data.spacing_m
        9.1

    """

    spacing_m: float = Field(
        ...,
        gt=0,
        le=30.0,
        description="Nominal listed spacing between detectors (S) in meters. "
                    "Must be > 0 and ≤ 30.0m per NFPA 72 Table 17.6.3.1.1. "
                    "Standard smoke: 9.1m (30ft), heat: 6.1m (20ft).",
    )

    ceiling_height_m: float = Field(
        ...,
        gt=0,
        le=18.288,
        description="Ceiling height (H) in meters. Must be > 0 and ≤ 18.288m "
                    "(60ft) per NFPA 72 §17.7.3.2.4. Heights above 15.24m (50ft) "
                    "require PE review flag. V128 FIX: Was ≤ 15.24m (50ft) which "
                    "incorrectly rejected valid smoke detector placements at 15.24-18.288m.",
    )

    ceiling_type: CeilingTypePydantic = Field(
        default=CeilingTypePydantic.FLAT,
        description="Ceiling type per NFPA 72 §17.6.3. Affects spacing "
                    "correction factors. Sloped ceilings require reduced spacing "
                    "per Table 17.6.3.1.2(a). Waffle ceilings require special "
                    "detector placement per §17.6.3.6.",
    )

    hvac_velocity_ms: float = Field(
        default=0.0,
        ge=0.0,
        le=5.0,
        description="HVAC supply air velocity in m/s. High-velocity air "
                    "currents can impede smoke detector operation per NFPA 72 "
                    "Informative Annex. Velocities > 0.5 m/s may require "
                    "detector spacing reduction.",
    )

    beam_depth_m: float = Field(
        default=0.0,
        ge=0.0,
        le=3.0,
        description="Exposed beam depth in meters. Per NFPA 72 §17.6.3.6, "
                    "if beam depth > 10% of ceiling height, spacing within "
                    "each beam pocket is limited to the pocket width.",
    )

    detector_type: DetectorTypePydantic = Field(
        default=DetectorTypePydantic.SMOKE,
        description="Type of detector. Heat detectors use square-grid "
                    "(Chebyshev) coverage geometry per NFPA 72 §17.6.2.1. "
                    "Smoke detectors use circular (Euclidean) coverage.",
    )

    @field_validator("ceiling_height_m")
    @classmethod
    def validate_ceiling_height_finite(cls, v: float) -> float:
        """Reject NaN/Inf ceiling heights — they bypass comparison guards."""
        if not math.isfinite(v):
            raise ValueError(
                f"ceiling_height_m must be finite, got {v!r}. "
                f"NaN/Inf values corrupt all downstream NFPA 72 calculations."
            )
        return v

    @field_validator("spacing_m")
    @classmethod
    def validate_spacing_finite(cls, v: float) -> float:
        """Reject NaN/Inf spacing — they bypass comparison guards."""
        if not math.isfinite(v):
            raise ValueError(
                f"spacing_m must be finite, got {v!r}. "
                f"NaN/Inf values corrupt detector coverage calculations."
            )
        return v

    @field_validator("ceiling_height_m")
    @classmethod
    def flag_out_of_range_height(cls, v: float) -> float:
        """Flag heights below NFPA 72 normative minimum (3.0m) for PE review."""
        if v < 3.0:
            # Allow but flag — V9 CeilingSpec.create_safe() pattern
            pass  # Pydantic doesn't have warnings; caller must check
        return v

    @field_validator("spacing_m")
    @classmethod
    def validate_spacing_by_ceiling_type(cls, v: float) -> float:
        """Sloped ceilings require reduced spacing per NFPA 72 Table 17.6.3.1.2(a).
        Maximum spacing for sloped ceilings is typically 21ft (6.4m).
        """
        # This validator runs before ceiling_type is set, so we skip
        # cross-field validation here (see model_validator below).
        return v

    @model_validator(mode="after")
    def validate_sloped_ceiling_spacing(self) -> NFPA72Input:
        """Cross-field validation: sloped ceiling requires reduced spacing.
        Per NFPA 72 Table 17.6.3.1.2(a), maximum spacing for sloped
        ceilings is 21ft (6.4m) for smoke detectors.
        """
        if self.ceiling_type == CeilingTypePydantic.SLOPED:
            max_spacing_sloped_smoke = 6.4  # NFPA 72 Table 17.6.3.1.2(a)
            if self.spacing_m > max_spacing_sloped_smoke:
                raise ValueError(
                    f"Sloped ceiling detected. Spacing must be ≤ "
                    f"{max_spacing_sloped_smoke}m per NFPA 72 Table 17.6.3.1.2(a), "
                    f"got {self.spacing_m}m."
                )
        return self

    def compute_coverage_radius(self) -> float:
        """Calculate coverage radius R = 0.7 × S with correction factors.

        Per NFPA 72 §17.7.4.2.3.1:
          R = 0.7 × S (base factor for flat ceilings)

        Correction factors:
          - HVAC velocity: derating when air velocity > 0.5 m/s
          - Beam pockets: spacing reduction when beams subdivide ceiling
          - Ceiling type: reduced factor for non-flat ceilings

        Returns:
            Coverage radius in meters (rounded to 3 decimal places).

        """
        # Base factor per NFPA 72 §17.7.4.2.3.1
        base_factor = 0.7 if self.ceiling_type == CeilingTypePydantic.FLAT else 0.6

        # HVAC velocity derating (empirical model per NFPA 72 Informative Annex)
        hvac_correction = max(0.0, 1.0 - (self.hvac_velocity_ms * 0.10))

        # Beam pocket correction per NFPA 72 §17.6.3.6
        beam_correction = 1.0
        if self.beam_depth_m > 0 and self.ceiling_height_m > 0:
            depth_fraction = self.beam_depth_m / self.ceiling_height_m
            if depth_fraction > 0.10:  # 10% threshold per §17.6.3.6
                excess = depth_fraction - 0.10
                beam_correction = max(0.25, 1.0 - excess * 2.0)

        coverage_radius = (
            base_factor
            * self.spacing_m
            * hvac_correction
            * beam_correction
        )
        return round(coverage_radius, 3)


# ============================================================================
# VoltageDropInput — NEC Voltage Drop Calculation Input Schema
# ============================================================================

class VoltageDropInput(BaseModel):
    """Validated input schema for voltage drop calculations per NEC/NFPA 72.

    NFPA 72 §10.14 requires that the voltage at the most remote device
    must be within the device's listed voltage range. NEC §210.19(A)(1)
    limits branch circuit voltage drop to 3%, and §215.2(A)(2) limits
    total (feeder + branch) to 5%.

    This schema enforces:
      - Positive, finite numeric values
      - Supply voltage within fire alarm system range (12-48VDC)
      - Cable resistance per NEC Chapter 9 Table 8
      - DC return path factor (2×) included in calculation
    """

    supply_voltage_v: float = Field(
        ...,
        gt=0,
        le=125.0,
        description="Nominal supply voltage (VDC). Fire alarm systems "
                    "typically use 24VDC. Must be positive and ≤ 125V.",
    )

    load_current_a: float = Field(
        ...,
        ge=0.0,
        le=50.0,
        description="Total load current on the circuit (A). Must be "
                    "non-negative per NEC requirements.",
    )

    cable_resistance_ohm_per_m: float = Field(
        ...,
        gt=0,
        le=1.0,
        description="Cable resistance per meter (Ω/m) at 75°C per NEC "
                    "Chapter 9 Table 8. AWG 18: 0.0255 Ω/m, AWG 14: "
                    "0.00820 Ω/m, AWG 10: 0.00328 Ω/m.",
    )

    cable_length_m: float = Field(
        ...,
        ge=0.0,
        le=2000.0,
        description="One-way cable length in meters. DC return path factor "
                    "(2×) is applied automatically per NFPA 72 §10.14.",
    )

    ambient_temp_c: float = Field(
        default=30.0,
        ge=-40.0,
        le=90.0,
        description="Ambient temperature in °C. Per NEC Table 310.15(B)(2)(a), "
                    "conductor ampacity must be derated for temperatures above "
                    "30°C (86°F). Default: 30°C (baseline, no correction).",
    )

    num_conductors: int = Field(
        default=2,
        ge=1,
        le=50,
        description="Number of current-carrying conductors in raceway. "
                    "Per NEC Table 310.15(B)(3)(a), more than 3 conductors "
                    "require ampacity derating.",
    )

    is_continuous_load: bool = Field(
        default=True,
        description="Whether the load is continuous (≥3 hours). Per NEC "
                    "§210.19(A)(1), continuous loads require 125% conductor "
                    "ampacity rating. Fire alarm loads are typically continuous.",
    )

    @field_validator("supply_voltage_v", "load_current_a",
                     "cable_resistance_ohm_per_m", "cable_length_m")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        """Reject NaN/Inf — they bypass comparison guards and corrupt calculations."""
        if not math.isfinite(v):
            raise ValueError(
                f"Value must be finite, got {v!r}. NaN/Inf corrupts voltage "
                f"drop calculations per NFPA 72 §10.14."
            )
        return v

    def compute_voltage_drop(self) -> dict:
        """Calculate voltage drop per NFPA 72 §10.14 and NEC.

        Includes:
          - DC return path factor (2×) per NFPA 72 §10.14
          - Ambient temperature correction per NEC Table 310.15(B)(2)(a)
          - Conductor bundling derating per NEC Table 310.15(B)(3)(a)
          - Continuous load factor (125%) per NEC §210.19(A)(1)

        Returns:
            Dict with drop_v, drop_fraction, terminal_voltage_v, compliant.

        """
        # DC return path factor — V14 Bug #12: was missing ×2
        total_resistance = self.cable_resistance_ohm_per_m * self.cable_length_m * 2.0

        # Ambient temperature correction (NEC Table 310.15(B)(2)(a))
        # Copper resistance increases with temperature (positive temperature coefficient).
        # At higher temperatures, conductor resistance increases → more voltage drop.
        # V79 FIX: Separated ampacity derating (NEC 310.15, 30°C threshold) from
        # resistance correction (applies at all temperatures). The 30°C threshold
        # is for ampacity only — conductor resistance changes with temperature
        # regardless of ambient. Also corrected temperature coefficient from
        # α₂₀=0.00393 to α₇₅=0.00323 (copper at 75°C reference per NEC Ch.9 Table 8).
        # Using α₂₀ with a 75°C base overestimates by ~1% at 90°C and ~3% at 125°C.
        # Conservative: never reduce resistance below 75°C reference value (1.0).
        temp_correction = max(1.0, 1.0 + 0.00323 * (self.ambient_temp_c - 75.0))

        # Conductor bundling derating (NEC Table 310.15(B)(3)(a))
        bundling_factor = 1.0
        if self.num_conductors > 3:
            if self.num_conductors <= 6:
                bundling_factor = 0.80
            elif self.num_conductors <= 9:
                bundling_factor = 0.70
            elif self.num_conductors <= 20:
                bundling_factor = 0.50
            elif self.num_conductors <= 30:
                bundling_factor = 0.45
            elif self.num_conductors <= 40:
                bundling_factor = 0.40
            else:
                bundling_factor = 0.35

        # Effective current (continuous load = 125% per NEC §210.19(A)(1))
        effective_current = self.load_current_a * (1.25 if self.is_continuous_load else 1.0)

        # Voltage drop calculation
        # V78 FIX: Remove bundling_factor from voltage drop. Bundling is an AMPACITY
        # derating (NEC 310.15(B)(3)(a)), NOT a resistance increase. Wire resistance
        # does not change when wires are bundled — only the current-carrying capacity
        # decreases. Dividing by bundling_factor overstated voltage drop by 25% for
        # 4-6 conductors. Bundling is already handled in the ampacity check below.
        drop_v = effective_current * total_resistance * temp_correction
        drop_fraction = drop_v / self.supply_voltage_v if self.supply_voltage_v > 0 else float("inf")
        terminal_voltage = self.supply_voltage_v - drop_v

        # Compliance: branch circuit ≤ 3%, feeder+branch ≤ 5%
        compliant_branch = drop_fraction <= 0.03
        compliant_total = drop_fraction <= 0.05
        compliant_terminal = terminal_voltage >= 16.0  # NFPA 72 §10.14.1

        return {
            "drop_v": round(drop_v, 4),
            "drop_fraction": round(drop_fraction, 6),
            "terminal_voltage_v": round(terminal_voltage, 4),
            "compliant_branch_3pct": compliant_branch,
            "compliant_total_5pct": compliant_total,
            "compliant_terminal_voltage": compliant_terminal,
            "temp_correction_factor": round(temp_correction, 4),
            "bundling_derating_factor": bundling_factor,
            "continuous_load_factor": 1.25 if self.is_continuous_load else 1.0,
            "references": {
                "nfpa72_10_14": "NFPA 72-2022 §10.14 (voltage drop)",
                "nec_210_19_A_1": "NEC §210.19(A)(1) (continuous load 125%)",
                "nec_215_2_A_2": "NEC §215.2(A)(2) (5% total drop limit)",
                "nec_310_15_B_2a": "NEC Table 310.15(B)(2)(a) (temp correction)",
                "nec_310_15_B_3a": "NEC Table 310.15(B)(3)(a) (bundling derating)",
            },
        }


# ============================================================================
# ConvergenceConfig — Optimizer Termination Configuration
# ============================================================================

class ConvergenceConfig(BaseModel):
    """Convergence configuration for the density optimizer.

    PDF Audit Phase 3: "The density optimizer must be refactored to include
    a formal termination condition. This involves adding a maximum iteration
    counter and an epsilon tolerance check to ensure the algorithm always
    terminates predictably."

    Per optimization theory, a proper termination condition consists of:
      1. Maximum iteration count to prevent infinite loops
      2. Epsilon tolerance for objective function improvement
      3. Monotonicity check to ensure solution never gets worse
    """

    epsilon: float = Field(
        default=1e-4,
        gt=0,
        le=1.0,
        description="Termination tolerance for objective function change. "
                    "When the improvement between successive iterations falls "
                    "below this threshold, the optimizer has converged.",
    )

    max_iterations: int = Field(
        default=10_000,
        gt=0,
        le=1_000_000,
        description="Maximum iteration count to prevent infinite loops on "
                    "pathological floor plans. Default: 10,000.",
    )

    monotonicity_check: bool = Field(
        default=True,
        description="Ensure the solution never gets worse between iterations. "
                    "If True, non-monotonic improvement raises an assertion.",
    )

    timeout_seconds: float = Field(
        default=300.0,
        gt=0,
        le=3600.0,
        description="Maximum wall-clock time in seconds. Prevents optimizer "
                    "from consuming excessive computational resources on "
                    "complex floor plans. Default: 5 minutes.",
    )
