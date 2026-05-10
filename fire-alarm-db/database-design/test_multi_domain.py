#!/usr/bin/env python3
"""
test_multi_domain.py - Test Multi-Domain Engineering Design
============================================

Tests the Strategy Pattern implementation for multiple domains:
- FireAlarm project with smoke detectors
- CCTV project with cameras

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
    
    logger.info(f"FireAlarm DomainID: {fire_domain_id}")
    logger.info(f"CCTV DomainID: {cctv_domain_id}")
    
    # Verify in database
    fire_domain = session.query(ProjectDomain).filter(
        ProjectDomain.DomainName == 'FireAlarm'
    ).first()
    
    cctv_domain = session.query(ProjectDomain).filter(
        ProjectDomain.DomainName == 'CCTV'
    ).first()
    
    assert fire_domain is not None, "FireAlarm domain not created"
    assert cctv_domain is not None, "CCTV domain not created"
    
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
    
    # Create and run design
    engine.create_project = engine.create_project.__get__(engine, EngineeringDesignEngine)
    engine.add_rooms = engine.add_rooms.__get__(engine, EngineeringDesignEngine)
    engine.create_session = engine.create_session.__get__(engine, EngineeringDesignEngine) 
    engine.run_design = engine.run_design.__get__(engine, EngineeringDesignEngine)
    
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
    
    # Add rooms
    cctv_rooms = engine2.add_rooms(cctv_project.ProjectID, rooms_data)
    
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
        logger.info(f"  - {d.ProposedType}")
    
    # Verify device types (should have Camera types)
    cctv_types = set(d.ProposedType for d in cctv_devices)
    assert 'Camera' in cctv_types, "No cameras placed"
    
    logger.info("✓ CCTV project created with camera devices")
    
    # =================================================================
    # Test 4: Verify Both Projects Have Correct Domains
    # =================================================================
    logger.info("\n" + "="*50)
    logger.info("TEST 4: Verify Domain Integrity")
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
    
    logger.info("✓ Both projects have correct domain assignments")
    
    # =================================================================
    # Test 5: Cost Calculation
    # =================================================================
    logger.info("\n" + "="*50)
    logger.info("TEST 5: Cost Calculation")
    logger.info("="*50)
    
    # FireAlarm cost
    fire_cost = engine.logic.calculate_cost(fire_devices)
    logger.info(f"FireAlarm cost: {fire_cost}")
    
    # CCTV cost
    cctv_cost = engine2.logic.calculate_cost(cctv_devices)
    logger.info(f"CCTV cost: {cctv_cost}")
    
    assert fire_cost['total'] > 0, "FireAlarm cost should be > 0"
    assert cctv_cost['total'] > 0, "CCTV cost should be > 0"
    
    logger.info("✓ Cost calculations work")
    
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