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
sys.path.insert(0, '/workspace/project/revit/fire-alarm-db/database-design')
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
    
    # Relationships
    device_type = relationship("DeviceType", foreign_keys=[DeviceTypeID])


# =============================================================================
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
    """Insert project domains into database."""
    logger.info("Seeding domains...")
    count = 0
    for domain_data in DOMAINS:
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
    ],
    'CCTV': [
        {'name': 'IP Camera', 'description': 'Network IP Camera'},
        {'name': 'PTZ Camera', 'description': 'Pan-Tilt-Zoom Camera'},
        {'name': 'Dome Camera', 'description': 'Dome Style Camera'},
        {'name': 'Bullet Camera', 'description': 'Bullet Style Camera'},
        {'name': 'NVR', 'description': 'Network Video Recorder'},
        {'name': 'Video Encoder', 'description': 'Video Encoder'},
        {'name': 'Monitor', 'description': 'CCTV Monitor'},
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
    ],
    'DataNetwork': [
        {'name': 'Data Outlet', 'description': 'Network Data Outlet'},
        {'name': 'Patch Panel', 'description': 'Network Patch Panel'},
        {'name': 'Switch', 'description': 'Network Switch'},
        {'name': 'Router', 'description': 'Network Router'},
        {'name': 'Access Point', 'description': 'Wireless Access Point'},
        {'name': 'Rack', 'description': 'Server/Network Rack'},
    ],
    'Lighting': [
        {'name': 'LED Panel', 'description': 'LED Light Panel'},
        {'name': 'Downlight', 'description': 'LED Downlight'},
        {'name': 'Emergency Light', 'description': 'Emergency Lighting'},
        {'name': 'Exit Sign', 'description': 'Emergency Exit Sign'},
        {'name': 'Occupancy Sensor', 'description': 'Occupancy/Presence Sensor'},
        {'name': 'Dimmer', 'description': 'Light Dimmer Module'},
    ],
    'Power': [
        {'name': 'Socket Outlet', 'description': 'Power Socket Outlet'},
        {'name': 'Distribution Board', 'description': 'Electrical Distribution Board'},
        {'name': 'MCB', 'description': 'Miniature Circuit Breaker'},
        {'name': 'RCCB', 'description': 'Residual Current Circuit Breaker'},
        {'name': 'Busbar', 'description': 'Busbar System'},
        {'name': 'Transformer', 'description': 'Voltage Transformer'},
    ],
}


def seed_device_types(session):
    """Insert device types for each domain."""
    logger.info("Seeding device types...")
    count = 0
    for domain_name, types in DEVICE_TYPES.items():
        domain = session.query(ProjectDomain).filter(
            ProjectDomain.DomainName == domain_name
        ).first()
        if not domain:
            logger.warning(f"  Domain not found: {domain_name}")
            continue
        for type_data in types:
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
    session.commit()
    logger.info(f"  Device types inserted: {count}")
    return count


# =============================================================================
# Design Standards Seeding
# =============================================================================

