"""
Fire Alarm AI Design Integration Module
======================================
This module integrates the FireAlarmAI engine with the database
for AI-powered fire alarm design workflow.
 
EVOLVED: Multi-domain building design platform supporting:
- FireAlarm, CCTV, AccessControl, PA, Data, Lighting, Power

Author: Fire Protection Engineering Consultant
Date: 2026-05-09
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

# SQLAlchemy imports
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime,
    Text, DECIMAL, ForeignKey, CheckConstraint, UniqueConstraint,
    Index, Sequence
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base, Session
from sqlalchemy.dialects.postgresql import JSONB, BYTEA

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# SQLAlchemy Base
# =============================================================================
Base = declarative_base()

# =============================================================================
# Existing Database Models (for reference)
# =============================================================================

class User(Base):
    """User table for authentication"""
    __tablename__ = 'Users'
    
    UserID = Column(Integer, primary_key=True, autoincrement=True)
    Username = Column(String(100), unique=True, nullable=False)
    Email = Column(String(200))
    PasswordHash = Column(String(255))
    FullName = Column(String(200))
    RoleID = Column(Integer, ForeignKey('Roles.RoleID'))
    IsActive = Column(Boolean, default=True)
    LastLogin = Column(DateTime)


class Role(Base):
    """User roles"""
    __tablename__ = 'Roles'
    
    RoleID = Column(Integer, primary_key=True, autoincrement=True)
    RoleName = Column(String(50), unique=True, nullable=False)
    Permissions = Column(Text)


class DeviceType(Base):
    """Device type lookup"""
    __tablename__ = 'DeviceType'
    
    DeviceTypeID = Column(Integer, primary_key=True, autoincrement=True)
    TypeName = Column(String(100), unique=True, nullable=False)
    Description = Column(Text)
    DomainID = Column(Integer, ForeignKey('ProjectDomain.DomainID'))  # NEW: Multi-domain support
    
    # Relationship
    domain = relationship("ProjectDomain", foreign_keys=[DomainID])


# =============================================================================
# NEW: Project Domain (Multi-domain support)
# =============================================================================

class ProjectDomain(Base):
    """Project domains for multi-domain building design"""
    __tablename__ = 'ProjectDomain'
    
    DomainID = Column(Integer, primary_key=True, autoincrement=True)
    DomainName = Column(String(50), unique=True, nullable=False)
    Description = Column(Text)
    IsActive = Column(Boolean, default=True)
    
    # Relationships
    projects = relationship("DesignProject", back_populates="domain")
    device_types = relationship("DeviceType", back_populates="domain")


# =============================================================================
# Backward Compatibility: Domain Enum
# =============================================================================

class DomainEnum:
    """Supported engineering domains"""
    FIRE_ALARM = 'FireAlarm'
    CCTV = 'CCTV'
    ACCESS_CONTROL = 'AccessControl'
    PA = 'PA'           # Public Address
    DATA = 'Data'       # Data/Telecom
    LIGHTING = 'Lighting'
    POWER = 'Power'
    
    ALL_DOMAINS = [FIRE_ALARM, CCTV, ACCESS_CONTROL, PA, DATA, LIGHTING, POWER]
    
    @classmethod
    def get_domain_id(cls, domain_name: str, session) -> int:
        """Get domain ID by name, create if not exists"""
        domain = session.query(ProjectDomain).filter(
            ProjectDomain.DomainName == domain_name
        ).first()
        
        if not domain:
            domain = ProjectDomain(
                DomainName=domain_name,
                Description=f'{domain_name} system'
            )
            session.add(domain)
            session.commit()
            session.refresh(domain)
        
        return domain.DomainID


class Device(Base):
    """Base device table"""
    __tablename__ = 'Devices'
    
    DeviceID = Column(Integer, primary_key=True, autoincrement=True)
    SystemID = Column(Integer, ForeignKey('FireAlarmSystems.SystemID'))
    DeviceTypeID = Column(Integer, ForeignKey('DeviceType.DeviceTypeID'))
    SerialNumber = Column(String(100), unique=True)
    Manufacturer = Column(String(100))
    Model = Column(String(100))
    LoopID = Column(Integer)
    AddressOnLoop = Column(Integer)
    ZoneID = Column(Integer, ForeignKey('Zones.ZoneID'))
    LocationDescription = Column(Text)
    Status = Column(String(20), default='Normal')
    InstallationDate = Column(DateTime)
    LastTestDate = Column(DateTime)
    NextTestDue = Column(DateTime)


class FireAlarmSystem(Base):
    """Fire alarm system"""
    __tablename__ = 'FireAlarmSystems'
    
    SystemID = Column(Integer, primary_key=True, autoincrement=True)
    FacilityID = Column(Integer, ForeignKey('Facilities.FacilityID'))
    Name = Column(String(255), nullable=False)
    InstallationDate = Column(DateTime)
    Status = Column(String(20), default='Operational')


class Zone(Base):
    """Zone for device grouping"""
    __tablename__ = 'Zones'
    
    ZoneID = Column(Integer, primary_key=True, autoincrement=True)
    SystemID = Column(Integer, ForeignKey('FireAlarmSystems.SystemID'))
    FloorID = Column(Integer, ForeignKey('Floors.FloorID'))
    ZoneName = Column(String(100), nullable=False)
    ZoneType = Column(String(20))


class Floor(Base):
    """Floor table"""
    __tablename__ = 'Floors'
    
    FloorID = Column(Integer, primary_key=True, autoincrement=True)
    BuildingID = Column(Integer, ForeignKey('Buildings.BuildingID'))
    FloorNumber = Column(Integer, nullable=False)
    Name = Column(String(100))


class Building(Base):
    """Building table"""
    __tablename__ = 'Buildings'
    
    BuildingID = Column(Integer, primary_key=True, autoincrement=True)
    FacilityID = Column(Integer, ForeignKey('Facilities.FacilityID'))
    Name = Column(String(200), nullable=False)
    NumberOfFloors = Column(Integer)


class Facility(Base):
    """Facility table"""
    __tablename__ = 'Facilities'
    
    FacilityID = Column(Integer, primary_key=True, autoincrement=True)
    Name = Column(String(200), nullable=False)
    Address = Column(String(500))
    TimeZone = Column(String(50))


# =============================================================================
# NEW AI Design Tables
# =============================================================================

class DesignProject(Base):
    """AI Design Project"""
    __tablename__ = 'DesignProject'
    
    ProjectID = Column(Integer, primary_key=True, autoincrement=True)
    ProjectName = Column(String(255), nullable=False)
    ClientName = Column(String(255))
    Location = Column(String(500))
    BuildingType = Column(String(100))
    TotalArea = Column(DECIMAL(12, 2))
    TotalFloors = Column(Integer)
    EngineerID = Column(Integer, ForeignKey('Users.UserID'))
    Status = Column(String(20), default='Draft')
    DomainID = Column(Integer, ForeignKey('ProjectDomain.DomainID'))  # NEW: Multi-domain support
    CreatedAt = Column(DateTime, default=datetime.utcnow)
    UpdatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    domain = relationship("ProjectDomain", back_populates="projects")
    engineer = relationship("User", foreign_keys=[EngineerID])
    sessions = relationship("DesignSession", back_populates="project", cascade="all, delete-orphan")
    rooms = relationship("Room", back_populates="project", cascade="all, delete-orphan")


class DesignStandard(Base):
    """Design standards and rules"""
    __tablename__ = 'DesignStandard'
    
    StandardID = Column(Integer, primary_key=True, autoincrement=True)
    DomainID = Column(Integer, ForeignKey('ProjectDomain.DomainID'))  # NEW: Multi-domain support
    StandardName = Column(String(100), nullable=False)
    ParameterKey = Column(String(100), nullable=False)
    ParameterValue = Column(Text, nullable=False)
    Description = Column(Text)
    
    # Relationship
    domain = relationship("ProjectDomain")
    
    __table_args__ = (
        UniqueConstraint('StandardName', 'ParameterKey', 'DomainID', name='uq_standard_param_domain'),
    )


class Room(Base):
    """Room in a design project"""
    __tablename__ = 'Room'
    
    RoomID = Column(Integer, primary_key=True, autoincrement=True)
    DesignProjectID = Column(Integer, ForeignKey('DesignProject.ProjectID', ondelete='CASCADE'), nullable=False)
    RoomName = Column(String(255), nullable=False)
    RoomType = Column(String(100))
    Length = Column(DECIMAL(8, 2))
    Width = Column(DECIMAL(8, 2))
    Height = Column(DECIMAL(6, 2))
    Area = Column(DECIMAL(10, 2))
    OccupancyLoad = Column(Integer)
    FloorNumber = Column(Integer)
    CreatedAt = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    project = relationship("DesignProject", back_populates="rooms")
    devices = relationship("AIDesignDevice", back_populates="room")


class DesignSession(Base):
    """AI Design Session"""
    __tablename__ = 'DesignSession'
    
    SessionID = Column(Integer, primary_key=True, autoincrement=True)
    DesignProjectID = Column(Integer, ForeignKey('DesignProject.ProjectID', ondelete='CASCADE'), nullable=False)
    AI_Version = Column(String(50))
    InputType = Column(String(20))  # 'Image', 'Manual', 'Hybrid'
    ConfidenceScore = Column(DECIMAL(5, 4))
    GeneratedBy = Column(Integer, ForeignKey('Users.UserID'))
    GeneratedAt = Column(DateTime, default=datetime.utcnow)
    Notes = Column(Text)
    
    # Relationships
    project = relationship("DesignProject", back_populates="sessions")
    designer = relationship("User", foreign_keys=[GeneratedBy])
    devices = relationship("AIDesignDevice", back_populates="session", cascade="all, delete-orphan")
    files = relationship("DesignFile", back_populates="session")


class AIDesignDevice(Base):
    """AI Proposed Device"""
    __tablename__ = 'AIDesignDevice'
    
    DesignDeviceID = Column(Integer, primary_key=True, autoincrement=True)
    SessionID = Column(Integer, ForeignKey('DesignSession.SessionID', ondelete='CASCADE'), nullable=False)
    RoomID = Column(Integer, ForeignKey('Room.RoomID'))
    ProposedType = Column(String(50), nullable=False)  # 'SmokeDetector', 'Speaker', etc.
    X = Column(DECIMAL(10, 4))
    Y = Column(DECIMAL(10, 4))
    Z = Column(DECIMAL(10, 4))
    Confidence = Column(DECIMAL(5, 4))
    AI_Justification = Column(Text)
    IsApproved = Column(Boolean, default=False)
    ApprovedBy = Column(Integer, ForeignKey('Users.UserID'))
    ApprovedAt = Column(DateTime)
    RevisedX = Column(DECIMAL(10, 4))
    RevisedY = Column(DECIMAL(10, 4))
    RevisedZ = Column(DECIMAL(10, 4))
    RevisionNote = Column(Text)
    DeviceID_Ref = Column(Integer, ForeignKey('Devices.DeviceID'))
    CreatedAt = Column(DateTime, default=datetime.utcnow)
    UpdatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    session = relationship("DesignSession", back_populates="devices")
    room = relationship("Room", back_populates="devices")
    approver = relationship("User", foreign_keys=[ApprovedBy])
    device_ref = relationship("Device", foreign_keys=[DeviceID_Ref])
    revisions = relationship("RevisionHistory", back_populates="device", cascade="all, delete-orphan")


class DesignFile(Base):
    """Design output files"""
    __tablename__ = 'DesignFile'
    
    FileID = Column(Integer, primary_key=True, autoincrement=True)
    SessionID = Column(Integer, ForeignKey('DesignSession.SessionID', ondelete='CASCADE'))
    ProjectID = Column(Integer, ForeignKey('DesignProject.ProjectID'))
    FileName = Column(String(255), nullable=False)
    FileType = Column(String(20))  # 'DWG', 'RVT', 'PDF', 'JSON', 'Excel'
    FileContent = Column(BYTEA)
    CreatedAt = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = relationship("DesignSession", back_populates="files")


class RevisionHistory(Base):
    """Revision history for device changes"""
    __tablename__ = 'RevisionHistory'
    
    RevisionID = Column(Integer, primary_key=True, autoincrement=True)
    DesignDeviceID = Column(Integer, ForeignKey('AIDesignDevice.DesignDeviceID', ondelete='CASCADE'), nullable=False)
    RevisedBy = Column(Integer, ForeignKey('Users.UserID'))
    RevisionTimestamp = Column(DateTime, default=datetime.utcnow)
    OldValues = Column(JSONB)
    NewValues = Column(JSONB)
    Note = Column(Text)
    
    # Relationships
    device = relationship("AIDesignDevice", back_populates="revisions")
    editor = relationship("User", foreign_keys=[RevisedBy])


# =============================================================================
# Database Connection Manager
# =============================================================================

class DatabaseManager:
    """Database connection and session manager"""
    
    def __init__(self, database_url: str):
        """
        Initialize database connection
        
        Args:
            database_url: PostgreSQL connection string
                         e.g., "postgresql://user:password@localhost/firealarmdb"
        """
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        logger.info(f"Database engine created for: {database_url.split('@')[1] if '@' in database_url else 'local'}")
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    def create_tables(self):
        """Create all tables"""
        Base.metadata.create_all(self.engine)
        logger.info("All tables created successfully")
    
    def drop_tables(self):
        """Drop all tables"""
        Base.metadata.drop_all(self.engine)
        logger.warning("All tables dropped")


# =============================================================================
# Design Standards Loader
# =============================================================================

class DesignStandardsLoader:
    """Load design standards from database"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def load_standards(self, standard_name: str) -> Dict[str, Any]:
        """
        Load design standards for a specific region/standard
        
        Args:
            standard_name: e.g., 'Egyptian', 'NFPA72', 'Saudi'
            
        Returns:
            Dictionary of parameter key-value pairs
        """
        standards = self.session.query(DesignStandard).filter(
            DesignStandard.StandardName == standard_name
        ).all()
        
        result = {}
        for std in standards:
            # Try to convert to numeric if possible
            try:
                result[std.ParameterKey] = float(std.ParameterValue)
            except ValueError:
                # Keep as string
                if std.ParameterValue.lower() == 'true':
                    result[std.ParameterKey] = True
                elif std.ParameterValue.lower() == 'false':
                    result[std.ParameterKey] = False
                else:
                    result[std.ParameterKey] = std.ParameterValue
        
        logger.info(f"Loaded {len(result)} standards for '{standard_name}'")
        return result


