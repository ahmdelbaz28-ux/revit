#!/usr/bin/env python3
"""
seed_all_domains.py - Database Seeding Script for Multi-Domain Engineering Platform
===============================================================================

This script populates the database with reference data for all engineering domains:
- Project domains (FireAlarm, CCTV, AccessControl, etc.)
- Device types for each domain
- Design standards for each domain
- Manufacturer catalogs with pricing

Usage:
    python seed_all_domains.py
    # Or with custom database URL:
    DATABASE_URL=postgresql://user:pass@host/db python seed_all_domains.py

Author: FireAlarmAI Engineering Team
Date: 2026-05-09
"""

import os
import sys
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship, sessionmaker, declarative_base

# Import from existing models
from ai_design_integration import DatabaseManager, ProjectDomain, DeviceType, DesignStandard

# =============================================================================
# Additional SQLAlchemy Models
# =============================================================================

Base = declarative_base()


class ManufacturerCatalog(Base):
    """Manufacturer product catalog"""
    __tablename__ = 'ManufacturerCatalog'
    
    CatalogID = Column(Integer, primary_key=True, autoincrement=True)
    DeviceTypeID = Column(Integer, ForeignKey('DeviceType.DeviceTypeID'))
    ManufacturerName = Column(String(100), nullable=False)
    Model = Column(String(100), nullable=False)
    Specifications = Column(JSON)  # JSON dict of specs
    UnitPrice = Column(Float)
    Currency = Column(String(3), default='USD')
    CreatedAt = Column(DateTime, default=datetime.utcnow)


# Route Network Seeding
# =============================================================================

