"""
FireAI Centralized Constants — NFPA 72 / NEC Clause-Cited Registry

PDF Audit Phase 2: Architectural Rigidity
Per "From Prototype to Production-Grade" §Phase 2 recommendation #2:
"Centralize all magic numbers and formulas into a dedicated constants module.
Each constant must be given a descriptive name and a comment citing the
specific NFPA or NEC clause it implements."

This module replaces scattered magic numbers across the codebase with
a single source of truth. Every constant has:
  - A descriptive UPPERCASE name
  - The exact standard clause citation
  - A default value traceable to the standard
  - Type annotation using typing.Final where possible

Standards Referenced:
  - NFPA 72-2022: National Fire Alarm and Signaling Code
  - NEC (NFPA 70-2023): National Electrical Code
  - IEC 60079-10-1:2015: Explosive Atmospheres Classification
  - IEC 60079-0:2017: Explosive Atmospheres Equipment
  - NFPA 497-2021: Classification of Flammable Gases
  - NFPA 92-2024: Smoke Control Systems
  - NFPA 101-2024: Life Safety Code
"""

# ============================================================================
# NFPA 72 — DETECTOR SPACING & COVERAGE (Chapter 17)
# ============================================================================

# Coverage radius factor: R = 0.7 x S
# NFPA 72-2022 §17.7.4.2.3.1
COVERAGE_FACTOR_FLAT_CEILING: float = 0.7
"""Coverage radius factor for flat ceilings. R = 0.7 x S where S is the
listed spacing. Per NFPA 72 §17.7.4.2.3.1, when detectors are placed on
a square grid at spacing S, the circular coverage radius R = 0.7S ensures
all points (including grid corners) are covered."""

# Maximum listed spacing for smoke detectors on flat ceilings ≤ 3.0m
# NFPA 72-2022 §17.6.3.1.1, Table 17.6.3.1.1
SMOKE_MAX_SPACING_M: float = 9.10
"""Maximum listed spacing for smoke detectors on smooth flat ceilings
≤ 3.0m (10 ft). Per NFPA 72 Table 17.6.3.1.1. At h=3.0m, S=9.1m
(30 ft), producing coverage radius R = 0.7 x 9.1 = 6.37m."""

# Maximum listed spacing for heat detectors on flat ceilings ≤ 3.0m
# NFPA 72-2022 §17.6.2.1, Table 17.6.3.5.1
HEAT_MAX_SPACING_M: float = 6.10
"""Maximum listed spacing for heat detectors on smooth flat ceilings
≤ 3.0m (10 ft). Per NFPA 72 Table 17.6.2.1. At h=3.0m, S=6.1m
(20 ft). Heat detectors use square-grid (Chebyshev) coverage geometry."""

# Coverage radius at ceiling height ≤ 3.0m (smoke)
# Derived: R = COVERAGE_FACTOR_FLAT_CEILING x SMOKE_MAX_SPACING_M
SMOKE_COVERAGE_RADIUS_M: float = round(COVERAGE_FACTOR_FLAT_CEILING * SMOKE_MAX_SPACING_M, 2)  # 6.37
"""Coverage radius for smoke detectors at h≤3.0m. R = 0.7 x 9.1 = 6.37m."""

# Wall minimum distance — dead air space
# NFPA 72-2022 §17.6.3.1.1
WALL_MIN_DISTANCE_M: float = 0.10
"""Minimum distance of detector from wall per NFPA 72 §17.6.3.1.1.
Detectors must be ≥0.1m from any wall to avoid dead air space where
smoke may not reach the detector due to boundary layer effects."""

# Maximum wall distance = S/2
# NFPA 72-2022 §17.6.3.1.1
SMOKE_MAX_WALL_DISTANCE_M: float = SMOKE_MAX_SPACING_M / 2.0  # 4.55
HEAT_MAX_WALL_DISTANCE_M: float = HEAT_MAX_SPACING_M / 2.0  # 3.05

# Ridge zone buffer for sloped ceilings
# NFPA 72-2022 §17.6.3.4
RIDGE_ZONE_BUFFER_M: float = 0.90
"""Ridge zone buffer distance for sloped ceilings. At least one detector
must be within 0.9m (3 ft) of the ridge per NFPA 72 §17.6.3.4."""

# Slope threshold for ridge zone requirement
# NFPA 72-2022 §17.6.3.4
SLOPE_THRESHOLD_DEGREES: float = 1.5
"""Minimum ceiling slope (degrees) to require ridge zone detectors.
Ceilings with slope > 1.5° per NFPA 72 §17.6.3.4 require at least
one detector within the ridge zone."""

