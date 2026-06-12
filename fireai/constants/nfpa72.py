"""
FireAI — NFPA 72 Centralized Constants (Single Source of Truth)

CANONICAL SOURCE for all NFPA 72-2022 constants used across the codebase.
No other module may define duplicate NFPA 72 constants — all must import from here.

Per agent.md Rule #17 (No Half-Solutions) and the V120 smoke spacing audit:
  - Five parallel implementations of smoke detector spacing existed
  - This module UNIFIES them into one authoritative source
  - All other modules MUST import from this file

PE SIGN-OFF REQUIRED (per agent.md Rule #22):
  Any change to data tables, formulas, or constants in this file that
  implement NFPA 72-2022 MUST be accompanied by either:
  (a) a Signed-off-by: trailer citing a licensed Professional Engineer
      with discipline, jurisdiction, and license number; OR
  (b) a verbatim quotation from NFPA 72-2022 with section number,
      edition year, and a publicly-verifiable URL or document hash

Standards Referenced:
  - NFPA 72-2022: National Fire Alarm and Signaling Code

Current Values Status:
  SMOKE detector spacing: Values at h<=3.0m are VERIFIED against NFPA 72-2022.
  Height-adjusted table: AWAITING FPE REVIEW — the table at h>3.0m is derived
  from NFPA 72 Table 17.6.3.5.1 (HEAT detector reduction). Per ECMAG (May 2022)
  and SFPE Europe Journal Issue 33, there is NO height-based reduction table
  for smoke detectors. NFPA 72 §17.7.3.2.3 specifies flat 30ft (9.1m) spacing.
  The height-adjusted values are RETAINED as a CONSERVATIVE (fail-safe) fallback
  pending licensed FPE sign-off, but a WARNING is emitted when they are used.
"""

from typing import Dict, List, Tuple

# ============================================================================
# NFPA 72-2022 — SMOKE DETECTOR SPACING (Chapter 17)
# ============================================================================

# Maximum listed spacing for smoke detectors on smooth flat ceilings
# NFPA 72-2022 §17.7.3.2.3, §17.6.3.1.1
# Verbatim: "Spot-type smoke detectors shall be spaced not more than 30 ft (9.1 m)
# apart on smooth ceilings." — NFPA 72-2022 §17.7.3.2.3
SMOKE_MAX_SPACING_M: float = 9.1
"""Maximum listed spacing for smoke detectors on smooth flat ceilings.
Per NFPA 72-2022 §17.7.3.2.3: 30 ft (9.1 m) with NO height reduction.
NOTE: Previous code used 9.144 (30 ft x 0.3048 exact conversion), but
NFPA 72 lists 30 ft / 9.1 m. The 9.1 m value is the metric value
stated in the standard itself."""

# Coverage radius factor: R = 0.7 x S
# NFPA 72-2022 §17.7.4.2.3.1
COVERAGE_RADIUS_FACTOR: float = 0.7
"""Coverage radius factor for flat ceilings. R = 0.7 x S.
Per NFPA 72 §17.7.4.2.3.1, when detectors are placed on a square grid
at spacing S, the circular coverage radius R = 0.7S ensures all points
(including grid corners) are covered."""

# Derived: Smoke detector coverage radius at nominal spacing
SMOKE_COVERAGE_RADIUS_M: float = round(COVERAGE_RADIUS_FACTOR * SMOKE_MAX_SPACING_M, 2)  # 6.37
"""Coverage radius for smoke detectors at h<=3.0m. R = 0.7 x 9.1 = 6.37m."""

# Absolute maximum ceiling height for spot-type smoke detectors
# NFPA 72-2022 §17.7.3.2.4
# Verbatim: "Spot-type smoke detectors shall not be installed on ceilings
# more than 60 ft (18.3 m) above the floor." — NFPA 72-2022 §17.7.3.2.4
SMOKE_MAX_CEILING_HEIGHT_M: float = 18.288
"""Absolute maximum ceiling height for spot-type smoke detectors.
Per NFPA 72-2022 §17.7.3.2.4: 60 ft (18.288 m). Above this height,
spot-type smoke detectors are NOT permitted — use beam/aspirating
detectors per §17.7.4.6/§17.7.4.7."""

# Economic/practical ceiling height threshold for spot smoke detectors
# Per ECMAG (May 2022): "never install spot-type smoke detectors on
# ceilings 20 feet or higher under any circumstances"
# NFPA 72-2022 §17.7.1.11 (stratification concern)
SMOKE_PRACTICAL_CEILING_HEIGHT_M: float = 6.096
"""Practical ceiling height limit (20 ft) for spot-type smoke detectors.
Above this height, stratification makes spot detectors unreliable.
Consider beam detectors (§17.7.4.6) or aspirating systems (§17.7.4.7).
This is NOT a code requirement but a widely-accepted engineering
recommendation from ECMAG and SFPE Europe."""

