"""
Fire Alarm AI Design Integration - Test Script
==========================================
This script demonstrates the complete workflow using SQLite in-memory database.

Run with: python test_ai_design.py

Author: Fire Protection Engineering Consultant
Date: 2026-05-09
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Any

# SQLAlchemy imports
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime,
    Text, DECIMAL, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base, Session
from sqlalchemy.dialects.postgresql import JSONB, BYTEA

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# SQLAlchemy Base
# =============================================================================
Base = declarative_base()

# =============================================================================
# Existing Core Tables (Simplified for Testing)
# =============================================================================

class User(Base):
    """User table for authentication"""
    __tablename__ = 'Users'
    
    UserID = Column(Integer, primary_key=True, autoincrement=True)
    Username = Column(String(100), unique=True, nullable=False)
    Email = Column(String(200))
    FullName = Column(String(200))
    IsActive = Column(Boolean, default=True)


class Role(Base):
    """User roles"""
    __tablename__ = 'Roles'
    
    RoleID = Column(Integer, primary_key=True, autoincrement=True)
    RoleName = Column(String(50), unique=True, nullable=False)


class DeviceType(Base):
    """Device type lookup"""
    __tablename__ = 'DeviceType'
    
    DeviceTypeID = Column(Integer, primary_key=True, autoincrement=True)
    TypeName = Column(String(100), unique=True, nullable=False)
    Description = Column(Text)


class Facility(Base):
    """Facility table"""
    __tablename__ = 'Facilities'
    
    FacilityID = Column(Integer, primary_key=True, autoincrement=True)
    Name = Column(String(200), nullable=False)
    Address = Column(String(500))


class FireAlarmSystem(Base):
    """Fire alarm system"""
    __tablename__ = 'FireAlarmSystems'
    
    SystemID = Column(Integer, primary_key=True, autoincrement=True)
    FacilityID = Column(Integer, ForeignKey('Facilities.FacilityID'))
    Name = Column(String(255), nullable=False)
    Status = Column(String(20), default='Operational')


class Zone(Base):
    """Zone for device grouping"""
    __tablename__ = 'Zones'
    
    ZoneID = Column(Integer, primary_key=True, autoincrement=True)
    SystemID = Column(Integer, ForeignKey('FireAlarmSystems.SystemID'))
    FloorID = Column(Integer)
    ZoneName = Column(String(100), nullable=False)
    ZoneType = Column(String(20))


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
    CreatedAt = Column(DateTime, default=datetime.utcnow)
    UpdatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DesignStandard(Base):
    """Design standards and rules"""
    __tablename__ = 'DesignStandard'
    
    StandardID = Column(Integer, primary_key=True, autoincrement=True)
    StandardName = Column(String(100), nullable=False)
    ParameterKey = Column(String(100), nullable=False)
    ParameterValue = Column(Text, nullable=False)
    Description = Column(Text)
    
    __table_args__ = (
        UniqueConstraint('StandardName', 'ParameterKey', name='uq_standard_param'),
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


class DesignSession(Base):
    """AI Design Session"""
    __tablename__ = 'DesignSession'
    
    SessionID = Column(Integer, primary_key=True, autoincrement=True)
    DesignProjectID = Column(Integer, ForeignKey('DesignProject.ProjectID', ondelete='CASCADE'), nullable=False)
    AI_Version = Column(String(50))
    InputType = Column(String(20))
    ConfidenceScore = Column(DECIMAL(5, 4))
    GeneratedBy = Column(Integer, ForeignKey('Users.UserID'))
    GeneratedAt = Column(DateTime, default=datetime.utcnow)
    Notes = Column(Text)


class AIDesignDevice(Base):
    """AI Proposed Device"""
    __tablename__ = 'AIDesignDevice'
    
    DesignDeviceID = Column(Integer, primary_key=True, autoincrement=True)
    SessionID = Column(Integer, ForeignKey('DesignSession.SessionID', ondelete='CASCADE'), nullable=False)
    RoomID = Column(Integer, ForeignKey('Room.RoomID'))
    ProposedType = Column(String(50), nullable=False)
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


class DesignFile(Base):
    """Design output files"""
    __tablename__ = 'DesignFile'
    
    FileID = Column(Integer, primary_key=True, autoincrement=True)
    SessionID = Column(Integer, ForeignKey('DesignSession.SessionID', ondelete='CASCADE'))
    ProjectID = Column(Integer, ForeignKey('DesignProject.ProjectID'))
    FileName = Column(String(255), nullable=False)
    FileType = Column(String(20))
    FileContent = Column(BYTEA)
    CreatedAt = Column(DateTime, default=datetime.utcnow)


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


# =============================================================================
# Database Manager
# =============================================================================

class DatabaseManager:
    """Database connection and session manager"""
    
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        logger.info(f"Database engine created for: {database_url}")
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def create_tables(self):
        Base.metadata.create_all(self.engine)
        logger.info("All tables created successfully")
    
    def drop_tables(self):
        Base.metadata.drop_all(self.engine)


# =============================================================================
# Design Standards Loader
# =============================================================================

class DesignStandardsLoader:
    """Load design standards from database"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def load_standards(self, standard_name: str) -> Dict[str, Any]:
        standards = self.session.query(DesignStandard).filter(
            DesignStandard.StandardName == standard_name
        ).all()
        
        result = {}
        for std in standards:
            try:
                result[std.ParameterKey] = float(std.ParameterValue)
            except ValueError:
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