DESIGN_STANDARDS = {
    'FireAlarm': [
        {'key': 'detector_spacing', 'value': '6.5', 'desc': 'Max detector spacing (m)'},
        {'key': 'max_area_per_detector', 'value': '40', 'desc': 'Max area per detector (m²)'},
        {'key': 'speaker_spacing', 'value': '6', 'desc': 'Max speaker spacing (m)'},
    ],
    'CCTV': [
        {'key': 'camera_height', 'value': '3.0', 'desc': 'Camera mounting height (m)'},
        {'key': 'min_lux', 'value': '0.5', 'desc': 'Minimum illumination (lux)'},
        {'key': 'max_camera_distance', 'value': '30', 'desc': 'Max cable distance (m)'},
        {'key': 'corridor_camera_spacing', 'value': '15', 'desc': 'Corridor camera spacing (m)'},
    ],
    'AccessControl': [
        {'key': 'reader_height', 'value': '1.2', 'desc': 'Reader mounting height (m)'},
        {'key': 'lock_holding_force', 'value': '500', 'desc': 'Lock holding force (kg)'},
        {'key': 'exit_button_height', 'value': '1.1', 'desc': 'Exit button height (m)'},
    ],
    'PublicAddress': [
        {'key': 'ceiling_speaker_spacing', 'value': '6', 'desc': 'Ceiling speaker spacing (m)'},
        {'key': 'min_spl', 'value': '85', 'desc': 'Min sound pressure (dB)'},
    ],
    'DataNetwork': [
        {'key': 'outlet_height', 'value': '0.3', 'desc': 'Outlet mounting height (m)'},
        {'key': 'max_cable_length', 'value': '90', 'desc': 'Max horizontal cable (m)'},
        {'key': 'ap_spacing', 'value': '15', 'desc': 'Access point spacing (m)'},
    ],
    'Lighting': [
        {'key': 'office_lux', 'value': '500', 'desc': 'Office illuminance (lux)'},
        {'key': 'corridor_lux', 'value': '150', 'desc': 'Corridor illuminance (lux)'},
        {'key': 'emergency_lux', 'value': '10', 'desc': 'Emergency lighting (lux)'},
    ],
    'Power': [
        {'key': 'socket_height', 'value': '0.3', 'desc': 'Socket outlet height (m)'},
        {'key': 'db_height', 'value': '1.5', 'desc': 'Distribution board height (m)'},
        {'key': 'voltage_drop_max', 'value': '3', 'desc': 'Max voltage drop (%)'},
    ],
}


def seed_design_standards(session):
    """Insert design standards for each domain."""
    logger.info("Seeding design standards...")
    count = 0
    for domain_name, standards in DESIGN_STANDARDS.items():
        domain = session.query(ProjectDomain).filter(
            ProjectDomain.DomainName == domain_name
        ).first()
        if not domain:
            continue
        for std in standards:
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
    session.commit()
    logger.info(f"  Standards inserted: {count}")
    return count


# =============================================================================
# Manufacturer Catalog Seeding
# =============================================================================

MANUFACTURER_CATALOG = {
    'CCTV': [
        {'type': 'IP Camera', 'manufacturer': 'Hikvision', 'model': 'DS-2CD2043G2', 'specs': {'resolution': '4MP', 'lens': '2.8mm'}, 'price': 180.00},
        {'type': 'IP Camera', 'manufacturer': 'Dahua', 'model': 'IPC-HFW2431S', 'specs': {'resolution': '4MP', 'ir_range': '30m'}, 'price': 165.00},
        {'type': 'PTZ Camera', 'manufacturer': 'Bosch', 'model': 'AUTODOME IP 5000i', 'specs': {'resolution': '1080p', 'zoom': '30x'}, 'price': 2200.00},
        {'type': 'NVR', 'manufacturer': 'Uniview', 'model': 'NVR301-04L', 'specs': {'channels': 4, 'resolution': '4K'}, 'price': 280.00},
    ],
    'AccessControl': [
        {'type': 'Card Reader', 'manufacturer': 'HID', 'model': 'iCLASS SE R40', 'specs': {'technology': 'iCLASS SE'}, 'price': 145.00},
        {'type': 'Biometric Reader', 'manufacturer': 'ZKTeco', 'model': 'C3-400', 'specs': {'capacity': 3000}, 'price': 280.00},
        {'type': 'Electric Lock', 'manufacturer': 'ASSA ABLOY', 'model': 'INOX 8800', 'specs': {'holding_force': '600kg'}, 'price': 195.00},
        {'type': 'Controller', 'manufacturer': 'HID', 'model': 'Edge ESPR40', 'specs': {'doors': 2}, 'price': 450.00},
    ],
    'PublicAddress': [
        {'type': 'Ceiling Speaker', 'manufacturer': 'Bosch', 'model': 'LBC 3081/41', 'specs': {'rating': '6W'}, 'price': 45.00},
        {'type': 'Wall Speaker', 'manufacturer': 'TOA', 'model': 'CS-304', 'specs': {'rating': '10W'}, 'price': 65.00},
        {'type': 'Amplifier', 'manufacturer': 'Bosch', 'model': 'PRA-AMP120', 'specs': {'output': '120W'}, 'price': 850.00},
    ],
    'DataNetwork': [
        {'type': 'Switch', 'manufacturer': 'Cisco', 'model': 'Cat2960-X', 'specs': {'ports': 48, 'poe': True}, 'price': 1800.00},
        {'type': 'Access Point', 'manufacturer': 'Ubiquiti', 'model': 'UAP-AC-PRO', 'specs': {'wifi': '802.11ac'}, 'price': 149.00},
        {'type': 'Router', 'manufacturer': 'HP', 'model': 'MSR3104', 'specs': {'firewall': True}, 'price': 2200.00},
    ],
    'Lighting': [
        {'type': 'LED Panel', 'manufacturer': 'Philips', 'model': 'RC065B LED60S', 'specs': {'wattage': '60W', 'lumen': 6000}, 'price': 125.00},
        {'type': 'Emergency Light', 'manufacturer': 'Sylvania', 'model': 'EFIX 3W', 'specs': {'duration': '3hrs'}, 'price': 35.00},
        {'type': 'Occupancy Sensor', 'manufacturer': 'Schneider', 'model': 'ODFCACT', 'specs': {'type': 'PIR'}, 'price': 55.00},
    ],
    'Power': [
        {'type': 'Distribution Board', 'manufacturer': 'Schneider', 'model': 'Prisma P', 'specs': {'rated_current': '125A'}, 'price': 450.00},
        {'type': 'MCB', 'manufacturer': 'ABB', 'model': 'S201', 'specs': {'current': '10A'}, 'price': 12.00},
        {'type': 'RCCB', 'manufacturer': 'Schneider', 'model': 'iID', 'specs': {'current': '40A'}, 'price': 45.00},
    ],
}


