"""FireAI Centralized Constants — NFPA 72 / NEC Clause-Cited Registry

PDF Audit Phase 2: Architectural Rigidity
Per "From Prototype to Production-Grade" §Phase 2 recommendation #2:
"Centralize all magic numbers and formulas into a dedicated constants module.
Each constant must be given a descriptive name and a comment citing the
specific NFPA or NEC clause it implements."

V128 FIX: This module now imports ALL NFPA 72 constants from the canonical
source (fireai.constants.nfpa72) per Single Source of Truth principle.
No NFPA 72 constant may be defined here — only re-exported from nfpa72.py.
This eliminates the 5-way parallel implementation bug where constants/__init__.py,
nfpa72.py, qomn_kernel.py, nfpa72_calculations.py, and nfpa72_technology_dispatcher.py
all had DIFFERENT values for the same NFPA 72 constant.

BATTERY_SAFETY_FACTOR FIX: Was 1.20 (20% margin) here but 1.25 (25% margin)
in canonical nfpa72.py per NFPA 72 §10.6.7.2.1. Now imported from canonical source.

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
# NFPA 72 — CANONICAL IMPORTS (Single Source of Truth)
# V128 FIX: All NFPA 72 constants imported from fireai.constants.nfpa72
# No duplicate definitions allowed — one source of truth only.
# ============================================================================

from fireai.constants.nfpa72 import (
    BATTERY_ALARM_MINUTES,
    BATTERY_DISCHARGE_EFFICIENCY,
    BATTERY_SAFETY_FACTOR,  # V128 FIX: Was 1.20 locally, now 1.25 from canonical
    # Battery calculations (Chapter 10)
    BATTERY_STANDBY_HOURS,
    BEAM_POCKET_DEPTH_FRACTION,
    CEILING_HEIGHT_HARD_LIMIT_M,
    CEILING_HEIGHT_MIN_M,
    CEILING_HEIGHT_SOFT_LIMIT_M,
    COVERAGE_THRESHOLD_PCT,
    # Voltage drop (Chapter 10)
    DC_RETURN_PATH_FACTOR,
    # Elevator shunt trip (Chapter 21)
    DEFAULT_HD_RTI,
    DEFAULT_SPRINKLER_RTI,
    HEAT_ABSOLUTE_MAX_SPACING_M,
    HEAT_HEIGHT_SPACING_TABLE,
    HEAT_MAX_CEILING_HEIGHT_M,
    HEAT_MAX_SPACING_M,
    HEAT_MAX_WALL_DISTANCE_M,
    MAX_ROOM_AREA_SQM,
    MIN_TERMINAL_VOLTAGE_V,
    NAC_MIN_CD,
    NAC_SLEEPING_MIN_CD,
    # Notification appliances (Chapter 18)
    NAC_WALL_HEIGHT_M,
    NOMINAL_SUPPLY_VOLTAGE_V,
    # PE sign-off
    PE_SIGNOFF_NOTICE,
    PLACEMENT_MARGIN_M,
    PULL_STATION_FROM_EXIT_M,
    # Pull stations (Chapter 17)
    PULL_STATION_HEIGHT_M,
    PULL_STATION_MAX_CORRIDOR_SPACING_M,
    RIDGE_ZONE_BUFFER_M,
    SHUNT_TRIP_MIN_TEMP_GAP_C,
    SLOPE_THRESHOLD_DEGREES,
    SMOKE_COVERAGE_RADIUS_M,
    SMOKE_HEIGHT_SPACING_TABLE,
    # Ceiling height limits (Chapter 17)
    SMOKE_MAX_CEILING_HEIGHT_M,
    # Detector spacing & coverage (Chapter 17)
    SMOKE_MAX_SPACING_M,
    SMOKE_MAX_WALL_DISTANCE_M,
    SMOKE_PRACTICAL_CEILING_HEIGHT_M,
    VERIFY_STEP_M,
    VOLTAGE_DROP_MAX_FRACTION,
    WALL_MIN_DISTANCE_M,
)
from fireai.constants.nfpa72 import (
    COMBINED_HEIGHT_SPACING_TABLE as NFPA72_HEIGHT_SPACING_TABLE,
)
from fireai.constants.nfpa72 import (
    COVERAGE_RADIUS_FACTOR as COVERAGE_FACTOR_FLAT_CEILING,
)
from fireai.constants.nfpa72 import (
    HEAT_SPACING_FALLBACK_M as NFPA72_HEAT_SPACING_FALLBACK_M,
)
from fireai.constants.nfpa72 import (
    SMOKE_SPACING_FALLBACK_M as NFPA72_SMOKE_SPACING_FALLBACK_M,
)
from fireai.constants.nfpa72 import (
    SMOKE_TABLE_MAX_HEIGHT_M as NFPA72_ABSOLUTE_MAX_HEIGHT_M,
)

# ============================================================================
# NEC — VOLTAGE DROP & CIRCUITS (not in nfpa72.py — kept here)
# ============================================================================

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


__all__ = [
    "BATTERY_ALARM_MINUTES",
    "BATTERY_DISCHARGE_EFFICIENCY",
    "BATTERY_SAFETY_FACTOR",
    "BATTERY_STANDBY_HOURS",
    "BEAM_POCKET_DEPTH_FRACTION",
    "CEILING_HEIGHT_HARD_LIMIT_M",
    "CEILING_HEIGHT_MIN_M",
    "CEILING_HEIGHT_SOFT_LIMIT_M",
    "COVERAGE_FACTOR_FLAT_CEILING",
    "COVERAGE_THRESHOLD_PCT",
    "DC_RETURN_PATH_FACTOR",
    "DEFAULT_HD_RTI",
    "DEFAULT_SPRINKLER_RTI",
    "HEAT_ABSOLUTE_MAX_SPACING_M",
    "HEAT_HEIGHT_SPACING_TABLE",
    "HEAT_MAX_CEILING_HEIGHT_M",
    "HEAT_MAX_SPACING_M",
    "HEAT_MAX_WALL_DISTANCE_M",
    "MAX_ROOM_AREA_SQM",
    "MIN_TERMINAL_VOLTAGE_V",
    "NAC_MIN_CD",
    "NAC_SLEEPING_MIN_CD",
    "NAC_WALL_HEIGHT_M",
    "NFPA72_ABSOLUTE_MAX_HEIGHT_M",
    "NFPA72_HEAT_SPACING_FALLBACK_M",
    "NFPA72_HEIGHT_SPACING_TABLE",
    "NFPA72_SMOKE_SPACING_FALLBACK_M",
    "NOMINAL_SUPPLY_VOLTAGE_V",
    "PE_SIGNOFF_NOTICE",
    "PLACEMENT_MARGIN_M",
    "PULL_STATION_FROM_EXIT_M",
    "PULL_STATION_HEIGHT_M",
    "PULL_STATION_MAX_CORRIDOR_SPACING_M",
    "RIDGE_ZONE_BUFFER_M",
    "SHUNT_TRIP_MIN_TEMP_GAP_C",
    "SLOPE_THRESHOLD_DEGREES",
    "SMOKE_COVERAGE_RADIUS_M",
    "SMOKE_HEIGHT_SPACING_TABLE",
    "SMOKE_MAX_CEILING_HEIGHT_M",
    "SMOKE_MAX_SPACING_M",
    "SMOKE_MAX_WALL_DISTANCE_M",
    "SMOKE_PRACTICAL_CEILING_HEIGHT_M",
    "VERIFY_STEP_M",
    "VOLTAGE_DROP_MAX_FRACTION",
    "WALL_MIN_DISTANCE_M",
]
