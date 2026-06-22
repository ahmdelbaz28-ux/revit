"""
ETAP-AI-WORK Engineering Copilot - Translation Engine
==================================================

Translation engine for converting between ETAP, AutoCAD, Revit, and Unified Engineering Model.

Principal Software Architect: Eng. Ahmed Elbaz
"""
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json

from engineering_copilot.models.unified_model import (
    UnifiedEngineeringModel, BaseEntity, Panel, Transformer, Bus, Cable, 
    Breaker, Load, Generator, Equipment, Coordinates, SourceSystem, EntityType
)
from engineering_copilot.connectors.autocad_connector import AutoCADConnector
from engineering_copilot.connectors.revit_connector import RevitConnector
from engineering_copilot.connectors.etap_connector import ETAPConnector


class TranslationEngine:
    """
    Translation engine for converting between different engineering systems:
    ETAP ↔ Unified Model ↔ AutoCAD
    ETAP ↔ Unified Model ↔ Revit
    AutoCAD ↔ Unified Model ↔ Revit
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Mapping rules between systems
        self.mapping_rules = {
            # ETAP to Unified
            ("ETAP", "Panel"): ("Panel", "create_switch"),
            ("ETAP", "Transformer"): ("Transformer", "create_transformer"),
            ("ETAP", "Bus"): ("Bus", "create_bus"),
            ("ETAP", "Cable"): ("Cable", "create_cable"),
            ("ETAP", "Breaker"): ("Breaker", "create_breaker"),
            ("ETAP", "Load"): ("Load", "create_load"),
            ("ETAP", "Generator"): ("Generator", "create_generator"),
            
            # AutoCAD to Unified
            ("AutoCAD", "Block"): ("Equipment", "create_block"),
            ("AutoCAD", "Line"): ("Cable", "create_line"),
            ("AutoCAD", "Circle"): ("Bus", "create_circle"),
            ("AutoCAD", "Text"): ("Annotation", "create_annotation"),
            
            # Revit to Unified
            ("Revit", "Panel"): ("Panel", "place_panel"),
            ("Revit", "Transformer"): ("Transformer", "place_transformer"),
            ("Revit", "CableTray"): ("Cable", "place_cable_tray"),
            ("Revit", "Conduit"): ("Cable", "place_conduit"),
            ("Revit", "ElectricalEquipment"): ("Equipment", "place_equipment"),
            
            # Unified to ETAP
            ("Unified", "Panel"): ("ETAP", "create_switch"),
            ("Unified", "Transformer"): ("ETAP", "create_transformer"),
            ("Unified", "Bus"): ("ETAP", "create_bus"),
            ("Unified", "Cable"): ("ETAP", "create_cable"),
            ("Unified", "Breaker"): ("ETAP", "create_breaker"),
            ("Unified", "Load"): ("ETAP", "create_load"),
            ("Unified", "Generator"): ("ETAP", "create_generator"),
            
            # Unified to AutoCAD
            ("Unified", "Panel"): ("AutoCAD", "insert_panel_block"),
            ("Unified", "Transformer"): ("AutoCAD", "insert_transformer_block"),
            ("Unified", "Bus"): ("AutoCAD", "draw_bus_duct"),
            ("Unified", "Cable"): ("AutoCAD", "draw_cable_polyline"),
            ("Unified", "Equipment"): ("AutoCAD", "insert_equipment_block"),
            
            # Unified to Revit
            ("Unified", "Panel"): ("Revit", "place_panel_family"),
            ("Unified", "Transformer"): ("Revit", "place_transformer_family"),
            ("Unified", "Cable"): ("Revit", "place_cable_tray"),
            ("Unified", "Equipment"): ("Revit", "place_equipment_family"),
        }
        
        # Symbol/Block mapping
        self.symbol_mapping = {
            "Transformer": {
                "ETAP": "XFMR_SYM",
                "AutoCAD": "TRANSFORMER_BLK",
                "Revit": "Transformer Family"
            },
            "Panel": {
                "ETAP": "SWITCH_SYM",
                "AutoCAD": "PANEL_BLK",
                "Revit": "Panel Family"
            },
            "Bus": {
                "ETAP": "BUS_SYM",
                "AutoCAD": "BUS_DUCT_PLINE",
                "Revit": "Busway Family"
            },
            "Cable": {
                "ETAP": "CABLE_SYM",
                "AutoCAD": "CABLE_PLINE",
                "Revit": "Cable Tray Family"
            },
            "Breaker": {
                "ETAP": "CB_SYM",
                "AutoCAD": "BREAKER_BLK",
                "Revit": "Breaker Family"
            }
        }
    
    def etap_to_unified(self, etap_data: Dict[str, Any]) -> UnifiedEngineeringModel:
        """
        Convert ETAP data to Unified Engineering Model.
        
        Args:
            etap_data: Raw ETAP data
            
        Returns:
            UnifiedEngineeringModel: Converted unified model
        """
        unified_model = UnifiedEngineeringModel()
        
        # Convert ETAP buses
        for bus_data in etap_data.get("buses", []):
            bus = Bus(
                id=bus_data["id"],
                name=bus_data["name"],
                description=f"ETAP bus: {bus_data['name']}",
                voltage_rating=bus_data.get("voltage", 0.0),
                current_rating=bus_data.get("rated_current", 0.0),
                source_system=SourceSystem.ETAP,
                coordinates=Coordinates(0.0, 0.0)  # Would come from SLD coordinates
            )
            unified_model.add_entity(bus)
        
        # Convert ETAP transformers
        for xfmer_data in etap_data.get("transformers", []):
            transformer = Transformer(
                id=xfmer_data["id"],
                name=xfmer_data["name"],
                description=f"ETAP transformer: {xfmer_data['name']}",
                primary_voltage=xfmer_data.get("primary_voltage", 0.0),
                secondary_voltage=xfmer_data.get("secondary_voltage", 0.0),
                power_rating=xfmer_data.get("power_rating", 0.0),
                source_system=SourceSystem.ETAP,
                coordinates=Coordinates(0.0, 0.0)
            )
            unified_model.add_entity(transformer)
        
        # Convert ETAP panels
        for panel_data in etap_data.get("panels", []):
            panel = Panel(
                id=panel_data["id"],
                name=panel_data["name"],
                description=f"ETAP panel: {panel_data['name']}",
                voltage_rating=panel_data.get("voltage_rating", 0.0),
                current_rating=panel_data.get("current_rating", 0.0),
                feeder_count=panel_data.get("feeder_count", 0),
                source_system=SourceSystem.ETAP,
                coordinates=Coordinates(0.0, 0.0)
            )
            unified_model.add_entity(panel)
        
        # Convert ETAP cables
        for cable_data in etap_data.get("cables", []):
            cable = Cable(
                id=cable_data["id"],
                name=cable_data["name"],
                description=f"ETAP cable: {cable_data['name']}",
                voltage_rating=cable_data.get("voltage_rating", 0.0),
                conductor_size=cable_data.get("conductor_size", ""),
                length=cable_data.get("length", 0.0),
                source_system=SourceSystem.ETAP,
                coordinates=Coordinates(0.0, 0.0)
            )
            unified_model.add_entity(cable)
        
        # Convert ETAP breakers
        for brkr_data in etap_data.get("breakers", []):
            breaker = Breaker(
                id=brkr_data["id"],
                name=brkr_data["name"],
                description=f"ETAP breaker: {brkr_data['name']}",
                voltage_rating=brkr_data.get("voltage_rating", 0.0),
                current_rating=brkr_data.get("current_rating", 0.0),
                interrupting_rating=brkr_data.get("interrupting_rating", 0.0),
                source_system=SourceSystem.ETAP,
                coordinates=Coordinates(0.0, 0.0)
            )
            unified_model.add_entity(breaker)
        
        # Convert ETAP loads
        for load_data in etap_data.get("loads", []):
            load = Load(
                id=load_data["id"],
                name=load_data["name"],
                description=f"ETAP load: {load_data['name']}",
                power_rating=load_data.get("power_rating", 0.0),
                power_factor=load_data.get("power_factor", 1.0),
                source_system=SourceSystem.ETAP,
                coordinates=Coordinates(0.0, 0.0)
            )
            unified_model.add_entity(load)
        
        # Convert ETAP generators
        for gen_data in etap_data.get("generators", []):
            generator = Generator(
                id=gen_data["id"],
                name=gen_data["name"],
                description=f"ETAP generator: {gen_data['name']}",
                power_rating=gen_data.get("power_rating", 0.0),
                voltage_rating=gen_data.get("voltage_rating", 0.0),
                source_system=SourceSystem.ETAP,
                coordinates=Coordinates(0.0, 0.0)
            )
            unified_model.add_entity(generator)
        
        self.logger.info(f"Converted ETAP data to unified model with {len(unified_model.entities)} entities")
        return unified_model
    
    def autocad_to_unified(self, autocad_data: Dict[str, Any]) -> UnifiedEngineeringModel:
        """
        Convert AutoCAD data to Unified Engineering Model.
        
        Args:
            autocad_data: Raw AutoCAD data
            
        Returns:
            UnifiedEngineeringModel: Converted unified model
        """
        unified_model = UnifiedEngineeringModel()
        
        # Convert AutoCAD blocks to equipment/panels/transformers
        for block_ref in autocad_data.get("blocks", []):
            block_name = block_ref.get("name", "").upper()
            
            if "PANEL" in block_name or "MDB" in block_name or "DB" in block_name:
                panel = Panel(
                    id=block_ref["id"],
                    name=block_ref.get("name", "Unnamed Panel"),
                    description=f"AutoCAD panel block: {block_ref['name']}",
                    voltage_rating=block_ref.get("voltage_rating", 480.0),
                    current_rating=block_ref.get("current_rating", 400.0),
                    feeder_count=block_ref.get("feeder_count", 0),
                    source_system=SourceSystem.AUTOCAD,
                    coordinates=Coordinates(
                        block_ref.get("x", 0.0),
                        block_ref.get("y", 0.0)
                    )
                )
                unified_model.add_entity(panel)
            
            elif "XFMR" in block_name or "TRANSFORMER" in block_name or "XFMER" in block_name:
                transformer = Transformer(
                    id=block_ref["id"],
                    name=block_ref.get("name", "Unnamed Transformer"),
                    description=f"AutoCAD transformer block: {block_ref['name']}",
                    primary_voltage=block_ref.get("primary_voltage", 13800.0),
                    secondary_voltage=block_ref.get("secondary_voltage", 480.0),
                    power_rating=block_ref.get("power_rating", 1000.0),
                    source_system=SourceSystem.AUTOCAD,
                    coordinates=Coordinates(
                        block_ref.get("x", 0.0),
                        block_ref.get("y", 0.0)
                    )
                )
                unified_model.add_entity(transformer)
            
            else:
                equipment = Equipment(
                    id=block_ref["id"],
                    name=block_ref.get("name", "Unnamed Equipment"),
                    description=f"AutoCAD equipment block: {block_ref['name']}",
                    equipment_type="General Equipment",
                    source_system=SourceSystem.AUTOCAD,
                    coordinates=Coordinates(
                        block_ref.get("x", 0.0),
                        block_ref.get("y", 0.0)
                    )
                )
                unified_model.add_entity(equipment)
        
        # Convert AutoCAD polylines to cables
        for polyline in autocad_data.get("polylines", []):
            cable = Cable(
                id=polyline["id"],
                name=f"Cable_{polyline['id']}",
                description="AutoCAD polyline converted to cable",
                voltage_rating=polyline.get("voltage_rating", 600.0),
                conductor_size=polyline.get("conductor_size", "AWG"),
                length=polyline.get("length", 0.0),
                source_system=SourceSystem.AUTOCAD,
                coordinates=Coordinates(0.0, 0.0)  # Would be calculated from polyline
            )
            unified_model.add_entity(cable)
        
        # Convert AutoCAD circles to buses
        for circle in autocad_data.get("circles", []):
            bus = Bus(
                id=circle["id"],
                name=f"Bus_{circle['id']}",
                description="AutoCAD circle converted to bus",
                voltage_rating=circle.get("voltage_rating", 480.0),
                current_rating=circle.get("current_rating", 1000.0),
                source_system=SourceSystem.AUTOCAD,
                coordinates=Coordinates(
                    circle.get("center_x", 0.0),
                    circle.get("center_y", 0.0)
                )
            )
            unified_model.add_entity(bus)
        
        self.logger.info(f"Converted AutoCAD data to unified model with {len(unified_model.entities)} entities")
        return unified_model
    
    def revit_to_unified(self, revit_data: Dict[str, Any]) -> UnifiedEngineeringModel:
        """
        Convert Revit data to Unified Engineering Model.
        
        Args:
            revit_data: Raw Revit data
            
        Returns:
            UnifiedEngineeringModel: Converted unified model
        """
        unified_model = UnifiedEngineeringModel()
        
        # Convert Revit electrical equipment to unified entities
        for element in revit_data.get("elements", []):
            element_type = element.get("type", "").lower()
            category = element.get("category", "").lower()
            
            if "panel" in element_type or "panel" in category:
                panel = Panel(
                    id=element["id"],
                    name=element.get("name", "Unnamed Panel"),
                    description=f"Revit panel: {element['name']}",
                    voltage_rating=element.get("voltage_rating", 480.0),
                    current_rating=element.get("current_rating", 400.0),
                    feeder_count=element.get("feeder_count", 0),
                    source_system=SourceSystem.REVIT,
                    coordinates=Coordinates(
                        element.get("x", 0.0),
                        element.get("y", 0.0)
                    )
                )
                unified_model.add_entity(panel)
            
            elif "transformer" in element_type or "transformer" in category:
                transformer = Transformer(
                    id=element["id"],
                    name=element.get("name", "Unnamed Transformer"),
                    description=f"Revit transformer: {element['name']}",
                    primary_voltage=element.get("primary_voltage", 13800.0),
                    secondary_voltage=element.get("secondary_voltage", 480.0),
                    power_rating=element.get("power_rating", 1000.0),
                    source_system=SourceSystem.REVIT,
                    coordinates=Coordinates(
                        element.get("x", 0.0),
                        element.get("y", 0.0)
                    )
                )
                unified_model.add_entity(transformer)
            
            elif "cable" in element_type or "tray" in element_type or "conduit" in element_type:
                cable = Cable(
                    id=element["id"],
                    name=element.get("name", "Unnamed Cable"),
                    description=f"Revit cable: {element['name']}",
                    voltage_rating=element.get("voltage_rating", 600.0),
                    conductor_size=element.get("conductor_size", "AWG"),
                    length=element.get("length", 0.0),
                    source_system=SourceSystem.REVIT,
                    coordinates=Coordinates(
                        element.get("x", 0.0),
                        element.get("y", 0.0)
                    )
                )
                unified_model.add_entity(cable)
            
            else:
                equipment = Equipment(
                    id=element["id"],
                    name=element.get("name", "Unnamed Equipment"),
                    description=f"Revit equipment: {element['name']}",
                    equipment_type=element.get("category", "General Equipment"),
                    source_system=SourceSystem.REVIT,
                    coordinates=Coordinates(
                        element.get("x", 0.0),
                        element.get("y", 0.0)
                    )
                )
                unified_model.add_entity(equipment)
        
        self.logger.info(f"Converted Revit data to unified model with {len(unified_model.entities)} entities")
        return unified_model
    
    def unified_to_etap(self, unified_model: UnifiedEngineeringModel) -> Dict[str, Any]:
        """
        Convert Unified Engineering Model to ETAP operations.
        
        Args:
            unified_model: Unified model to convert
            
        Returns:
            Dict: ETAP operations
        """
        etap_operations = {
            "create_buses": [],
            "create_transformers": [],
            "create_panels": [],
            "create_cables": [],
            "create_breakers": [],
            "create_loads": [],
            "create_generators": [],
            "update_parameters": [],
            "run_studies": []
        }
        
        for entity in unified_model.entities:
            if isinstance(entity, Bus):
                etap_operations["create_buses"].append({
                    "name": entity.name,
                    "voltage": entity.voltage_rating,
                    "rated_current": entity.current_rating,
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0]
                })
            
            elif isinstance(entity, Transformer):
                etap_operations["create_transformers"].append({
                    "name": entity.name,
                    "primary_voltage": entity.primary_voltage,
                    "secondary_voltage": entity.secondary_voltage,
                    "power_rating": entity.power_rating,
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0]
                })
            
            elif isinstance(entity, Panel):
                etap_operations["create_panels"].append({
                    "name": entity.name,
                    "voltage_rating": entity.voltage_rating,
                    "current_rating": entity.current_rating,
                    "feeder_count": entity.feeder_count,
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0]
                })
            
            elif isinstance(entity, Cable):
                etap_operations["create_cables"].append({
                    "name": entity.name,
                    "voltage_rating": entity.voltage_rating,
                    "conductor_size": entity.conductor_size,
                    "length": entity.length,
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0]
                })
            
            elif isinstance(entity, Breaker):
                etap_operations["create_breakers"].append({
                    "name": entity.name,
                    "voltage_rating": entity.voltage_rating,
                    "current_rating": entity.current_rating,
                    "interrupting_rating": entity.interrupting_rating,
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0]
                })
            
            elif isinstance(entity, Load):
                etap_operations["create_loads"].append({
                    "name": entity.name,
                    "power_rating": entity.power_rating,
                    "power_factor": entity.power_factor,
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0]
                })
            
            elif isinstance(entity, Generator):
                etap_operations["create_generators"].append({
                    "name": entity.name,
                    "power_rating": entity.power_rating,
                    "voltage_rating": entity.voltage_rating,
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0]
                })
        
        self.logger.info(f"Converted unified model to {sum(len(v) for v in etap_operations.values())} ETAP operations")
        return etap_operations
    
    def unified_to_autocad(self, unified_model: UnifiedEngineeringModel) -> Dict[str, Any]:
        """
        Convert Unified Engineering Model to AutoCAD operations.
        
        Args:
            unified_model: Unified model to convert
            
        Returns:
            Dict: AutoCAD operations
        """
        autocad_operations = {
            "insert_blocks": [],
            "draw_lines": [],
            "draw_polylines": [],
            "draw_circles": [],
            "draw_arcs": [],
            "draw_text": [],
            "create_layers": [],
            "set_properties": []
        }
        
        for entity in unified_model.entities:
            if isinstance(entity, Panel):
                autocad_operations["insert_blocks"].append({
                    "block_name": self.symbol_mapping["Panel"]["AutoCAD"],
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0],
                    "rotation": 0.0,
                    "scale": 1.0,
                    "attributes": {
                        "NAME": entity.name,
                        "VOLTAGE": entity.voltage_rating,
                        "CURRENT": entity.current_rating,
                        "FEEDERS": entity.feeder_count
                    }
                })
            
            elif isinstance(entity, Transformer):
                autocad_operations["insert_blocks"].append({
                    "block_name": self.symbol_mapping["Transformer"]["AutoCAD"],
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0],
                    "rotation": 0.0,
                    "scale": 1.0,
                    "attributes": {
                        "NAME": entity.name,
                        "PRIMARY_VOLTAGE": entity.primary_voltage,
                        "SECONDARY_VOLTAGE": entity.secondary_voltage,
                        "POWER_RATING": entity.power_rating
                    }
                })
            
            elif isinstance(entity, Bus):
                autocad_operations["draw_circles"].append({
                    "center": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0],
                    "radius": 1.0,
                    "layer": "E-BUS"
                })
            
            elif isinstance(entity, Cable):
                # Create a polyline representing the cable
                autocad_operations["draw_polylines"].append({
                    "points": [
                        [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0],
                        [entity.coordinates.x + entity.length/10, entity.coordinates.y] if entity.coordinates else [0.0, 0.0]  # Simplified
                    ],
                    "layer": "E-CABLE",
                    "width": 0.1
                })
            
            elif isinstance(entity, Equipment):
                autocad_operations["insert_blocks"].append({
                    "block_name": "EQUIPMENT_GENERIC",
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0],
                    "rotation": 0.0,
                    "scale": 1.0,
                    "attributes": {
                        "NAME": entity.name,
                        "TYPE": entity.equipment_type
                    }
                })
        
        self.logger.info(f"Converted unified model to {sum(len(v) for v in autocad_operations.values())} AutoCAD operations")
        return autocad_operations
    
    def unified_to_revit(self, unified_model: UnifiedEngineeringModel) -> Dict[str, Any]:
        """
        Convert Unified Engineering Model to Revit operations.
        
        Args:
            unified_model: Unified model to convert
            
        Returns:
            Dict: Revit operations
        """
        revit_operations = {
            "place_families": [],
            "create_groups": [],
            "set_parameters": [],
            "create_views": [],
            "update_sheets": []
        }
        
        for entity in unified_model.entities:
            if isinstance(entity, Panel):
                revit_operations["place_families"].append({
                    "family_name": self.symbol_mapping["Panel"]["Revit"],
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0],
                    "parameters": {
                        "Panel Name": entity.name,
                        "Voltage Rating": entity.voltage_rating,
                        "Current Rating": entity.current_rating,
                        "Feeder Count": entity.feeder_count
                    }
                })
            
            elif isinstance(entity, Transformer):
                revit_operations["place_families"].append({
                    "family_name": self.symbol_mapping["Transformer"]["Revit"],
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0],
                    "parameters": {
                        "Transformer Name": entity.name,
                        "Primary Voltage": entity.primary_voltage,
                        "Secondary Voltage": entity.secondary_voltage,
                        "Power Rating": entity.power_rating
                    }
                })
            
            elif isinstance(entity, Cable):
                revit_operations["place_families"].append({
                    "family_name": self.symbol_mapping["Cable"]["Revit"],
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0],
                    "parameters": {
                        "Cable Name": entity.name,
                        "Voltage Rating": entity.voltage_rating,
                        "Conductor Size": entity.conductor_size,
                        "Length": entity.length
                    }
                })
            
            elif isinstance(entity, Equipment):
                revit_operations["place_families"].append({
                    "family_name": "Generic Model",  # Default family
                    "coordinates": [entity.coordinates.x, entity.coordinates.y] if entity.coordinates else [0.0, 0.0],
                    "parameters": {
                        "Equipment Name": entity.name,
                        "Equipment Type": entity.equipment_type
                    }
                })
        
        self.logger.info(f"Converted unified model to {len(revit_operations['place_families'])} Revit operations")
        return revit_operations
    
    def translate(self, source_data: Any, source_system: str, target_system: str) -> Any:
        """
        Generic translation method between any two systems.
        
        Args:
            source_data: Source data to translate
            source_system: Source system name
            target_system: Target system name
            
        Returns:
            Translated data in target system format
        """
        self.logger.info(f"Translating from {source_system} to {target_system}")
        
        # First convert to unified model if source is not unified
        if source_system.lower() != "unified":
            if source_system.lower() == "etap":
                unified_model = self.etap_to_unified(source_data)
            elif source_system.lower() == "autocad":
                unified_model = self.autocad_to_unified(source_data)
            elif source_system.lower() == "revit":
                unified_model = self.revit_to_unified(source_data)
            else:
                raise ValueError(f"Unsupported source system: {source_system}")
        else:
            unified_model = source_data
        
        # Then convert from unified to target if target is not unified
        if target_system.lower() != "unified":
            if target_system.lower() == "etap":
                return self.unified_to_etap(unified_model)
            elif target_system.lower() == "autocad":
                return self.unified_to_autocad(unified_model)
            elif target_system.lower() == "revit":
                return self.unified_to_revit(unified_model)
            else:
                raise ValueError(f"Unsupported target system: {target_system}")
        else:
            return unified_model
    
    def sync_models(self, source_model: UnifiedEngineeringModel, target_model: UnifiedEngineeringModel) -> Dict[str, Any]:
        """
        Synchronize differences between two unified models.
        
        Args:
            source_model: Source unified model
            target_model: Target unified model to sync
            
        Returns:
            Dict: Sync results
        """
        sync_results = {
            "added": 0,
            "updated": 0,
            "removed": 0,
            "conflicts": [],
            "summary": ""
        }
        
        # Create lookup dictionaries for both models
        source_entities = {entity.id: entity for entity in source_model.entities}
        target_entities = {entity.id: entity for entity in target_model.entities}
        
        # Add new entities from source that don't exist in target
        for entity_id, entity in source_entities.items():
            if entity_id not in target_entities:
                target_model.add_entity(entity)
                sync_results["added"] += 1
        
        # Update existing entities that have changed
        for entity_id, source_entity in source_entities.items():
            if entity_id in target_entities:
                target_entity = target_entities[entity_id]
                
                # Check if entities are different (simplified comparison)
                if (source_entity.name != target_entity.name or 
                    source_entity.description != target_entity.description or
                    (source_entity.coordinates and target_entity.coordinates and
                     source_entity.coordinates.x != target_entity.coordinates.x) or
                    (source_entity.coordinates and target_entity.coordinates and
                     source_entity.coordinates.y != target_entity.coordinates.y)):
                    
                    # Update the target entity
                    target_model.update_entity(source_entity)
                    sync_results["updated"] += 1
        
        # Remove entities from target that don't exist in source
        for entity_id in list(target_entities.keys()):
            if entity_id not in source_entities:
                target_model.remove_entity(entity_id)
                sync_results["removed"] += 1
        
        sync_results["summary"] = f"Sync completed: {sync_results['added']} added, {sync_results['updated']} updated, {sync_results['removed']} removed"
        self.logger.info(sync_results["summary"])
        
        return sync_results