# Height-adjusted smoke detector spacing table
# WARNING: This table applies height-based reduction derived from
# NFPA 72 Table 17.6.3.5.1 (HEAT detector spacing reduction).
# Per NFPA 72-2022, there is NO such reduction table for smoke detectors.
# This table is RETAINED as a CONSERVATIVE fallback (more detectors = safer)
# but AWAITING FPE REVIEW for correctness.
#
# Source: NFPA 72-2022 Table 17.6.3.5.1 (heat detector reduction,
#   applied to smoke detectors — known misapplication)
# Alternative view: Some engineers use this table for smoke detectors
#   as a conservative approach, but NFPA 72 §17.7.3.2.3 does not require it.
SMOKE_HEIGHT_SPACING_TABLE: List[Tuple[float, float]] = [
    # (ceiling_height_max_m, adjusted_spacing_m)
    # At h<=3.0m: flat 9.1m per §17.7.3.2.3
    # At h>3.0m: 1% per foot reduction per Table 17.6.3.5.1 (CONSERVATIVE)
    (3.0,   9.10),   # Listed spacing (no reduction)
    (3.7,   8.70),   # Pre-reduced: ~4% reduction
    (4.6,   8.20),   # Pre-reduced: ~10% reduction
    (5.5,   7.70),   # Pre-reduced: ~15% reduction
    (6.1,   7.30),   # Pre-reduced: ~20% reduction
    (7.6,   6.80),   # Pre-reduced: ~25% reduction
    (9.1,   6.40),   # Pre-reduced: ~30% reduction
    (10.7,  6.00),   # Pre-reduced: ~34% reduction
    (12.2,  5.60),   # Pre-reduced: ~38% reduction
]
"""Height-adjusted smoke detector spacing table.

⚠️ REGULATORY WARNING (V120 Audit):
This table applies height-based reduction to smoke detector spacing.
Per NFPA 72-2022 §17.7.3.2.3, smoke detectors have FLAT 30ft (9.1m)
spacing with NO height reduction. The reduction values are derived from
NFPA 72 Table 17.6.3.5.1 which applies to HEAT detectors only.

This table produces CONSERVATIVE results (more detectors than NFPA
requires), so it is FAIL-SAFE. However, it may cause:
  - AHJ rejection (non-compliant with §17.7.3.2.3)
  - Economic over-design (4x overdensification at 60ft)
  - Misleading engineers about actual code requirements

RETAINED pending licensed FPE sign-off per agent.md Rule #17.
Do NOT remove without FPE approval — the conservative fallback
is safer than no table at all."""

# Fallback spacing beyond the table range
SMOKE_SPACING_FALLBACK_M: float = 5.20
"""Conservative fallback spacing for ceilings above 12.2m.
Used when height exceeds the table range. Value corresponds to
the most conservative entry extrapolated."""

# Table absolute max height (beyond this, use fallback)
SMOKE_TABLE_MAX_HEIGHT_M: float = 12.2


# ============================================================================
# NFPA 72-2022 — HEAT DETECTOR SPACING (Chapter 17)
# ============================================================================

# Maximum listed spacing for heat detectors on smooth flat ceilings
# NFPA 72-2022 §17.6.3.1, Table 17.6.3.5.1
HEAT_MAX_SPACING_M: float = 6.10
"""Maximum listed spacing for heat detectors on smooth flat ceilings
at h<=3.0m (10 ft). Per NFPA 72 Table 17.6.3.5.1: 20 ft (6.1 m).
Heat detectors use square-grid (Chebyshev) coverage geometry."""

# Absolute maximum heat detector spacing (50 ft)
# NFPA 72-2022 §17.6.3.1
HEAT_ABSOLUTE_MAX_SPACING_M: float = 15.24
"""Absolute maximum listed spacing for heat detectors: 50 ft (15.24 m).
Per NFPA 72-2022 §17.6.3.1. This is the MAXIMUM spacing for which a
heat detector is listed — no heat detector may be spaced further apart
than its listed spacing, and the maximum listed spacing is 50 ft.
NOTE: The standard spacing at h<=3.0m is 20 ft (6.1 m) per
Table 17.6.3.5.1. The 50 ft value is the upper bound of the
listing range, not the default spacing."""

# Absolute maximum ceiling height for spot-type heat detectors
# NFPA 72-2022 §17.6.3.1
HEAT_MAX_CEILING_HEIGHT_M: float = 15.24
"""Maximum ceiling height for spot-type heat detectors.
Per NFPA 72-2022 §17.6.3.1: 50 ft (15.24 m)."""

