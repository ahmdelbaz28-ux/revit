"""
ETAP-AI-WORK Engineering Copilot - Unified Engineering Model
===========================================================

Python classes for the unified engineering data model across ETAP, AutoCAD, and Revit.

Principal Software Architect: Eng. Ahmed Elbaz
"""
from datetime import datetime
from typing import List, Dict, Optional, Any, Union
from enum import Enum
from dataclasses import dataclass, field
from uuid import uuid4


class SourceSystem(str, Enum):
    """Enumeration of source systems for entities."""
    ETAP = "ETAP"
    AUTOCAD = "AutoCAD"
    REVIT = "Revit"
    UNIFIED = "Unified"


class EntityType(str, Enum):
    """Enumeration of entity types."""
    PROJECT = "Project"
    BUILDING = "Building"
    LEVEL = "Level"
    ROOM = "Room"
    ELECTRICAL_ROOM = "ElectricalRoom"
    PANEL = "Panel"
    SWITCHBOARD = "Switchboard"
    BUS = "Bus"
    TRANSFORMER = "Transformer"
    GENERATOR = "Generator"
    CABLE = "Cable"
    BREAKER = "Breaker"
    LOAD = "Load"
    MOTOR = "Motor"
    RELAY = "Relay"
    PROTECTION_DEVICE = "ProtectionDevice"
    CONDUIT = "Conduit"
    TRAY = "Tray"
    EQUIPMENT = "Equipment"
    ANNOTATION = "Annotation"


@dataclass
class Relationship:
    """Relationship between entities."""
    type: str
    entity_id: str
    relationship: str


@dataclass
class Coordinates:
    """Coordinates for positioning entities."""
    x: float
    y: float
    z: Optional[float] = 0.0


