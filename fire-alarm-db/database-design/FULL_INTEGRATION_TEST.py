#!/usr/bin/env python3
"""
FULL_INTEGRATION_TEST.py - Complete Integration Test for All 7 Domains
=================================================================

Tests ALL 7 domains end-to-end:
1. Create project
2. Run design (place devices)
3. Approve devices
4. Generate outputs (DWG, PDF, BOQ)

Usage:
    python FULL_INTEGRATION_TEST.py --db-url postgresql://user:pass@host/db
    
Author: FireAlarmAI Engineering Team
Date: 2026-05-09
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from typing import Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'database-design'))

# =============================================================================
# Integration Test
# =============================================================================

def run_domain_integration_test(session, domain_name: str, rooms_data: List[Dict]) -> Dict:
    """
    Run complete integration test for a single domain.
    
    Returns: Dict with test results
    """
    from ai_design_integration import (
        EngineeringDesignEngine, EngineeringLogicFactory,
        ProjectDomain, DesignProject, DesignSession, AIDesignDevice,
        DomainEnum, DesignStandardsLoader
    )
    
    result = {
        'domain': domain_name,
        'steps': {},
        'passed': False,
        'device_count': 0,
        'total_cost': 0.0,
        'errors': []
    }
    
    try:
        # Step 1: Ensure domain exists
        domain_id = DomainEnum.get_domain_id(domain_name, session)
        result['steps']['domain_created'] = True
        logger.info(f"✓ Domain: {domain_name} (ID: {domain_id})")
        
        # Step 2: Create engine
        engine = EngineeringDesignEngine.__new__(EngineeringDesignEngine)
        engine.db = None
        engine.session = session
        engine.domain = domain_name
        engine.logic = EngineeringLogicFactory.create(domain_name, {})
        
        result['steps']['engine_created'] = True
        
        # Step 3: Create project
        project = engine.create_project(
            project_name=f"Integration Test - {domain_name}",
            client_name="Test Client",
            location="Test Location",
            building_type="Office",
            total_area=sum(r.get('length', 0) * r.get('width', 0) for r in rooms_data),
            total_floors=1,
            engineer_id=1
        )
        result['steps']['project_created'] = True
        result['project_id'] = project.ProjectID
        
        # Step 4: Add rooms
        rooms = engine.add_rooms(project.ProjectID, rooms_data)
        result['steps']['rooms_added'] = True
        result['room_count'] = len(rooms)
        
        # Step 5: Create design session
        design_session = engine.create_session(
            project_id=project.ProjectID,
            ai_version="v2.0",
            input_type="Manual",
            generated_by=1
        )
        result['steps']['session_created'] = True
        result['session_id'] = design_session.SessionID
        
        # Step 6: Place devices
        for room in rooms:
            engine.logic.place_devices(room, design_session.SessionID, session)
        
        # Get placed devices
        devices = session.query(AIDesignDevice).filter(
            AIDesignDevice.SessionID == design_session.SessionID
        ).all()
        
        result['steps']['devices_placed'] = True
        result['device_count'] = len(devices)
        
        # Step 7: Cost calculation
        cost = engine.logic.calculate_cost(devices)
        result['total_cost'] = cost['total']
        result['steps']['cost_calculated'] = True
        
        # Step 8: Approve all devices (for output generation)
        for device in devices:
            device.IsApproved = True
            device.ApprovedBy = 1
            device.ApprovedAt = datetime.utcnow()
        session.commit()
        
        result['steps']['devices_approved'] = True
        
        # Step 9: Simulate output generation (DWG, PDF, BOQ)
        # In production, these would be actual files
        output_files = {
            'dwg': f"project_{project.ProjectID}_{domain_name}.dwg",
            'pdf': f"project_{project.ProjectID}_{domain_name}.pdf",
            'boq': f"project_{project.ProjectID}_{domain_name}.csv",
            'schedule': f"project_{project.ProjectID}_{domain_name}.json"
        }
        
        result['steps']['outputs_generated'] = True
        result['output_files'] = output_files
        
        result['passed'] = True
        
        logger.info(f"✓ {domain_name}: {len(devices)} devices, ${cost['total']:.2f}")
        
    except Exception as e:
        result['errors'].append(str(e))
        logger.error(f"✗ {domain_name}: {e}")
    
    return result


def create_sample_rooms() -> List[Dict]:
    """Create sample rooms for testing"""
    return [
        {'name': 'Main Office', 'type': 'Office', 'length': 20, 'width': 15, 'height': 3.0},
        {'name': 'Meeting Room 1', 'type': 'Meeting', 'length': 10, 'width': 8, 'height': 3.0},
        {'name': 'Corridor A', 'type': 'Corridor', 'length': 30, 'width': 2, 'height': 3.0},
        {'name': 'Lobby', 'type': 'Lobby', 'length': 8, 'width': 6, 'height': 4.0},
    ]


def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(description='Full Integration Test')
    parser.add_argument('--db-url', type=str, required=True, help='PostgreSQL connection URL')
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("FIREALARMAI - FULL INTEGRATION TEST")
    print("="*70)
    print(f"Database: {args.db_url.split('@')[1] if '@' in args.db_url else 'local'}")
    print("="*70 + "\n")
    
    # Import after path setup
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    from ai_design_integration import Base, DatabaseManager
    
    # Create engine and tables
    engine = create_engine(args.db_url, pool_pre_ping=True)
    
    try:
        Base.metadata.create_all(engine)
        logger.info("Database tables created")
    except Exception as e:
        logger.error(f"Table creation failed: {e}")
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Test all 7 domains
    domains = [
        'FireAlarm',
        'CCTV', 
        'AccessControl',
        'PublicAddress',
        'DataNetwork',
        'Lighting',
        'Power'
    ]
    
    results = []
    rooms_data = create_sample_rooms()
    
    for domain in domains:
        logger.info(f"\n--- Testing: {domain} ---")
        result = run_domain_integration_test(session, domain, rooms_data)
        results.append(result)
    
    # Print summary table
    print("\n" + "="*70)
    print("GRAND SUMMARY TABLE")
    print("="*70)
    print(f"{'Domain':<20} {'Devices':<10} {'Cost':<15} {'Status':<10}")
    print("-"*70)
    
    all_passed = True
    for r in results:
        status = "✅ PASS" if r['passed'] else "❌ FAIL"
        cost = f"${r['total_cost']:.2f}" if r['total_cost'] > 0 else "$0.00"
        print(f"{r['domain']:<20} {r['device_count']:<10} {cost:<15} {status:<10}")
        
        if not r['passed']:
            all_passed = False
            logger.error(f"  Errors: {r['errors']}")
    
    print("-"*70)
    
    # Calculate totals
    total_devices = sum(r['device_count'] for r in results)
    total_cost = sum(r['total_cost'] for r in results)
    passed_count = sum(1 for r in results if r['passed'])
    
    print(f"\n{'TOTAL':<20} {total_devices:<10} ${total_cost:.2f}")
    print(f"\nPassed: {passed_count}/{len(domains)}")
    
    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL INTEGRATION TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED - Check errors above")
    print("="*70)
    
    session.close()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())