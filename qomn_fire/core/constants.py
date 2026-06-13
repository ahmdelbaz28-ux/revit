"""
QOMN-FIRE PHYSICAL AND REGULATORY CONSTANTS
"""

# NFPA 72 Spacing Limits (2022 §17)
NFPA_SMOKE_DETECTOR_SPACING_M = 9.1  # 30 ft (9.1 m) per NFPA 72-2022 §17.7.3.2.3

# BUG-NFPA1 FIX: Changed from 0.7S (6.400m) to 0.5S (4.572m) per NFPA 72 §17.7.3.2.3.
# The previous value 6.400m = 0.7 × 9.144m = coverage radius R (NFPA 72 §17.7.3.2.5),
# NOT the maximum wall distance. The wall distance rule (§17.7.3.2.3) states:
# "The distance from a wall or partition to the nearest detector shall not exceed
# one-half the nominal spacing." = 0.5S = 15 ft = 4.572m.
# Using 0.7S as the wall distance threshold left gaps up to 6.4m from walls without
# detectors — NFPA 72 violation. While coverage was technically maintained (every
# point within 0.7S of a detector), detector sensitivity near walls is reduced by
# dead air space and air currents, making the 0.5S placement rule critical for
# reliable early detection. A detector 6m from a wall may not detect a fire at
# the wall quickly enough to meet the code's intent.
NFPA_MAX_WALL_DISTANCE_M = 4.55   # 0.5 times 9.1m spacing per §17.7.3.2.3

# Coverage radius for single-detector rooms per NFPA 72 §17.7.3.2.5
# Used as exception: a single detector in a room ≤ 900 ft² (84 m²) can be placed
# up to 0.7S from walls IF it covers the entire room.
NFPA_COVERAGE_RADIUS_M = 6.37     # 0.7 times 9.1m spacing per §17.7.3.2.5

# NEC Conduit Area Specifications (mm2) - Chapter 9 Table 4
EMT_INTERNAL_AREA_1_2_MM2 = 196.1
EMT_INTERNAL_AREA_3_4_MM2 = 343.9
EMT_INTERNAL_AREA_1_MM2 = 557.4

# NEC Wire Cross Sectional Areas (mm2) - Chapter 9 Table 5
WIRE_AREA_14_AWG_MM2 = 6.26
WIRE_AREA_12_AWG_MM2 = 8.58
WIRE_AREA_10_AWG_MM2 = 13.61

# NEC Chapter 9 Table 1 Fill Limits
NEC_FILL_LIMIT_1_WIRE = 0.53
NEC_FILL_LIMIT_2_WIRES = 0.31
NEC_FILL_LIMIT_OVER_2_WIRES = 0.40