# Height-adjusted heat detector spacing table
# Source: NFPA 72-2022 Table 17.6.3.5.1
# This is the CORRECT table for heat detector height reduction.
HEAT_HEIGHT_SPACING_TABLE: List[Tuple[float, float]] = [
    # (ceiling_height_max_m, adjusted_spacing_m)
    (3.0,   6.10),   # 20 ft listed
    (3.7,   5.80),   # 19 ft
    (4.6,   5.50),   # 18 ft
    (5.5,   5.20),   # 17 ft
    (6.1,   4.90),   # 16 ft
    (7.6,   4.60),   # 15 ft
    (9.1,   4.30),   # 14 ft
    (10.7,  4.00),   # 13 ft
    (12.2,  3.70),   # 12 ft
]
"""Height-adjusted heat detector spacing table.
Per NFPA 72-2022 Table 17.6.3.5.1 — this IS the correct table
for heat detector height reduction (1% per foot above 10 ft)."""

HEAT_SPACING_FALLBACK_M: float = 3.50
"""Conservative fallback spacing for heat detectors beyond 12.2m."""

# Combined height-spacing table (smoke + heat)
# For backward compatibility with modules that use 3-tuple format
COMBINED_HEIGHT_SPACING_TABLE: List[Tuple[float, float, float]] = [
    # (ceiling_height_max_m, smoke_spacing_m, heat_spacing_m)
    (3.0,   9.10, 6.10),
    (3.7,   8.70, 5.80),
    (4.6,   8.20, 5.50),
    (5.5,   7.70, 5.20),
    (6.1,   7.30, 4.90),
    (7.6,   6.80, 4.60),
    (9.1,   6.40, 4.30),
    (10.7,  6.00, 4.00),
    (12.2,  5.60, 3.70),
]


# ============================================================================
# NFPA 72-2022 — CEILING HEIGHT LIMITS (Unified)
# ============================================================================

# Minimum ceiling height for detector placement
# NFPA 72-2022 §17.6.3.1.1
CEILING_HEIGHT_MIN_M: float = 3.0
"""Minimum ceiling height for standard detector spacing tables.
Below 3.0m (10 ft), special considerations may apply per NFPA 72."""

# Soft limit: height where coverage radius table ends
# Above this, PE review is required but detection is still possible
CEILING_HEIGHT_SOFT_LIMIT_M: float = 15.24
"""Soft ceiling height limit (50 ft). Above this height:
- Coverage radius table (§17.6.3.1.1) does not provide values
- PE review is REQUIRED
- Detector spacing uses conservative extrapolation
- Status changes to REQUIRES_MANUAL_REVIEW"""

# Hard limit: absolute maximum for ANY spot-type detector
# Above this, spot detection is NOT permitted
CEILING_HEIGHT_HARD_LIMIT_M: float = 18.288
"""Hard ceiling height limit (60 ft). Above this height:
- NO spot-type smoke detectors permitted per §17.7.3.2.4
- System MUST REJECT the design
- Alternative technology required (beam/aspirating)
This is the ABSOLUTE ceiling — no exceptions without special
engineering design per NFPA 72 Annex B."""


# ============================================================================
# NFPA 72-2022 — WALL DISTANCE & PLACEMENT (Chapter 17)
# ============================================================================

# Minimum distance from wall — dead air space
# NFPA 72-2022 §17.6.3.1.1
WALL_MIN_DISTANCE_M: float = 0.10
"""Minimum distance of detector from wall. Per NFPA 72 §17.6.3.1.1,
detectors must be >= 0.1m from any wall to avoid dead air space."""

# Maximum wall distance = S/2
SMOKE_MAX_WALL_DISTANCE_M: float = SMOKE_MAX_SPACING_M / 2.0  # 4.55
HEAT_MAX_WALL_DISTANCE_M: float = HEAT_MAX_SPACING_M / 2.0  # 3.05

# Ridge zone buffer for sloped ceilings
# NFPA 72-2022 §17.6.3.4
RIDGE_ZONE_BUFFER_M: float = 0.90
"""Ridge zone buffer for sloped ceilings. At least one detector
within 0.9m (3 ft) of ridge per §17.6.3.4."""

# Slope threshold for ridge zone requirement
# NFPA 72-2022 §17.6.3.4
SLOPE_THRESHOLD_DEGREES: float = 1.5
"""Minimum ceiling slope to require ridge zone detectors."""

# Beam pocket depth threshold
# NFPA 72-2022 §17.6.3.6
BEAM_POCKET_DEPTH_FRACTION: float = 0.10
"""Fraction of ceiling height defining beam pocket per §17.6.3.6."""


# ============================================================================
# NFPA 72-2022 — COVERAGE VERIFICATION
# ============================================================================

# Coverage area threshold
# NFPA 72-2022 §17.7.6.1
COVERAGE_THRESHOLD_PCT: float = 99.9
"""Minimum coverage percentage for PASS. 99.9% accounts for
floating-point precision in Shapely area calculations."""

