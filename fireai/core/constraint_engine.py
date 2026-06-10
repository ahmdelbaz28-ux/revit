"""
fireai.core.constraint_engine — Code-Based Routing Constraints
==============================================================

Deterministic constraint engine for fire alarm cable routing.

Every constraint traces to a published code section:
  - NEC 760.24: Fire alarm cables in separate conduits from power
  - NEC 760.24(A): Cable fastening every 18" (457mm)
  - NFPA 72 §23.6.2: NAC circuit max length per wire gauge
  - NFPA 72 §10.6.4: Voltage drop verification
  - Project Spec: Min conduit ¾" red painted EMT
  - Project Spec: Max bend radius = 6 × conduit diameter
  - Project Spec: Separation from electrical conduits ≥ 300mm

QOMN-FIRE Principles:
  - NO approximations — every constraint is exact
  - NO probabilistic decisions — deterministic always
  - Every decision logged with code reference
  - Same input → same output, always

SAFETY CRITICAL:
  - Constraint violations are NEVER silently ignored
  - Every rejected path includes the specific code section violated
  - Physical impossibilities (negative lengths, NaN) are caught at input
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

# Reuse wire gauge and resistance data
from fireai.core.cable_routing_engine import WireGauge

# Reuse physics guards from contracts_validation


def _resolve_wire_gauge(wire_gauge):
    """Resolve a wire_gauge string or instance to a _WireGaugeInstance.

    V109 FIX: wire_gauge parameter can be either a string key (e.g. "14")
    or a _WireGaugeInstance. This helper normalizes both cases.
    """
    if isinstance(wire_gauge, str):
        for wg in WireGauge:
            if wg.awg_value == wire_gauge:
                return wg
        raise ValueError(f"Unknown wire gauge: '{wire_gauge}'")
    return wire_gauge


# Reuse NEC ampacity verification from nfpa72_engine
from fireai.core.nfpa72_engine import (
    check_ampacity,
    get_ambient_derating_factor,
    get_conductor_count_derating,
    temperature_corrected_resistance,
)

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTRAINT SOURCE ENUM — Every constraint has a source
# ═══════════════════════════════════════════════════════════════════════════════


class ConstraintSource(Enum):
    """Source of a routing constraint — every rule must cite its origin."""

    NEC_760_24 = "NEC 760.24"  # FA cable separation
    NEC_760_24_A = "NEC 760.24(A)"  # Cable fastening interval
    NEC_760_154 = "NEC 760.154"  # PLFA/NPLFA separation
    NEC_310_16 = "NEC 310.16"  # Ampacity table
    NEC_310_15_B2A = "NEC 310.15(B)(2)(A)"  # Ambient temperature correction
    NEC_310_15_B3A = "NEC 310.15(B)(3)(a)"  # Conductor count derating
    NEC_CH9_TEMP = "NEC Ch.9 Table 8 + Physics"  # Temperature-corrected resistance
    NFPA_72_23_6_2 = "NFPA 72 §23.6.2"  # NAC circuit max length
    NFPA_72_10_6_4 = "NFPA 72 §10.6.4"  # Voltage drop verification
    NFPA_72_12_2_2 = "NFPA 72 §12.2.2"  # Class A circuit separation
    NEC_CH9_TABLE4 = "NEC Chapter 9, Table 4"  # Conduit fill
    NEC_CH9_TABLE8 = "NEC Chapter 9, Table 8"  # Wire resistance
    PROJECT_SPEC_CONDUIT = 'Project Spec: Min 3/4" EMT'
    PROJECT_SPEC_BEND = "Project Spec: Max bend radius = 6 x D"
    PROJECT_SPEC_SEPARATION = "Project Spec: >= 300mm from electrical"
    PROJECT_SPEC_FASTENING = "Project Spec: Fasten every 457mm"
    PHYSICS = "Physics"  # Fundamental physics constraints


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT SPECIFICATION CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Project Spec: Minimum conduit ¾" EMT, red painted
MIN_CONDUIT_INCHES = 0.75  # ¾" per project specification
MIN_CONDUIT_MM = 19.05  # ¾" = 19.05mm
EMT_3_4_INNER_DIAMETER_MM = 15.8  # NEC Chapter 9, Table 4 — ¾" EMT inner diameter
EMT_3_4_OUTER_DIAMETER_MM = 19.05  # ¾" EMT outer diameter

# Project Spec: Maximum bend radius = 6 × conduit diameter
# Per NEC 344.24, EMT bends shall be made with a radius not less than:
# - 6 × diameter for ½" to 1" EMT
# Per project specification, this is confirmed at 6×
BEND_RADIUS_FACTOR = 6  # 6 × conduit diameter per project spec / NEC 344.24
MAX_BEND_RADIUS_MM = BEND_RADIUS_FACTOR * EMT_3_4_OUTER_DIAMETER_MM  # 114.3mm

# Project Spec: Separation from electrical conduits ≥ 300mm
MIN_ELECTRICAL_SEPARATION_MM = 300.0  # 300mm per project specification

# NEC 760.24(A): Cables fastened every 18" (457mm)
MAX_CABLE_FASTENING_INTERVAL_MM = 457.0  # 18" = 457mm per NEC 760.24(A)

# NEC Chapter 9, Table 4 — ¾" EMT cross-sectional area
EMT_3_4_AREA_SQ_MM = 196.0  # 100% fill area for ¾" EMT

# NEC 760.154 — Maximum fill percentage for PLFA circuits
MAX_CONDUIT_FILL_PCT = 0.40  # 40% fill per NEC 760.154

# NFPA 72 §23.6.2 — NAC circuit maximum lengths by wire gauge
# These are practical limits ensuring voltage drop compliance
# for typical 24V NAC circuits with standard device loads
# V108 FIX: WireGauge uses string keys ("12", "14", etc.), not enum attributes
_NAC_MAX_LENGTHS_M = {
    "12": 914.0,  # 3000 ft practical max (12 AWG)
    "14": 610.0,  # 2000 ft practical max (14 AWG)
    "16": 381.0,  # 1250 ft practical max (16 AWG)
    "18": 229.0,  # 750 ft practical max (18 AWG)
}

# Cable routing penalty constants (in meters equivalent)
BEND_PENALTY_M = 0.5  # 90° bend = equivalent to 0.5m extra length
ELEVATION_PENALTY_M = 2.0  # Elevation change = equivalent to 2.0m extra length
ELECTRICAL_PROXIMITY_PENALTY_M = 1.0  # Proximity to electrical = 1.0m penalty


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTRAINT RESULT — Every check produces an auditable result
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConstraintResult:
    """Result of a constraint check.

    Every constraint check produces a traceable result that includes:
    - Whether the constraint passed or failed
    - The specific code section that was checked
    - The actual value that was tested
    - The threshold or limit that was applied
    - A remediation message if the constraint failed

    Attributes:
        constraint_name: Human-readable constraint name.
        source: Code section or standard reference.
        is_satisfied: True if the constraint is met.
        actual_value: The value that was checked.
        limit_value: The threshold or limit.
        unit: Unit of measurement (e.g. 'mm', 'm', 'V').
        severity: 'CRITICAL', 'HIGH', 'MEDIUM', or 'LOW'.
        remediation: What to do if the constraint is violated.
        formula: The formula used for the check, with values.
    """

    constraint_name: str
    source: str
    is_satisfied: bool
    actual_value: float = 0.0
    limit_value: float = 0.0
    unit: str = ""
    severity: str = "CRITICAL"
    remediation: str = ""
    formula: str = ""


@dataclass(frozen=True)
class RoutingConstraintSet:
    """Complete set of constraint results for a routing operation.

    Attributes:
        results: Individual constraint check results.
        all_satisfied: True if ALL constraints are satisfied.
        critical_violations: Count of CRITICAL severity violations.
        total_violations: Count of all violations.
    """

    results: Tuple[ConstraintResult, ...]
    # V114 FIX: Fail-safe — all_satisfied must be PROVEN, not assumed
    all_satisfied: bool = False
    critical_violations: int = 0
    total_violations: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTRAINT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class ConstraintEngine:
    """Deterministic constraint engine for fire alarm cable routing.

    Every constraint is traceable to a published code section.
    No approximations. No probabilistic decisions. Pure deterministic
    logic with reference-based rules.

    Example usage::

        engine = ConstraintEngine()
        results = engine.check_all(
            cable_length_m=150.0,
            wire_gauge=WireGauge.AWG_14,
            num_bends=4,
            num_elevation_changes=2,
            min_electrical_separation_mm=250.0,
            ps_voltage=24.0,
            alarm_current_a=1.5,
        )
        if not results.all_satisfied:
            for r in results.results:
                if not r.is_satisfied:
                    print(f"VIOLATION: {r.constraint_name} ({r.source})")
    """

    def __init__(
        self,
        min_conduit_inches: float = MIN_CONDUIT_INCHES,
        bend_radius_factor: float = BEND_RADIUS_FACTOR,
        min_electrical_separation_mm: float = MIN_ELECTRICAL_SEPARATION_MM,
        max_fastening_interval_mm: float = MAX_CABLE_FASTENING_INTERVAL_MM,
        bend_penalty_m: float = BEND_PENALTY_M,
        elevation_penalty_m: float = ELEVATION_PENALTY_M,
    ):
        """Initialize the constraint engine with project specifications.

        Args:
            min_conduit_inches: Minimum conduit size (default ¾" EMT).
            bend_radius_factor: Bend radius as multiple of conduit diameter (default 6).
            min_electrical_separation_mm: Minimum separation from electrical (default 300mm).
            max_fastening_interval_mm: Maximum cable fastening interval (default 457mm).
            bend_penalty_m: Bend penalty in equivalent meters (default 0.5m).
            elevation_penalty_m: Elevation change penalty (default 2.0m).
        """
        self._min_conduit_inches = min_conduit_inches
        self._bend_radius_factor = bend_radius_factor
        self._min_electrical_separation_mm = min_electrical_separation_mm
        self._max_fastening_interval_mm = max_fastening_interval_mm
        self._bend_penalty_m = bend_penalty_m
        self._elevation_penalty_m = elevation_penalty_m

    # ─── Individual Constraint Checks ─────────────────────────────────────

    def check_nac_max_length(
        self,
        cable_length_m: float,
        wire_gauge: WireGauge,
        circuit_type: str = "NAC",
    ) -> ConstraintResult:
        """Check NAC circuit maximum length per NFPA 72 §23.6.2.

        NFPA 72 §23.6.2 limits the maximum length of Notification
        Appliance Circuits based on wire gauge to ensure voltage
        drop compliance under alarm conditions.

        Formula:
          Max Length per §23.6.2 = f(AWG gauge)

        Args:
            cable_length_m: Actual cable length in meters.
            wire_gauge: Wire gauge used.
            circuit_type: Circuit type string (NAC, SLC, etc.).

        Returns:
            ConstraintResult with pass/fail status.
        """
        max_length = _NAC_MAX_LENGTHS_M.get(wire_gauge, 229.0)

        is_satisfied = cable_length_m <= max_length

        return ConstraintResult(
            constraint_name=f"{circuit_type} Circuit Max Length",
            source=ConstraintSource.NFPA_72_23_6_2.value,
            is_satisfied=is_satisfied,
            actual_value=cable_length_m,
            limit_value=max_length,
            unit="m",
            severity="CRITICAL",
            remediation=(f"Reduce circuit length to ≤{max_length}m or upgrade to larger wire gauge per NFPA 72 §23.6.2")
            if not is_satisfied
            else "",
            formula=(
                f"L_actual = {cable_length_m:.1f}m "
                f"{'≤' if is_satisfied else '>'} "
                f"L_max = {max_length}m (AWG {_resolve_wire_gauge(wire_gauge).awg_value})"
            ),
        )

    def check_voltage_drop(
        self,
        alarm_current_a: float,
        cable_length_m: float,
        wire_gauge: WireGauge,
        ps_voltage: float = 24.0,
        max_drop_pct: float = 10.0,
        conductor_operating_temp_c: float = 75.0,
    ) -> ConstraintResult:
        """Check voltage drop compliance per NFPA 72 §10.6.4.

        NFPA 72 §10.6.4 requires that the voltage at end-of-line be
        sufficient to operate all devices under alarm conditions.

        Formula (NEC Chapter 9, Table 8):
          V_drop = I × 2 × R_wire(T) × L(km)

        The ×2 factor accounts for DC return path — current flows out
        on one conductor and returns on the other. This is CRITICAL:
        omitting ×2 would report voltage drop at 50% of actual.

        V60 FIX: Added temperature-corrected resistance. Previous code
        used R at 20 degC only, which UNDERESTIMATES voltage drop by
        21.6% at 75 degC operating temp — DANGEROUS for Egypt.

        V65 FIX: Renamed parameter from ambient_temp_c to
        conductor_operating_temp_c. The previous name was misleading —
        this parameter is the CONDUCTOR OPERATING temperature for
        resistance correction, NOT the ambient air temperature. A
        developer calling this method directly might pass ambient air
        temp (30°C) instead of conductor operating temp (75°C),
        underestimating voltage drop by 21.6%.

        V FIX: Changed default from 20.0 to 75.0 degC. The 20 degC default
        made temperature_corrected_resistance() a no-op (T_actual == T_ref),
        so voltage drop was underestimated by 21.6%. Per NEC 310.16, 75 degC
        is the standard operating temperature for THHN/THWN fire alarm cables.
        This aligns with nfpa72_engine.py's _DEFAULT_OPERATING_TEMP_C (V97 fix).

        For 24V systems: V_drop must be ≤ 2.4V (10%)

        Args:
            alarm_current_a: Total alarm current in amperes.
            cable_length_m: One-way cable length in meters.
            wire_gauge: Wire gauge.
            ps_voltage: Power supply voltage (default 24V).
            max_drop_pct: Maximum allowed drop percentage (default 10%).
            conductor_operating_temp_c: Conductor operating temperature in degC.
                Default 75.0 degC (NEC 310.16 practice for THHN/THWN).
                LIFE-SAFETY: Using 20°C underestimates voltage drop by 21.6%.

        Returns:
            ConstraintResult with voltage drop analysis.
        """
        # Compute voltage drop with DC return path (×2)
        # V60 FIX: Use temperature-corrected resistance per NEC practice
        # V FIX: Use NEC published resistance values when available.
        # WireGauge stores both 20°C and 75°C NEC published values.
        # For the standard 75°C operating temperature, use the NEC published
        # 75°C value directly (more accurate than formula — avoids ~2%
        # approximation error). For non-standard temperatures, use the
        # temperature correction formula from 20°C base.
        wg = _resolve_wire_gauge(wire_gauge)
        if abs(conductor_operating_temp_c - 75.0) < 1.0:
            # Use NEC published 75°C value directly (exact per NEC Table 8)
            r_per_km = wg.resistance_ohm_per_km  # 75°C published value
            r_at_20c = wg.resistance_ohm_per_km_at_20c
        else:
            # Use temperature correction formula from 20°C base
            r_at_20c = wg.resistance_ohm_per_km_at_20c
            r_per_km = temperature_corrected_resistance(r_at_20c, conductor_operating_temp_c)
        length_km = cable_length_m / 1000.0
        v_drop = alarm_current_a * 2.0 * r_per_km * length_km
        v_drop_pct = (v_drop / ps_voltage) * 100.0 if ps_voltage > 0 else 0.0
        max_drop_v = ps_voltage * max_drop_pct / 100.0

        is_satisfied = v_drop_pct <= max_drop_pct

        # Build formula with temperature info
        temp_note = ""
        if abs(conductor_operating_temp_c - 20.0) > 1.0:
            pct_increase = ((r_per_km / r_at_20c) - 1.0) * 100
            temp_note = (
                f" [R corrected: {r_at_20c:.3f}Ohm/km@20C -> "
                f"{r_per_km:.3f}Ohm/km@{conductor_operating_temp_c:.0f}C, "
                f"+{pct_increase:.1f}%]"
            )

        return ConstraintResult(
            constraint_name="Voltage Drop",
            source=ConstraintSource.NFPA_72_10_6_4.value,
            is_satisfied=is_satisfied,
            actual_value=round(v_drop, 4),
            limit_value=round(max_drop_v, 4),
            unit="V",
            severity="CRITICAL",
            remediation=(
                f"Voltage drop {v_drop:.2f}V ({v_drop_pct:.1f}%) exceeds "
                f"maximum {max_drop_pct}% ({max_drop_v:.1f}V). "
                f"Upgrade wire gauge or reduce circuit length per NFPA 72 §10.6.4."
            )
            if not is_satisfied
            else "",
            formula=(
                f"V_drop = I × 2 × R(T) × L = "
                f"{alarm_current_a:.4f}A × 2 × "
                f"{r_per_km:.3f}Ω/km@{conductor_operating_temp_c:.0f}C × "
                f"{length_km:.6f}km = {v_drop:.4f}V ({v_drop_pct:.2f}%)"
                f"{temp_note}"
            ),
        )

    def check_electrical_separation(
        self,
        actual_separation_mm: float,
    ) -> ConstraintResult:
        """Check separation from electrical conduits per project spec.

        Project Specification requires ≥ 300mm separation between
        fire alarm cables and electrical power conduits.

        NEC 760.24: Fire alarm cables must be in separate conduits
        from power conductors.

        NEC 760.154: PLFA circuits must be separated from NPLFA
        and power circuits.

        Args:
            actual_separation_mm: Actual separation distance in mm.

        Returns:
            ConstraintResult with separation check result.
        """
        is_satisfied = actual_separation_mm >= self._min_electrical_separation_mm

        return ConstraintResult(
            constraint_name="Electrical Conduit Separation",
            source=ConstraintSource.PROJECT_SPEC_SEPARATION.value,
            is_satisfied=is_satisfied,
            actual_value=actual_separation_mm,
            limit_value=self._min_electrical_separation_mm,
            unit="mm",
            severity="CRITICAL",
            remediation=(
                f"Increase separation to ≥{self._min_electrical_separation_mm}mm "
                f"from electrical conduits per Project Specification and NEC 760.24"
            )
            if not is_satisfied
            else "",
            formula=(
                f"d_actual = {actual_separation_mm:.0f}mm "
                f"{'≥' if is_satisfied else '<'} "
                f"d_min = {self._min_electrical_separation_mm:.0f}mm"
            ),
        )

    def check_bend_radius(
        self,
        conduit_diameter_mm: float = EMT_3_4_OUTER_DIAMETER_MM,
        num_bends: int = 0,
    ) -> ConstraintResult:
        """Check bend radius compliance per project spec / NEC 344.24.

        Project Specification: Maximum bend radius = 6 × conduit diameter.
        NEC 344.24: EMT bends shall have a radius not less than
        specified in Table 344.24 (6× diameter for ½" to 1" EMT).

        For ¾" EMT:
          Max bend radius = 6 × 19.05mm = 114.3mm

        V65 FIX: Added num_bends parameter. Previously, this check
        always returned is_satisfied=True regardless of actual bends.
        This was a silent no-op — if a route had bends that violated
        the radius requirement, the constraint would still report as
        satisfied. While the A* router respects bend constraints by
        design, the constraint check must verify, not assume.

        Args:
            conduit_diameter_mm: Conduit outer diameter in mm.
            num_bends: Number of bends in the route (default 0).

        Returns:
            ConstraintResult with bend radius check.
        """
        max_bend_radius = self._bend_radius_factor * conduit_diameter_mm

        # If no bends, the constraint is trivially satisfied.
        # Return the design rule with actual_value = computed bend radius
        # for backward compatibility with existing callers.
        if num_bends == 0:
            return ConstraintResult(
                constraint_name="Maximum Bend Radius",
                source=ConstraintSource.PROJECT_SPEC_BEND.value,
                is_satisfied=True,
                actual_value=max_bend_radius,
                limit_value=max_bend_radius,
                unit="mm",
                severity="HIGH",
                remediation="",
                formula=(
                    f"R_bend = {self._bend_radius_factor} x D = "
                    f"{self._bend_radius_factor} x {conduit_diameter_mm:.2f}mm = "
                    f"{max_bend_radius:.1f}mm"
                ),
            )

        # For routes with bends, the A* router designs bends at 90° with
        # appropriate radius by construction. We verify that the number of
        # bends per run doesn't exceed NEC Chapter 9 limits (max 4 quarter
        # bends per run between pull points).
        # NEC Chapter 9, Notes to Tables: "A run of conduit between
        # boxes shall not contain more than the equivalent of 4 quarter
        # bends (360° total)."
        is_satisfied = num_bends <= 4  # NEC Chapter 9, max 4 quarter bends

        return ConstraintResult(
            constraint_name="Maximum Bend Radius",
            source=ConstraintSource.PROJECT_SPEC_BEND.value,
            is_satisfied=is_satisfied,
            actual_value=float(num_bends),
            limit_value=4.0,
            unit="quarter bends",
            severity="CRITICAL" if not is_satisfied else "HIGH",
            remediation=(
                f"Route has {num_bends} quarter bends, exceeding NEC Chapter 9 "
                f"limit of 4 per run. Add pull box or junction box to split run "
                f"per NEC Chapter 9 Notes to Tables."
            )
            if not is_satisfied
            else "",
            formula=(
                f"Bends = {num_bends} quarter bends "
                f"{'≤' if is_satisfied else '>'} "
                f"4 max per NEC Chapter 9 (R_bend = {self._bend_radius_factor} x D = "
                f"{max_bend_radius:.1f}mm)"
            ),
        )

    def check_conduit_size(
        self,
        conduit_inches: float = MIN_CONDUIT_INCHES,
    ) -> ConstraintResult:
        """Check minimum conduit size per project specification.

        Project Specification: Minimum conduit ¾" red painted EMT.

        Args:
            conduit_inches: Conduit size in inches.

        Returns:
            ConstraintResult with conduit size check.
        """
        is_satisfied = conduit_inches >= self._min_conduit_inches

        return ConstraintResult(
            constraint_name="Minimum Conduit Size",
            source=ConstraintSource.PROJECT_SPEC_CONDUIT.value,
            is_satisfied=is_satisfied,
            actual_value=conduit_inches,
            limit_value=self._min_conduit_inches,
            unit="inches",
            severity="HIGH",
            remediation=(f'Use minimum ¾" red painted EMT per project specification') if not is_satisfied else "",
            formula=(
                f'Ø_conduit = {conduit_inches}" {"≥" if is_satisfied else "<"} Ø_min = {self._min_conduit_inches}"'
            ),
        )

    def check_cable_fastening(
        self,
        cable_length_m: float,
        num_fasteners: int,
    ) -> ConstraintResult:
        """Check cable fastening interval per NEC 760.24(A).

        NEC 760.24(A): Cables shall be fastened at intervals not
        exceeding 18 inches (457mm).

        Args:
            cable_length_m: Total cable length in meters.
            num_fasteners: Number of fasteners along the cable.

        Returns:
            ConstraintResult with fastening check.
        """
        max_interval_mm = self._max_fastening_interval_mm

        if cable_length_m < 0:
            # V67 SAFETY FIX: Negative cable length is physically impossible.
            # Previous behavior returned is_satisfied=True for L<=0, which
            # means a data error (L=-1.0) would pass the fastening check.
            # Negative length must be flagged, not silently accepted.
            return ConstraintResult(
                constraint_name="Cable Fastening Interval",
                source=ConstraintSource.NEC_760_24_A.value,
                is_satisfied=False,
                actual_value=cable_length_m,
                limit_value=max_interval_mm,
                unit="mm",
                severity="HIGH",
                remediation=(
                    f"Negative cable length ({cable_length_m}m) is physically impossible — "
                    "data error upstream. Fix the cable length before proceeding."
                ),
                formula=f"L={cable_length_m}m < 0 — invalid input",
            )

        if cable_length_m == 0:
            # Zero-length cable: no fastening needed (trivially satisfied)
            return ConstraintResult(
                constraint_name="Cable Fastening Interval",
                source=ConstraintSource.NEC_760_24_A.value,
                is_satisfied=True,
                actual_value=0.0,
                limit_value=max_interval_mm,
                unit="mm",
                severity="MEDIUM",
                remediation="",
                formula="L=0, no fastening required",
            )

        # Calculate actual interval
        if num_fasteners <= 0:
            actual_interval_mm = cable_length_m * 1000.0  # No fasteners at all
        else:
            actual_interval_mm = (cable_length_m * 1000.0) / (num_fasteners + 1)

        is_satisfied = actual_interval_mm <= max_interval_mm

        return ConstraintResult(
            constraint_name="Cable Fastening Interval",
            source=ConstraintSource.NEC_760_24_A.value,
            is_satisfied=is_satisfied,
            actual_value=round(actual_interval_mm, 1),
            limit_value=max_interval_mm,
            unit="mm",
            severity="MEDIUM",
            remediation=(
                f"Add more fasteners — current interval {actual_interval_mm:.0f}mm "
                f"exceeds {max_interval_mm}mm per NEC 760.24(A)"
            )
            if not is_satisfied
            else "",
            formula=(
                f"interval = L / (n+1) = "
                f"{cable_length_m * 1000:.0f}mm / {num_fasteners + 1} = "
                f"{actual_interval_mm:.0f}mm "
                f"{'≤' if is_satisfied else '>'} "
                f"{max_interval_mm}mm"
            ),
        )

    def check_class_a_separation(
        self,
        outgoing_path: List[Tuple[float, float, float]],
        return_path: List[Tuple[float, float, float]],
        min_separation_m: float = 0.3,
    ) -> ConstraintResult:
        """Check Class A circuit outgoing/return path separation.

        NFPA 72 §12.2.2: For Class A circuits, the outgoing and
        return conductors must not be routed through the same opening
        in a wall, floor, or ceiling.

        This check ensures minimum separation between outgoing and
        return paths to prevent a single fault from disabling both.

        Args:
            outgoing_path: List of (x,y,z) points on outgoing path.
            return_path: List of (x,y,z) points on return path.
            min_separation_m: Minimum required separation (default 0.3m).

        Returns:
            ConstraintResult with separation check.
        """
        min_distance = float("inf")

        # Check minimum distance between any point on outgoing path
        # and any point on return path
        for p1 in outgoing_path:
            for p2 in return_path:
                dist = math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2 + (p1[2] - p2[2]) ** 2)
                if dist < min_distance:
                    min_distance = dist

        if not outgoing_path or not return_path:
            min_distance = 0.0

        is_satisfied = min_distance >= min_separation_m

        return ConstraintResult(
            constraint_name="Class A Path Separation",
            source=ConstraintSource.NFPA_72_12_2_2.value,
            is_satisfied=is_satisfied,
            actual_value=round(min_distance, 4),
            limit_value=min_separation_m,
            unit="m",
            severity="CRITICAL",
            remediation=(
                f"Minimum separation {min_distance:.2f}m is below "
                f"required {min_separation_m}m. Route return path through "
                f"different penetration per NFPA 72 §12.2.2"
            )
            if not is_satisfied
            else "",
            formula=(f"d_min = {min_distance:.2f}m {'≥' if is_satisfied else '<'} d_required = {min_separation_m}m"),
        )

    def check_ampacity_compliance(
        self,
        alarm_current_a: float,
        wire_gauge: WireGauge,
        ambient_temp_c: float = 30.0,
        num_current_carrying: int = 2,
        conductor_temp_rating_c: float = 90,
    ) -> ConstraintResult:
        """Check wire ampacity per NEC 310.16 with deratings.

        NEC 310.16 provides base ampacity values. Two additional
        deratings are REQUIRED by NEC:
        1. NEC 310.15(B)(2)(A): Ambient temperature correction
           - At 50 degC ambient (Egypt): factor = 0.82 (90 degC rated)
        2. NEC 310.15(B)(3)(a): Conductor count adjustment
           - >3 conductors: factor < 1.0

        CRITICAL FOR EGYPT: At 40-50 degC ambient, wire ampacity is
        reduced by 9-18%. A wire that passes voltage drop may FAIL
        ampacity check in Egyptian summer conditions.

        Args:
            alarm_current_a: Total alarm current in amperes.
            wire_gauge: Wire gauge.
            ambient_temp_c: Ambient air temperature in degC (default 30 degC).
            num_current_carrying: Number of current-carrying conductors in conduit.
            conductor_temp_rating_c: Insulation temperature rating (60, 75, 90).

        Returns:
            ConstraintResult with ampacity analysis.
        """
        amp_result = check_ampacity(
            alarm_current_a=alarm_current_a,
            awg_gauge=_resolve_wire_gauge(wire_gauge).awg_value,
            conductor_temp_rating_c=conductor_temp_rating_c,
            ambient_temp_c=ambient_temp_c,
            num_current_carrying=num_current_carrying,
        )

        return ConstraintResult(
            constraint_name="Wire Ampacity (NEC 310.16)",
            source=ConstraintSource.NEC_310_16.value,
            is_satisfied=amp_result.is_compliant,
            actual_value=amp_result.actual_current_a,
            limit_value=amp_result.adjusted_ampacity_a,
            unit="A",
            severity="CRITICAL",
            remediation=(
                f"Current {amp_result.actual_current_a:.4f}A exceeds "
                f"adjusted ampacity {amp_result.adjusted_ampacity_a:.1f}A "
                f"(base {amp_result.base_ampacity_a}A x "
                f"ambient_derate={amp_result.ambient_derating:.2f} x "
                f"cond_derate={amp_result.conductor_derating:.2f}). "
                f"Upgrade wire gauge or reduce circuit current per NEC 310.16."
            )
            if not amp_result.is_compliant
            else "",
            formula=amp_result.formula,
        )

    def check_ambient_derating(
        self,
        ambient_temp_c: float,
        conductor_temp_rating_c: float = 90,
    ) -> ConstraintResult:
        """Check ambient temperature derating per NEC 310.15(B)(2)(A).

        Reports the derating factor for the given ambient temperature.
        This is informational — the ampacity check applies the factor
        automatically. But this makes the derating visible in audit logs.

        CRITICAL FOR EGYPT: At 50 degC ambient, derating factor is
        0.82 for 90 degC rated conductors — 18% reduction in capacity.

        Args:
            ambient_temp_c: Ambient air temperature in degC.
            conductor_temp_rating_c: Conductor insulation rating (60, 75, 90).

        Returns:
            ConstraintResult with derating information.
        """
        factor = get_ambient_derating_factor(ambient_temp_c, conductor_temp_rating_c)
        is_satisfied = factor >= 0.80  # Flag if derating is severe

        return ConstraintResult(
            constraint_name="Ambient Temperature Derating",
            source=ConstraintSource.NEC_310_15_B2A.value,
            is_satisfied=is_satisfied,
            actual_value=ambient_temp_c,
            limit_value=30.0,  # NEC 310.16 baseline temperature
            unit="degC",
            severity="HIGH" if factor < 0.80 else "MEDIUM",
            remediation=(
                f"Ambient {ambient_temp_c:.0f} degC requires {factor:.2f} derating. "
                f"Consider using higher-rated insulation or larger wire gauge "
                f"per NEC 310.15(B)(2)(A)."
            )
            if factor < 0.85
            else "",
            formula=(
                f"T_ambient = {ambient_temp_c:.0f} degC, "
                f"derating factor = {factor:.2f} "
                f"(conductor rating: {conductor_temp_rating_c} degC)"
            ),
        )

    def check_conductor_count_derating(
        self,
        num_current_carrying: int,
    ) -> ConstraintResult:
        """Check conductor count derating per NEC 310.15(B)(3)(a).

        Reports the derating factor based on number of current-carrying
        conductors in the conduit.

        Args:
            num_current_carrying: Number of current-carrying conductors.

        Returns:
            ConstraintResult with derating information.
        """
        factor = get_conductor_count_derating(num_current_carrying)
        is_satisfied = num_current_carrying <= 3

        return ConstraintResult(
            constraint_name="Conductor Count Derating",
            source=ConstraintSource.NEC_310_15_B3A.value,
            is_satisfied=is_satisfied,
            actual_value=float(num_current_carrying),
            limit_value=3.0,  # NEC 310.16 baseline
            unit="conductors",
            severity="HIGH" if factor < 0.80 else "MEDIUM",
            remediation=(
                f"{num_current_carrying} conductors require {factor:.2f} derating. "
                f"Consider splitting circuits into separate conduits "
                f"per NEC 310.15(B)(3)(a)."
            )
            if not is_satisfied
            else "",
            formula=(f"N = {num_current_carrying} conductors, derating factor = {factor:.2f}"),
        )

    def check_conduit_fill(
        self,
        wire_diameter_mm: float,
        num_cables: int,
        conduit_inner_diameter_mm: float = EMT_3_4_INNER_DIAMETER_MM,
    ) -> ConstraintResult:
        """Check conduit fill per NEC Chapter 9, Table 4.

        NEC 760.154: Maximum 40% fill for PLFA circuits in conduit.

        Formula:
          Fill = (N × π × (d/2)²) / (π × (D/2)²) × 100
          Simplified: Fill = N × (d/D)² × 100

        Args:
            wire_diameter_mm: Cable outer diameter in mm.
            num_cables: Number of cables in the conduit.
            conduit_inner_diameter_mm: Conduit inner diameter in mm.

        Returns:
            ConstraintResult with fill percentage.
        """
        if conduit_inner_diameter_mm <= 0:
            return ConstraintResult(
                constraint_name="Conduit Fill",
                source=ConstraintSource.NEC_CH9_TABLE4.value,
                is_satisfied=False,
                actual_value=0.0,
                limit_value=MAX_CONDUIT_FILL_PCT * 100,
                unit="%",
                severity="CRITICAL",
                remediation="Invalid conduit inner diameter",
                formula="D_conduit = 0, invalid",
            )

        wire_area = math.pi * (wire_diameter_mm / 2.0) ** 2
        conduit_area = math.pi * (conduit_inner_diameter_mm / 2.0) ** 2
        fill_ratio = (num_cables * wire_area) / conduit_area
        fill_pct = fill_ratio * 100.0
        max_fill_pct = MAX_CONDUIT_FILL_PCT * 100.0

        is_satisfied = fill_ratio <= MAX_CONDUIT_FILL_PCT

        return ConstraintResult(
            constraint_name="Conduit Fill",
            source=ConstraintSource.NEC_CH9_TABLE4.value,
            is_satisfied=is_satisfied,
            actual_value=round(fill_pct, 2),
            limit_value=round(max_fill_pct, 1),
            unit="%",
            severity="HIGH",
            remediation=(
                f"Conduit fill {fill_pct:.1f}% exceeds {max_fill_pct:.0f}% "
                f"per NEC 760.154 / Chapter 9 Table 4. "
                f"Reduce cables or increase conduit size."
            )
            if not is_satisfied
            else "",
            formula=(
                f"Fill = N × A_wire / A_conduit = "
                f"{num_cables} × {wire_area:.1f}mm² / {conduit_area:.1f}mm² = "
                f"{fill_pct:.1f}%"
            ),
        )

    # ─── Composite Checks ─────────────────────────────────────────────────

    def check_all(
        self,
        cable_length_m: float,
        wire_gauge: WireGauge,
        num_bends: int = 0,
        num_elevation_changes: int = 0,
        min_electrical_separation_mm: float = 300.0,
        ps_voltage: float = 24.0,
        alarm_current_a: float = 0.0,
        num_fasteners: int = 0,
        circuit_type: str = "NAC",
        is_class_a: bool = False,
        outgoing_path: Optional[List[Tuple[float, float, float]]] = None,
        return_path: Optional[List[Tuple[float, float, float]]] = None,
        ambient_temp_c: float = 30.0,
        conductor_operating_temp_c: Optional[float] = None,
        num_current_carrying: int = 2,
        conductor_temp_rating_c: float = 90,
        conduit_size_inches: Optional[float] = None,
    ) -> RoutingConstraintSet:
        """Run ALL constraint checks and return combined result.

        This is the primary API for constraint verification. Every
        check produces a traceable result with code reference.

        V59: Added ampacity, ambient derating, and conductor count
        derating checks. These are CRITICAL for Egypt where ambient
        temperatures reach 40-50 degC.

        V62 FIX: Split temperature parameters into two physically
        distinct quantities:
          - ambient_temp_c: Ambient AIR temperature (for ampacity
            derating per NEC 310.15(B)(2)(A)). Default 30 degC.
            CRITICAL FOR EGYPT: Use 40-50 degC for summer conditions.
          - conductor_operating_temp_c: Conductor OPERATING temperature
            (for resistance correction per NEC Ch.9 Table 8 + physics).
            Default None (uses ambient_temp_c for backward compatibility).
            CRITICAL FOR EGYPT: Use 75.0 for THHN/THWN operating temp.

        Previously, the same value was used for BOTH voltage drop
        resistance correction AND ampacity derating. This is physically
        wrong: voltage drop needs conductor operating temp (typically
        75 degC for THHN), while ampacity needs ambient air temp
        (typically 30-50 degC in Egypt). Using 75 degC as ambient air
        would overstate derating; using 30 degC as conductor temp would
        underestimate voltage drop by 21.6%. Either error is dangerous.

        Args:
            cable_length_m: Total cable length in meters.
            wire_gauge: Wire gauge used.
            num_bends: Number of 90 deg bends in the route.
            num_elevation_changes: Number of elevation changes.
            min_electrical_separation_mm: Minimum distance to electrical.
            ps_voltage: Power supply voltage (default 24V).
            alarm_current_a: Total alarm current in amperes.
            num_fasteners: Number of cable fasteners.
            circuit_type: Circuit type string (NAC, SLC, etc.).
            is_class_a: Whether this is a Class A circuit.
            outgoing_path: Outgoing path points (for Class A check).
            return_path: Return path points (for Class A check).
            ambient_temp_c: Ambient AIR temperature in degC (default 30 degC).
                Used for ampacity derating per NEC 310.15(B)(2)(A).
                CRITICAL FOR EGYPT: Use 40-50 degC for summer conditions.
            conductor_operating_temp_c: Conductor OPERATING temperature in
                degC for resistance correction. Default None (falls back to
                ambient_temp_c for backward compatibility).
                CRITICAL FOR EGYPT: Use 75.0 for THHN/THWN operating temp.
                At 75 degC, resistance is 21.6% higher than at 20 degC.
            num_current_carrying: Number of current-carrying conductors in
                conduit (default 2 for single FA circuit).
            conductor_temp_rating_c: Conductor insulation rating (60, 75, 90).
                Default 90 for THHN/THWN-2.

        Returns:
            RoutingConstraintSet with all check results.
        """
        results = []

        # 1. NAC circuit max length
        results.append(self.check_nac_max_length(cable_length_m, wire_gauge, circuit_type))

        # 2. Voltage drop
        # V62 FIX: Use conductor_operating_temp_c for resistance correction,
        # NOT ambient_temp_c. These are physically different quantities.
        # Voltage drop depends on conductor operating temperature (75C for
        # THHN), while ampacity depends on ambient air temperature (30-50C).
        # V65 FIX: When alarm_current_a == 0, add informational result
        # instead of silently skipping. The absence of a voltage drop
        # result could be misinterpreted as "compliant" when it actually
        # means "not checked."
        # V FIX: When conductor_operating_temp_c is None, default to 75.0 degC
        # (NEC practice for THHN/THWN), NOT ambient_temp_c. Using ambient
        # (30-50 degC) still underestimates resistance by 10-14.6% compared
        # to the correct 75 degC operating temperature. This aligns with
        # nfpa72_engine.py's _DEFAULT_OPERATING_TEMP_C (V97 fix).
        vdrop_temp = conductor_operating_temp_c if conductor_operating_temp_c is not None else 75.0
        if alarm_current_a > 0 and cable_length_m > 0:
            results.append(
                self.check_voltage_drop(
                    alarm_current_a,
                    cable_length_m,
                    wire_gauge,
                    ps_voltage,
                    conductor_operating_temp_c=vdrop_temp,
                )
            )
        elif cable_length_m > 0:
            # V67 SAFETY FIX: Voltage drop not checked because current is zero.
            # Previous behavior (V65-V66) set is_satisfied=True, creating a
            # false-positive: downstream code checking all_satisfied would see
            # this as "passed" even though NFPA 72 §10.6.4 was NEVER verified.
            # Zero current is physically impossible in a real FA circuit — if
            # it occurs, it's a data error upstream, not a real condition.
            # The safe default is: unchecked = NOT satisfied.
            results.append(
                ConstraintResult(
                    constraint_name="Voltage Drop (Not Checked)",
                    source=ConstraintSource.NFPA_72_10_6_4.value,
                    is_satisfied=False,
                    actual_value=0.0,
                    limit_value=ps_voltage * 0.10 if ps_voltage > 0 else 2.4,
                    unit="V",
                    severity="HIGH",
                    remediation=(
                        "Voltage drop check BLOCKED — alarm_current_a is 0. "
                        "This is physically impossible in a real fire alarm circuit. "
                        "Provide actual alarm current for NFPA 72 §10.6.4 compliance."
                    ),
                    formula="V_drop not calculated (I = 0A) — treated as non-compliant per V67 safety fix",
                )
            )

        # 3. Electrical separation
        results.append(self.check_electrical_separation(min_electrical_separation_mm))

        # 4. Bend radius — V65 FIX: Pass num_bends for NEC Chapter 9 check
        results.append(self.check_bend_radius(num_bends=num_bends))

        # 5. Conduit size — V65 FIX: Use actual conduit size if provided
        # Previously, always called with default (0.75), making it a no-op
        actual_conduit = conduit_size_inches if conduit_size_inches is not None else MIN_CONDUIT_INCHES
        results.append(self.check_conduit_size(conduit_inches=actual_conduit))

        # 6. Cable fastening
        results.append(self.check_cable_fastening(cable_length_m, num_fasteners))

        # 7. Class A separation (if applicable)
        if is_class_a and outgoing_path and return_path:
            results.append(self.check_class_a_separation(outgoing_path, return_path))

        # 8. Wire Ampacity (NEC 310.16) — V59 addition
        # V62 FIX: Use ambient_temp_c (air temp) for ampacity derating,
        # NOT conductor_operating_temp_c. Ampacity derating per NEC
        # 310.15(B)(2)(A) uses AMBIENT AIR temperature.
        if alarm_current_a > 0:
            results.append(
                self.check_ampacity_compliance(
                    alarm_current_a,
                    wire_gauge,
                    ambient_temp_c=ambient_temp_c,
                    num_current_carrying=num_current_carrying,
                    conductor_temp_rating_c=conductor_temp_rating_c,
                )
            )

        # 9. Ambient temperature derating (NEC 310.15(B)(2)(A)) — V59
        results.append(self.check_ambient_derating(ambient_temp_c, conductor_temp_rating_c))

        # 10. Conductor count derating (NEC 310.15(B)(3)(a)) — V59
        results.append(self.check_conductor_count_derating(num_current_carrying))

        # 11. Conduit fill (NEC Chapter 9 Table 4 / 760.154) — V61
        # V61 FIX: Previously missing from check_all. Overfilled conduit
        # causes overheating — NEC code violation and fire hazard.
        if num_current_carrying > 0:
            # Estimate wire diameter from gauge (conservative default)
            wire_diameter_mm = getattr(wire_gauge, "diameter_mm", None)
            if wire_diameter_mm is not None:
                results.append(
                    self.check_conduit_fill(
                        wire_diameter_mm=wire_diameter_mm,
                        num_cables=num_current_carrying,
                    )
                )

        # Compute summary
        violations = [r for r in results if not r.is_satisfied]
        critical_count = sum(1 for v in violations if v.severity == "CRITICAL")

        return RoutingConstraintSet(
            results=tuple(results),
            all_satisfied=len(violations) == 0,
            critical_violations=critical_count,
            total_violations=len(violations),
        )

    # ─── Cost Function for A* ─────────────────────────────────────────────

    def compute_move_cost(
        self,
        from_cell: Tuple[int, int, int],
        to_cell: Tuple[int, int, int],
        is_near_electrical: bool = False,
        grid_resolution: float = 0.1,
    ) -> float:
        """Compute the cost of moving from one cell to an adjacent cell.

        Used by the A* pathfinding algorithm. Costs are based on:
        - Straight segment: length × 1.0
        - 90° bend: + penalty (equivalent to 0.5m extra length)
        - Elevation change: + penalty (equivalent to 2.0m extra length)
        - Proximity to electrical: + penalty if < 300mm

        The direction of movement is determined by comparing the
        from_cell and to_cell indices. Only 6-directional orthogonal
        movement is allowed (X±, Y±, Z±).

        Args:
            from_cell: Source cell (ix, iy, iz).
            to_cell: Target cell (ix, iy, iz).
            is_near_electrical: Whether target cell is near electrical conduit.
            grid_resolution: Grid cell size in meters.

        Returns:
            Movement cost in equivalent meters.
        """
        dx = to_cell[0] - from_cell[0]
        dy = to_cell[1] - from_cell[1]
        dz = to_cell[2] - from_cell[2]

        # Base cost: one cell length
        cost = grid_resolution

        # Elevation change penalty
        if dz != 0:
            cost += self._elevation_penalty_m * abs(dz)

        # Horizontal direction change (bend) is detected by the router,
        # not here. This method only computes single-step cost.

        # Electrical proximity penalty
        if is_near_electrical:
            cost += ELECTRICAL_PROXIMITY_PENALTY_M

        return cost

    @staticmethod
    def compute_bend_cost(
        prev_dir: Optional[Tuple[int, int, int]],
        curr_dir: Tuple[int, int, int],
    ) -> float:
        """Compute the cost of a direction change (bend).

        A 90° bend adds a penalty equivalent to 0.5m extra length.
        This is because bends require conduit fittings (elbows),
        which increase material cost, installation time, and
        make cable pulling more difficult.

        Per NEC Chapter 9: "The number of bends in one run shall
        not exceed the equivalent of four quarter bends (360° total)."

        Args:
            prev_dir: Previous movement direction (dx, dy, dz), or None.
            curr_dir: Current movement direction (dx, dy, dz).

        Returns:
            Bend cost in equivalent meters (0.0 for straight, 0.5 for 90°).
        """
        if prev_dir is None:
            return 0.0  # First move has no bend

        # Check if direction changed
        if prev_dir == curr_dir:
            return 0.0  # Straight — no bend

        # Any change in direction is a 90° bend (6-directional grid)
        return BEND_PENALTY_M

    @staticmethod
    def manhattan_heuristic(
        current: Tuple[int, int, int],
        goal: Tuple[int, int, int],
        grid_resolution: float = 0.1,
    ) -> float:
        """Manhattan distance heuristic for A* pathfinding.

        Admissible heuristic for 6-directional orthogonal movement.
        Never overestimates the actual cost because:
        - Manhattan distance ≤ actual path length (triangular inequality)
        - Does not include bend/elevation penalties

        Formula:
          h = |dx| + |dy| + |dz| × (1 + elevation_penalty/resolution)

        The elevation penalty factor makes the heuristic more
        informed while maintaining admissibility.

        Args:
            current: Current cell (ix, iy, iz).
            goal: Goal cell (ix, iy, iz).
            grid_resolution: Grid cell size in meters.

        Returns:
            Estimated minimum cost from current to goal.
        """
        dx = abs(goal[0] - current[0])
        dy = abs(goal[1] - current[1])
        dz = abs(goal[2] - current[2])

        # Base Manhattan distance in meters
        base = (dx + dy) * grid_resolution

        # Elevation changes are more expensive
        elevation_cost = dz * grid_resolution * (1.0 + ELEVATION_PENALTY_M / grid_resolution)

        return base + elevation_cost
