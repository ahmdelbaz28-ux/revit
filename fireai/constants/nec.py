"""FireAI — NEC (National Electrical Code) Constants

NEC (NFPA 70-2023) clause-cited constants for:
  - Conductor ampacity and derating
  - Conduit fill limits
  - Temperature correction
  - Wire gauge specifications

All values sourced from NEC 2023 Edition.
"""

# ============================================================================
# NEC Chapter 9, Table 1 — Conduit Fill Limits
# ============================================================================

# Maximum fill percentages per NEC Chapter 9 Table 1
MAX_CONDUCTOR_FILL_PCT: dict = {
    "1_conductor": 53,   # NEC Ch.9 Table 1: 1 conductor = 53%
    "2_conductors": 31,  # NEC Ch.9 Table 1: 2 conductors = 31%
    "3_plus":      40,   # NEC Ch.9 Table 1: 3+ conductors = 40%
}
"""Maximum conduit fill percentages per NEC Chapter 9, Table 1.
V20 Bug #20: Original dict had "40%" appearing twice — the second "40%"
was meant to be "53%" (1_conductor value). This has been corrected:
current values are 53/31/40 which match NEC Chapter 9 Table 1.
PE SIGN-OFF REQUIRED per agent.md Rule #22: Any change to these values
must be verified against NEC 2023 Chapter 9, Table 1 official PDF."""

# ============================================================================
# NEC Table 310.15(B)(3)(a) — Conductor Derating for Bundling
# ============================================================================

CONDUCTOR_DERATING_TABLE: dict = {
    # (num_conductors_range): derating_percentage
    (1, 3):   100,  # No derating for 1-3 conductors
    (4, 6):    80,  # NEC Table 310.15(B)(3)(a): 80% for 4-6 conductors
    (7, 9):    70,  # NEC Table 310.15(B)(3)(a): 70% for 7-9 conductors
    (10, 20):  50,  # NEC Table 310.15(B)(3)(a): 50% for 10-20 conductors
    (21, 30):  45,  # NEC Table 310.15(B)(3)(a): 45% for 21-30 conductors
    (31, 40):  40,  # NEC Table 310.15(B)(3)(a): 40% for 31-40 conductors
    (41, 999): 35,  # NEC Table 310.15(B)(3)(a): 35% for 41+ conductors
}
"""Conductor ampacity derating for more than 3 current-carrying conductors
in a raceway or cable. Per NEC Table 310.15(B)(3)(a). Heat buildup from
adjacent conductors reduces effective ampacity."""

# ============================================================================
# NEC Table 310.15(B)(2)(a) — Ambient Temperature Correction
# ============================================================================

AMBIENT_TEMP_CORRECTION: dict = {
    # temperature_F: correction_factor_for_75C_rated_conductors
    78:   1.05,   # 21-25°C
    86:   1.00,   # 26-30°C (baseline for 75°C rated conductors)
    95:   0.96,   # 31-35°C
    104:  0.91,   # 36-40°C
    113:  0.87,   # 41-45°C
    122:  0.82,   # 46-50°C
    131:  0.76,   # 51-55°C
    140:  0.71,   # 56-60°C
    158:  0.58,   # 61-70°C
}
"""Ambient temperature correction factors for 75°C rated conductors.
Per NEC Table 310.15(B)(2)(a). Above 30°C, conductor ampacity must be
reduced because the conductor cannot dissipate heat as effectively.
PDF §Phase 3: "Must include temperature correction per NEC Table
310.15(B)(2)(a)." """

# ============================================================================
# NEC Chapter 9, Table 4 — Conduit Internal Cross-Sectional Areas
# ============================================================================

# EMT (Electrical Metallic Tubing) — 40% fill column
CONDUIT_SPECS_EMT: dict = {
    # trade_size_inches: {"inner_diameter_mm": D, "area_100pct_mm2": A, "area_40pct_mm2": A40}
    0.5:  {"inner_diameter_mm": 15.8,  "area_100pct_mm2": 196.0,  "area_40pct_mm2": 78.0},
    0.75: {"inner_diameter_mm": 20.9,  "area_100pct_mm2": 343.0,  "area_40pct_mm2": 137.0},
    1.0:  {"inner_diameter_mm": 26.6,  "area_100pct_mm2": 556.0,  "area_40pct_mm2": 222.0},
    1.25: {"inner_diameter_mm": 35.1,  "area_100pct_mm2": 968.0,  "area_40pct_mm2": 387.0},
    1.5:  {"inner_diameter_mm": 40.9,  "area_100pct_mm2": 1314.0, "area_40pct_mm2": 526.0},
    2.0:  {"inner_diameter_mm": 52.5,  "area_100pct_mm2": 2165.0, "area_40pct_mm2": 866.0},
    2.5:  {"inner_diameter_mm": 63.0,  "area_100pct_mm2": 3117.0, "area_40pct_mm2": 1247.0},
    3.0:  {"inner_diameter_mm": 78.5,  "area_100pct_mm2": 4840.0, "area_40pct_mm2": 1936.0},
    3.5:  {"inner_diameter_mm": 90.1,  "area_100pct_mm2": 6376.0, "area_40pct_mm2": 2550.0},
    4.0:  {"inner_diameter_mm": 102.3, "area_100pct_mm2": 8217.0, "area_40pct_mm2": 3287.0},
}
"""EMT conduit specifications per NEC Chapter 9, Table 4.
40% fill column used for 3+ conductor installations."""

