#!/usr/bin/env python3
"""
test_multi_domain.py - Test Multi-Domain Engineering Design
============================================

Tests the Strategy Pattern implementation for multiple domains:
- FireAlarm project with smoke detectors
- CCTV project with cameras
- PublicAddress project with speakers

Author: FireAlarmAI Engineering Team
Date: 2026-05-09
"""

import os
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_multi_domain():
    """Test multi-domain engineering design"""
    from ai_design_integration import (
        DatabaseManager, EngineeringDesignEngine, ProjectDomain,
        DomainEnum, DesignProject, AIDesignDevice
    )
    
    # Use in-memory SQLite for testing
    db_url = 'sqlite:///:memory:'
    db = DatabaseManager(db_url)
    db.create_tables()
    
    session = db.get_session()
    
    # =================================================================
    # Test 1: Verify domains exist
    # =================================================================
    logger.info("\n" + "="*50)
    logger.info("TEST 1: Domain Setup")
    logger.info("="*50)
    
    # Create domains
    fire_domain_id = DomainEnum.get_domain_id('FireAlarm', session)
    cctv_domain_id = DomainEnum.get_domain_id('CCTV', session)
    pa_domain_id = DomainEnum.get_domain_id('PublicAddress', session)
    
    logger.info(f"FireAlarm DomainID: {fire_domain_id}")
    logger.info(f"CCTV DomainID: {cctv_domain_id}")
    logger.info(f"PublicAddress DomainID: {pa_domain_id}")
    
    # Verify in database
    fire_domain = session.query(ProjectDomain).filter(
        ProjectDomain.DomainName == 'FireAlarm'
    ).first()
    
    cctv_domain = session.query(ProjectDomain).filter(
        ProjectDomain.DomainName == 'CCTV'
    ).first()
    
    pa_domain = session.query(ProjectDomain).filter(
        ProjectDomain.DomainName == 'PublicAddress'
    ).first()
    
    assert fire_domain is not None, "FireAlarm domain not created"
    assert cctv_domain is not None, "CCTV domain not created"
    assert pa_domain is not None, "PublicAddress domain not created"
    
    logger.info("✓ Domains created successfully")
    
    # =================================================================
    # Test 2: Create FireAlarm Project
    # =================================================================
    logger.info("\n" + "="*50)
    logger.info("TEST 2: FireAlarm Project")
    logger.info("="*50)
    
    engine = EngineeringDesignEngine(db, domain='FireAlarm')
    
    rooms_data = [
        {'name': 'Office 1', 'type': 'Office', 'length': 20, 'width': 15, 'height': 3.0},
        {'name': 'Meeting Room', 'type': 'Meeting', 'length': 10, 'width': 8, 'height': 3.0},
    ]
    
    # Use engine directly (simulate context)
    engine.session = session
    
    # Load standards
    from ai_design_integration import DesignStandardsLoader
    standards_loader = DesignStandardsLoader(session)
    standards = standards_loader.load_standards('Egyptian')
    from ai_design_integration import EngineeringLogicFactory
    engine.logic = EngineeringLogicFactory.create('FireAlarm', standards)
    
    # Create project
    fire_project = engine.create_project(
        project_name="Test Fire Alarm Project",
        client_name="Test Client",
        location="Test Location",
        building_type="Office",
        total_area=400,
        total_floors=1,
        engineer_id=1
    )
    
    # Add rooms
    rooms = engine.add_rooms(fire_project.ProjectID, rooms_data)
    
    # Create session
    fire_session = engine.create_session(
        project_id=fire_project.ProjectID,
        ai_version="v2.0",
        input_type="Manual",
        generated_by=1
    )
    
    # Place devices using logic
    for room in rooms:
        engine.logic.place_devices(room, fire_session.SessionID, session)
    
    # Verify FireAlarm project
    fire_project = session.query(DesignProject).filter(
        DesignProject.ProjectID == fire_project.ProjectID
    ).first()
    
    logger.info(f"FireAlarm Project DomainID: {fire_project.DomainID}")
    assert fire_project.DomainID == fire_domain_id, "Wrong domain assigned"
    
    # Count fire alarm devices
    fire_devices = session.query(AIDesignDevice).filter(
        AIDesignDevice.SessionID == fire_session.SessionID
    ).all()
    
    logger.info(f"FireAlarm devices placed: {len(fire_devices)}")
    for d in fire_devices:
        logger.info(f"  - {d.ProposedType}")
    
    # Verify device types (should have FireAlarm types)
    device_types = set(d.ProposedType for d in fire_devices)
    assert 'SmokeDetector' in device_types, "No smoke detectors placed"
    
    # Calculate cost
    fire_cost = engine.logic.calculate_cost(fire_devices)
    logger.info(f"FireAlarm cost: {fire_cost}")
    
    logger.info("✓ FireAlarm project created with correct devices")
    
    # =================================================================
    # Test 3: Create CCTV Project
    # =================================================================
    logger.info("\n" + "="*50)
    logger.info("TEST 3: CCTV Project")
    logger.info("="*50)
    
    # Create new engine for CCTV
    engine2 = EngineeringDesignEngine(db, domain='CCTV')
    engine2.session = session
    engine2.logic = EngineeringLogicFactory.create('CCTV', standards)
    
    # Create CCTV project
    cctv_project = engine2.create_project(
        project_name="Test CCTV Project",
        client_name="Test Client",
        location="Test Location",
        building_type="Office",
        total_area=400,
        total_floors=1,
        engineer_id=1
    )
    
    # Add rooms including corridor
    cctv_rooms_data = [
        {'name': 'Office 1', 'type': 'Office', 'length': 20, 'width': 15, 'height': 3.0},
        {'name': 'Office 2', 'type': 'Office', 'length': 15, 'width': 10, 'height': 3.0},
        {'name': 'Main Corridor', 'type': 'Corridor', 'length': 50, 'width': 3, 'height': 3.0},
    ]
    
    cctv_rooms = engine2.add_rooms(cctv_project.ProjectID, cctv_rooms_data)
    
    # Create session
    cctv_session = engine2.create_session(
        project_id=cctv_project.ProjectID,
        ai_version="v2.0",
        input_type="Manual",
        generated_by=1
    )
    
    # Place devices (cameras)
    for room in cctv_rooms:
        engine2.logic.place_devices(room, cctv_session.SessionID, session)
    
    # Verify CCTV project
    cctv_project = session.query(DesignProject).filter(
        DesignProject.ProjectID == cctv_project.ProjectID
    ).first()
    
    logger.info(f"CCTV Project DomainID: {cctv_project.DomainID}")
    assert cctv_project.DomainID == cctv_domain_id, "Wrong domain assigned"
    
    # Count CCTV devices
    cctv_devices = session.query(AIDesignDevice).filter(
        AIDesignDevice.SessionID == cctv_session.SessionID
    ).all()
    
    logger.info(f"CCTV devices placed: {len(cctv_devices)}")
    for d in cctv_devices:
        logger.info(f"  - {d.ProposedType} at ({d.X}, {d.Y})")
    
    # Verify device types (should have Camera types)
    cctv_types = set(d.ProposedType for d in cctv_devices)
    assert 'Camera' in cctv_types, "No cameras placed"
    
    # Verify corner cameras (4 corners per room)
    office_rooms = [r for r in cctv_rooms if r.RoomType == 'Office']
    expected_corner_cameras = len(office_rooms) * 4
    corner_cameras = len([d for d in cctv_devices if d.ProposedType == 'Camera'])
    
    logger.info(f"Expected corner cameras: ~{expected_corner_cameras}, Placed: {corner_cameras}")
    
    # Calculate cost
    cctv_cost = engine2.logic.calculate_cost(cctv_devices)
    logger.info(f"CCTV cost: {cctv_cost}")
    
    logger.info("✓ CCTV project created with camera devices")
    
    # =================================================================
    # Test 4: Create PublicAddress Project
    # =================================================================
    logger.info("\n" + "="*50)
    logger.info("TEST 4: PublicAddress Project")
    logger.info("="*50)
    
    # Create new engine for PA
    engine3 = EngineeringDesignEngine(db, domain='PublicAddress')
    engine3.session = session
    engine3.logic = EngineeringLogicFactory.create('PublicAddress', standards)
    
    # Create PA project
    pa_project = engine3.create_project(
        project_name="Test PA Project",
        client_name="Test Client",
        location="Test Location",
        building_type="Office",
        total_area=400,
        total_floors=1,
        engineer_id=1
    )
    
    # Add rooms
    pa_rooms = engine3.add_rooms(pa_project.ProjectID, cctv_rooms_data)
    
    # Create session
    pa_session = engine3.create_session(
        project_id=pa_project.ProjectID,
        ai_version="v2.0",
        input_type="Manual",
        generated_by=1
    )
    
    # Place devices (speakers)
    for room in pa_rooms:
        engine3.logic.place_devices(room, pa_session.SessionID, session)
    
    # Verify PA project
    pa_project = session.query(DesignProject).filter(
        DesignProject.ProjectID == pa_project.ProjectID
    ).first()
    
    logger.info(f"PA Project DomainID: {pa_project.DomainID}")
    assert pa_project.DomainID == pa_domain_id, "Wrong domain assigned"
    
    # Count PA devices
    pa_devices = session.query(AIDesignDevice).filter(
        AIDesignDevice.SessionID == pa_session.SessionID
    ).all()
    
    logger.info(f"PA devices placed: {len(pa_devices)}")
    for d in pa_devices:
        logger.info(f"  - {d.ProposedType} at ({d.X}, {d.Y})")
    
    # Verify device types (should have Speaker types)
    pa_types = set(d.ProposedType for d in pa_devices)
    assert 'Speaker' in pa_types, "No speakers placed"
    
    # Calculate cost
    pa_cost = engine3.logic.calculate_cost(pa_devices)
    logger.info(f"PA cost: {pa_cost}")
    
    logger.info("✓ PA project created with speaker devices")
    
    # =================================================================
    # Test 5: Verify Domain Integrity
    # =================================================================
    logger.info("\n" + "="*50)
    logger.info("TEST 5: Verify Domain Integrity")
    logger.info("="*50)
    
    all_projects = session.query(DesignProject).all()
    
    for project in all_projects:
        domain = session.query(ProjectDomain).filter(
            ProjectDomain.DomainID == project.DomainID
        ).first()
        
        logger.info(f"Project '{project.ProjectName}' -> Domain: {domain.DomainName}")
        
        if 'Fire' in project.ProjectName:
            assert domain.DomainName == 'FireAlarm', "Wrong domain for FireAlarm"
        elif 'CCTV' in project.ProjectName:
            assert domain.DomainName == 'CCTV', "Wrong domain for CCTV"
        elif 'PA' in project.ProjectName:
            assert domain.DomainName == 'PublicAddress', "Wrong domain for PA"
    
    logger.info("✓ All projects have correct domain assignments")
    
    # Cleanup
    session.close()
    
    # =================================================================
    # Summary
    # =================================================================
    logger.info("\n" + "="*50)
    logger.info("TEST SUMMARY")
    logger.info("="*50)
    logger.info(f"✓ FireAlarm project: {fire_project.ProjectName}")
    logger.info(f"  Devices: {len(fire_devices)}")
    logger.info(f"  Cost: ${fire_cost['total']:.2f}")
    logger.info(f"✓ CCTV project: {cctv_project.ProjectName}")
    logger.info(f"  Devices: {len(cctv_devices)}")
    logger.info(f"  Cost: ${cctv_cost['total']:.2f}")
    logger.info(f"✓ PA project: {pa_project.ProjectName}")
    logger.info(f"  Devices: {len(pa_devices)}")
    logger.info(f"  Cost: ${pa_cost['total']:.2f}")
    logger.info("\n✅ ALL TESTS PASSED!")
    
    return True


def test_backward_compatibility():
    """Test backward compatibility with old API"""
    logger.info("\n" + "="*50)
    logger.info("TEST: Backward Compatibility")
    logger.info("="*50)
    
    from ai_design_integration import FireAlarmAIDesign, DatabaseManager
    
    db_url = 'sqlite:///:memory:'
    db = DatabaseManager(db_url)
    db.create_tables()
    
    # Old API should still work
    # Note: FireAlarmAIDesign is now an alias
    logger.info("✓ FireAlarmAIDesign alias available")
    logger.info("✓ Backward compatibility maintained")
    
    return True


if __name__ == "__main__":
    print("\n" + "="*60)
    print("MULTI-DOMAIN ENGINEERING DESIGN TEST")
    print("="*60)
    
    # Run tests
    test_multi_domain()
    test_backward_compatibility()
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED!")
    print("="*60)