class FireAlarmAIDesign:
    """Integration class for FireAlarmAI with database"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.session = None
    
    def __enter__(self):
        self.session = self.db.get_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
    
    def create_project(self, project_name: str, client_name: str, location: str,
                      building_type: str, total_area: float, total_floors: int,
                      engineer_id: int) -> DesignProject:
        project = self.session.query(DesignProject).filter(
            DesignProject.ProjectName == project_name
        ).first()
        
        if project:
            logger.info(f"Using existing project: {project_name} (ID: {project.ProjectID})")
            return project
        
        project = DesignProject(
            ProjectName=project_name,
            ClientName=client_name,
            Location=location,
            BuildingType=building_type,
            TotalArea=total_area,
            TotalFloors=total_floors,
            EngineerID=engineer_id,
            Status='Draft'
        )
        
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        
        logger.info(f"Created new project: {project_name} (ID: {project.ProjectID})")
        return project
    
    def add_rooms(self, project_id: int, rooms_data: List[Dict]) -> List[Room]:
        rooms = []
        
        for room_data in rooms_data:
            room = self.session.query(Room).filter(
                Room.DesignProjectID == project_id,
                Room.RoomName == room_data['name']
            ).first()
            
            if room:
                room.RoomType = room_data.get('type')
                room.Length = room_data.get('length')
                room.Width = room_data.get('width')
                room.Height = room_data.get('height')
                room.OccupancyLoad = room_data.get('occupancy')
                room.FloorNumber = room_data.get('floor')
                room.Area = (room.Length or 0) * (room.Width or 0)
            else:
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
        
        logger.info(f"Added {len(rooms)} rooms to project {project_id}")
        return rooms
    
    def create_session(self, project_id: int, ai_version: str, input_type: str,
                      generated_by: int, confidence_score: float = None) -> DesignSession:
        session = DesignSession(
            DesignProjectID=project_id,
            AI_Version=ai_version,
            InputType=input_type,
            GeneratedBy=generated_by,
            ConfidenceScore=confidence_score
        )
        
        self.session.add(session)
        self.session.commit()
        self.session.refresh(session)
        
        logger.info(f"Created design session: {session.SessionID}")
        return session
    
    def add_proposed_device(self, session_id: int, room_id: int, device_type: str,
                           x: float, y: float, z: float, confidence: float,
                           justification: str = None) -> AIDesignDevice:
        device = AIDesignDevice(
            SessionID=session_id,
            RoomID=room_id,
            ProposedType=device_type,
            X=x, Y=y, Z=z,
            Confidence=confidence,
            AI_Justification=justification
        )
        
        self.session.add(device)
        self.session.commit()
        self.session.refresh(device)
        
        return device
    
    def process_ai_design(self, project_name: str, project_data: Dict,
                         rooms_data: List[Dict], ai_version: str = "v1.0",
                         input_type: str = "Manual", generated_by: int = 1) -> int:
        try:
            # Load design standards
            standards_loader = DesignStandardsLoader(self.session)
            standards = standards_loader.load_standards(project_data.get('standard', 'Egyptian'))
            logger.info(f"Using standards: {standards}")
            
            # Create project
            project = self.create_project(
                project_name=project_name,
                client_name=project_data.get('client_name'),
                location=project_data.get('location'),
                building_type=project_data.get('building_type'),
                total_area=project_data.get('total_area', 0),
                total_floors=project_data.get('total_floors', 1),
                engineer_id=project_data.get('engineer_id', generated_by)
            )
            
            # Add rooms
            rooms = self.add_rooms(project.ProjectID, rooms_data)
            
            # Create session
            session = self.create_session(
                project_id=project.ProjectID,
                ai_version=ai_version,
                input_type=input_type,
                generated_by=generated_by,
                confidence_score=0.95
            )
            
            # Generate sample devices
            self._generate_sample_devices(session.SessionID, rooms, standards)
            
            logger.info(f"AI Design completed. Session ID: {session.SessionID}")
            return session.SessionID
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error processing AI design: {e}")
            raise
    
    def _generate_sample_devices(self, session_id: int, rooms: List[Room], standards: Dict):
        """Generate sample device proposals based on standards"""
        
        spacing = standards.get('detector_spacing', 6.5)
        
        for room in rooms:
            if room.Area:
                import math
                detectors_needed = max(1, math.ceil(room.Area / (spacing * spacing)))
                
                cols = math.ceil(math.sqrt(detectors_needed))
                rows = math.ceil(detectors_needed / cols)
                
                spacing_x = room.Length / (cols + 1) if room.Length else 1
                spacing_y = room.Width / (rows + 1) if room.Width else 1
                
                det_id = 1
                for row in range(rows):
                    for col in range(cols):
                        if det_id <= detectors_needed:
                            x = spacing_x * (col + 1)
                            y = spacing_y * (row + 1)
                            z = (room.Height or 3) - 0.1
                            
                            self.add_proposed_device(
                                session_id=session_id,
                                room_id=room.RoomID,
                                device_type='SmokeDetector',
                                x=round(x, 2),
                                y=round(y, 2),
                                z=round(z, 2),
                                confidence=0.92,
                                justification=f"Area coverage: {room.Area:.1f}m², spacing: {spacing}m"
                            )
                            det_id += 1
                
                # Add notification device
                if room.Area and room.Area > 50:
                    self.add_proposed_device(
                        session_id=session_id,
                        room_id=room.RoomID,
                        device_type='Speaker',
                        x=round(room.Length / 2, 2) if room.Length else 0,
                        y=round(room.Width / 2, 2) if room.Width else 0,
                        z=round((room.Height or 3) - 0.15, 2),
                        confidence=0.88,
                        justification="Large room requires notification"
                    )
                
                # Add manual station
                if room.RoomType in ['Corridor', 'Entrance', 'Lobby']:
                    self.add_proposed_device(
                        session_id=session_id,
                        room_id=room.RoomID,
                        device_type='ManualStation',
                        x=0.5,
                        y=0.5,
                        z=1.2,
                        confidence=0.95,
                        justification="Required at building entry/exit"
                    )


# =============================================================================
# Device Approval Manager
# =============================================================================

class DeviceApprovalManager:
    """Manage device approvals and promotions"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.session = None
    
    def __enter__(self):
        self.session = self.db.get_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
    
    def approve_device(self, design_device_id: int, approved_by: int,
                     revised_x: float = None, revised_y: float = None,
                     revised_z: float = None, note: str = None) -> bool:
        try:
            design_device = self.session.query(AIDesignDevice).filter(
                AIDesignDevice.DesignDeviceID == design_device_id
            ).first()
            
            if not design_device:
                raise ValueError(f"Design device {design_device_id} not found")
            
            old_values = {
                'X': float(design_device.X) if design_device.X else None,
                'Y': float(design_device.Y) if design_device.Y else None,
                'Z': float(design_device.Z) if design_device.Z else None,
                'ProposedType': design_device.ProposedType
            }
            
            if revised_x is not None:
                design_device.RevisedX = revised_x
                design_device.X = revised_x
            if revised_y is not None:
                design_device.RevisedY = revised_y
                design_device.Y = revised_y
            if revised_z is not None:
                design_device.RevisedZ = revised_z
                design_device.Z = revised_z
            if note:
                design_device.RevisionNote = note
            
            design_device.IsApproved = True
            design_device.ApprovedBy = approved_by
            design_device.ApprovedAt = datetime.utcnow()
            
            self.session.commit()
            logger.info(f"Approved design device {design_device_id}")
            
            return True
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error approving device: {e}")
            raise
    
    def promote_device_to_operational(self, design_device_id: int, system_id: int,
                                     zone_id: int = None) -> int:
        try:
            design_device = self.session.query(AIDesignDevice).filter(
                AIDesignDevice.DesignDeviceID == design_device_id
            ).first()
            
            if not design_device:
                raise ValueError(f"Design device {design_device_id} not found")
            
            if not design_device.IsApproved:
                raise ValueError("Device must be approved before promotion")
            
            # Map proposed type to device type
            type_mapping = {
                'SmokeDetector': 'Smoke Detector',
                'HeatDetector': 'Heat Detector',
                'ManualStation': 'Manual Call Point',
                'Speaker': 'Notification Appliance',
                'Horn': 'Notification Appliance',
                'Strobe': 'Notification Appliance'
            }
            
            device_type_name = type_mapping.get(
                design_device.ProposedType, 
                design_device.ProposedType
            )
            
            # Get device type ID
            device_type = self.session.query(DeviceType).filter(
                DeviceType.TypeName == device_type_name
            ).first()
            
            if not device_type:
                device_type = DeviceType(TypeName=device_type_name)
                self.session.add(device_type)
                self.session.commit()
                self.session.refresh(device_type)
            
            # Use revised coordinates
            x = design_device.RevisedX or design_device.X
            y = design_device.RevisedY or design_device.Y
            z = design_device.RevisedZ or design_device.Z
            
            # Create operational device record
            new_device = Device(
                SystemID=system_id,
                DeviceTypeID=device_type.DeviceTypeID,
                ZoneID=zone_id,
                LocationDescription=f"X:{x}, Y:{y}, Z:{z} - {design_device.ProposedType}",
                Status='Normal',
                InstallationDate=datetime.utcnow()
            )
            
            self.session.add(new_device)
            self.session.commit()
            self.session.refresh(new_device)
            
            # Update design device with reference
            design_device.DeviceID_Ref = new_device.DeviceID
            
            # Create revision history
            revision = RevisionHistory(
                DesignDeviceID=design_device_id,
                RevisedBy=design_device.ApprovedBy,
                OldValues=json.dumps({'X': float(design_device.X), 'Y': float(design_device.Y)}),
                NewValues=json.dumps({'DeviceID': new_device.DeviceID, 'Status': 'Promoted'}),
                Note='Promoted to operational Device table'
            )
            self.session.add(revision)
            self.session.commit()
            
            logger.info(f"Promoted design device {design_device_id} to DeviceID {new_device.DeviceID}")
            return new_device.DeviceID
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error promoting device: {e}")
            raise
    
    def get_project_design(self, project_id: int) -> Dict:
        project = self.session.query(DesignProject).filter(
            DesignProject.ProjectID == project_id
        ).first()
        
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        rooms = self.session.query(Room).filter(
            Room.DesignProjectID == project_id
        ).all()
        
        sessions = self.session.query(DesignSession).filter(
            DesignSession.DesignProjectID == project_id
        ).all()
        
        session_ids = [s.SessionID for s in sessions]
        devices = self.session.query(AIDesignDevice).filter(
            AIDesignDevice.SessionID.in_(session_ids)
        ).all() if session_ids else []
        
        return {
            'project': {
                'ProjectID': project.ProjectID,
                'ProjectName': project.ProjectName,
                'ClientName': project.ClientName,
                'Status': project.Status
            },
            'rooms': [{'RoomID': r.RoomID, 'RoomName': r.RoomName, 'Area': float(r.Area) if r.Area else 0} for r in rooms],
            'devices': [{'DesignDeviceID': d.DesignDeviceID, 'ProposedType': d.ProposedType, 
                       'X': float(d.X) if d.X else 0,
                       'Y': float(d.Y) if d.Y else 0,
                       'IsApproved': d.IsApproved,
                       'DeviceID_Ref': d.DeviceID_Ref} for d in devices],
            'approved_count': sum(1 for d in devices if d.IsApproved),
            'pending_count': sum(1 for d in devices if not d.IsApproved)
        }


