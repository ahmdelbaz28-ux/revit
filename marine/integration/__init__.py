"""marine/integration — External system bridges (SCADA, ETAP, Revit, AutoCAD)."""
from marine.integration.autocad_exporter import (
    DXF_LAYERS, draw_zones, generate_dxf_layer_definitions, generate_full_dxf,
    place_detector_entities,
)
from marine.integration.etap_bridge import (
    export_etap_loads_csv, export_etap_sources_csv,
)
from marine.integration.revit_exporter import (
    generate_revit_division, generate_revit_family, generate_revit_placement,
)
from marine.integration.scada_bridge import (
    SCADATag, build_modbus_registers, build_mqtt_topics, build_opcua_node_ids,
    build_pyscada_yaml, dashboard_payload,
)

__all__ = [
    "DXF_LAYERS", "SCADATag", "build_modbus_registers", "build_mqtt_topics",
    "build_opcua_node_ids", "build_pyscada_yaml", "dashboard_payload",
    "draw_zones", "export_etap_loads_csv", "export_etap_sources_csv",
    "generate_dxf_layer_definitions", "generate_full_dxf",
    "generate_revit_division", "generate_revit_family",
    "generate_revit_placement", "place_detector_entities",
]