# =============================================================================
# AI Design Integration
# =============================================================================

# =============================================================================
# STRATEGY PATTERN: Engineering Logic Base Class
# =============================================================================

class EngineeringLogic:
    """
    Abstract base class for engineering domain logic.
    
    This class defines the interface for all engineering systems
    (Fire Alarm, CCTV, Access Control, etc.) using the Strategy Pattern.
    
    Methods:
        analyze_room(): Analyze a room and return requirements/constraints
        place_devices(): Place devices based on room analysis
        calculate_cost(): Calculate material/labor cost
    """
    
    DOMAIN_NAME = "Generic"
    
    def __init__(self, standards: Dict = None):
        """
        Initialize with design standards
        
        Args:
            standards: Dictionary of standards parameters
        """
        self.standards = standards or {}
        logger.info(f"Initialized {self.DOMAIN_NAME} logic")
    
    def analyze_room(self, room_data: Dict) -> Dict:
        """
        Analyze a room and return requirements
        
        Args:
            room_data: Dictionary with room properties (name, type, area, dimensions, etc.)
            
        Returns:
            Dictionary with analysis results (requirements, constraints, devices_needed)
        """
        raise NotImplementedError("Subclasses must implement analyze_room()")
    
    def place_devices(self, room: 'Room', session_id: int) -> List['AIDesignDevice']:
        """
        Place devices in a room based on analysis
        
        Args:
            room: Room object
            session_id: Design session ID
            
        Returns:
            List of AIDesignDevice objects
        """
        raise NotImplementedError("Subclasses must implement place_devices()")
    
    def calculate_cost(self, devices: List['AIDesignDevice']) -> Dict:
        """
        Calculate total cost for devices
        
        Args:
            devices: List of proposed devices
            
        Returns:
            Dictionary with cost breakdown (equipment, labor, total)
        """
        raise NotImplementedError("Subclasses must implement calculate_cost()")