def seed_manufacturer_catalogs(session):
    """Insert manufacturer catalog data."""
    logger.info("Seeding manufacturer catalogs...")
    count = 0
    
    try:
        Base.metadata.create_all(session.get_bind())
    except:
        pass
    
    for domain_name, products in MANUFACTURER_CATALOG.items():
        domain = session.query(ProjectDomain).filter(
            ProjectDomain.DomainName == domain_name
        ).first()
        if not domain:
            continue
        for product in products:
            device_type = session.query(DeviceType).filter(
                DeviceType.TypeName == product['type'],
                DeviceType.DomainID == domain.DomainID
            ).first()
            if not device_type:
                continue
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
    session.commit()
    logger.info(f"  Catalog items inserted: {count}")
    return count


# =============================================================================
# Main Seeding Function
# =============================================================================

def seed_all(session):
    """Run all seeding functions in order."""
    logger.info("="*60)
    logger.info("STARTING DATABASE SEEDING")
    logger.info("="*60)
    
    counts = {}
    counts['domains'] = seed_domains(session)
    counts['device_types'] = seed_device_types(session)
    counts['standards'] = seed_design_standards(session)
    counts['catalogs'] = seed_manufacturer_catalogs(session)
    
    logger.info("="*60)
    logger.info("SEEDING COMPLETE")
    logger.info("="*60)
    logger.info(f"  Domains: {counts['domains']}")
    logger.info(f"  Device Types: {counts['device_types']}")
    logger.info(f"  Standards: {counts['standards']}")
    logger.info(f"  Catalog Items: {counts['catalogs']}")
    
    return counts


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
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
    
    engine = create_engine(db_url, pool_pre_ping=True)
    
    try:
        Base.metadata.create_all(engine)
    except Exception as e:
        logger.warning(f"Could not create tables: {e}")
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        counts = seed_all(session)
        print("\n" + "="*60)
        print("✅ SEEDING COMPLETED SUCCESSFULLY")
        print("="*60)
    except Exception as e:
        print(f"\n❌ SEEDING FAILED: {e}")
        sys.exit(1)
    finally:
        session.close()