# RMC (Rigid Metal Conduit) — 40% fill column
CONDUIT_SPECS_RMC: dict = {
    0.5:  {"inner_diameter_mm": 16.3,  "area_100pct_mm2": 209.0,  "area_40pct_mm2": 84.0},
    0.75: {"inner_diameter_mm": 21.4,  "area_100pct_mm2": 359.0,  "area_40pct_mm2": 144.0},
    1.0:  {"inner_diameter_mm": 27.0,  "area_100pct_mm2": 573.0,  "area_40pct_mm2": 229.0},
    1.25: {"inner_diameter_mm": 35.4,  "area_100pct_mm2": 984.0,  "area_40pct_mm2": 394.0},
    1.5:  {"inner_diameter_mm": 41.2,  "area_100pct_mm2": 1334.0, "area_40pct_mm2": 534.0},
    2.0:  {"inner_diameter_mm": 52.9,  "area_100pct_mm2": 2198.0, "area_40pct_mm2": 879.0},
    2.5:  {"inner_diameter_mm": 63.2,  "area_100pct_mm2": 3138.0, "area_40pct_mm2": 1255.0},
    3.0:  {"inner_diameter_mm": 78.5,  "area_100pct_mm2": 4840.0, "area_40pct_mm2": 1936.0},
    3.5:  {"inner_diameter_mm": 90.7,  "area_100pct_mm2": 6454.0, "area_40pct_mm2": 2582.0},
    4.0:  {"inner_diameter_mm": 102.3, "area_100pct_mm2": 8217.0, "area_40pct_mm2": 3287.0},
}
"""RMC conduit specifications per NEC Chapter 9, Table 4."""


# ============================================================================
# NEC Chapter 9, Table 8 — Wire Resistance (Copper, Stranded)
# C-3 FIX: Single Source of Truth for NEC Table 8 resistance values.
# All other modules MUST import from here — no duplicate tables.
# ============================================================================

# Resistance values in ohm/km at 20°C reference temperature
# Source: NEC 2023 Edition, Chapter 9, Table 8 (Copper, Stranded)
# Using STRANDED values (conservative: higher resistance = higher voltage drop)
# Stranded conductors have slightly higher resistance than solid due to
# inter-strand contact resistance and slightly reduced cross-sectional area.
# For safety-critical voltage drop calculations, stranded values ensure
# we never UNDERESTIMATE voltage drop.
NEC_TABLE8_RESISTANCE_OHM_PER_KM_20C: dict = {
    "18": 10.870,   # AWG 18 stranded
    "16": 6.820,    # AWG 16 stranded
    "14": 4.263,    # AWG 14 stranded (per 1000ft: 1.299 ohm → 4.263 ohm/km)
    "12": 2.668,    # AWG 12 stranded (per 1000ft: 0.812 ohm → 2.668 ohm/km)
    "10": 1.678,    # AWG 10 stranded (per 1000ft: 0.511 ohm → 1.678 ohm/km)
    "8":  1.054,    # AWG 8 stranded
    "6":  0.662,    # AWG 6 stranded
    "4":  0.416,    # AWG 4 stranded
    "3":  0.330,    # AWG 3 stranded
    "2":  0.261,    # AWG 2 stranded
    "1":  0.207,    # AWG 1 stranded
    "1/0": 0.164,   # AWG 1/0 stranded
    "2/0": 0.130,   # AWG 2/0 stranded
    "3/0": 0.103,   # AWG 3/0 stranded
    "4/0": 0.0818,  # AWG 4/0 stranded
}
"""NEC Chapter 9, Table 8 — Copper stranded conductor resistance at 20°C.
Values in ohm/km. Source: NEC 2023, Chapter 9, Table 8.
Using STRANDED values as they are HIGHER than solid (conservative for
voltage drop calculations — never underestimates)."""

# Copper temperature coefficient of resistance
# Source: NEC Chapter 9, Table 8 notes; NEMA/IEC standards
COPPER_TEMP_COEFFICIENT: float = 0.00393
"""Temperature coefficient of resistance for copper: 0.00393 per degree C.
Formula: R_T = R_20 * [1 + alpha * (T - 20)]
At 75°C operating temperature: R_75 = R_20 * 1.2163 (21.6% higher than 20°C)"""

# Default operating temperature for fire alarm circuits
# Per NEC 310.16: 75°C for THHN/THWN insulated cables (75°C column)
DEFAULT_OPERATING_TEMP_C: float = 75.0

# Reference temperature for NEC Table 8 values
TABLE8_REFERENCE_TEMP_C: float = 20.0
