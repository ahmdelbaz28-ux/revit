"""
electrical_ceiling_analyzer.py — FireAI V5.3.0 Guardian
Analyzes electrical infrastructure and ceiling types from DXF.

SAFETY-CRITICAL: Identifies obstructions that affect detector placement.
"""

import ezdxf
import logging
from shapely.geometry import Polygon, Point, box
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("fireai.guardian")


# ════════════════════════════════════════════════════════════════════════════
# ELECTRICAL ELEMENT TYPES
# ════════════════════════════════════════════════════════════════════════════

class ElectricalElementType(Enum):
    """Types of electrical elements."""
    CABLE_TRAY = "cable_tray"
    CONDUIT = "conduit"
    JUNCTION_BOX = "junction_box"
    PANEL = "panel"
    BUSWAY = "busway"
    WIREWAY = "wireway"


class CeilingStructureType(Enum):
    """Ceiling structure types."""
    SLAB = "slab"                    # Concrete slab
    SUSPENDED = "suspended"          # Drop/t-bar ceiling
    SLOPED = "sloped"              # Sloped ceiling
    BEAM_POCKET = "beam_pocket"    # Beam pockets
    CLOUD = "cloud"               # Cloud ceilings
    CATHEDRAL = "cathedral"       # High cathedral
    VAULTED = "vaulted"            # Vaulted


# ════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ElectricalObstruction:
    """
    Electrical element that affects detector placement.
    
    Per NEC Table 110.26 - requires minimum separation from:
    - Cable trays: 1.0m (39 in)
    - Conduits: 0.5m (19.7 in)
    - Junction boxes: 1.2m (47 in)
    """
    element_type: ElectricalElementType
    polygon: Optional[Polygon]
    layer: str
    name: str = ""
    height_above_floor_m: float = 0.0
    fire_rating: str = ""  # e.g., "2-hour"
    
    def get_min_separation(self) -> float:
        """Minimum separation distance in meters (NEC)."""
        distances = {
            ElectricalElementType.CABLE_TRAY: 1.0,
            ElectricalElementType.CONDUIT: 0.5,
            ElectricalElementType.JUNCTION_BOX: 1.2,
            ElectricalElementType.PANEL: 1.0,
            ElectricalElementType.BUSWAY: 1.0,
            ElectricalElementType.WIREWAY: 0.5,
        }
        return distances.get(self.element_type, 1.0)


@dataclass
class CeilingInfo:
    """
    Ceiling structure details for a room.
    
    Affects detector placement per NFPA 72 17.7.4.3:
    - Suspended ceilings: detectors must be below ceiling
    - Beam spacing affects coverage area
    """
    structure_type: CeilingStructureType
    height_above_floor_m: float
    plenum_depth_m: float = 0.0
    beam_depth_m: float = 0.0
    beam_spacing_m: float = 0.0
    is_plenum_return_air: bool = False
    
    def get_coverage_reduction(self) -> float:
        """
        Coverage reduction factor due to ceiling type.
        1.0 = full coverage, <1.0 = reduced
        """
        reductions = {
            CeilingStructureType.SLAB: 1.0,
            CeilingStructureType.SUSPENDED: 0.9,
            CeilingStructureType.SLOPED: 1.0,
            CeilingStructureType.BEAM_POCKET: 0.8,
            CeilingStructureType.CLOUD: 0.85,
            CeilingStructureType.CATHEDRAL: 0.8,
            CeilingStructureType.VAULTED: 0.85,
        }
        return reductions.get(self.structure_type, 1.0)


@dataclass
class RoomInfrastructure:
    """Infrastructure analysis for a room."""
    room_id: str
    room_name: str
    polygon: Polygon
    ceiling: CeilingInfo
    obstructions: List[ElectricalObstruction] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════
# ANALYZER
# ════════════════════════════════════════════════════════════════════════════