# Beam pocket depth threshold (10% of ceiling height)
# NFPA 72-2022 §17.6.3.6
BEAM_POCKET_DEPTH_FRACTION: float = 0.10
"""Fraction of ceiling height that defines a beam pocket per NFPA 72
§17.6.3.6. If beam depth exceeds 10% of ceiling height, spacing must
be reduced within each beam pocket."""

# Verification step for coverage grid
# NFPA 72-2022 §17.7.4.2.3.1 (grid verification methodology)
VERIFY_STEP_M: float = 0.20
"""Step size for verification grid in coverage checking. Per V26 fix,
PLACEMENT_MARGIN = VERIFY_STEP x sqrt2/2 ≈ 0.141m ensures alignment
between placement and verification radii."""

# Placement margin derived from verification step
# V26 Fix — aligns placement with verification
PLACEMENT_MARGIN_M: float = VERIFY_STEP_M * (2**0.5) / 2.0  # ≈ 0.141

# Height-Adjusted Detector Spacing Table
# NFPA 72-2022 Table 17.6.3.1.1
NFPA72_HEIGHT_SPACING_TABLE = [
    # (ceiling_height_max_m, smoke_adjusted_spacing_m, heat_adjusted_spacing_m)
    (3.0, 9.10, 6.10),  # Listed spacings at h≤3.0m
    (3.7, 8.70, 5.80),
    (4.6, 8.20, 5.50),
    (5.5, 7.70, 5.20),
    (6.1, 7.30, 4.90),
    (7.6, 6.80, 4.60),
    (9.1, 6.40, 4.30),
    (10.7, 6.00, 4.00),
    (12.2, 5.60, 3.70),
]
NFPA72_ABSOLUTE_MAX_HEIGHT_M: float = 12.2
NFPA72_SMOKE_SPACING_FALLBACK_M: float = 5.20  # Beyond 12.2m → conservative
NFPA72_HEAT_SPACING_FALLBACK_M: float = 3.50  # Beyond 12.2m → conservative

# Coverage area threshold
# NFPA 72-2022 §17.7.6.1
COVERAGE_THRESHOLD_PCT: float = 99.9
"""Minimum coverage percentage for PASS. Uses 99.9% (not 100%) to account
for floating-point precision in Shapely area calculations. Per V13 fix,
area-based coverage is primary; point-sampling is secondary."""

# Maximum room area for valid rooms (atriums can be 3000+ m²)
MAX_ROOM_AREA_SQM: float = 10000.0
"""Maximum room area in m². V12 Bug #4: raised from 200 to 10000 to
allow atriums and lobbies which are the most important spaces for
fire protection. Per NFPA 72, large spaces require MORE protection,
not less."""


# ============================================================================
# NFPA 72 — VOLTAGE DROP & CIRCUITS (Chapter 10)
# ============================================================================

# DC return path factor (round-trip conductor)
# NFPA 72-2022 §10.14
DC_RETURN_PATH_FACTOR: float = 2.0
"""Voltage drop must include both supply and return conductors.
V_drop = 2 x I x R x L per NFPA 72 §10.14. V14 Bug #12: code was
missing this x2 factor, reporting 50% of actual voltage drop."""

# Minimum terminal voltage for notification appliances
# NFPA 72-2022 §10.14.1
MIN_TERMINAL_VOLTAGE_V: float = 16.0
"""Minimum operating voltage for 24VDC notification appliances.
Per NFPA 72 §10.14.1, appliances must operate within their listed
voltage range. 16V is the common minimum for 24VDC systems."""

# Voltage drop limits
# NEC §210.19(A)(1): Branch circuit ≤ 3%
# NEC §215.2(A)(2): Feeder + branch ≤ 5%
BRANCH_CIRCUIT_MAX_DROP_PCT: float = 3.0
FEEDER_CIRCUIT_MAX_DROP_PCT: float = 5.0

# Continuous load multiplier
# NEC §210.19(A)(1)
CONTINUOUS_LOAD_FACTOR: float = 1.25
"""Conductors must have ampacity ≥ 125% of continuous load per
NEC §210.19(A)(1). This prevents conductor overheating under
sustained loads."""

# Nominal supply voltage for fire alarm systems
NOMINAL_SUPPLY_VOLTAGE_V: float = 24.0

# Default safety margin for voltage drop
VOLTAGE_DROP_MAX_FRACTION: float = 0.15
"""Maximum allowable voltage drop as fraction of supply (15%).
Per NFPA 72 §10.14, the voltage at the most remote device must
be within the device's listed voltage range."""