# =============================================================================
# Fire Alarm Logic Implementation
# =============================================================================

class FireAlarmLogic(EngineeringLogic):
    """
    Fire Alarm system engineering logic.
    
    Implements the Strategy Pattern for fire alarm design:
    - Smoke detectors per area coverage
    - Notification appliances for rooms > 50m²
    - Manual call points at exits
    """
    
    DOMAIN_NAME = "FireAlarm"
    
    # Device costs (sample prices in USD)
    DEVICE_COSTS = {
        'SmokeDetector': 150,
        'HeatDetector': 175,
        'ManualStation': 85,
        'Speaker': 220,
        'Horn': 195,
        'Strobe': 280,
        'ControlPanel': 5000,
    }
    
    def analyze_room(self, room_data: Dict) -> Dict:
        """Analyze room for fire alarm requirements"""
        area = room_data.get('area', 0)
        room_type = room_data.get('type', 'Office')
        
        # Calculate detectors needed (spacing: 6.5m for ordinary occupancy)
        spacing = self.standards.get('detector_spacing', 6.5)
        detectors_needed = max(1, int(area / (spacing * spacing)))
        
        # Check for notification requirement
        needs_notification = area > 50
        
        # Check for manual station requirement
        needs_manual = room_type in ['Corridor', 'Entrance', 'Lobby', 'Exit']
        
        return {
            'detectors_needed': detectors_needed,
            'needs_notification': needs_notification,
            'needs_manual': needs_manual,
            'coverage_area': area,
            'justification': f"Area {area}m² requires {detectors_needed} detector(s)"
        }
    
    def place_devices(self, room, session_id: int, db_session) -> List[AIDesignDevice]:
        """Place fire alarm devices in room"""
        devices = []
        
        # Get room analysis
        room_data = {
            'area': float(room.Area or 0),
            'type': room.RoomType or 'Office',
            'length': float(room.Length or 0),
            'width': float(room.Width or 0),
            'height': float(room.Height or 3)
        }
        analysis = self.analyze_room(room_data)
        
        # Calculate grid for detectors
        detectors = analysis['detectors_needed']
        import math
        cols = math.ceil(math.sqrt(detectors))
        rows = math.ceil(detectors / cols)
        
        spacing_x = room.Length / (cols + 1) if room.Length else 1
        spacing_y = room.Width / (rows + 1) if room.Width else 1
        
        # Place detectors
        for row in range(rows):
            for col in range(cols):
                if len(devices) < detectors:
                    x = spacing_x * (col + 1)
                    y = spacing_y * (row + 1)
                    z = (room.Height or 3) - 0.1
                    
                    device = AIDesignDevice(
                        SessionID=session_id,
                        RoomID=room.RoomID,
                        ProposedType='SmokeDetector',
                        X=x, Y=y, Z=z,
                        Confidence=0.92,
                        AI_Justification=analysis['justification']
                    )
                    devices.append(device)
        
        # Place notification (speaker) if needed
        if analysis['needs_notification']:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                ProposedType='Speaker',
                X=room.Length / 2 if room.Length else 0,
                Y=room.Width / 2 if room.Width else 0,
                Z=(room.Height or 3) - 0.15,
                Confidence=0.88,
                AI_Justification="Large room notification"
            )
            devices.append(device)
        
        # Place manual station if needed
        if analysis['needs_manual']:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                ProposedType='ManualStation',
                X=0.5, Y=0.5, Z=1.2,
                Confidence=0.95,
                AI_Justification="Building exit requirement"
            )
            devices.append(device)
        
        # Add to session
        for device in devices:
            db_session.add(device)
        
        db_session.commit()
        return devices
    
    def calculate_cost(self, devices: List[AIDesignDevice]) -> Dict:
        """Calculate fire alarm costs"""
        equipment = 0
        labor = 0
        
        for device in devices:
            device_cost = self.DEVICE_COSTS.get(device.ProposedType, 150)
            equipment += device_cost
            labor += device_cost * 0.5  # 50% labor estimate
        
        return {
            'equipment': equipment,
            'labor': labor,
            'total': equipment + labor,
            'device_count': len(devices)
        }