def seed_route_network(session):
    """
    Create a standard routing network for cable routing.
    
    Standard floor plan: 100m x 100m
    - Corridor lines at y=50m, y=60m (horizontal) and x=50m, x=60m (vertical)
    - RouteNodes every 5m along corridors
    - CableTray nodes with segments to nearest corridor
    
    Args:
        session: SQLAlchemy session
        
    Returns:
        Count of nodes created
    """
    from ai_design_integration import RouteNode, RouteSegment
    
    logger.info("Creating route network nodes...")
    
    node_count = 0
    segment_count = 0
    corridor_y = [50.0, 60.0]  # Horizontal corridors
    corridor_x = [50.0, 60.0]  # Vertical corridors
    
    # Create corridor nodes
    for y in corridor_y:
        for x in range(0, 101, 5):
            if x % 5 == 0:
                node = RouteNode(
                    FloorID=1,
                    XCoord=float(x),
                    YCoord=float(y),
                    ZCoord=3.0,
                    NodeType='junction',
                    Description=f'Corridor Node x={x}, y={y}'
                )
                session.add(node)
                node_count += 1
    
    for x in corridor_x:
        for y in range(0, 101, 5):
            if y % 5 == 0 and y not in corridor_y:
                node = RouteNode(
                    FloorID=1,
                    XCoord=float(x),
                    YCoord=float(y),
                    ZCoord=3.0,
                    NodeType='junction',
                    Description=f'Corridor Node x={x}, y={y}'
                )
                session.add(node)
                node_count += 1
    
    session.commit()
    logger.info(f"Created {node_count} corridor nodes")
    
    # Create segments connecting adjacent nodes
    nodes = session.query(RouteNode).filter(RouteNode.FloorID == 1).all()
    nodes_by_coord = {(n.XCoord, n.YCoord): n for n in nodes}
    
    # Horizontal segments on y=50 and y=60
    for y in corridor_y:
        prev_x = None
        for x in range(0, 101, 5):
            node = nodes_by_coord.get((float(x), float(y)))
            if node and prev_x is not None:
                prev_node = nodes_by_coord.get((float(prev_x), float(y)))
                if prev_node and node.NodeID != prev_node.NodeID:
                    segment = RouteSegment(
                        FloorID=1,
                        FromNodeID=prev_node.NodeID,
                        ToNodeID=node.NodeID,
                        SegmentType='Corridor',
                        LengthMeters=5.0,
                        IsAccessible=True
                    )
                    session.add(segment)
                    segment_count += 1
            prev_x = x
    
    # Vertical segments on x=50 and x=60  
    for x in corridor_x:
        prev_y = None
        for y in range(0, 101, 5):
            node = nodes_by_coord.get((float(x), float(y)))
            if node and prev_y is not None:
                prev_node = nodes_by_coord.get((float(x), float(prev_y)))
                if prev_node and node.NodeID != prev_node.NodeID:
                    segment = RouteSegment(
                        FloorID=1,
                        FromNodeID=prev_node.NodeID,
                        ToNodeID=node.NodeID,
                        SegmentType='Corridor',
                        LengthMeters=5.0,
                        IsAccessible=True
                    )
                    session.add(segment)
                    segment_count += 1
            prev_y = y
    
    session.commit()
    logger.info(f"Created {segment_count} corridor segments")
    
    # Create CableTray nodes (10 nodes + segments)
    tray_positions = [(10, 20), (20, 30), (30, 40), (70, 80), (80, 90),
                     (10, 70), (20, 80), (30, 90), (90, 10), (80, 20)]
    
    for x, y in tray_positions:
        # Find nearest corridor node
        nearest = None
        min_dist = float('inf')
        for node in nodes:
            dist = ((node.XCoord - x) ** 2 + (node.YCoord - y) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                nearest = node
        
        if nearest:
            tray_node = RouteNode(
                FloorID=1,
                XCoord=float(x),
                YCoord=float(y),
                ZCoord=3.0,
                NodeType='cable_tray',
                Description=f'CableTray at x={x}, y={y}'
            )
            session.add(tray_node)
            session.flush()
            node_count += 1
            
            # Connect to nearest corridor
            seg = RouteSegment(
                FloorID=1,
                FromNodeID=tray_node.NodeID,
                ToNodeID=nearest.NodeID,
                SegmentType='CableTray',
                LengthMeters=float(min_dist),
                IsAccessible=True
            )
            session.add(seg)
            segment_count += 1
    
    session.commit()
    logger.info(f"Created 10 CableTray nodes with segments")
    
    logger.info(f"Route network seeding complete: {node_count} nodes, {segment_count} segments")
    return node_count


# Relationships
# Domain Seeding
# =============================================================================

DOMAINS = [
    {'name': 'FireAlarm', 'description': 'Fire Alarm and Detection System'},
    {'name': 'CCTV', 'description': 'Closed-Circuit Television / Video Surveillance'},
    {'name': 'AccessControl', 'description': 'Access Control System'},
    {'name': 'PublicAddress', 'description': 'Public Address / Voice Alarm System'},
    {'name': 'DataNetwork', 'description': 'Data and Telecom Network'},
    {'name': 'Lighting', 'description': 'Intelligent Lighting System'},
    {'name': 'Power', 'description': 'Electrical Power Distribution'},
]


def seed_domains(session):
    """
    Insert project domains into database.
    
    Args:
        session: SQLAlchemy session
        
    Returns:
        Number of domains inserted
    """
    logger.info("Seeding domains...")
    
    count = 0
    for domain_data in DOMAINS:
        # Check if exists
        existing = session.query(ProjectDomain).filter(
            ProjectDomain.DomainName == domain_data['name']
        ).first()
        
        if not existing:
            domain = ProjectDomain(
                DomainName=domain_data['name'],
                Description=domain_data['description'],
                IsActive=True
            )
            session.add(domain)
            count += 1
            logger.debug(f"  Added domain: {domain_data['name']}")
    
    session.commit()
    logger.info(f"  Domains inserted: {count}")
    return count


# =============================================================================
# Device Types Seeding
# =============================================================================

DEVICE_TYPES = {
    'FireAlarm': [
        {'name': 'SmokeDetector', 'description': 'Smoke Detection Device'},
        {'name': 'HeatDetector', 'description': 'Heat Detection Device'},
        {'name': 'ManualCallPoint', 'description': 'Manual Fire Alarm Call Point'},
        {'name': 'Speaker', 'description': 'Voice Alarm Speaker'},
        {'name': 'Horn', 'description': 'Sound Alarm Horn'},
        {'name': 'Strobe', 'description': 'Visual Alarm Strobe'},
        {'name': 'ControlPanel', 'description': 'Fire Alarm Control Panel'},
        {'name': 'RepeaterPanel', 'description': 'Repeater Panel'},
    ],
    'CCTV': [
        {'name': 'IP Camera', 'description': 'Network IP Camera'},
        {'name': 'PTZ Camera', 'description': 'Pan-Tilt-Zoom Camera'},
        {'name': 'Dome Camera', 'description': 'Dome Style Camera'},
        {'name': 'Bullet Camera', 'description': 'Bullet Style Camera'},
        {'name': 'NVR', 'description': 'Network Video Recorder'},
        {'name': 'Video Encoder', 'description': 'Video Encoder'},
        {'name': 'Monitor', 'description': 'CCTV Monitor'},
        {'name': 'Joystick Controller', 'description': 'PTZ Joystick Controller'},
    ],
    'AccessControl': [
        {'name': 'Card Reader', 'description': 'RFID Card Reader'},
        {'name': 'Biometric Reader', 'description': 'Biometric Fingerprint/Face Reader'},
        {'name': 'Electric Lock', 'description': 'Electric Door Lock'},
        {'name': 'Door Contact', 'description': 'Door Position Contact'},
        {'name': 'Exit Button', 'description': 'Emergency Exit Button'},
        {'name': 'Controller', 'description': 'Access Control Controller'},
        {'name': 'Power Supply', 'description': 'Access Control Power Supply'},
    ],
    'PublicAddress': [
        {'name': 'Ceiling Speaker', 'description': 'Ceiling Mounted Speaker'},
        {'name': 'Wall Speaker', 'description': 'Wall Mounted Speaker'},
        {'name': 'Horn Speaker', 'description': 'Horn Speaker for Outdoor'},
        {'name': 'Amplifier', 'description': 'PA Amplifier'},
        {'name': 'Mixer', 'description': 'Audio Mixer'},
        {'name': 'Microphone', 'description': 'Announcement Microphone'},
        {'name': 'Message Player', 'description': 'Pre-recorded Message Player'},
    ],
    'DataNetwork': [
        {'name': 'Data Outlet', 'description': 'Network Data Outlet'},
        {'name': 'Patch Panel', 'description': 'Network Patch Panel'},
        {'name': 'Switch', 'description': 'Network Switch'},
        {'name': 'Router', 'description': 'Network Router'},
        {'name': 'Access Point', 'description': 'Wireless Access Point'},
        {'name': 'Rack', 'description': 'Server/Network Rack'},
        {'name': 'UPS', 'description': 'Uninterruptible Power Supply'},
    ],
    'Lighting': [
        {'name': 'LED Panel', 'description': 'LED Light Panel'},
        {'name': 'Downlight', 'description': 'LED Downlight'},
        {'name': 'Emergency Light', 'description': 'Emergency Lighting'},
        {'name': 'Exit Sign', 'description': 'Emergency Exit Sign'},
        {'name': 'Occupancy Sensor', 'description': 'Occupancy/Presence Sensor'},
        {'name': 'Dimmer', 'description': 'Light Dimmer Module'},
        {'name': 'Relay Module', 'description': 'Lighting Relay Module'},
    ],
    'Power': [
        {'name': 'Socket Outlet', 'description': 'Power Socket Outlet'},
        {'name': 'Distribution Board', 'description': 'Electrical Distribution Board'},
        {'name': 'MCB', 'description': 'Miniature Circuit Breaker'},
        {'name': 'RCCB', 'description': 'Residual Current Circuit Breaker'},
        {'name': 'Busbar', 'description': 'Busbar System'},
        {'name': 'Transformer', 'description': 'Voltage Transformer'},
        {'name': 'Generator', 'description': 'Backup Generator'},
    ],
}


def seed_device_types(session):
    """
    Insert device types for each domain.
    
    Args:
        session: SQLAlchemy session
        
    Returns:
        Number of device types inserted
    """
    logger.info("Seeding device types...")
    
    count = 0
    for domain_name, types in DEVICE_TYPES.items():
        # Get domain ID
        domain = session.query(ProjectDomain).filter(
            ProjectDomain.DomainName == domain_name
        ).first()
        
        if not domain:
            logger.warning(f"  Domain not found: {domain_name}")
            continue
        
        for type_data in types:
            # Check if exists
            existing = session.query(DeviceType).filter(
                DeviceType.TypeName == type_data['name']
            ).first()
            
            if not existing:
                device_type = DeviceType(
                    TypeName=type_data['name'],
                    Description=type_data['description'],
                    DomainID=domain.DomainID
                )
                session.add(device_type)
                count += 1
                logger.debug(f"  Added: {domain_name} - {type_data['name']}")
    
    session.commit()
    logger.info(f"  Device types inserted: {count}")
    return count


# =============================================================================
# Design Standards Seeding
# =============================================================================

DESIGN_STANDARDS = {
    'FireAlarm': [
        {'key': 'detector_spacing', 'value': '6.5', 'desc': 'Max spacing between detectors (m)'},
        {'key': 'max_area_per_detector', 'value': '40', 'desc': 'Max area covered per detector (m²)'},
        {'key': 'speaker_spacing', 'value': '6', 'desc': 'Max speaker spacing (m)'},
        {'key': 'manual_station_spacing', 'value': '30', 'desc': 'Max distance to manual station (m)'},
    ],
    'CCTV': [
        {'key': 'camera_height', 'value': '3.0', 'desc': 'Standard camera mounting height (m)'},
        {'key': 'min_lux', 'value': '0.5', 'desc': 'Minimum illumination (lux)'},
        {'key': 'max_camera_distance', 'value': '30', 'desc': 'Max camera cable distance (m)'},
        {'key': 'corridor_camera_spacing', 'value': '15', 'desc': 'Corridor camera spacing (m)'},
        {'key': 'storage_days', 'value': '30', 'desc': 'Video storage retention (days)'},
    ],
    'AccessControl': [
        {'key': 'reader_height', 'value': '1.2', 'desc': 'Reader mounting height (m)'},
        {'key': 'lock_holding_force', 'value': '500', 'desc': 'Lock holding force (kg)'},
        {'key': 'door_contact_type', 'value': 'reed', 'desc': 'Door contact type'},
        {'key': 'exit_button_height', 'value': '1.1', 'desc': 'Exit button height (m)'},
    ],
    'PublicAddress': [
        {'key': 'ceiling_speaker_spacing', 'value': '6', 'desc': 'Ceiling speaker spacing (m)'},
        {'key': 'min_spl', 'value': '85', 'desc': 'Minimum sound pressure level (dB)'},
        {'key': 'wall_speaker_height', 'value': '2.5', 'desc': 'Wall speaker height (m)'},
        {'key': 'amplifier_headroom', 'value': '20', 'desc': 'Amplifier headroom (%)'},
    ],
    'DataNetwork': [
        {'key': 'outlet_height', 'value': '0.3', 'desc': 'Outlet mounting height (m)'},
        {'key': 'max_cable_length', 'value': '90', 'desc': 'Max horizontal cable length (m)'},
        {'key': 'ap_spacing', 'value': '15', 'desc': 'Access point spacing (m)'},
        {'key': 'rack_capacity', 'value': '42', 'desc': 'Rack capacity (U)'},
    ],
    'Lighting': [
        {'key': 'office_lux', 'value': '500', 'desc': 'Office illuminance (lux)'},
        {'key': 'corridor_lux', 'value': '150', 'desc': 'Corridor illuminance (lux)'},
        {'key': 'emergency_lux', 'value': '10', 'desc': 'Emergency lighting (lux)'},
        {'key': 'sensor_timeout', 'value': '15', 'desc': 'Occupancy sensor timeout (min)'},
    ],
    'Power': [
        {'key': 'socket_height', 'value': '0.3', 'desc': 'Socket outlet height (m)'},
        {'key': 'db_height', 'value': '1.5', 'desc': 'Distribution board height (m)'},
        {'key': 'voltage_drop_max', 'value': '3', 'desc': 'Max voltage drop (%)'},
        {'key': 'mcb_rating_lighting', 'value': '10', 'desc': 'MCB rating for lighting (A)'},
        {'key': 'mcb_rating_power', 'value': '16', 'desc': 'MCB rating for power (A)'},
    ],
}


def seed_design_standards(session):
    """
    Insert design standards for each domain.
    
    Args:
        session: SQLAlchemy session
        
    Returns:
        Number of standards inserted
    """
    logger.info("Seeding design standards...")
    
    count = 0
    for domain_name, standards in DESIGN_STANDARDS.items():
        # Get domain ID
        domain = session.query(ProjectDomain).filter(
            ProjectDomain.DomainName == domain_name
        ).first()
        
        if not domain:
            logger.warning(f"  Domain not found: {domain_name}")
            continue
        
        for std in standards:
            # Check if exists
            existing = session.query(DesignStandard).filter(
                DesignStandard.StandardName == 'international',
                DesignStandard.ParameterKey == std['key'],
                DesignStandard.DomainID == domain.DomainID
            ).first()
            
            if not existing:
                standard = DesignStandard(
                    StandardName='international',
                    ParameterKey=std['key'],
                    ParameterValue=std['value'],
                    Description=std['desc'],
                    DomainID=domain.DomainID
                )
                session.add(standard)
                count += 1
                logger.debug(f"  Added: {domain_name} - {std['key']}")
    
    session.commit()
    logger.info(f"  Standards inserted: {count}")
    return count


# =============================================================================
# Manufacturer Catalog Seeding
# =============================================================================

MANUFACTURER_CATALOG = {
    'CCTV': [
        {
            'type': 'IP Camera',
            'manufacturer': 'Hikvision',
            'model': 'DS-2CD2043G2',
            'specs': {'resolution': '4MP', 'lens': '2.8mm', 'night_vision': '30m', 'ip_rating': 'IP67'},
            'price': 180.00
        },
        {
            'type': 'PTZ Camera',
            'manufacturer': 'Dahua',
            'model': 'SD6C232UE',
            'specs': {'resolution': '2MP', 'optical_zoom': '32x', 'night_vision': '150m', 'ip_rating': 'IP66'},
            'price': 650.00
        },
        {
            'type': 'NVR',
            'manufacturer': 'Bosch',
            'model': 'NDI-77032',
            'specs': {'channels': 32, 'resolution': '12MP', 'storage': '24TB'},
            'price': 1200.00
        },
        {
            'type': 'Dome Camera',
            'manufacturer': 'Hikvision',
            'model': 'DS-2CD2347G2',
            'specs': {'resolution': '4MP', 'lens': '2.8mm', 'colorvu': True, 'ip_rating': 'IP67'},
            'price': 220.00
        },
    ],
    'AccessControl': [
        {
            'type': 'Card Reader',
            'manufacturer': 'HID',
            'model': 'iCLASS SE R40',
            'specs': {'technology': 'iCLASS SE', 'frequency': '13.56MHz', 'read_range': '10cm'},
            'price': 145.00
        },
        {
            'type': 'Biometric Reader',
            'manufacturer': 'ZKTeco',
            'model': 'C3-400',
            'specs': {'capacity': '3000', 'comm': 'TCP/IP, RS485', 'verify_time': '<1s'},
            'price': 280.00
        },
        {
            'type': 'Electric Lock',
            'manufacturer': 'ASSA ABLOY',
            'model': 'INOX 8800',
            'specs': {'type': 'Magnetic', 'holding_force': '600kg', 'voltage': '12V/24V'},
            'price': 195.00
        },
        {
            'type': 'Controller',
            'manufacturer': 'HID',
            'model': 'Edge ESPR40',
            'specs': {'doors': 2, 'capacity': '100000', 'comm': 'OSDP, Wiegand'},
            'price': 450.00
        },
    ],
    'PublicAddress': [
        {
            'type': 'Ceiling Speaker',
            'manufacturer': 'Bosch',
            'model': 'LBC 3081/41',
            'specs': {'rating': '6W', 'dispersion': '110deg', 'freq_range': '80Hz-18kHz'},
            'price': 45.00
        },
        {
            'type': 'Wall Speaker',
            'manufacturer': 'TOA',
            'model': 'CS-304',
            'specs': {'rating': '10W', 'dispersion': '90deg', 'wall_mount': True},
            'price': 65.00
        },
        {
            'type': 'Amplifier',
            'manufacturer': 'Bosch',
            'model': 'PRA-AMP120',
            'specs': {'output': '120W', 'zones': 6, ' Dante': False},
            'price': 850.00
        },
        {
            'type': 'Horn Speaker',
            'manufacturer': 'AtlasIED',
            'model': 'HS-30T',
            'specs': {'rating': '30W', 'dispersion': '45deg', 'weather_rated': True},
            'price': 95.00
        },
    ],
    'DataNetwork': [
        {
            'type': 'Switch',
            'manufacturer': 'Cisco',
            'model': 'Cat2960-X',
            'specs': {'ports': 48, 'poe': True, 'speed': '1Gbps', 'layer': 2},
            'price': 1800.00
        },
        {
            'type': 'Access Point',
            'manufacturer': 'Ubiquiti',
            'model': 'UAP-AC-PRO',
            'specs': {'wifi': '802.11ac', 'speed': '1300Mbps', 'range': '122m'},
            'price': 149.00
        },
        {
            'type': 'Router',
            'manufacturer': 'HP',
            'model': 'MSR3104',
            'specs': {'ports': 4, 'firewall': True, 'vpn': True, 'throughput': '2Gbps'},
            'price': 2200.00
        },
        {
            'type': 'Patch Panel',
            'manufacturer': 'Panduit',
            'model': 'CPP24WMWB',
            'specs': {'ports': 24, 'cat': '6A', 'shielded': True},
            'price': 185.00
        },
    ],
    'Lighting': [
        {
            'type': 'LED Panel',
            'manufacturer': 'Philips',
            'model': 'RC065B LED60S',
            'specs': {'wattage': '60W', 'cct': '4000K', 'lumen': '6000', 'dim': 'DALI'},
            'price': 125.00
        },
        {
            'type': 'Emergency Light',
            'manufacturer': 'Sylvania',
            'model': 'EFIX 3W',
            'specs': {'wattage': '3W', 'duration': '3hrs', 'lumens': '300'},
            'price': 35.00
        },
        {
            'type': 'Occupancy Sensor',
            'manufacturer': ' Schneider',
            'model': 'ODFCACT',
            'specs': {'type': 'PIR', 'range': '8m', 'mounting': 'Ceiling', 'dali': True},
            'price': 55.00
        },
        {
            'type': 'Exit Sign',
            'manufacturer': 'R. STAHL',
            'model': '146 271',
            'specs': {'wattage': '3W', 'duration': '8hrs', 'mounting': 'Wall/Ceiling'},
            'price': 85.00
        },
    ],
    'Power': [
        {
            'type': 'Distribution Board',
            'manufacturer': 'Schneider',
            'model': 'Prisma P',
            'specs': {'rated_current': '125A', 'modules': 36, 'ip': '65'},
            'price': 450.00
        },
        {
            'type': 'MCB',
            'manufacturer': 'ABB',
            'model': 'S201',
            'specs': {'current': '10A', 'curve': 'C', 'poles': '1P', 'breaking': '6kA'},
            'price': 12.00
        },
        {
            'type': 'RCCB',
            'manufacturer': 'Schneider',
            'model': 'iID',
            'specs': {'current': '40A', 'sensitivity': '30mA', 'poles': '2P', 'type': 'A'},
            'price': 45.00
        },
        {
            'type': 'UPS',
            'manufacturer': 'Eaton',
            'model': '9PX 3000',
            'specs': {'power': '3000VA', 'topology': 'Online Double Conv', 'runtime': '15min'},
            'price': 2800.00
        },
    ],
}


def seed_manufacturer_catalogs(session):
    """
    Insert manufacturer catalog data.
    
    Args:
        session: SQLAlchemy session
        
    Returns:
        Number of catalog items inserted
    """
    logger.info("Seeding manufacturer catalogs...")
    
    count = 0
    
    # Ensure ManufacturerCatalog table exists
    try:
        Base.metadata.create_all(session.get_bind())
    except Exception as e:
        logger.warning(f"  Could not create ManufacturerCatalog table: {e}")
    
    for domain_name, products in MANUFACTURER_CATALOG.items():
        # Get domain ID
        domain = session.query(ProjectDomain).filter(
            ProjectDomain.DomainName == domain_name
        ).first()
        
        if not domain:
            logger.warning(f"  Domain not found: {domain_name}")
            continue
        
        for product in products:
            # Get device type ID
            device_type = session.query(DeviceType).filter(
                DeviceType.TypeName == product['type'],
                DeviceType.DomainID == domain.DomainID
            ).first()
            
            if not device_type:
                logger.warning(f"  Device type not found: {product['type']} in {domain_name}")
                continue
            
            # Check if exists
            existing = session.query(ManufacturerCatalog).filter(
                ManufacturerCatalog.ManufacturerName == product['manufacturer'],
                ManufacturerCatalog.Model == product['model'],
                ManufacturerCatalog.DeviceTypeID == device_type.DeviceTypeID
            ).first()
            
            if not existing:
                catalog = ManufacturerCatalog(
                    DeviceTypeID=device_type.DeviceTypeID,
                    ManufacturerName=product['manufacturer'],
                    Model=product['model'],
                    Specifications=product['specs'],
                    UnitPrice=product.get('price', 0),
                    Currency='USD'
                )
                session.add(catalog)
                count += 1
                logger.debug(f"  Added: {product['manufacturer']} {product['model']}")
    
    session.commit()
    logger.info(f"  Catalog items inserted: {count}")
    return count


# =============================================================================
# Main Seeding Function
# =============================================================================

def seed_all(session):
    """
    Run all seeding functions in order.
    
    Args:
        session: SQLAlchemy session
        
    Returns:
        Dict with counts
    """
    logger.info("="*60)
    logger.info("STARTING DATABASE SEEDING")
    logger.info("="*60)
    
    counts = {}
    
    try:
        counts['domains'] = seed_domains(session)
        counts['device_types'] = seed_device_types(session)
        counts['standards'] = seed_design_standards(session)
        counts['catalogs'] = seed_manufacturer_catalogs(session)
        counts['route_nodes'] = seed_route_network(session)

        logger.info("="*60)
        logger.info("SEEDING COMPLETE")
        logger.info("="*60)
        logger.info(f"  Domains: {counts['domains']}")
        logger.info(f"  Device Types: {counts['device_types']}")
        logger.info(f"  Standards: {counts['standards']}")
        logger.info(f"  Catalog Items: {counts['catalogs']}")
        logger.info(f"  Route Nodes: {counts['route_nodes']}")
        
        return counts
        
    except Exception as e:
        logger.error(f"Error during seeding: {e}")
        session.rollback()
        raise


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    # Get database URL
    db_url = os.environ.get('DATABASE_URL')
    
    if not db_url:
        print("Error: DATABASE_URL environment variable not set")
        print("Usage: DATABASE_URL=postgresql://user:pass@host/db python seed_all_domains.py")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("DATABASE SEEDING FOR MULTI-DOMAIN ENGINEERING PLATFORM")
    print("="*60)
    print(f"Database: {db_url.split('@')[1] if '@' in db_url else 'local'}")
    print("="*60 + "\n")
    
    # Create engine and session
    engine = create_engine(db_url, pool_pre_ping=True)
    
    # Create tables
    try:
        Base.metadata.create_all(engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.warning(f"Could not create tables: {e}")
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Run seeding
        counts = seed_all(session)
        
        print("\n" + "="*60)
        print("✅ SEEDING COMPLETED SUCCESSFULLY")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ SEEDING FAILED: {e}")
        sys.exit(1)
    
    finally:
        session.close()