"""
FireAI — Constants Index (Single Source of Truth Reference)

=============================================================================
THIS FILE IS THE CANONICAL REFERENCE FOR ALL CONSTANTS IN THE PROJECT.
All constants MUST be imported from their source modules listed below.
DO NOT redefine constants inline — import from the canonical source.
=============================================================================

╔══════════════════════════════════════════════════════════════════════════╗
║                        NFPA 72 CONSTANTS                                  ║
║                   Source: fireai/constants/nfpa72.py                      ║
╠══════════════════════════════════════════════════════════════════════════╣
║ CONSTANT                          │ VALUE    │ DESCRIPTION                ║
╠══════════════════════════════════════════════════════════════════════════╣
║ SMOKE_MAX_SPACING_M               │ 9.1      │ Smoke detector max spacing ║
║ HEAT_MAX_SPACING_M                │ 6.10     │ Heat detector max spacing  ║
║ COVERAGE_RADIUS_FACTOR            │ 0.7      │ R = 0.7 × S               ║
║ SMOKE_COVERAGE_RADIUS_M           │ 6.37     │ R = 0.7 × 9.1             ║
║ HEAT_COVERAGE_RADIUS_M            │ 4.27     │ R = 0.7 × 6.1             ║
║ WALL_MIN_DISTANCE_M               │ 0.1016   │ 4 inches = 101.6mm        ║
║ SMOKE_MAX_WALL_DISTANCE_M         │ 4.55     │ S/2 for smoke             ║
║ HEAT_MAX_WALL_DISTANCE_M          │ 3.05     │ S/2 for heat              ║
║ SMOKE_MAX_CEILING_HEIGHT_M        │ 18.288   │ 60 ft absolute max        ║
║ HEAT_MAX_CEILING_HEIGHT_M         │ 15.24    │ 50 ft absolute max        ║
║ CEILING_HEIGHT_MIN_M              │ 3.0      │ Minimum for tables        ║
║ BATTERY_STANDBY_HOURS             │ 24.0     │ 24 hours standby          ║
║ BATTERY_ALARM_MINUTES             │ 5.0      │ 5 minutes alarm           ║
║ BATTERY_SAFETY_FACTOR             │ 1.25     │ 25% additional capacity   ║
║ NAC_MIN_CD                        │ 75       │ 75 candela minimum        ║
║ NAC_SLEEPING_MIN_CD               │ 177      │ 177 candela sleeping      ║
║ PULL_STATION_HEIGHT_M             │ 1.219    │ 48 inches AFF             ║
║ PULL_STATION_FROM_EXIT_M          │ 1.524    │ 5 ft from exit            ║
║ RIDGE_ZONE_BUFFER_M               │ 0.90     │ 3 ft from ridge           ║
║ VOLTAGE_DROP_MAX_FRACTION         │ 0.10     │ 10% max voltage drop      ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║                    NON-NFPA CONSTANTS                                     ║
║              (Canonical source per module)                                ║
╠══════════════════════════════════════════════════════════════════════════╣
║ CONSTANT                          │ VALUE    │ SOURCE MODULE             ║
╠══════════════════════════════════════════════════════════════════════════╣
║ GRAVITY_M_S2                      │ 9.80665  │ backend/services/elevation║
║ MOLAR_MASS_AIR                    │ 0.0289644│ backend/services/elevation║
║ UNIVERSAL_GAS_CONSTANT            │ 8.31447  │ backend/services/elevation║
║ DEFAULT_AQI                       │ 100      │ backend/services/air_quality║
║ DEFAULT_PM25_UG_M3                │ 35.0     │ backend/services/air_quality║
║ DEFAULT_PM10_UG_M3                │ 50.0     │ backend/services/air_quality║
║ DEFAULT_LFL_VOL_PCT               │ 0.5      │ backend/services/hazmat   ║
║ DEFAULT_AUTO_IGNITION_C           │ 200.0    │ backend/services/hazmat   ║
║ NFPA72_MINIMUM_SAFETY_FACTOR      │ 1.20     │ fireai/core/battery_aging_derating║
║ MAX_DEVICES_BETWEEN_ISOLATORS     │ 32       │ fireai/core/circuit_topology║
║ MAX_SLC_DEVICES_DEFAULT           │ 250      │ fireai/core/circuit_topology║
║ MIN_STAIRWELL_PRESSURIZATION_PA   │ 25.0     │ fireai/core/building_systems_integration║
║ MAX_PRESSURE_DIFFERENTIAL_PA      │ 133.0    │ fireai/core/building_systems_integration║
║ COVERAGE_THRESHOLD_PCT            │ 99.9     │ fireai/core/spatial_engine/constraint_solver║
║ MIN_GRID_STEP                     │ 0.5      │ fireai/core/spatial_engine/constraint_solver║
║ CIRCLE_SEGMENTS                   │ 16       │ fireai/core/spatial_engine/constraint_solver║
║ TIA568_HORIZONTAL_MAX_M           │ 90.0     │ fireai/core/qomn_kernel   ║
║ TIA568_TOTAL_CHANNEL_MAX_M        │ 100.0    │ fireai/core/qomn_kernel   ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║                   KNOWN DRIFT ISSUES (TO BE FIXED)                        ║
╠══════════════════════════════════════════════════════════════════════════╣
║ FILE                                    │ ISSUE                        ║
╠══════════════════════════════════════════════════════════════════════════╣
║ fireai/core/nfpa72_models.py:48         │ MIN_WALL_DISTANCE_M = 0.10   ║
║                                        │ Should be 0.1016             ║
║ fireai/core/spatial_engine/             │ MAX_SPACING_M defined inline ║
║ density_optimizer.py:63-64              │ Should import from nfpa72.py ║
║ fireai/core/digital_twin.py:95-105      │ NFPA72_*_RADIUS_M hardcoded  ║
║                                        │ Should import from nfpa72.py ║
║ fireai/validation/qa_engine.py:194-195  │ NFPA_*_MAX_SPACING_M defined ║
║                                        │ Should import from nfpa72.py ║
╚══════════════════════════════════════════════════════════════════════════╝

=============================================================================
USAGE EXAMPLE:
=============================================================================

    # ✅ CORRECT: Import from canonical source
    from fireai.constants.nfpa72 import (
        SMOKE_MAX_SPACING_M,
        HEAT_MAX_SPACING_M,
        WALL_MIN_DISTANCE_M,
        COVERAGE_RADIUS_FACTOR,
    )

    # ❌ WRONG: Redefining constants inline
    MAX_SPACING_M = 9.1  # DO NOT DO THIS

=============================================================================
"""

# This file is for DOCUMENTATION purposes only.
# It does not define any constants itself.