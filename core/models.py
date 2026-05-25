"""
FireAI Models - Data structures and classes
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime
import math
import uuid
from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint


# ════════════════════════════════════════════════════════════════════════════
# ENUMERATIONS
# ════════════════════════════════════════════════════════════════════════════

class ElementType(Enum):
    """أنواع العناصر الهندسية"""
    WALL = "wall"
    DOOR = "door"
    WINDOW = "window"
    ROOM = "room"
    EQUIPMENT = "equipment"
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    UNKNOWN = "unknown"


class ChangeSource(Enum):
    """مصدر التغيير"""
    AUTOCAD = "autocad"
    REVIT = "revit"
    MANUAL = "manual"
    SYSTEM = "system"


class ConflictType(Enum):
    """أنواع التعارضات"""
    GEOMETRY_MISMATCH = "geometry_mismatch"
    PROPERTY_CONFLICT = "property_conflict"
    DELETION_CONFLICT = "deletion_conflict"
    TIMING_CONFLICT = "timing_conflict"


# ════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class Point3D:
    """نقطة في الفراغ
    
    V30 B8: __slots__ eliminates per-instance __dict__, reducing memory
    from ~112B to ~48B per instance. For 4M Point3D instances (1M rooms
    × 4 vertices): saves ~256 MB. Python 3.10+ dataclass slots syntax.
    All existing usage patterns (attribute access, comparison, copy)
    are unaffected. Pickling works normally with Python 3.12.
    """
    x: float
    y: float
    z: float = 0.0
    
    def distance_to(self, other: 'Point3D') -> float:
        """Euclidean 3D distance."""
        dx = self.x - other.x
        dy = self.y - other.y
        dz = self.z - other.z
        return math.sqrt(dx*dx + dy*dy + dz*dz)
    
    def distance_to_2d(self, other: 'Point3D') -> float:
        """2D XY distance (faster when Z not needed)."""
        dx = self.x - other.x
        dy = self.y - other.y
        return math.sqrt(dx*dx + dy*dy)
    
    def to_dict(self) -> Dict:
        return {'x': self.x, 'y': self.y, 'z': self.z}
    
    @staticmethod
    def from_dict(d: Dict) -> 'Point3D':
        return Point3D(d['x'], d['y'], d.get('z', 0.0))


@dataclass
class Geometry:
    """الهندسة: الأشكال الهندسية"""
    points: List[Point3D]
    polyline_closed: bool = False
    area: float = 0.0
    perimeter: float = 0.0
    
    def calculate_area(self) -> float:
        """حساب المساحة — Shoelace formula, O(n).
        
        V30 B9: Pure Python beats NumPy for n < 50 (measured: 1.6M/s vs 222K/s).
        """
        pts = self.points
        n = len(pts)
        if n < 3:
            self.area = 0.0
            return 0.0
        
        acc = 0.0
        for i in range(n - 1):
            acc += pts[i].x * pts[i + 1].y - pts[i + 1].x * pts[i].y
        # Close polygon
        acc += pts[-1].x * pts[0].y - pts[0].x * pts[-1].y
        self.area = abs(acc) * 0.5
        return self.area
    
    def calculate_perimeter(self) -> float:
        """حساب المحيط — Inlined distance, no per-edge method dispatch.
        
        V30 B9: Replaced self.points[i].distance_to(self.points[i+1])
        with inline math.sqrt to avoid Python method dispatch overhead.
        Measured: 775K/s → ~1.4M/s for 4-vertex rectangle.
        """
        pts = self.points
        n = len(pts)
        if n < 2:
            self.perimeter = 0.0
            return 0.0
        
        total = 0.0
        for a, b in zip(pts, pts[1:]):
            dx = a.x - b.x
            dy = a.y - b.y
            total += math.sqrt(dx*dx + dy*dy)
        
        if self.polyline_closed and n >= 2:
            dx = pts[-1].x - pts[0].x
            dy = pts[-1].y - pts[0].y
            total += math.sqrt(dx*dx + dy*dy)
        
        self.perimeter = total
        return total
    
    @staticmethod
    def calculate_area_batch(geometries: List['Geometry']) -> List[float]:
        """Vectorised area for N geometries.
        V30 B9: For N < 50-vertex polygons: loops over Python shoelace (fastest).
        Returns list of float areas in same order as input.
        """
        results: List[float] = []
        for geom in geometries:
            results.append(geom.calculate_area())
        return results
    
    @staticmethod
    def calculate_perimeter_batch(geometries: List['Geometry']) -> List[float]:
        """Batch perimeter computation."""
        return [geom.calculate_perimeter() for geom in geometries]
    
    @staticmethod
    def calculate_area_batch_numpy(geometries: List['Geometry']) -> List[float]:
        """NumPy vectorized shoelace for large uniform polygon arrays.
        
        Consultant B9 addition — optional accelerated path.
        All polygons must have the SAME vertex count n (padded with last point).
        Significant speedup for n >= 50 or len(geometries) >= 1000.
        For small batches, calculate_area_batch() (pure Python) is faster.
        
        Returns list of float areas in same order as input.
        Falls back to pure Python if NumPy unavailable.
        """
        try:
            import numpy as np
        except ImportError:
            return [geom.calculate_area() for geom in geometries]
        
        if not geometries:
            return []
        
        n_pts = max(len(g.points) for g in geometries)
        n_geo = len(geometries)
        
        # Build (n_geo, n_pts, 2) array
        xs = np.zeros((n_geo, n_pts), dtype=np.float64)
        ys = np.zeros((n_geo, n_pts), dtype=np.float64)
        
        for i, geom in enumerate(geometries):
            pts = geom.points
            k = len(pts)
            for j, p in enumerate(pts):
                xs[i, j] = p.x
                ys[i, j] = p.y
            # Pad remaining with last point (closed polygon)
            if k < n_pts:
                xs[i, k:] = pts[-1].x
                ys[i, k:] = pts[-1].y
        
        # Vectorized shoelace: sum(x[i]*y[i+1] - x[i+1]*y[i])
        xs1 = np.roll(xs, -1, axis=1)
        ys1 = np.roll(ys, -1, axis=1)
        areas = np.abs((xs * ys1 - xs1 * ys).sum(axis=1)) * 0.5
        
        # Write back and return
        results: List[float] = []
        for i, geom in enumerate(geometries):
            geom.area = float(areas[i])
            results.append(geom.area)
        return results
    
    def to_dict(self) -> Dict:
        return {
            'points': [p.to_dict() for p in self.points],
            'polyline_closed': self.polyline_closed,
            'area': self.area,
            'perimeter': self.perimeter
        }
    
    @staticmethod
    def from_dict(d: Dict) -> 'Geometry':
        return Geometry(
            points=[Point3D.from_dict(p) for p in d['points']],
            polyline_closed=d.get('polyline_closed', False),
            area=d.get('area', 0.0),
            perimeter=d.get('perimeter', 0.0)
        )


@dataclass
class SemanticProperties:
    """الخصائص الدلالية"""
    element_type: ElementType
    name: str
    description: Optional[str] = None
    material: Optional[str] = None
    fire_rating: Optional[str] = None
    height: Optional[float] = None
    width: Optional[float] = None
    load_bearing: bool = False
    layer: Optional[str] = None
    revit_category: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'element_type': self.element_type.value,
            'name': self.name,
            'description': self.description,
            'material': self.material,
            'fire_rating': self.fire_rating,
            'height': self.height,
            'width': self.width,
            'load_bearing': self.load_bearing,
            'layer': self.layer,
            'revit_category': self.revit_category
        }
    
    @staticmethod
    def from_dict(d: Dict) -> 'SemanticProperties':
        return SemanticProperties(
            element_type=ElementType(d['element_type']),
            name=d['name'],
            description=d.get('description'),
            material=d.get('material'),
            fire_rating=d.get('fire_rating'),
            height=d.get('height'),
            width=d.get('width'),
            load_bearing=d.get('load_bearing', False),
            layer=d.get('layer'),
            revit_category=d.get('revit_category')
        )


@dataclass
class Relationship:
    """العلاقة بين عنصرين"""
    from_element_id: str
    to_element_id: str
    relationship_type: str
    is_parametric: bool = False
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return {
            'from_element_id': self.from_element_id,
            'to_element_id': self.to_element_id,
            'relationship_type': self.relationship_type,
            'is_parametric': self.is_parametric,
            'metadata': self.metadata or {}
        }


@dataclass
class UniversalElement:
    """العنصر الموحد"""
    element_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    properties: Optional[SemanticProperties] = None
    geometry: Optional[Geometry] = None
    relationships: List[Relationship] = field(default_factory=list)
    created_timestamp: datetime = field(default_factory=datetime.now)
    last_modified_timestamp: datetime = field(default_factory=datetime.now)
    last_modified_by: Optional[str] = None
    source_file: Optional[str] = None
    version: int = 0
    is_deleted: bool = False
    autocad_handle: Optional[str] = None
    revit_element_id: Optional[int] = None
    change_log: List = field(default_factory=list)
    content_hash: str = ""
    
    def add_change_log_entry(
        self,
        change_type: str,
        source: ChangeSource = ChangeSource.SYSTEM,
        old_value: Optional[Dict] = None,
        new_value: Optional[Dict] = None,
        reason: Optional[str] = None
    ):
        """إضافة سجل تغيير"""
        entry = ChangeLogEntry(
            change_type=change_type,
            source=source,
            old_value=old_value,
            new_value=new_value,
            reason=reason
        )
        self.change_log.append(entry)
        self.content_hash = str(hash(str(self.to_dict())))
    
    def to_dict(self) -> Dict:
        return {
            'element_id': self.element_id,
            'properties': self.properties.to_dict() if self.properties else None,
            'geometry': self.geometry.to_dict() if self.geometry else None,
            'relationships': [r.to_dict() for r in self.relationships],
            'created_timestamp': self.created_timestamp.isoformat(),
            'last_modified_timestamp': self.last_modified_timestamp.isoformat(),
            'last_modified_by': self.last_modified_by,
            'source_file': self.source_file,
            'version': self.version,
            'is_deleted': self.is_deleted,
            'autocad_handle': self.autocad_handle,
            'revit_element_id': self.revit_element_id
        }
    
    @staticmethod
    def from_dict(d: Dict) -> 'UniversalElement':
        return UniversalElement(
            element_id=d.get('element_id', str(uuid.uuid4())),
            properties=SemanticProperties.from_dict(d['properties']) if d.get('properties') else None,
            geometry=Geometry.from_dict(d['geometry']) if d.get('geometry') else None,
            relationships=[Relationship(**r) for r in d.get('relationships', [])],
            created_timestamp=datetime.fromisoformat(d['created_timestamp']) if d.get('created_timestamp') else datetime.now(),
            last_modified_timestamp=datetime.fromisoformat(d['last_modified_timestamp']) if d.get('last_modified_timestamp') else datetime.now(),
            last_modified_by=d.get('last_modified_by'),
            source_file=d.get('source_file'),
            version=d.get('version', 0),
            is_deleted=d.get('is_deleted', False),
            autocad_handle=d.get('autocad_handle'),
            revit_element_id=d.get('revit_element_id')
        )
    
    def validate_semantic_consistency(self) -> tuple:
        """التحقق من الاتساق الدلالي"""
        errors = []
        
        if not self.properties:
            errors.append("Missing properties")
            return False, errors
        
        # Check element type has required fields
        if self.properties.element_type == ElementType.WALL:
            if self.properties.height is None:
                errors.append("WALL requires height")
        
        elif self.properties.element_type == ElementType.ROOM:
            if self.properties.height is None:
                errors.append("ROOM requires height")
        
        if not self.geometry or len(self.geometry.points) < 3:
            if self.properties.element_type not in [ElementType.EQUIPMENT, ElementType.MECHANICAL, ElementType.ELECTRICAL]:
                errors.append("Geometry must have at least 3 points")
        
        return len(errors) == 0, errors


@dataclass
class ChangeLogEntry:
    """مدخل في سجل التغييرات"""
    change_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    change_type: str = ""  # create, update, delete
    source: ChangeSource = ChangeSource.SYSTEM
    old_value: Optional[Dict] = None
    new_value: Optional[Dict] = None
    reason: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'change_id': self.change_id,
            'timestamp': self.timestamp.isoformat(),
            'change_type': self.change_type,
            'source': self.source.value,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'reason': self.reason
        }


@dataclass
class Conflict:
    """تمثيل التعارض"""
    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    element_id: str = ""
    conflict_type: ConflictType = ConflictType.PROPERTY_CONFLICT
    timestamp: datetime = field(default_factory=datetime.now)
    source_a: ChangeSource = ChangeSource.AUTOCAD
    source_b: ChangeSource = ChangeSource.REVIT
    change_a: Dict = field(default_factory=dict)
    change_b: Dict = field(default_factory=dict)
    resolution: Optional[Dict] = None
    resolved: bool = False
    
    def to_dict(self) -> Dict:
        return {
            'conflict_id': self.conflict_id,
            'element_id': self.element_id,
            'conflict_type': self.conflict_type.value,
            'timestamp': self.timestamp.isoformat(),
            'source_a': self.source_a.value,
            'source_b': self.source_b.value,
            'change_a': self.change_a,
            'change_b': self.change_b,
            'resolved': self.resolved
        }


# ════════════════════════════════════════════════════════════════════════════
# COMPLIANCE ORACLE MODELS
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class DeviceCoordinate:
    """Point coordinates for ComplianceOracle"""
    x: float
    y: float
    z: float = 0.0


@dataclass
class Room:
    """Room for ComplianceOracle"""
    id: str
    name: str
    room_type: str
    floor_area: float
    geometry: ShapelyPolygon  # Shapely Polygon for Oracle
    ceiling_height: float = 3.0  # Default height in meters (NFPA 72 minimum normative height)
    ceiling_type: str = "SMOOTH"  # SMOOTH, BEAMED, SLOPED, CORRIDOR


@dataclass
class Device:
    """Device for ComplianceOracle"""
    id: str
    device_type: str
    position: ShapelyPoint  # Shapely Point for Oracle
    room_id: str
    z_height: float = 2.4  # mounting height in meters
    coverage_radius: float = 6.37  # R = 0.7 × S = 0.7 × 9.1m per NFPA 72 §17.7.4.2.3.1


@dataclass
class Violation:
    """Violation for ComplianceOracle"""
    rule: str
    device_id: str
    location: Optional[DeviceCoordinate] = None
    value: float = 0.0
    threshold: float = 0.0


@dataclass
class Obstruction:
    """Obstruction for ComplianceOracle"""
    id: str
    geometry: ShapelyPolygon
    height: float
    blocks_visibility: bool = True