# =============================================================================
# CCTV Logic Implementation (Placeholder)
# =============================================================================

class CCTVLogic(EngineeringLogic):
    """
    CCTV system engineering logic (placeholder/demonstration).
    
    Places cameras at room corners for basic coverage.
    """
    
    DOMAIN_NAME = "CCTV"
    
    DEVICE_COSTS = {
        'Camera': 350,
        'DomeCamera': 420,
        'PTZCamera': 850,
    }
    
    def analyze_room(self, room_data: Dict) -> Dict:
        """Analyze room for CCTV coverage (placeholder)"""
        # Simple rule: 4 cameras at corners for basic coverage
        return {
            'cameras_needed': 4,
            'coverage': 'corners',
            'justification': 'Corner placement for full coverage'
        }
    
    def place_devices(self, room, session_id: int, db_session) -> List[AIDesignDevice]:
        """Place CCTV cameras at room corners"""
        devices = []
        
        # Get room dimensions
        length = float(room.Length or 0)
        width = float(room.Width or 0)
        height = float(room.Height or 3)
        
        # Place at 4 corners
        corners = [
            (0.5, 0.5),
            (length - 0.5, 0.5),
            (0.5, width - 0.5),
            (length - 0.5, width - 0.5)
        ]
        
        for x, y in corners:
            device = AIDesignDevice(
                SessionID=session_id,
                RoomID=room.RoomID,
                ProposedType='Camera',
                X=x, Y=y, Z=height - 0.3,
                Confidence=0.90,
                AI_Justification="Corner placement for coverage"
            )
            devices.append(device)
        
        # Add to session
        for device in devices:
            db_session.add(device)
        
        db_session.commit()
        return devices
    
    def calculate_cost(self, devices: List[AIDesignDevice]) -> Dict:
        """Calculate CCTV costs"""
        equipment = sum(self.DEVICE_COSTS.get(d.ProposedType, 350) for d in devices)
        labor = equipment * 0.4
        
        return {
            'equipment': equipment,
            'labor': labor,
            'total': equipment + labor,
            'device_count': len(devices)
        }


