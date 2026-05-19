"""
core/production_config.py
==========================
Production-grade engineering constants for FireAI.

Consolidates all NFPA, NEC, and building code constants used across
the FireAI system. Single source of truth for engineering parameters.

Sections:
  0. NFPA 72 — Fire alarm spacing and coverage
  1. NEC — Conduit, cable, and wiring constraints
  2. Building code — Room dimensions, clearance
  3. Routing — Bend radius, max run, fill ratios
  4. IFC — Schema version, GUID format
  5. Geometry — Snap tolerance, intersection epsilon

Usage:
    from core.production_config import ProductionConfig
    cfg = ProductionConfig()
    print(cfg.nfpa72_smoke_spacing_smooth)  # 9.1 m
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Tuple

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# NFPA 72 Constants (2022 Edition)
# ════════════════════════════════════════════════════════════════════════════

NFPA72_SMOKE_SPACING = {
    "smooth":       9.1,    # m — ceiling with slope <= 10°, no beams
    "beam_spacing": 9.1,    # m — base, adjusted per beam depth
    "corridor":     9.1,    # m — corridor spacing
    "sloped":       9.1,    # m — within 0.9 m measured vertically
}

NFPA72_HEAT_SPACING = {
    "fixed_135F":   6.77,   # m — 57°C fixed-temperature
    "fixed_165F":   6.77,   # m — 74°C
    "rate_of_rise": 6.77,   # m
}

NFPA72_AREA_COVERAGE = {
    "smoke_smooth":      83.6,   # m² (9.1 m spacing → 9.1² × π/π ≈ square)
    "heat_fixed":        45.6,   # m² (6.77 m spacing)
    "smoke_corridor":    83.6,   # m²
    "smoke_beam_ceiling": 37.2,  # m² — when beam depth >= 10% of ceiling height
}

NFPA72_SOUND_PRESSURE = {
    "min_db_office":       55,     # dBA — private offices
    "min_db_corridor":     55,     # dBA — corridors
    "min_db_sleeping":     75,     # dBA — sleeping areas (measured at pillow)
    "min_db_mechanical":   65,     # dBA — mechanical rooms
    "min_db_outdoor":      55,     # dBA — outdoor areas
    "max_db":              110,    # dBA — maximum allowed
}

NFPA72_MONITORING = {
    "supervisory_interval_s":  90,     # seconds — check every 90s
    "trouble_response_s":      200,    # seconds — trouble signal response
    "alarm_verification_s":    60,     # seconds — alarm verification
}


# ════════════════════════════════════════════════════════════════════════════
# NEC Constants (2023 Edition)
# ════════════════════════════════════════════════════════════════════════════

NEC_CONDUIT_FILL = {
    "1_wire":  0.53,   # 53% fill — 1 wire in conduit
    "2_wires": 0.31,   # 31% fill — 2 wires
    "3_plus":  0.40,   # 40% fill — 3+ wires
}

NEC_CONDUIT_TYPES = {
    "EMT":   {"min_bend_radius_factor": 4.0,  "max_run_m": 30.48},   # 100 ft
    "RMC":   {"min_bend_radius_factor": 6.0,  "max_run_m": 30.48},
    "IMC":   {"min_bend_radius_factor": 5.0,  "max_run_m": 30.48},
    "FMC":   {"min_bend_radius_factor": 3.0,  "max_run_m": 15.24},   # 50 ft
    "PVC":   {"min_bend_radius_factor": 8.0,  "max_run_m": 30.48},
    "LFMC":  {"min_bend_radius_factor": 3.5,  "max_run_m": 15.24},
}

NEC_WIRE_GAUGE = {
    # AWG → {diameter_mm, area_mm2, max_amps, resistance_ohm_per_km}
    "18AWG": {"diameter_mm": 1.024,  "area_mm2": 0.823,  "max_amps": 5,   "resistance": 21.4},
    "16AWG": {"diameter_mm": 1.291,  "area_mm2": 1.309,  "max_amps": 10,  "resistance": 13.17},
    "14AWG": {"diameter_mm": 1.628,  "area_mm2": 2.081,  "max_amps": 15,  "resistance": 8.282},
    "12AWG": {"diameter_mm": 2.053,  "area_mm2": 3.309,  "max_amps": 20,  "resistance": 5.211},
    "10AWG": {"diameter_mm": 2.588,  "area_mm2": 5.261,  "max_amps": 30,  "resistance": 3.277},
}

NEC_CABLE_DE_RATING = {
    "2_4_active":    0.80,   # 80% derating for 2-4 current-carrying conductors
    "5_7_active":    0.70,   # 70%
    "8_10_active":   0.70,
    "11_21_active":  0.50,
    "22_31_active":  0.45,
    "32_41_active":  0.40,
}

NEC_VOLTAGE_DROP_MAX = 0.05   # 5% max voltage drop on branch circuit


# ════════════════════════════════════════════════════════════════════════════
# Building Code Constants
# ════════════════════════════════════════════════════════════════════════════

BUILDING_CODE = {
    "min_corridor_width_m":     1.12,    # 44 inches minimum
    "min_door_width_m":         0.91,    # 36 inches
    "min_ceiling_height_m":     2.44,    # 8 feet
    "max_travel_distance_m":    60.0,    # to exit — business occupancy
    "max_travel_warehouse_m":   90.0,    # warehouse
    "stair_width_min_m":        1.12,    # 44 inches
    "min_room_area_m2":         9.3,     # habitable room minimum
}

ROOM_TYPE_DEFAULTS = {
    "office":        {"ceiling_height": 2.8, "ceiling_type": "SMOOTH"},
    "corridor":      {"ceiling_height": 2.6, "ceiling_type": "SMOOTH"},
    "warehouse":     {"ceiling_height": 6.0, "ceiling_type": "SMOOTH"},
    "server_room":   {"ceiling_height": 3.0, "ceiling_type": "SMOOTH"},
    "stairwell":     {"ceiling_height": 2.8, "ceiling_type": "SLOPED"},
    "mechanical":    {"ceiling_height": 3.6, "ceiling_type": "BEAMED"},
    "assembly":      {"ceiling_height": 4.0, "ceiling_type": "SMOOTH"},
    "storage":       {"ceiling_height": 3.0, "ceiling_type": "SMOOTH"},
    "kitchen":       {"ceiling_height": 2.8, "ceiling_type": "SMOOTH"},
    "lobby":         {"ceiling_height": 3.5, "ceiling_type": "SMOOTH"},
}


# ════════════════════════════════════════════════════════════════════════════
# Routing Constraints
# ════════════════════════════════════════════════════════════════════════════

ROUTING_DEFAULTS = {
    "bend_radius_mm":           300.0,   # Minimum bend radius
    "max_cable_length_m":       300.0,   # Max cable run before junction
    "clearance_mm":             50.0,    # Minimum clearance from obstacles
    "conduit_type_default":     "EMT",
    "conduit_size_mm":          20.0,    # 3/4" EMT
    "vertical_rise_penalty":    1.5,     # Cost multiplier for vertical runs
    "cross_corridor_penalty":   2.0,     # Cost multiplier for crossing corridors
}

OBSTACLE_CLEARANCES = {
    "wall":       50.0,    # mm — minimum clearance from wall surface
    "hvac":       150.0,   # mm — clearance from HVAC duct
    "sprinkler":  450.0,   # mm — NFPA 13 clearance from sprinkler
    "stairwell":  300.0,   # mm — clearance from stair edges
    "beam":       100.0,   # mm — clearance from beam bottom
    "light":      200.0,   # mm — clearance from light fixtures
    "column":     50.0,    # mm — clearance from column surface
}


# ════════════════════════════════════════════════════════════════════════════
# IFC Constants
# ════════════════════════════════════════════════════════════════════════════

IFC_CONSTANTS = {
    "schema_version":      "IFC4",
    "guid_length":         22,          # buildingSMART Compressed GUID
    "guid_charset":        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$",
    "step_header_org":     "FireAI",
    "step_header_app":     "FireAI-BIM-Engine",
    "step_header_version": "2.0",
}


# ════════════════════════════════════════════════════════════════════════════
# Geometry Constants
# ════════════════════════════════════════════════════════════════════════════

GEOMETRY_CONSTANTS = {
    "snap_tolerance":      0.001,    # m — 1mm snap grid for deduplication
    "intersection_epsilon": 1e-10,   # Numerical tolerance for self-intersection
    "min_polygon_area":    0.01,     # m² — reject degenerate polygons
    "ccw_area_threshold":  0.0,      # Positive area = CCW
    "max_polygon_vertices": 10000,   # Safety limit
}


# ════════════════════════════════════════════════════════════════════════════
# ProductionConfig — Single Access Point
# ════════════════════════════════════════════════════════════════════════════

class ProductionConfig:
    """
    Single source of truth for all FireAI engineering constants.

    Provides dot-notation access to all NFPA/NEC/routing/IFC constants.
    Immutable after creation — no runtime modifications.

    Usage:
        cfg = ProductionConfig()
        spacing = cfg.nfpa72_smoke_spacing("smooth")       # 9.1
        fill    = cfg.nec_conduit_fill("3_plus")            # 0.40
        radius  = cfg.routing_bend_radius                   # 300.0
    """

    def __init__(self, overrides: Dict = None):
        """
        Initialize with optional overrides for testing.

        Parameters
        ----------
        overrides : dict, optional
            Key-value pairs to override defaults. Keys must match
            existing attribute names.
        """
        # NFPA 72
        self._nfpa72_smoke_spacing = dict(NFPA72_SMOKE_SPACING)
        self._nfpa72_heat_spacing = dict(NFPA72_HEAT_SPACING)
        self._nfpa72_area_coverage = dict(NFPA72_AREA_COVERAGE)
        self._nfpa72_sound = dict(NFPA72_SOUND_PRESSURE)
        self._nfpa72_monitoring = dict(NFPA72_MONITORING)

        # NEC
        self._nec_conduit_fill = dict(NEC_CONDUIT_FILL)
        self._nec_conduit_types = dict(NEC_CONDUIT_TYPES)
        self._nec_wire_gauge = dict(NEC_WIRE_GAUGE)
        self._nec_derating = dict(NEC_CABLE_DE_RATING)
        self._nec_voltage_drop_max = NEC_VOLTAGE_DROP_MAX

        # Building
        self._building_code = dict(BUILDING_CODE)
        self._room_type_defaults = dict(ROOM_TYPE_DEFAULTS)

        # Routing
        self._routing = dict(ROUTING_DEFAULTS)
        self._obstacle_clearances = dict(OBSTACLE_CLEARANCES)

        # IFC
        self._ifc = dict(IFC_CONSTANTS)

        # Geometry
        self._geometry = dict(GEOMETRY_CONSTANTS)

        # Apply overrides
        if overrides:
            for key, value in overrides.items():
                if hasattr(self, key):
                    setattr(self, key, value)
                else:
                    log.warning("ProductionConfig: unknown override key '%s'", key)

    # ── NFPA 72 Accessors ──

    def nfpa72_smoke_spacing(self, ceiling_type: str = "smooth") -> float:
        """Get smoke detector spacing for given ceiling type (metres)."""
        return self._nfpa72_smoke_spacing.get(ceiling_type, 9.1)

    def nfpa72_heat_spacing(self, heat_type: str = "fixed_135F") -> float:
        """Get heat detector spacing (metres)."""
        return self._nfpa72_heat_spacing.get(heat_type, 6.77)

    def nfpa72_area_coverage(self, config: str = "smoke_smooth") -> float:
        """Get area coverage for detector type/config (m²)."""
        return self._nfpa72_area_coverage.get(config, 83.6)

    def nfpa72_sound_min(self, area_type: str = "office") -> int:
        """Get minimum sound pressure level (dBA)."""
        key = f"min_db_{area_type}"
        return self._nfpa72_sound.get(key, 55)

    @property
    def nfpa72_supervisory_interval_s(self) -> int:
        """Supervisory check interval in seconds."""
        return self._nfpa72_monitoring["supervisory_interval_s"]

    # ── NEC Accessors ──

    def nec_conduit_fill(self, wire_count_class: str = "3_plus") -> float:
        """Get conduit fill ratio."""
        return self._nec_conduit_fill.get(wire_count_class, 0.40)

    def nec_conduit_info(self, conduit_type: str = "EMT") -> Dict:
        """Get conduit type info (bend radius factor, max run)."""
        return self._nec_conduit_types.get(conduit_type,
                                            self._nec_conduit_types["EMT"])

    def nec_wire_info(self, gauge: str = "14AWG") -> Dict:
        """Get wire gauge info."""
        return self._nec_wire_gauge.get(gauge, self._nec_wire_gauge["14AWG"])

    def nec_derating(self, conductor_count_class: str = "2_4_active") -> float:
        """Get cable derating factor."""
        return self._nec_derating.get(conductor_count_class, 0.80)

    @property
    def nec_voltage_drop_max(self) -> float:
        """Maximum allowable voltage drop ratio."""
        return self._nec_voltage_drop_max

    # ── Building Code Accessors ──

    def building_code(self, key: str) -> float:
        """Get building code value."""
        return self._building_code.get(key, 0.0)

    def room_type_defaults(self, room_type: str) -> Dict:
        """Get default parameters for a room type."""
        return self._room_type_defaults.get(room_type,
                                             self._room_type_defaults["office"])

    # ── Routing Accessors ──

    @property
    def routing_bend_radius(self) -> float:
        """Minimum bend radius in mm."""
        return self._routing["bend_radius_mm"]

    @property
    def routing_max_cable_length(self) -> float:
        """Maximum cable run length in metres."""
        return self._routing["max_cable_length_m"]

    @property
    def routing_clearance(self) -> float:
        """Minimum clearance from obstacles in mm."""
        return self._routing["clearance_mm"]

    @property
    def routing_conduit_type(self) -> str:
        """Default conduit type."""
        return self._routing["conduit_type_default"]

    @property
    def routing_vertical_penalty(self) -> float:
        """Cost multiplier for vertical cable runs."""
        return self._routing["vertical_rise_penalty"]

    @property
    def routing_cross_corridor_penalty(self) -> float:
        """Cost multiplier for crossing corridors."""
        return self._routing["cross_corridor_penalty"]

    def obstacle_clearance(self, obstacle_type: str) -> float:
        """Get clearance for a specific obstacle type (mm)."""
        return self._obstacle_clearances.get(obstacle_type,
                                              self._routing["clearance_mm"])

    # ── IFC Accessors ──

    @property
    def ifc_schema(self) -> str:
        """IFC schema version."""
        return self._ifc["schema_version"]

    @property
    def ifc_guid_length(self) -> int:
        """Expected IFC GUID length."""
        return self._ifc["guid_length"]

    @property
    def ifc_guid_charset(self) -> str:
        """Valid characters for IFC GUID."""
        return self._ifc["guid_charset"]

    @property
    def ifc_step_header(self) -> Dict:
        """STEP file header info."""
        return {
            "organization": self._ifc["step_header_org"],
            "application": self._ifc["step_header_app"],
            "version": self._ifc["step_header_version"],
        }

    # ── Geometry Accessors ──

    @property
    def snap_tolerance(self) -> float:
        """Snap-to-grid tolerance (metres)."""
        return self._geometry["snap_tolerance"]

    @property
    def intersection_epsilon(self) -> float:
        """Numerical tolerance for intersection tests."""
        return self._geometry["intersection_epsilon"]

    @property
    def min_polygon_area(self) -> float:
        """Minimum valid polygon area (m²)."""
        return self._geometry["min_polygon_area"]

    # ── Summary ──

    def summary(self) -> Dict:
        """Return a summary of all configuration values."""
        return {
            "nfpa72_smoke_spacing_smooth": self.nfpa72_smoke_spacing("smooth"),
            "nfpa72_heat_spacing": self.nfpa72_heat_spacing(),
            "nec_voltage_drop_max": self.nec_voltage_drop_max,
            "routing_bend_radius_mm": self.routing_bend_radius,
            "routing_max_cable_m": self.routing_max_cable_length,
            "ifc_schema": self.ifc_schema,
            "snap_tolerance_m": self.snap_tolerance,
        }


# ════════════════════════════════════════════════════════════════════════════
# Module-level singleton
# ════════════════════════════════════════════════════════════════════════════

_config_instance: ProductionConfig = None


def get_production_config(overrides: Dict = None) -> ProductionConfig:
    """Get or create the singleton ProductionConfig instance."""
    global _config_instance
    if _config_instance is None or overrides is not None:
        _config_instance = ProductionConfig(overrides=overrides)
    return _config_instance


# ════════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════════

def _self_test():
    """Run self-test for ProductionConfig."""
    print("=" * 60)
    print("ProductionConfig — Self-Test")
    print("=" * 60)

    cfg = ProductionConfig()

    # Test NFPA 72 accessors
    assert cfg.nfpa72_smoke_spacing("smooth") == 9.1, "Smoke spacing mismatch"
    assert cfg.nfpa72_heat_spacing("fixed_135F") == 6.77, "Heat spacing mismatch"
    assert cfg.nfpa72_area_coverage("smoke_smooth") == 83.6, "Area coverage mismatch"
    assert cfg.nfpa72_sound_min("sleeping") == 75, "Sound pressure mismatch"
    print("  [PASS] NFPA 72 accessors")

    # Test NEC accessors
    assert cfg.nec_conduit_fill("3_plus") == 0.40, "Conduit fill mismatch"
    emt = cfg.nec_conduit_info("EMT")
    assert emt["min_bend_radius_factor"] == 4.0, "EMT bend radius factor mismatch"
    wire = cfg.nec_wire_info("14AWG")
    assert wire["max_amps"] == 15, "14AWG ampacity mismatch"
    assert cfg.nec_voltage_drop_max == 0.05, "Voltage drop mismatch"
    print("  [PASS] NEC accessors")

    # Test building code
    assert cfg.building_code("min_corridor_width_m") == 1.12, "Corridor width mismatch"
    office = cfg.room_type_defaults("office")
    assert office["ceiling_height"] == 2.8, "Office ceiling height mismatch"
    print("  [PASS] Building code accessors")

    # Test routing
    assert cfg.routing_bend_radius == 300.0, "Bend radius mismatch"
    assert cfg.routing_max_cable_length == 300.0, "Max cable length mismatch"
    assert cfg.obstacle_clearance("sprinkler") == 450.0, "Sprinkler clearance mismatch"
    print("  [PASS] Routing accessors")

    # Test IFC
    assert cfg.ifc_schema == "IFC4", "IFC schema mismatch"
    assert cfg.ifc_guid_length == 22, "GUID length mismatch"
    header = cfg.ifc_step_header
    assert header["organization"] == "FireAI", "STEP header org mismatch"
    print("  [PASS] IFC accessors")

    # Test geometry
    assert cfg.snap_tolerance == 0.001, "Snap tolerance mismatch"
    assert cfg.min_polygon_area == 0.01, "Min polygon area mismatch"
    print("  [PASS] Geometry accessors")

    # Test singleton
    cfg2 = get_production_config()
    assert cfg2.nfpa72_smoke_spacing("smooth") == 9.1
    print("  [PASS] Singleton access")

    # Test summary
    s = cfg.summary()
    assert "nfpa72_smoke_spacing_smooth" in s
    print("  [PASS] Summary")

    # Test override
    cfg3 = ProductionConfig(overrides={})
    assert cfg3.ifc_schema == "IFC4"
    print("  [PASS] Empty overrides")

    print("\n" + "=" * 60)
    print("ProductionConfig Self-Test: PASS")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
