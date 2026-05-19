#!/usr/bin/env python3
"""
rule_checker.py - Self-Review Module for Cable Routing
==================================================

This module validates cable routing against physical and electrical constraints:
- Loop length limits
- Voltage drop calculations
- Device count per loop
- Fire wall penetration warnings

Author: FireAlarmAI Engineering Team
Date: 2026-05-09
"""

import os
import sys
import json
import logging
import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Validation Result Data Classes
# =============================================================================

@dataclass
class ValidationResult:
    """Result of a validation check"""
    passed: bool
    check_name: str
    message: str
    details: Dict = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


# =============================================================================
# Routing Validator
# =============================================================================

class RoutingValidator:
    """
    Self-Review Module for Cable Routing
    
    Validates routing against:
    - Maximum loop length (NFPA 72 default: 2000m for SLC)
    - Voltage drop (max 10% for nominal 24V system)
    - Maximum devices per loop (250 for SLC)
    - Fire wall penetration detection
    """
    
    # Standard thresholds
    DEFAULT_MAX_LOOP_LENGTH = 2000  # meters (NFPA 72 SLC)
    DEFAULT_MAX_VOLTAGE_DROP = 0.10  # 10% of nominal
    DEFAULT_MAX_DEVICES_PER_LOOP = 250
    DEFAULT_PANEL_VOLTAGE = 24.0  # Volts
    
    # Wire gauge resistance (ohms per 1000ft)
    WIRE_RESISTANCE = {
        22: 16.0,
        20: 10.0,
        18: 6.4,
        16: 4.0,
        14: 2.5,
        12: 1.6,
        10: 1.0,
    }
    
    # Device typical current draw (amps)
    DEVICE_CURRENT_DRAW = {
        'SmokeDetector': 0.0001,  # 100µA standby
        'HeatDetector': 0.0001,
        'ManualCallPoint': 0.0001,
        'Speaker': 0.05,  # 50mA at rated
        'Horn': 0.10,    # 100mA
        'Strobe': 0.15,  # 150mA
        'Panel': 0.0,    # Power source
    }
    
    def __init__(self, 
                max_loop_length: float = DEFAULT_MAX_LOOP_LENGTH,
                max_voltage_drop: float = DEFAULT_MAX_VOLTAGE_DROP,
                max_devices: int = DEFAULT_MAX_DEVICES_PER_LOOP):
        self.max_loop_length = max_loop_length
        self.max_voltage_drop = max_voltage_drop
        self.max_devices = max_devices
        logger.info(f"RoutingValidator initialized")
        logger.info(f"  Max loop length: {max_loop_length}m")
        logger.info(f"  Max voltage drop: {max_voltage_drop*100}%")
        logger.info(f"  Max devices: {max_devices}")
    
    def check_loop_length(self, 
                          connections: List[Dict],
                          max_length: float = None) -> ValidationResult:
        """
        Check if total loop length is within limits
        
        Args:
            connections: List of device connection dicts with 'total_length'
            max_length: Maximum allowed length (default: self.max_loop_length)
            
        Returns:
            ValidationResult
        """
        max_len = max_length or self.max_loop_length
        
        total = sum(
            c.get('total_length', c.get('CalculatedLength', 0))
            for c in connections
        )
        
        passed = total <= max_len
        
        return ValidationResult(
            passed=passed,
            check_name="Loop Length",
            message=f"Total length {total:.1f}m {'within' if passed else 'exceeds'} limit {max_len}m",
            details={
                'total_length': total,
                'max_length': max_len,
                'margin': max_len - total if passed else None,
                'excess': total - max_len if not passed else None
            }
        )
    
    def check_voltage_drop(self,
                        connections: List[Dict],
                        wire_gauge: int = 18,
                        panel_voltage: float = DEFAULT_PANEL_VOLTAGE) -> ValidationResult:
        """
        Check voltage drop along the loop
        
        Uses simple formula: V_drop = I * R * L
        where:
        - I = total current draw
        - R = resistance per length (from wire gauge table)
        - L = total loop length in thousands of feet
        
        Args:
            connections: List of device connections with device info
            wire_gauge: Wire gauge (AWG)
            panel_voltage: Panel nominal voltage
            
        Returns:
            ValidationResult
        """
        # Get wire resistance (ohms per 1000ft)
        resistance = self.WIRE_RESISTANCE.get(wire_gauge, 6.4)
        
        # Get total loop length in feet
        total_length_m = sum(
            c.get('total_length', c.get('CalculatedLength', 0))
            for c in connections
        )
        total_length_ft = total_length_m * 3.28084  # Convert to feet
        
        # Calculate total current
        total_current = 0
        for conn in connections:
            dev_type = conn.get('device_type', 'SmokeDetector')
            current = self.DEVICE_CURRENT_DRAW.get(dev_type, 0.0001)
            total_current += current
        
        # Voltage drop calculation
        # V_drop = I * (R/1000) * (L/1000) converted to metric
        length_kft = total_length_ft / 1000
        voltage_drop = total_current * resistance * length_kft
        
        drop_percent = voltage_drop / panel_voltage
        passed = drop_percent <= self.max_voltage_drop
        
        return ValidationResult(
            passed=passed,
            check_name="Voltage Drop",
            message=f"Voltage drop {voltage_drop:.2f}V ({drop_percent*100:.1f%}) {'within' if passed else 'exceeds'} limit",
            details={
                'voltage_drop': voltage_drop,
                'drop_percent': drop_percent,
                'max_percent': self.max_voltage_drop,
                'total_current': total_current,
                'wire_gauge': wire_gauge,
                'resistance_ohm_per_kft': resistance,
                'loop_length_m': total_length_m,
                'loop_length_ft': total_length_ft
            }
        )
    
    def check_device_count_per_loop(self,
                              loop_id: int,
                              device_count: int = None,
                              max_devices: int = None) -> ValidationResult:
        """
        Check if device count on loop is within limits
        
        Args:
            loop_id: Loop ID for logging
            device_count: Number of devices on loop
            max_devices: Maximum allowed (default: self.max_devices)
            
        Returns:
            ValidationResult
        """
        max_devs = max_devices or self.max_devices
        
        passed = device_count <= max_devs
        
        return ValidationResult(
            passed=passed,
            check_name="Device Count",
            message=f"Loop {loop_id}: {device_count} devices {'within' if passed else 'exceeds'} limit {max_devs}",
            details={
                'loop_id': loop_id,
                'device_count': device_count,
                'max_devices': max_devs,
                'margin': max_devs - device_count if passed else None,
                'excess': device_count - max_devs if not passed else None
            }
        )
    
    def check_fire_wall_penetration(self,
                                path_segments: List[Dict]) -> ValidationResult:
        """
        Check if path passes through fire walls
        
        Args:
            path_segments: List of segment dicts with 'segment_type' or 'segment_type'
            
        Returns:
            ValidationResult
        """
        fire_wall_segments = []
        
        for seg in path_segments:
            seg_type = seg.get('segment_type', seg.get('type', 'unknown'))
            if seg_type == 'FireWall':
                fire_wall_segments.append(seg)
        
        passed = len(fire_wall_segments) == 0
        
        return ValidationResult(
            passed=passed,
            check_name="Fire Wall Penetration",
            message=f"{'No' if passed else f'{len(fire_wall_segments)}'} fire wall penetrations detected",
            details={
                'count': len(fire_wall_segments),
                'penetrations': fire_wall_segments
            }
        )
    
    def check_all(self,
               connections: List[Dict],
               loop_id: int = 1,
               wire_gauge: int = 18,
               panel_voltage: float = DEFAULT_PANEL_VOLTAGE) -> Dict:
        """
        Run all validation checks
        
        Args:
            connections: List of device connections
            loop_id: Loop ID for logging
            wire_gauge: Wire gauge for voltage drop
            panel_voltage: Panel voltage
            
        Returns:
            Dict with all validation results
        """
        results = {
            'loop_id': loop_id,
            'checks': {}
        }
        
        # Extract path segments
        all_segments = []
        for conn in connections:
            segments = conn.get('segments', [])
            all_segments.extend(segments)
        
        # Run checks
        results['checks']['loop_length'] = self.check_loop_length(connections)
        results['checks']['voltage_drop'] = self.check_voltage_drop(connections, wire_gauge, panel_voltage)
        results['checks']['device_count'] = self.check_device_count_per_loop(
            loop_id, len(connections)
        )
        results['checks']['fire_wall'] = self.check_fire_wall_penetration(all_segments)
        
        # Summary
        all_passed = all(r.passed for r in results['checks'].values())
        results['passed'] = all_passed
        results['summary'] = f"{sum(1 for r in results['checks'].values() if r.passed)}/{len(results['checks'])} checks passed"
        
        # Warnings list
        results['warnings'] = [
            r.message for r in results['checks'].values() if not r.passed
        ]
        
        return results


