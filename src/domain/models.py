"""
FireAlarmAI Core Domain Models
==============================
Single Source of Truth for all domain entities.

This module defines the core domain models used throughout the system.
All other modules must import from here, not define their own versions.

Author: Chief Architect
Date: 2026-05-11
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from decimal import Decimal


# =============================================================================
# Enums
# =============================================================================

class DomainType(str, Enum):
    """Engineering domain types"""
    FIRE_ALARM = "FireAlarm"
    CCTV = "CCTV"
    ACCESS_CONTROL = "AccessControl"
    PA = "PA"
    DATA = "Data"
    LIGHTING = "Lighting"
    POWER = "Power"


class DeviceType(str, Enum):
    """Device types for fire alarm systems"""
    SMOKE_DETECTOR = "SmokeDetector"
    HEAT_DETECTOR = "HeatDetector"
    MANUAL_CALL_POINT = "ManualCallPoint"
    SOUNDER = "Sounder"
    STROBE = "Strobe"
    SPEAKER = "Speaker"
    CONTROL_PANEL = "ControlPanel"
    RELAY_MODULE = "RelayModule"
    MONITOR_MODULE = "MonitorModule"
    ISOLATOR = "Isolator"


class RoomType(str, Enum):
    """Room type classifications"""
    OFFICE = "Office"
    CORRIDOR = "Corridor"
    STAIRWELL = "Stairwell"
    ELECTRICAL_ROOM = "ElectricalRoom"
    SERVER_ROOM = "ServerRoom"
    KITCHEN = "Kitchen"
    BATHROOM = "Bathroom"
    STORAGE = "Storage"
    LOBBY = "Lobby"
    CONFERENCE_ROOM = "ConferenceRoom"
    OTHER = "Other"


class ViolationSeverity(str, Enum):
    """Severity levels for code violations"""
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"
    INFO = "Info"


class DesignStatus(str, Enum):
    """Design project status"""
    DRAFT = "Draft"
    IN_REVIEW = "InReview"
    APPROVED = "Approved"
    REJECTED = "Rejected"


# =============================================================================
# Core Domain Models
# =============================================================================

@dataclass
class Point:
    """2D/3D point representation"""
    x: float
    y: float
    z: float = 0.0
    
    def to_tuple(self) -> tuple:
        return (self.x, self.y, self.z)
    
    def distance_to(self, other: 'Point') -> float:
        """Calculate Euclidean distance to another point"""
        return ((self.x - other.x)**2 + (self.y - other.y)**2 + (self.z - other.z)**2)**0.5


@dataclass
class LineString:
    """Line string representation"""
    points: List[Point]
    
    def length(self) -> float:
        """Calculate total length of line string"""
        total = 0.0
        for i in range(len(self.points) - 1):
            total += self.points[i].distance_to(self.points[i+1])
        return total


@dataclass
class Polygon:
    """Polygon representation"""
    exterior: List[Point]
    holes: List[List[Point]] = field(default_factory=list)
    
    def area(self) -> float:
        """Calculate polygon area using shoelace formula"""
        n = len(self.exterior)
        if n < 3:
            return 0.0
        
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.exterior[i].x * self.exterior[j].y
            area -= self.exterior[j].x * self.exterior[i].y
        
        return abs(area) / 2.0


@dataclass
class Room:
    """
    Room entity representing a space in a building.
    
    Attributes:
        room_id: Unique identifier
        name: Room name/label
        room_type: Type classification
        polygon: Geometric boundary
        height: Ceiling height in meters
        area: Floor area in m² (calculated)
        occupancy_load: Number of occupants
        floor_number: Floor level
    """
    room_id: Optional[int] = None
    name: str = ""
    room_type: RoomType = RoomType.OTHER
    polygon: Optional[Polygon] = None
    length: Optional[float] = None
    width: Optional[float] = None
    height: float = 3.0
    area: Optional[float] = None
    occupancy_load: Optional[int] = None
    floor_number: int = 1
    project_id: Optional[int] = None
    
    def __post_init__(self):
        """Calculate area from polygon or dimensions if available"""
        if self.area is None and self.polygon is not None:
            self.area = self.polygon.area()
        elif self.area is None and self.length and self.width:
            self.area = self.length * self.width
    
    def get_walls(self) -> List[LineString]:
        """Extract wall boundaries from polygon"""
        if not self.polygon or len(self.polygon.exterior) < 2:
            return []
        
        walls = []
        points = self.polygon.exterior
        for i in range(len(points)):
            j = (i + 1) % len(points)
            wall = LineString(points=[points[i], points[j]])
            walls.append(wall)
        
        return walls
    
    def get_centroid(self) -> Optional[Point]:
        """Calculate room centroid"""
        if not self.polygon or len(self.polygon.exterior) == 0:
            if self.length and self.width:
                return Point(x=self.length/2, y=self.width/2)
            return None
        
        points = self.polygon.exterior
        n = len(points)
        cx, cy = 0.0, 0.0
        for p in points:
            cx += p.x
            cy += p.y
        
        return Point(x=cx/n, y=cy/n)


@dataclass
class Device:
    """
    Device entity representing a fire alarm device.
    
    Attributes:
        device_id: Unique identifier
        device_type: Type of device
        position: 3D location
        orientation: Rotation angle in degrees
        coverage_radius: Coverage radius in meters
        loop_id: Loop/circuit identifier
        address: Address on loop
        is_approved: Approval status
    """
    device_id: Optional[int] = None
    device_type: DeviceType = DeviceType.SMOKE_DETECTOR
    position: Optional[Point] = None
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    orientation: float = 0.0
    coverage_radius: float = 7.5
    loop_id: Optional[int] = None
    address: Optional[int] = None
    is_approved: bool = False
    room_id: Optional[int] = None
    session_id: Optional[int] = None
    confidence: float = 1.0
    ai_justification: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    
    def __post_init__(self):
        """Initialize position from x,y,z if provided"""
        if self.position is None and self.x is not None and self.y is not None:
            self.position = Point(x=self.x, y=self.y, z=self.z or 0.0)
    
    def distance_to_wall(self, room: Room) -> float:
        """Calculate minimum distance to any wall in the room"""
        if not self.position or not room.polygon:
            return float('inf')
        
        walls = room.get_walls()
        min_distance = float('inf')
        
        for wall in walls:
            dist = self._point_to_line_distance(self.position, wall)
            min_distance = min(min_distance, dist)
        
        return min_distance
    
    def _point_to_line_distance(self, point: Point, line: LineString) -> float:
        """Calculate perpendicular distance from point to line segment"""
        if len(line.points) < 2:
            return float('inf')
        
        p1, p2 = line.points[0], line.points[1]
        dx = p2.x - p1.x
        dy = p2.y - p1.y
        
        if dx == 0 and dy == 0:
            return point.distance_to(p1)
        
        t = max(0, min(1, ((point.x - p1.x) * dx + (point.y - p1.y) * dy) / (dx*dx + dy*dy)))
        proj_x = p1.x + t * dx
        proj_y = p1.y + t * dy
        
        return ((point.x - proj_x)**2 + (point.y - proj_y)**2)**0.5


@dataclass
class Obstruction:
    """Obstruction entity affecting device placement"""
    obstruction_id: Optional[int] = None
    name: str = ""
    obstruction_type: str = "Beam"
    polygon: Optional[Polygon] = None
    height_from_ceiling: float = 0.0
    affects_coverage: bool = True


@dataclass
class Violation:
    """
    Code violation entity.
    
    Rich violation information without generic message.
    Uses violation_code and params for structured reporting.
    """
    violation_id: Optional[int] = None
    violation_code: str = ""
    standard_name: str = ""
    severity: ViolationSeverity = ViolationSeverity.MINOR
    device_id: Optional[int] = None
    room_id: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)
    description_template: str = ""
    
    @property
    def message(self) -> str:
        """Generate human-readable message from template and params"""
        try:
            return self.description_template.format(**self.params)
        except (KeyError, ValueError):
            return f"{self.standard_name} violation: {self.violation_code}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'violation_id': self.violation_id,
            'violation_code': self.violation_code,
            'standard_name': self.standard_name,
            'severity': self.severity.value,
            'device_id': self.device_id,
            'room_id': self.room_id,
            'params': self.params,
            'message': self.message
        }


@dataclass
class Standard:
    """Design standard/codes entity"""
    standard_id: Optional[int] = None
    domain: DomainType = DomainType.FIRE_ALARM
    name: str = ""
    version: str = ""
    region: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignProject:
    """Design project entity"""
    project_id: Optional[int] = None
    name: str = ""
    client_name: Optional[str] = None
    location: Optional[str] = None
    building_type: Optional[str] = None
    total_area: Optional[float] = None
    total_floors: int = 1
    domain: DomainType = DomainType.FIRE_ALARM
    status: DesignStatus = DesignStatus.DRAFT
    engineer_id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    rooms: List[Room] = field(default_factory=list)
    devices: List[Device] = field(default_factory=list)
    standards: List[Standard] = field(default_factory=list)


@dataclass
class DesignSession:
    """AI design session entity"""
    session_id: Optional[int] = None
    project_id: int = 0
    ai_version: str = "1.0.0"
    input_type: str = "Manual"
    confidence_score: float = 0.0
    generated_by: Optional[int] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    
    devices: List[Device] = field(default_factory=list)


# =============================================================================
# Type Aliases
# =============================================================================

DeviceList = List[Device]
RoomList = List[Room]
ViolationList = List[Violation]


# =============================================================================
# Validation Helpers
# =============================================================================

def validate_room(room: Room) -> List[Violation]:
    """Validate room has required properties"""
    violations = []
    
    if not room.name:
        violations.append(Violation(
            violation_code="ROOM_NO_NAME",
            standard_name="Internal",
            severity=ViolationSeverity.MAJOR,
            room_id=room.room_id,
            description_template="Room has no name",
            params={}
        ))
    
    if room.area and room.area <= 0:
        violations.append(Violation(
            violation_code="ROOM_INVALID_AREA",
            standard_name="Internal",
            severity=ViolationSeverity.CRITICAL,
            room_id=room.room_id,
            description_template="Room area must be positive: {area}",
            params={'area': room.area}
        ))
    
    return violations


def validate_device(device: Device) -> List[Violation]:
    """Validate device has required properties"""
    violations = []
    
    if device.position is None and (device.x is None or device.y is None):
        violations.append(Violation(
            violation_code="DEVICE_NO_POSITION",
            standard_name="Internal",
            severity=ViolationSeverity.CRITICAL,
            device_id=device.device_id,
            description_template="Device has no position",
            params={}
        ))
    
    return violations