class ElectricalCeilingAnalyzer:
    """
    Extracts electrical infrastructure and ceiling details from DXF.
    
    IDENTIFIES:
        - Cable trays (E-TRAY, CABLE TRAY)
        - Conduits (E-COND, CONDUIT)
        - Junction boxes (E-JBOX, JUNCTION BOX)
        - Panels (E-PANEL, PANEL)
        
    CEILING TYPES:
        - Suspended ceilings
        - Concrete slabs
        - Sloped ceilings
        - Beam pockets
        - Cloud ceilings
        
    Usage:
        analyzer = ElectricalCeilingAnalyzer()
        analyzer.analyze("floor_plan.dxf", room_polygons)
        
        for room in analyzer.get_room_infrastructure():
            print(f"{room.room_id}: {room.ceiling.structure_type.value}")
            print(f"  Obstructions: {len(room.obstructions)}")
    """
    
    # Layer keywords (case-insensitive search)
    CABLE_TRAY_KEYWORDS = [
        'e-tray', 'cable tray', 'tray', 'e-cabletray',
        'cable_tray', 'tray-', '-tray'
    ]
    CONDUIT_KEYWORDS = [
        'e-cond', 'conduit', 'e-pipe',
        'cond-', '-cond', 'pipe'
    ]
    JUNCTION_BOX_KEYWORDS = [
        'e-jbox', 'junction box', 'jbox',
        'pull box', 'jb', '-jb'
    ]
    PANEL_KEYWORDS = [
        'e-panel', 'panel', 'panelboard',
        'switchgear', ' MDP', 'EDP'
    ]
    
    # Ceiling keywords
    SUSPENDED_CEILING_KEYWORDS = [
        'a-clng-susp', 'suspended ceiling', 't-bar',
        'drop ceiling', 'susp', 'clng-susp'
    ]
    BEAM_KEYWORDS = [
        'a-beam', 'beam', 'girders',
        'joist', 'header'
    ]
    SLAB_KEYWORDS = [
        'a-clng-slab', 'slab', 'concrete',
        'floor', 'deck'
    ]
    CLOUD_KEYWORDS = [
        'cloud', 'cloud ceiling',
        'soffit'
    ]

    def __init__(self):
        self.rooms: Dict[str, RoomInfrastructure] = {}
        self.all_obstructions: List[ElectricalObstruction] = []
        
    def analyze(
        self, 
        dxf_path: str, 
        room_polygons: Dict[str, Polygon],
        scale_factor: float = 0.01
    ) -> Dict[str, RoomInfrastructure]:
        """
        Analyze DXF for electrical and ceiling infrastructure.
        
        Args:
            dxf_path: Path to DXF file
            room_polygons: Dict of room_id -> shapely Polygon
            scale_factor: Drawing scale (default 0.01 = 1cm)
            
        Returns:
            Dict of room_id -> RoomInfrastructure
        """
        logger.info(f"Guardian analyzing: {dxf_path}")
        
        try:
            doc = ezdxf.readfile(dxf_path)
        except Exception as e:
            logger.error(f"Failed to read DXF: {e}")
            return {}
            
        msp = doc.modelspace()
        
        # Find all electrical obstructions
        for entity in msp:
            obstruction = self._identify_electrical(entity, scale_factor)
            if obstruction:
                self.all_obstructions.append(obstruction)
                
        logger.info(f"Found {len(self.all_obstructions)} electrical elements")
        
        # Analyze ceiling and assign obstructions per room
        for room_id, room_poly in room_polygons.items():
            ceiling = self._analyze_ceiling_for_room(room_id, room_poly, msp, scale_factor)
            
            # Find obstructions in this room
            room_obstructions = self._get_obstructions_in_room(
                room_id, room_poly, self.all_obstructions
            )
            
            # Get room name from ID
            room_name = room_id
            
            self.rooms[room_id] = RoomInfrastructure(
                room_id=room_id,
                room_name=room_name,
                polygon=room_poly,
                ceiling=ceiling,
                obstructions=room_obstructions
            )
            
        return self.rooms

    def _identify_electrical(
        self, 
        entity, 
        scale: float
    ) -> Optional[ElectricalObstruction]:
        """Identify electrical element from entity."""
        try:
            layer = entity.dxf.layer.upper() if hasattr(entity.dxf, 'layer') else ""
            
            # Check for cable tray
            if any(kw in layer for kw in self.CABLE_TRAY_KEYWORDS):
                poly = self._entity_to_polygon(entity, scale)
                if poly:
                    return ElectricalObstruction(
                        element_type=ElectricalElementType.CABLE_TRAY,
                        polygon=poly,
                        layer=layer,
                        name=self._get_block_name(entity)
                    )
                    
            # Check for conduit
            if any(kw in layer for kw in self.CONDUIT_KEYWORDS):
                poly = self._entity_to_polygon(entity, scale)
                if poly:
                    return ElectricalObstruction(
                        element_type=ElectricalElementType.CONDUIT,
                        polygon=poly,
                        layer=layer,
                        name=self._get_block_name(entity)
                    )
                    
            # Check for junction box
            if any(kw in layer for kw in self.JUNCTION_BOX_KEYWORDS):
                poly = self._entity_to_polygon(entity, scale)
                if poly:
                    return ElectricalObstruction(
                        element_type=ElectricalElementType.JUNCTION_BOX,
                        polygon=poly,
                        layer=layer,
                        name=self._get_block_name(entity)
                    )
                    
            # Check for panel
            if any(kw in layer for kw in self.PANEL_KEYWORDS):
                poly = self._entity_to_polygon(entity, scale)
                if poly:
                    return ElectricalObstruction(
                        element_type=ElectricalElementType.PANEL,
                        polygon=poly,
                        layer=layer,
                        name=self._get_block_name(entity)
                    )
                    
        except Exception as e:
            logger.debug(f"Entity analysis error: {e}")
            
        return None

    def _entity_to_polygon(
        self, 
        entity, 
        scale: float
    ) -> Optional[Polygon]:
        """Convert entity to shapely polygon."""
        try:
            dxftype = entity.dxftype()
            
            # Handle LWPOLYLINE
            if dxftype == 'LWPOLYLINE':
                points = entity.get_points()
                if len(points) >= 3:
                    coords = [(p[0] * scale, p[1] * scale) for p in points]
                    return Polygon(coords)
                    
            # Handle INSERT (blocks)
            if dxftype == 'INSERT' and hasattr(entity.dxf, 'insert'):
                x, y = entity.dxf.insert[0] * scale, entity.dxf.insert[1] * scale
                # Create small polygon around insertion point
                size = 0.3  # 30cm box
                return box(x - size, y - size, x + size, y + size)
                
        except Exception as e:
            logger.debug(f"Polygon conversion error: {e}")
            
        return None

    def _get_block_name(self, entity) -> str:
        """Get block/entity name."""
        try:
            if hasattr(entity.dxf, 'name'):
                return entity.dxf.name
            if hasattr(entity.dxf, 'layer'):
                return entity.dxf.layer
        except:
            pass
        return ""

    def _analyze_ceiling_for_room(
        self, 
        room_id: str,
        room_poly: Polygon,
        msp,
        scale: float
    ) -> CeilingInfo:
        """Analyze ceiling type for a room."""
        
        # Check intersection with ceiling layers
        has_suspended = False
        has_beam = False
        has_cloud = False
        
        for entity in msp:
            try:
                layer = entity.dxf.layer.upper() if hasattr(entity.dxf, 'layer') else ""
                
                if any(kw in layer for kw in self.SUSPENDED_CEILING_KEYWORDS):
                    has_suspended = True
                if any(kw in layer for kw in self.BEAM_KEYWORDS):
                    has_beam = True
                if any(kw in layer for kw in self.CLOUD_KEYWORDS):
                    has_cloud = True
                    
            except:
                continue
                
        # Determine ceiling type
        if has_suspended:
            return CeilingInfo(
                structure_type=CeilingStructureType.SUSPENDED,
                height_above_floor_m=3.0,  # default
                plenum_depth_m=0.3  # typical plenum
            )
        if has_cloud:
            return CeilingInfo(
                structure_type=CeilingStructureType.CLOUD,
                height_above_floor_m=3.5,
                beam_depth_m=0.3
            )
        if has_beam:
            return CeilingInfo(
                structure_type=CeilingStructureType.BEAM_POCKET,
                height_above_floor_m=3.0,
                beam_depth_m=0.5,
                beam_spacing_m=0.6  # typical 60cm
            )
            
        # Default to slab
        return CeilingInfo(
            structure_type=CeilingStructureType.SLAB,
            height_above_floor_m=3.0
        )

    def _get_obstructions_in_room(
        self,
        room_id: str,
        room_poly: Polygon,
        all_obstructions: List[ElectricalObstruction]
    ) -> List[ElectricalObstruction]:
        """Get obstructions that intersect a room."""
        
        room_obstructions = []
        for obs in all_obstructions:
            if obs.polygon and room_poly.intersects(obs.polygon):
                room_obstructions.append(obs)
                
        return room_obstructions

    def get_room_infrastructure(self) -> List[RoomInfrastructure]:
        """Get list of all room infrastructure."""
        return list(self.rooms.values())

    def get_room_obstructions(self, room_id: str) -> List[ElectricalObstruction]:
        """Get obstructions for a specific room."""
        room = self.rooms.get(room_id)
        return room.obstructions if room else []

    def get_room_ceiling(self, room_id: str) -> Optional[CeilingInfo]:
        """Get ceiling info for a specific room."""
        room = self.rooms.get(room_id)
        return room.ceiling if room else None


# ════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ════════════════════════════════════════════════════════════════════════════

def analyze_infrastructure(
    dxf_path: str,
    room_polygons: Dict[str, Polygon],
    scale_factor: float = 0.01
) -> Dict[str, RoomInfrastructure]:
    """
    Quick infrastructure analysis.
    
    Usage:
        rooms = analyze_infrastructure("floor.dxf", room_polygons)
        for room in rooms.values():
            print(f"{room.room_id}: {room.ceiling.structure_type.value}")
    """
    analyzer = ElectricalCeilingAnalyzer()
    return analyzer.analyze(dxf_path, room_polygons, scale_factor)