@dataclass
class BaseEntity:
    """Base class for all entities in the unified model."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    type: str = "BaseEntity"
    coordinates: Optional[Coordinates] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    relationships: List[Relationship] = field(default_factory=list)
    source_system: SourceSystem = SourceSystem.UNIFIED
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())
        if self.coordinates is None:
            self.coordinates = Coordinates(0.0, 0.0, 0.0)
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()


@dataclass
class Project(BaseEntity):
    """Project entity."""
    type: EntityType = EntityType.PROJECT
    project_number: str = ""
    project_phase: str = ""
    location: str = ""
    owner: str = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


@dataclass
class Building(BaseEntity):
    """Building entity."""
    type: EntityType = EntityType.BUILDING
    building_type: str = ""
    floors: int = 1
    address: str = ""
    floor_area: float = 0.0


@dataclass
class Level(BaseEntity):
    """Level/Floor entity."""
    type: EntityType = EntityType.LEVEL
    level_number: int = 0
    elevation: float = 0.0
    floor_height: float = 0.0


@dataclass
class Room(BaseEntity):
    """Room entity."""
    type: EntityType = EntityType.ROOM
    room_number: str = ""
    room_type: str = ""
    area: float = 0.0
    volume: float = 0.0
    level_id: str = ""


@dataclass
class ElectricalRoom(BaseEntity):
    """Electrical room entity."""
    type: EntityType = EntityType.ELECTRICAL_ROOM
    room_classification: str = ""
    voltage_level: float = 0.0
    equipment_count: int = 0


@dataclass
class Panel(BaseEntity):
    """Electrical panel entity."""
    type: EntityType = EntityType.PANEL
    panel_type: str = ""
    voltage_rating: float = 0.0
    current_rating: float = 0.0
    pole_count: int = 0
    feeder_count: int = 0
    manufacturer: str = ""
    model: str = ""
    location_room_id: str = ""


@dataclass
class Switchboard(BaseEntity):
    """Switchboard entity."""
    type: EntityType = EntityType.SWITCHBOARD
    voltage_rating: float = 0.0
    current_rating: float = 0.0
    interrupting_rating: float = 0.0
    bus_configuration: str = ""
    location_room_id: str = ""


@dataclass
class Bus(BaseEntity):
    """Electrical bus entity."""
    type: EntityType = EntityType.BUS
    voltage_rating: float = 0.0
    current_rating: float = 0.0
    bus_material: str = ""
    bus_size: str = ""
    length: float = 0.0
    parent_switchboard_id: str = ""


@dataclass
class Transformer(BaseEntity):
    """Transformer entity."""
    type: EntityType = EntityType.TRANSFORMER
    transformer_type: str = ""
    primary_voltage: float = 0.0
    secondary_voltage: float = 0.0
    power_rating: float = 0.0
    impedance: float = 0.0
    efficiency: float = 0.0
    cooling_type: str = ""
    location_room_id: str = ""


@dataclass
class Generator(BaseEntity):
    """Generator entity."""
    type: EntityType = EntityType.GENERATOR
    generator_type: str = ""
    power_rating: float = 0.0
    voltage_rating: float = 0.0
    fuel_type: str = ""
    prime_mover: str = ""
    location_room_id: str = ""


@dataclass
class Cable(BaseEntity):
    """Cable entity."""
    type: EntityType = EntityType.CABLE
    cable_type: str = ""
    conductor_count: int = 0
    conductor_size: str = ""
    voltage_rating: float = 0.0
    ampacity: float = 0.0
    length: float = 0.0
    installation_method: str = ""
    source_equipment_id: str = ""
    destination_equipment_id: str = ""


@dataclass
class Breaker(BaseEntity):
    """Circuit breaker entity."""
    type: EntityType = EntityType.BREAKER
    breaker_type: str = ""
    voltage_rating: float = 0.0
    current_rating: float = 0.0
    interrupting_rating: float = 0.0
    pole_count: int = 0
    frame_size: str = ""
    location_panel_id: str = ""


@dataclass
class Load(BaseEntity):
    """Electrical load entity."""
    type: EntityType = EntityType.LOAD
    load_type: str = ""
    power_rating: float = 0.0
    voltage_rating: float = 0.0
    power_factor: float = 1.0
    demand_factor: float = 1.0
    connected_equipment_id: str = ""


@dataclass
class Motor(BaseEntity):
    """Motor entity."""
    type: EntityType = EntityType.MOTOR
    motor_type: str = ""
    horsepower: float = 0.0
    voltage_rating: float = 0.0
    current_rating: float = 0.0
    efficiency: float = 0.0
    speed_rpm: int = 0
    connected_equipment_id: str = ""


@dataclass
class Relay(BaseEntity):
    """Protection relay entity."""
    type: EntityType = EntityType.RELAY
    relay_type: str = ""
    manufacturer: str = ""
    model: str = ""
    settings: Dict[str, Any] = field(default_factory=dict)
    connected_equipment_id: str = ""


@dataclass
class ProtectionDevice(BaseEntity):
    """Generic protection device entity."""
    type: EntityType = EntityType.PROTECTION_DEVICE
    device_type: str = ""
    voltage_rating: float = 0.0
    current_rating: float = 0.0
    settings: Dict[str, Any] = field(default_factory=dict)
    connected_equipment_id: str = ""


@dataclass
class Conduit(BaseEntity):
    """Conduit entity."""
    type: EntityType = EntityType.CONDUIT
    conduit_type: str = ""
    size: str = ""
    material: str = ""
    length: float = 0.0
    start_point: Optional[Coordinates] = None
    end_point: Optional[Coordinates] = None


@dataclass
class Tray(BaseEntity):
    """Cable tray entity."""
    type: EntityType = EntityType.TRAY
    tray_type: str = ""
    width: float = 0.0
    height: float = 0.0
    material: str = ""
    length: float = 0.0
    fill_capacity: float = 0.0


@dataclass
class Equipment(BaseEntity):
    """Generic equipment entity."""
    type: EntityType = EntityType.EQUIPMENT
    equipment_type: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    installation_date: Optional[datetime] = None
    location_room_id: str = ""


@dataclass
class Annotation(BaseEntity):
    """Annotation entity."""
    type: EntityType = EntityType.ANNOTATION
    annotation_type: str = ""
    text: str = ""
    style: str = ""
    attached_to_entity_id: str = ""


@dataclass
class UnifiedEngineeringModel:
    """Container for the unified engineering model."""
    entities: List[Union[BaseEntity]] = field(default_factory=list)
    project_id: str = ""
    schema_version: str = "1.0.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_entity(self, entity: BaseEntity) -> None:
        """Add an entity to the model."""
        self.entities.append(entity)
        self.updated_at = datetime.utcnow()
    
    def get_entities_by_type(self, entity_type: EntityType) -> List[BaseEntity]:
        """Get all entities of a specific type."""
        return [entity for entity in self.entities if entity.type == entity_type]
    
    def get_entity_by_id(self, entity_id: str) -> Optional[BaseEntity]:
        """Get an entity by its ID."""
        for entity in self.entities:
            if entity.id == entity_id:
                return entity
        return None
    
    def update_entity(self, entity: BaseEntity) -> bool:
        """Update an existing entity in the model."""
        for i, existing_entity in enumerate(self.entities):
            if existing_entity.id == entity.id:
                self.entities[i] = entity
                self.updated_at = datetime.utcnow()
                return True
        return False
    
    def remove_entity(self, entity_id: str) -> bool:
        """Remove an entity from the model."""
        for i, entity in enumerate(self.entities):
            if entity.id == entity_id:
                del self.entities[i]
                self.updated_at = datetime.utcnow()
                return True
        return False
    
    def get_related_entities(self, entity_id: str) -> List[BaseEntity]:
        """Get all entities related to a specific entity."""
        related = []
        for entity in self.entities:
            for rel in entity.relationships:
                if rel.entity_id == entity_id:
                    related.append(entity)
        return related