# =============================================================================
# Logic Factory
# =============================================================================

class EngineeringLogicFactory:
    """Factory to create engineering logic instances"""
    
    _LOGICS = {
        'FireAlarm': FireAlarmLogic,
        'CCTV': CCTVLogic,
        'PublicAddress': None,  # Will be loaded from pa_logic.py
    }
    
    @classmethod
    def create(cls, domain: str, standards: Dict = None) -> EngineeringLogic:
        """Create logic instance for domain"""
        logic_class = cls._LOGICS.get(domain)
        
        # Try to load from module if not registered
        if logic_class is None and domain == 'PublicAddress':
            try:
                from pa_logic import PublicAddressLogic
                cls._LOGICS['PublicAddress'] = PublicAddressLogic
                logic_class = PublicAddressLogic
            except ImportError:
                pass
        
        # Load AccessControlLogic
        if logic_class is None and domain == 'AccessControl':
            try:
                from access_control_logic import AccessControlLogic
                cls._LOGICS['AccessControl'] = AccessControlLogic
                logic_class = AccessControlLogic
            except ImportError:
                pass
        
        # Load DataNetworkLogic
        if logic_class is None and domain == 'DataNetwork':
            try:
                from data_network_logic import DataNetworkLogic
                cls._LOGICS['DataNetwork'] = DataNetworkLogic
                logic_class = DataNetworkLogic
            except ImportError:
                pass
        
        # Load LightingLogic
        if logic_class is None and domain == 'Lighting':
            try:
                from lighting_logic import LightingLogic
                cls._LOGICS['Lighting'] = LightingLogic
                logic_class = LightingLogic
            except ImportError:
                pass
        
        # Load PowerLogic
        if logic_class is None and domain == 'Power':
            try:
                from power_logic import PowerLogic
                cls._LOGICS['Power'] = PowerLogic
                logic_class = PowerLogic
            except ImportError:
                pass
        
        if logic_class is None:
            logger.warning(f"No logic for domain {domain}, using FireAlarm as default")
            logic_class = cls._LOGICS['FireAlarm']
        
        return logic_class(standards)
    
    @classmethod
    def register(cls, domain: str, logic_class: type):
        """Register a new logic class"""
        cls._LOGICS[domain] = logic_class
    
    @classmethod
    def get_available_domains(cls) -> List[str]:
        """Get list of available domains"""
        return list(cls._LOGICS.keys())