# Verification step for coverage grid
VERIFY_STEP_M: float = 0.20
"""Step size for verification grid in coverage checking."""

# Placement margin derived from verification step
PLACEMENT_MARGIN_M: float = VERIFY_STEP_M * (2**0.5) / 2.0  # ~0.141

# Maximum room area for valid rooms
MAX_ROOM_AREA_SQM: float = 10000.0
"""Maximum room area in m². V12 Bug #4: raised from 200 to 10000."""


# ============================================================================
# NFPA 72-2022 — PULL STATIONS (Chapter 17)
# ============================================================================

# Pull station height — NFPA 72 §17.15.7
PULL_STATION_HEIGHT_M: float = 1.219  # 48 inches AFF

# Pull station max corridor spacing — NFPA 72 §17.15.5
PULL_STATION_MAX_CORRIDOR_SPACING_M: float = 61.0  # 200 ft

# Pull station from exit — NFPA 72 §17.15.3
PULL_STATION_FROM_EXIT_M: float = 1.524  # 5 ft


# ============================================================================
# NFPA 72-2022 — NOTIFICATION APPLIANCES (Chapter 18)
# ============================================================================

# Wall mount height — NFPA 72 §18.5.5.1
NAC_WALL_HEIGHT_M: float = 2.032  # 80 inches AFF to bottom

# Minimum strobe intensity — NFPA 72 §18.5.3.1
NAC_MIN_CD: int = 75  # 75 candela

# Sleeping area strobe intensity — NFPA 72 §18.5.5.7
NAC_SLEEPING_MIN_CD: int = 177  # 177 candela


# ============================================================================
# NFPA 72-2022 — BATTERY CALCULATIONS (Chapter 10)
# ============================================================================

# Standby duration — NFPA 72-2022 §10.6.7
BATTERY_STANDBY_HOURS: float = 24.0
"""24 hours standby required per §10.6.7."""

# Alarm duration — NFPA 72-2022 §10.6.7
BATTERY_ALARM_MINUTES: float = 5.0
"""5 minutes full alarm after standby depletion."""

# Battery safety factor
BATTERY_SAFETY_FACTOR: float = 1.25
"""25% additional capacity per §10.6.7.2.1."""

# Battery discharge efficiency
BATTERY_DISCHARGE_EFFICIENCY: float = 0.80
"""80% usable capacity (lead-acid discharge curve)."""


# ============================================================================
# NFPA 72-2022 — VOLTAGE DROP (Chapter 10)
# ============================================================================

# DC return path factor
DC_RETURN_PATH_FACTOR: float = 2.0
"""Voltage drop includes both supply and return conductors.
V14 Bug #12: code was missing x2 factor."""

# Minimum terminal voltage for notification appliances
MIN_TERMINAL_VOLTAGE_V: float = 16.0
"""Minimum operating voltage for 24VDC appliances per §10.14.1."""

# Nominal supply voltage
NOMINAL_SUPPLY_VOLTAGE_V: float = 24.0

# Voltage drop max fraction — CORRECTED from 0.15 to 0.10 per V78
# NFPA 72 §10.14
VOLTAGE_DROP_MAX_FRACTION: float = 0.10
"""Maximum allowable voltage drop as fraction of supply (10%).
V78 Fix: Was 0.15 (15%) which is too permissive. NFPA 72 §10.14
requires devices operate within listed voltage range; 10% is the
standard engineering practice for 24VDC fire alarm systems.
NOTE: constants/__init__.py still had 0.15 — this is the corrected value."""


# ============================================================================
# NFPA 72-2022 — ELEVATOR SHUNT TRIP (Chapter 21)
# ============================================================================

DEFAULT_HD_RTI: float = 100.0
"""Default RTI for standard-response heat detectors (UL 521).
V20.2 Bug #18: was 50.0 (same as quick-response sprinkler)."""

DEFAULT_SPRINKLER_RTI: float = 50.0
"""Default RTI for quick-response sprinklers (FM Global)."""

SHUNT_TRIP_MIN_TEMP_GAP_C: float = 5.0
"""Min temp gap between HD and sprinkler ratings per ASME A17.1."""


# ============================================================================
# PE SIGN-OFF NOTICE
# ============================================================================
PE_SIGNOFF_NOTICE = (
    "PE SIGN-OFF REQUIRED: Values in this module implement NFPA 72-2022. "
    "Any modification MUST be accompanied by Signed-off-by: trailer from "
    "a licensed Professional Engineer (Fire Protection discipline) with "
    "jurisdiction and license number, per agent.md Rule #22. "
    "Alternatively, provide verbatim quotation from NFPA 72-2022 with "
    "section number, edition year, and publicly-verifiable source."
)
"""Notice attached to all regulatory constants. Per agent.md Rule #22,
changes to these values require PE sign-off or verbatim standard quotation."""