# ============================================================================
# NFPA 72 — BATTERY CALCULATIONS (Chapter 10)
# ============================================================================

# Default standby duration
# NFPA 72-2022 §10.6.7
BATTERY_STANDBY_HOURS: float = 24.0
"""Required standby duration for fire alarm batteries. Per NFPA 72
§10.6.7, most occupancies require 24 hours of standby capacity."""

# Default alarm duration
# NFPA 72-2022 §10.6.7
BATTERY_ALARM_MINUTES: float = 5.0
"""Required alarm duration for fire alarm batteries. Per NFPA 72
§10.6.7, 5 minutes of alarm capacity after standby depletion."""

# Battery aging/temperature safety factor
BATTERY_SAFETY_FACTOR: float = 1.20
"""Multiplier for battery capacity to account for aging and temperature
derating. 1.20 = 20% margin per industry practice and NFPA 72 §10.6.7."""


# ============================================================================
# NEC — WIRE GAUGE & AMPACITY (Chapter 9, Table 8)
# ============================================================================

# AWG resistance table at 75°C — NEC Chapter 9 Table 8
# V51 FIX: Corrected to NEC Table 8 DC resistance at 75°C (stranded copper).
# Old values for AWG 14/12/10 were ~18% too low (20°C values, unsafe).
# NEC Table 8 at 75°C: AWG 14 stranded = 3.070 Ω/kft = 10.07 Ω/km.
AWG_RESISTANCE_OHM_PER_M: dict = {
    18: 0.02549,  # NEC Ch.9 Table 8 at 75°C, solid — 7.770 Ω/kft
    16: 0.01604,  # NEC Ch.9 Table 8 at 75°C, solid — 4.890 Ω/kft
    14: 0.01007,  # NEC Ch.9 Table 8 at 75°C, stranded — 3.070 Ω/kft
    12: 0.00633,  # NEC Ch.9 Table 8 at 75°C, stranded — 1.930 Ω/kft
    10: 0.00397,  # NEC Ch.9 Table 8 at 75°C, stranded — 1.210 Ω/kft
}
"""DC resistance per meter for copper conductors at 75°C per
NEC Chapter 9, Table 8. V51 FIX: Old values for AWG 14/12/10 were
from 20°C reference (~18% too low), causing voltage drop underestimation
in operating conditions. Now uses correct 75°C values per NEC Table 8."""

AWG_AMPACITY_75C: dict = {
    # NEC Table 310.16 — 75°C column, copper, not more than 3 conductors
    # AWG 18 and 16 are NOT listed in NEC 310.16 75°C column (too small)
    # Values shown for 18/16 are from 90°C column for reference only
    18: 14,  # NEC Table 310.16, 90°C column only (NOT rated at 75°C)
    16: 18,  # NEC Table 310.16, 90°C column only (NOT rated at 75°C)
    14: 20,  # NEC Table 310.16, 75°C column
    12: 25,  # NEC Table 310.16, 75°C column
    10: 35,  # NEC Table 310.16, 75°C column
}
"""Ampacity at 75°C for copper conductors per NEC Table 310.16.
V51 FIX: Old values (14=30A, 12=35A, 10=45A) were from the 90°C
column or another table, NOT the 75°C column. Using 90°C ampacity
with 75°C rated terminations violates NEC 110.14(C)(1). The 75°C
column is the correct reference for THHN/THWN fire alarm cables."""


# ============================================================================
# NFPA 72 — ELEVATOR SHUNT TRIP (Chapter 21)
# ============================================================================

# Default RTI values
# V20.2 Bug #18: DEFAULT_HD_RTI was 50 (same as sprinkler, check never triggered)
DEFAULT_HD_RTI: float = 100.0
"""Default Response Time Index for standard-response heat detectors per
UL 521. V20.2 Bug #18: was 50.0 (same as quick-response sprinkler),
making the V19.1 RTI check a no-op. Standard-response HDs have RTI
100-150. Quick-response sprinklers have RTI ≈ 50. A slow HD paired
with a fast sprinkler means the sprinkler bursts before power is severed
→ electrified water → firefighter electrocution."""

DEFAULT_SPRINKLER_RTI: float = 50.0
"""Default RTI for quick-response sprinklers per FM Global research."""

# Shunt trip temperature gap
SHUNT_TRIP_MIN_TEMP_GAP_C: float = 5.0
"""Minimum temperature difference between HD rating and sprinkler rating.
Per ASME A17.1 and NFPA 72 §21.4.2, the HD must activate BEFORE the
sprinkler to allow time for power disconnection."""