# =============================================================================
# Routing Models - Cable Routing and Network Topology
# =============================================================================

class RouteNode(Base):
    """Routing nodes for cable path calculation"""
    __tablename__ = 'RouteNodes'
    
    NodeID = Column(Integer, primary_key=True, autoincrement=True)
    FloorID = Column(Integer, ForeignKey('Rooms.FloorID'), nullable=True)
    XCoord = Column(Float, nullable=False)
    YCoord = Column(Float, nullable=False)
    ZCoord = Column(Float, default=0.0)
    NodeType = Column(String(50), default='junction')  # junction, endpoint, pullbox
    Description = Column(String(200))
    CreatedAt = Column(DateTime, default=datetime.utcnow)


class RouteSegment(Base):
    """Cable segments between route nodes"""
    __tablename__ = 'RouteSegments'
    
    SegmentID = Column(Integer, primary_key=True, autoincrement=True)
    FloorID = Column(Integer, ForeignKey('Rooms.FloorID'), nullable=True)
    FromNodeID = Column(Integer, ForeignKey('RouteNodes.NodeID'), nullable=False)
    ToNodeID = Column(Integer, ForeignKey('RouteNodes.NodeID'), nullable=False)
    SegmentType = Column(String(50), default='conduit')  # conduit, cable-tray, exposed
    LengthMeters = Column(Float, nullable=False)
    IsAccessible = Column(Boolean, default=True)
    CreatedAt = Column(DateTime, default=datetime.utcnow)


