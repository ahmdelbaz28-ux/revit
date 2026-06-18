"""marine/engine — Core calculation engines (zone_mapper, detector_selector,
fire_resistance, extinguishment, alarm_logic)."""
from marine.engine.alarm_logic import export_to_plc_script, generate_logic_tree
from marine.engine.extinguishment import (
    size_co2_total_flooding, size_foam_low_expansion, size_inert_gas,
    size_sprinkler, size_system, size_water_mist,
)
from marine.engine.fire_resistance import (
    generate_division_specs, select_insulation_material,
)
from marine.engine.zone_mapper import (
    assign_space_categories, compute_escape_route_adjacency,
    divide_into_main_vertical_zones,
)

__all__ = [
    "assign_space_categories", "compute_escape_route_adjacency",
    "divide_into_main_vertical_zones", "export_to_plc_script",
    "generate_division_specs", "generate_logic_tree",
    "select_insulation_material", "size_co2_total_flooding",
    "size_foam_low_expansion", "size_inert_gas", "size_sprinkler",
    "size_system", "size_water_mist",
]
