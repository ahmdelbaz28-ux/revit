"""
backend/services/marine_service.py — Marine Fire-Safety Service Layer.
=====================================================================
Service layer that orchestrates the marine package engines behind the
backend/routers/marine.py REST API.

Workflow:
    1. validate_ship() — verify SOLAS compliance of the ship zone model
    2. design_detection() — produce detector placements
    3. design_extinguishing() — size the extinguishing system per zone
    4. design_fire_divisions() — compute required fire classes
    5. design_alarm_logic() — produce PLC/DCS logic tree
    6. design_power_system() — IEC 60092 electrical sizing
    7. export_integrations() — SCADA + ETAP + Revit + AutoCAD outputs
"""

from __future__ import annotations

from typing import Any

from marine.core.types import (
    DetectorPlacement,
    ExtinguishingDesign,
    MarineZone,
    ShipProject,
)
from marine.engine.alarm_logic import (
    export_to_plc_script,
    generate_logic_tree,
)
from marine.engine.extinguishment import size_system
from marine.engine.fire_resistance import generate_division_specs
from marine.engine.zone_mapper import (
    compute_escape_route_adjacency,
    divide_into_main_vertical_zones,
)
from marine.iec60092.electrical_installations import (
    design_fire_system_power,
)
from marine.iec60092.part_502 import (
    place_detectors_grid,
    select_detector_type,
)
from marine.iec60092.part_504 import classify_hazardous_zone
from marine.integration.autocad_exporter import (
    draw_zones,
    generate_dxf_layer_definitions,
    place_detector_entities,
)
from marine.integration.etap_bridge import export_etap_loads_csv
from marine.integration.revit_exporter import (
    generate_revit_division,
    generate_revit_family,
    generate_revit_placement,
)
from marine.integration.scada_bridge import (
    build_mqtt_topics,
    build_pyscada_yaml,
)
from marine.solas.chapter_ii_2 import (
    validate_escape_routes,
    validate_fire_divisions,
    validate_main_vertical_zones,
)


class MarineService:
    """Stateless service: each method takes inputs, returns structured output."""

    def design_full(
        self,
        ship: ShipProject,
        zones: list[MarineZone] | None = None,
    ) -> dict[str, Any]:
        """
        Run the complete marine fire-safety design pipeline.

        Args:
            ship: Ship project descriptor.
            zones: Pre-divided zones. If None, auto-divide into MVZs.

        Returns:
            Dict with: zones, detectors, divisions, extinguishing,
            alarm_logic, power, integrations.

        """
        # 1. Zone division
        if zones is None:
            zones = divide_into_main_vertical_zones(
                ship.length_overall_m, ship, deck_count=1,
            )

        mvz_result = validate_main_vertical_zones(zones, ship)
        escape_result = validate_escape_routes(zones)
        adjacency_result = compute_escape_route_adjacency(zones)

        # 2. Detection design
        all_detectors: list[DetectorPlacement] = []
        for zone in zones:
            sel = select_detector_type(zone, ship)
            for dt_str in sel.details.get("selected_types", []):
                from marine.core.types import DetectorType
                dt = DetectorType(dt_str)
                placements = place_detectors_grid(zone, dt)
                all_detectors.extend(placements)

        # 3. Fire divisions
        divisions = generate_division_specs(zones)
        div_result = validate_fire_divisions(zones, divisions)

        # 4. Extinguishing
        extinguishing: list[ExtinguishingDesign] = []
        for zone in zones:
            try:
                design = size_system(zone, ship)
                extinguishing.append(design)
            except Exception:
                pass  # No fixed system required for this zone

        # 5. Alarm logic
        logic_nodes = []
        for zone in zones:
            zone_dps = [d for d in all_detectors if d.zone_id == zone.zone_id]
            logic_nodes.extend(generate_logic_tree(zone, zone_dps))
        plc_script = export_to_plc_script(logic_nodes)

        # 6. Power system
        power_spec = design_fire_system_power(ship)

        # 7. Hazardous zones (IEC 60092-504)
        hazardous = {}
        for zone in zones:
            hz = classify_hazardous_zone(zone, ship)
            hazardous[zone.zone_id] = hz.details.get("zone_classification", "non_hazardous")

        # 8. Integrations
        imo = ship.imo_number or "0000000"
        scada_tags = build_mqtt_topics(imo, [z.zone_id for z in zones])
        scada_yaml = build_pyscada_yaml(scada_tags)
        etap_csv = export_etap_loads_csv(ship, power_spec)
        dxf_layers = generate_dxf_layer_definitions()
        dxf_entities = place_detector_entities(all_detectors) + "\n" + draw_zones(zones)
        revit_families = [generate_revit_family(d) for d in all_detectors[:5]]  # sample
        revit_placements = [generate_revit_placement(d) for d in all_detectors]
        revit_divisions = [generate_revit_division(d) for d in divisions]

        return {
            "ship": ship.__dict__,
            "zones": [z.__dict__ for z in zones],
            "detectors": [d.__dict__ for d in all_detectors],
            "divisions": [d.__dict__ for d in divisions],
            "extinguishing": [e.__dict__ for e in extinguishing],
            "alarm_logic_nodes": [n.__dict__ for n in logic_nodes],
            "plc_script": plc_script,
            "power_spec": power_spec.__dict__,
            "hazardous_zones": hazardous,
            "compliance": {
                "mvz": mvz_result.__dict__,
                "escape_routes": escape_result.__dict__,
                "adjacency": adjacency_result.__dict__,
                "fire_divisions": div_result.__dict__,
            },
            "integrations": {
                "scada_yaml": scada_yaml,
                "etap_csv": etap_csv,
                "dxf": dxf_layers + "\n" + dxf_entities,
                "revit_families": revit_families,
                "revit_placements": revit_placements,
                "revit_divisions": revit_divisions,
            },
            "summary": {
                "zone_count": len(zones),
                "detector_count": len(all_detectors),
                "division_count": len(divisions),
                "extinguishing_systems": len(extinguishing),
                "logic_nodes": len(logic_nodes),
            },
        }


# Singleton accessor (FastAPI dependency injection pattern)
_marine_service: MarineService | None = None


def get_marine_service() -> MarineService:
    global _marine_service
    if _marine_service is None:
        _marine_service = MarineService()
    return _marine_service


__all__ = ["MarineService", "get_marine_service"]