class DeviceConnection(Base):
    """Device connection topology for wiring and loops"""
    __tablename__ = 'DeviceConnections'
    
    ConnectionID = Column(Integer, primary_key=True, autoincrement=True)
    FromDeviceID = Column(Integer, ForeignKey('Devices.DeviceID'), nullable=False)
    ToDeviceID = Column(Integer, ForeignKey('Devices.DeviceID'), nullable=False)
    ConnectionType = Column(String(50), nullable=False)  # series, parallel, loop
    CableType = Column(String(100))
    CalculatedLength = Column(Float)
    PolylinePath = Column(JSON)  # GeoJSON coordinates for path
    LoopID = Column(String(50))
    WireGauge = Column(String(20))
    RoutingStatus = Column(String(20), default='pending')  # pending, validated, failed
    CreatedAt = Column(DateTime, default=datetime.utcnow)

# =============================================================================
# RENAMED: Engineering Design Engine (with domain support)
# =============================================================================

class EngineeringDesignEngine:
    """
    Multi-domain Engineering Design Engine.
    
    Renamed from FireAlarmAIDesign to support multiple domains.
    Uses Strategy Pattern to load appropriate logic.
    """
    
    # Domain registry for quick lookup
    domain_registry = {
        'FireAlarm': 'FireAlarmLogic',
        'CCTV': 'CCTVLogic',
        'PublicAddress': 'PublicAddressLogic',
        'AccessControl': 'AccessControlLogic',
        'DataNetwork': 'DataNetworkLogic',
        'Lighting': 'LightingLogic',
        'Power': 'PowerLogic',
    }
    
    def __init__(self, db_manager: DatabaseManager, domain: str = 'FireAlarm'):
        """
        Initialize the design engine
        
        Args:
            db_manager: DatabaseManager instance
            domain: Domain name ('FireAlarm', 'CCTV', etc.)
        """
        self.db = db_manager
        self.session = None
        self.domain = domain
        self.logic = None  # Set in __enter__
    
    def __enter__(self):
        self.session = self.db.get_session()
        
        # Load standards for this domain
        standards_loader = DesignStandardsLoader(self.session)
        standards = standards_loader.load_standards('Egyptian')
        
        # Create logic instance for domain
        self.logic = EngineeringLogicFactory.create(self.domain, standards)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
    
    def create_project(self, 
                      project_name: str,
                      client_name: str,
                      location: str,
                      building_type: str,
                      total_area: float,
                      total_floors: int,
                      engineer_id: int,
                      standard_name: str = 'Egyptian') -> DesignProject:
        """Create a new design project with domain"""
        # Check if project exists
        project = self.session.query(DesignProject).filter(
            DesignProject.ProjectName == project_name
        ).first()
        
        if project:
            logger.info(f"Using existing project: {project_name}")
            return project
        
        # Get or create domain
        domain_id = DomainEnum.get_domain_id(self.domain, self.session)
        
        # Create new project
        project = DesignProject(
            ProjectName=project_name,
            ClientName=client_name,
            Location=location,
            BuildingType=building_type,
            TotalArea=total_area,
            TotalFloors=total_floors,
            EngineerID=engineer_id,
            Status='Draft',
            DomainID=domain_id
        )
        
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        
        logger.info(f"Created project: {project_name} (ID: {project.ProjectID}, Domain: {self.domain})")
        return project
    
    def add_rooms(self, project_id: int, rooms_data: List[Dict]) -> List[Room]:
        """Add rooms to project (unchanged)"""
        rooms = []
        
        for room_data in rooms_data:
            room = Room(
                DesignProjectID=project_id,
                RoomName=room_data['name'],
                RoomType=room_data.get('type'),
                Length=room_data.get('length'),
                Width=room_data.get('width'),
                Height=room_data.get('height'),
                Area=(room_data.get('length', 0) or 0) * (room_data.get('width', 0) or 0),
                OccupancyLoad=room_data.get('occupancy'),
                FloorNumber=room_data.get('floor')
            )
            self.session.add(room)
            rooms.append(room)
        
        self.session.commit()
        
        for room in rooms:
            self.session.refresh(room)
        
        logger.info(f"Added {len(rooms)} rooms")
        return rooms
    
    def create_session(self, project_id: int, ai_version: str, input_type: str,
                 generated_by: int, confidence_score: float = None) -> DesignSession:
        """Create design session (domain-aware)"""
        session = DesignSession(
            DesignProjectID=project_id,
            AI_Version=ai_version,
            InputType=input_type,
            GeneratedBy=generated_by,
            ConfidenceScore=confidence_score,
            Notes=f"Generated by {self.logic.DOMAIN_NAME} logic"
        )
        
        self.session.add(session)
        self.session.commit()
        self.session.refresh(session)
        
        return session
    
    def run_design(self, rooms_data: List[Dict], 
              ai_version: str = "v2.0",
              input_type: str = "Manual",
              generated_by: int = 1) -> int:
        """Run domain-specific design"""
        # Create project
        project = self.create_project(
            project_name=f"{self.domain} Design",
            client_name="Client",
            location="Location",
            building_type="Office",
            total_area=sum(r.get('length', 0) * r.get('width', 0) for r in rooms_data),
            total_floors=1,
            engineer_id=generated_by
        )
        
        # Add rooms
        rooms = self.add_rooms(project.ProjectID, rooms_data)
        
        # Create session
        session = self.create_session(
            project_id=project.ProjectID,
            ai_version=ai_version,
            input_type=input_type,
            generated_by=generated_by
        )
        
        # Place devices using domain logic
        for room in rooms:
            self.logic.place_devices(room, session.SessionID, self.session)
        
        # Count devices
        device_count = self.session.query(AIDesignDevice).filter(
            AIDesignDevice.SessionID == session.SessionID
        ).count()
        
        logger.info(f"Design complete: {device_count} {self.domain} devices placed")
        return session.SessionID
    
    # Backward compatibility: Keep old class name as alias
    create_project_old = create_project
    add_rooms_old = add_rooms
    create_session_old = create_session
    run_design_old = run_design


# Backward compatibility alias
FireAlarmAIDesign = EngineeringDesignEngine
    
# =============================================================================
# Approval and Promotion Functions
# =============================================================================

class DeviceApprovalManager:
    """Manage device approvals and promotions to operational table"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.session = None
    
    def __enter__(self):
        self.session = self.db.get_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
    
# =============================================================================
# Usage Example
# =============================================================================