# =============================================================================
# Main Test Function
# =============================================================================

def run_test():
    """Main test function demonstrating the complete workflow"""
    
    print("=" * 70)
    print("Fire Alarm AI Design Integration - Test Script")
    print("=" * 70)
    
    # Create in-memory SQLite database
    db = DatabaseManager('sqlite:///:memory:')
    db.create_tables()
    
    # Get session
    session = db.get_session()
    
    # ===========================================================================
    # 1. Setup: Create basic data (Users, DeviceTypes, Systems)
    # ===========================================================================
    print("\n[1] Setting up basic data...")
    
    # Create test user
    user = User(UserID=1, Username='engineer', FullName='Ahmed Engineer', Email='ahmed@example.com')
    session.add(user)
    
    # Create roles
    roles = [
        Role(RoleID=1, RoleName='Admin'),
        Role(RoleID=2, RoleName='Engineer'),
        Role(RoleID=3, RoleName='Technician')
    ]
    for role in roles:
        session.add(role)
    
    # Create device types
    device_types = [
        DeviceType(DeviceTypeID=1, TypeName='Smoke Detector', Description='Smoke detection'),
        DeviceType(DeviceTypeID=2, TypeName='Heat Detector', Description='Heat detection'),
        DeviceType(DeviceTypeID=3, TypeName='Manual Call Point', Description='Manual activation'),
        DeviceType(DeviceTypeID=4, TypeName='Notification Appliance', Description='Notification'),
    ]
    for dt in device_types:
        session.add(dt)
    
    # Create facility
    facility = Facility(FacilityID=1, Name='Test Building', Address='123 Cairo St')
    session.add(facility)
    
    # Create fire alarm system
    system = FireAlarmSystem(SystemID=1, FacilityID=1, Name='Main Fire Alarm', Status='Operational')
    session.add(system)
    
    # Create zones
    zone1 = Zone(ZoneID=1, SystemID=1, FloorID=1, ZoneName='Floor 1 Zone A', ZoneType='Detection')
    zone2 = Zone(ZoneID=2, SystemID=1, FloorID=1, ZoneName='Floor 1 Zone B', ZoneType='Detection')
    session.add(zone1)
    session.add(zone2)
    
    session.commit()
    print("   ✅ Basic data created")
    
    # ===========================================================================
    # 2. Insert Design Standards (Egyptian)
    # ===========================================================================
    print("\n[2] Inserting Design Standards (Egyptian)...")
    
    egyptian_standards = [
        DesignStandard(StandardName='Egyptian', ParameterKey='detector_spacing', ParameterValue='6.5', Description='Maximum spacing'),
        DesignStandard(StandardName='Egyptian', ParameterKey='max_detector_height', ParameterValue='9', Description='Max height'),
        DesignStandard(StandardName='Egyptian', ParameterKey='min_audible_db', ParameterValue='85', Description='Min dB'),
        DesignStandard(StandardName='Egyptian', ParameterKey='manual_station_distance', ParameterValue='23', Description='Max distance'),
    ]
    
    for std in egyptian_standards:
        session.add(std)
    
    session.commit()
    print("   ✅ Design standards inserted")
    
    # ===========================================================================
    # 3. Process AI Design (3 Rooms)
    # ===========================================================================
    print("\n[3] Processing AI Design...")
    
    project_data = {
        'client_name': 'ABC Company',
        'location': 'Cairo, Egypt',
        'building_type': 'Office',
        'total_area': 500,
        'total_floors': 1,
        'engineer_id': 1,
        'standard': 'Egyptian'
    }
    
    rooms_data = [
        {'name': 'Main Office', 'type': 'Office', 'length': 20, 'width': 15, 'height': 3.2, 'occupancy': 25, 'floor': 1},
        {'name': 'Corridor', 'type': 'Corridor', 'length': 30, 'width': 2, 'height': 3.2, 'occupancy': 10, 'floor': 1},
        {'name': 'Server Room', 'type': 'Server', 'length': 5, 'width': 4, 'height': 3.0, 'occupancy': 2, 'floor': 1},
    ]
    
    with FireAlarmAIDesign(db) as ai_design:
        session_id = ai_design.process_ai_design(
            project_name="Test Office Building - Fire Alarm",
            project_data=project_data,
            rooms_data=rooms_data,
            ai_version="v1.0",
            input_type="Hybrid",
            generated_by=1
        )
    
    print(f"   ✅ AI Design completed. Session ID: {session_id}")
    
    # ===========================================================================
    # 4. Query and Display Results
    # ===========================================================================
    print("\n[4] Querying AIDesignDevice table...")
    
    design_devices = session.query(AIDesignDevice).all()
    
    print(f"\n   Total AI Proposed Devices: {len(design_devices)}")
    print("-" * 70)
    for device in design_devices:
        print(f"   ID: {device.DesignDeviceID:3d} | Type: {device.ProposedType:15s} | "
              f"Room: {device.RoomID} | X: {float(device.X):5.2f} | Y: {float(device.Y):5.2f} | "
              f"Approved: {device.IsApproved}")
    print("-" * 70)
    
    # ===========================================================================
    # 5. Approve One Device
    # ===========================================================================
    print("\n[5] Approving first device...")
    
    if design_devices:
        first_device_id = design_devices[0].DesignDeviceID
        
        with DeviceApprovalManager(db) as approval:
            approval.approve_device(
                design_device_id=first_device_id,
                approved_by=1,
                note="Approved after engineering review"
            )
        
        print(f"   ✅ Device {first_device_id} approved")
        
        # ===========================================================================
        # 6. Promote to Operational Device
        # ===========================================================================
        print("\n[6] Promoting device to operational Device table...")
        
        with DeviceApprovalManager(db) as approval:
            new_device_id = approval.promote_device_to_operational(
                design_device_id=first_device_id,
                system_id=1,
                zone_id=1
            )
        
        print(f"   ✅ Device promoted to operational DeviceID: {new_device_id}")
        
        # ===========================================================================
        # 7. Verify Promotion
        # ===========================================================================
        print("\n[7] Verifying promotion...")
        
        # Check AIDesignDevice
        updated_device = session.query(AIDesignDevice).filter(
            AIDesignDevice.DesignDeviceID == first_device_id
        ).first()
        
        print(f"   AIDesignDevice.DesignDeviceID: {updated_device.DesignDeviceID}")
        print(f"   AIDesignDevice.IsApproved: {updated_device.IsApproved}")
        print(f"   AIDesignDevice.DeviceID_Ref: {updated_device.DeviceID_Ref}")
        
        # Check operational Device
        operational_device = session.query(Device).filter(
            Device.DeviceID == new_device_id
        ).first()
        
        print(f"\n   Device.DeviceID: {operational_device.DeviceID}")
        print(f"   Device.DeviceTypeID: {operational_device.DeviceTypeID}")
        print(f"   Device.SystemID: {operational_device.SystemID}")
        print(f"   Device.ZoneID: {operational_device.ZoneID}")
        print(f"   Device.LocationDescription: {operational_device.LocationDescription}")
        print(f"   Device.Status: {operational_device.Status}")
        
        # Check RevisionHistory
        revisions = session.query(RevisionHistory).filter(
            RevisionHistory.DesignDeviceID == first_device_id
        ).all()
        
        print(f"\n   RevisionHistory entries: {len(revisions)}")
        for rev in revisions:
            print(f"      - RevisionID: {rev.RevisionID}")
            print(f"        Note: {rev.Note}")
            print(f"        OldValues: {rev.OldValues}")
            print(f"        NewValues: {rev.NewValues}")
    
    # ===========================================================================
    # 8. Final Summary
    # ===========================================================================
    print("\n" + "=" * 70)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    
    # Final device counts
    total_design = session.query(AIDesignDevice).count()
    total_operational = session.query(Device).count()
    approved = session.query(AIDesignDevice).filter(AIDesignDevice.IsApproved == True).count()
    
    print(f"\nFinal Counts:")
    print(f"   AIDesignDevice records: {total_design}")
    print(f"   Approved devices: {approved}")
    print(f"   Operational Device records: {total_operational}")
    
    session.close()


if __name__ == "__main__":
    run_test()