# =============================================================================
# Integration with Pipeline
# =============================================================================

def validate_routing_results(connections: List[Dict],
                            loop_id: int = 1) -> Dict:
    """
    Validate routing results from pipeline
    
    This function is called by ai_design_pipeline.py after routing
    
    Args:
        connections: List of DeviceConnection dicts
        loop_id: Loop ID
        
    Returns:
        Dict with validation results
    """
    validator = RoutingValidator()
    
    # Convert to validation format
    conn_dicts = []
    for conn in connections:
        conn_dicts.append({
            'device_id': conn.get('DeviceID'),
            'device_type': conn.get('DeviceType'),
            'total_length': conn.get('CalculatedLength', 0),
            'segments': json.loads(conn.get('PolylinePath', '[]'))
        })
    
    # Run all checks
    results = validator.check_all(conn_dicts, loop_id)
    
    # Log results
    if results['passed']:
        logger.info(f"Loop {loop_id}: All validations passed")
    else:
        logger.warning(f"Loop {loop_id}: Validation failures: {results['warnings']}")
    
    return results


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Routing Validator")
    parser.add_argument('--loop-length', type=float, default=1800)
    parser.add_argument('--wire-gauge', type=int, default=18)
    parser.add_argument('--panel-voltage', type=float, default=24.0)
    parser.add_argument('--device-count', type=int, default=200)
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("ROUTING VALIDATOR TEST")
    print("="*60)
    
    validator = RoutingValidator()
    
    # Test connections
    connections = [
        {'device_id': 1, 'device_type': 'SmokeDetector', 'total_length': 500},
        {'device_id': 2, 'device_type': 'Speaker', 'total_length': 600},
        {'device_id': 3, 'device_type': 'HeatDetector', 'total_length': 700},
    ]
    
    # Test loop length
    result = validator.check_loop_length(connections, args.loop_length)
    print(f"\n1. Loop Length Check:")
    print(f"   {result.message}")
    
    # Test voltage drop
    result = validator.check_voltage_drop(connections, args.wire_gauge, args.panel_voltage)
    print(f"\n2. Voltage Drop Check:")
    print(f"   {result.message}")
    
    # Test device count
    result = validator.check_device_count_per_loop(1, args.device_count)
    print(f"\n3. Device Count Check:")
    print(f"   {result.message}")
    
    # Test fire wall
    segments = [
        {'from_node': 1, 'to_node': 2, 'segment_type': 'CableTray'},
        {'from_node': 2, 'to_node': 3, 'segment_type': 'FireWall'},
    ]
    result = validator.check_fire_wall_penetration(segments)
    print(f"\n4. Fire Wall Check:")
    print(f"   {result.message}")
    
    # All checks
    all_results = validator.check_all(connections, 1, args.wire_gauge, args.panel_voltage)
    print(f"\n{'='*60}")
    print(f"SUMMARY: {all_results['summary']}")
    if all_results['warnings']:
        print(f"WARNINGS: {all_results['warnings']}")