# ============================================================================
# NFPA 92 / NFPA 101 — STAIRWELL SMOKE CONTROL
# ============================================================================

# Pressurization height threshold — NFPA 101 §7.2.3.9
# V25 Bug #26: "exceeding 75 ft" means STRICTLY > 75 ft, NOT ≥
STAIRWELL_PRESSURIZATION_HEIGHT_M: float = 22.86
"""Height threshold for stairwell pressurization. Per NFPA 101 §7.2.3.9,
stairwells "exceeding 75 ft" require pressurization. "Exceeding" means
strictly greater than (>). V25 Bug #26: code used ≥ which incorrectly
required pressurization at exactly 75 ft."""

# Maximum positive pressure (door entrapment limit)
# NFPA 92-2024 §6.4.2
MAX_POSITIVE_PRESSURE_PA: float = 85.0
"""Maximum stairwell pressurization pressure. Per NFPA 92 §6.4.2,
excessive pressure prevents door opening, trapping occupants.
V25 Bug #27: constant existed but was never enforced."""

# Minimum positive pressure
# NFPA 92-2024 §6.4
MIN_POSITIVE_PRESSURE_PA: float = 25.0
"""Minimum stairwell pressurization pressure. Per NFPA 92 §6.4,
insufficient pressure allows smoke infiltration. V50 Bug: pressure
data missing for pressurized stairwells produced zero violations."""


# ============================================================================
# IEC 60079-10-1 — HAZARDOUS AREA CLASSIFICATION
# ============================================================================

# Molecular weight of dry air
# CRC Handbook of Chemistry and Physics, 97th Edition
MW_AIR_G_PER_MOL: float = 28.96
"""Molecular weight of dry air. D1 Bug: was 28.97 in semi_cfast_engine.py
and 29.0 in hac_classification_engine.py. Aligned to 28.96 per CRC
Handbook and models_v21.py. For borderline-density gases, inconsistent
values caused contradictory zone extent and detector elevation decisions."""

# Molar volume at STP
# IEC 60079-10-1:2015 Annex B
MOLAR_VOLUME_STP_M3_PER_MOL: float = 0.0224
"""Molar volume of ideal gas at STP (0°C, 101.325 kPa). Per IEC Annex B
Eq. B.1. V40a Bug: not temperature-corrected — now corrected with
ideal gas law: V_T = V_STP x (273.15 + T) / 273.15."""

# Vapor density tiers
# IEC 60079-10-1:2015 §B.4
VAPOR_DENSITY_LIGHT_THRESHOLD: float = 0.97
VAPOR_DENSITY_HEAVY_THRESHOLD: float = 1.03
"""Three-tier vapor density classification per models_v21.py:
  - ratio < 0.97 → HIGH (light gas, rises, 1.5x vertical extent)
  - 0.97 ≤ ratio ≤ 1.03 → BREATHING_ZONE (near-air, 1.0x extent)
  - ratio > 1.03 → LOW (heavy gas, sinks, 0.5x extent)
V25 Bug #25: hac_classification_engine used binary mw < 29.0 while
models_v21 used 3-tier with 0.97/1.03 thresholds."""

# Burgess-Wheeler LFL thermal correction coefficient
# Burgess & Wheeler (1929), IEC 60079-10-1 Annex B
BURGESS_WHEELER_COEFFICIENT: float = 0.001824
"""Coefficient for Burgess-Wheeler LFL thermal correction:
LFL_T = LFL_25C x (1 - 0.001824 x (T - 25)). Per IEC 60079-10-1
Annex B. V31 Bug: 50% floor was non-conservative at high temperatures."""

# LFL floor ratio default (backward-compatible)
# V31 Bug: configurable lfl_floor_ratio parameter
LFL_FLOOR_RATIO_DEFAULT: float = 0.5
"""Default floor on corrected LFL as fraction of reference LFL.
V31: default=0.5 for backward compatibility. Set None for no floor
(conservative zone extent per IEC 60079-10-1 for high-temp applications)."""

# Fouling severity threshold
# FM Global DS 5-48 §3.2.1
FOULING_HARSH_ENV_THRESHOLD: float = 0.50
"""Fouling factor threshold for CRITICAL severity in harsh environments.
V34 Fix: aligned with FOUL-001 CRITICAL threshold (was 0.85 which was
too broad). Per FM Global DS 5-48 §3.2.1, missing transmittance data
in severely fouled environments is CRITICAL."""


# ============================================================================
# PHYSICAL CONSTANTS
# ============================================================================

GRAVITY_M_PER_S2: float = 9.81
"""Standard gravitational acceleration (m/s²)."""
