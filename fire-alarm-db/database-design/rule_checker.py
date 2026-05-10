#!/usr/bin/env python3
"""
rule_checker.py - Routing Rule Validation for Cable Networks
==========================================================

Validates cable routing against design standards:
- Voltage drop calculations
- Loop length limits
- Device count per loop
- NFPA72, BS5839 compliance

Usage:
    from rule_checker import RoutingValidator
    validator = RoutingValidator(session)
    validator.load_standards_from_db()
    result = validator.check_voltage_drop(connection, source_voltage)
"""

import logging
from typing import Optional, Dict, List, Any, Tuple
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class RoutingValidator:
    """
    Validate cable routing against design standards.
    
    Loads standards from DesignStandard table and falls back to
    defaults if not found in database.
    """
    
    # Default values if DB standards not available
    DEFAULT_MAX_VOLTAGE_DROP_PERCENT = 10.0  # 10% max voltage drop
    DEFAULT_MAX_LOOP_LENGTH = 100.0  # meters
    DEFAULT_MAX_DEVICES_PER_LOOP = 25
    
    def __init__(self, session: Session):
        """
        Initialize validator with database session.
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
        
        # Standards values (loaded from DB or defaults)
        self.max_voltage_drop_percent = self.DEFAULT_MAX_VOLTAGE_DROP_PERCENT
        self.max_loop_length = self.DEFAULT_MAX_LOOP_LENGTH
        self.max_devices_per_loop = self.DEFAULT_MAX_DEVICES_PER_LOOP
        
        self._standards_loaded = False
    
    def load_standards_from_db(self, standard_name: str = 'international') -> bool:
        """
        Load routing standards from DesignStandard table.
        
        Args:
            standard_name: Standard name to load ('international', 'nfpa72', etc.)
            
        Returns:
            True if standards loaded successfully, False otherwise
        """
        try:
            from ai_design_integration import DesignStandard
            
            # Try to find international standards
            standard = self.session.query(DesignStandard).filter(
                DesignStandard.StandardName == standard_name
            ).first()
            
            if standard:
                # Parse specifications
                specs = standard.Specifications or {}
                
                self.max_voltage_drop_percent = specs.get(
                    'max_voltage_drop_percent',
                    self.DEFAULT_MAX_VOLTAGE_DROP_PERCENT
                )
                self.max_loop_length = specs.get(
                    'max_loop_length',
                    self.DEFAULT_MAX_LOOP_LENGTH
                )
                self.max_devices_per_loop = specs.get(
                    'max_devices_per_loop',
                    self.DEFAULT_MAX_DEVICES_PER_LOOP
                )
                
                self._standards_loaded = True
                logger.info(f"Loaded routing standards from DB: {standard_name}")
                logger.info(f"  max_voltage_drop: {self.max_voltage_drop_percent}%")
                logger.info(f"  max_loop_length: {self.max_loop_length}m")
                logger.info(f"  max_devices_per_loop: {self.max_devices_per_loop}")
                
                return True
            else:
                logger.warning(f"Standard '{standard_name}' not found in DB, using defaults")
                return False
                
        except Exception as e:
            logger.warning(f"Could not load standards from DB: {e}")
            return False
    
    def get_settings(self) -> Dict[str, float]:
        """
        Get current routing validation settings.
        
        Returns:
            Dict with max_voltage_drop_percent, max_loop_length, max_devices_per_loop
        """
        if not self._standards_loaded:
            self.load_standards_from_db()
        
        return {
            'max_voltage_drop_percent': self.max_voltage_drop_percent,
            'max_loop_length': self.max_loop_length,
            'max_devices_per_loop': self.max_devices_per_loop,
            'source': 'database' if self._standards_loaded else 'defaults'
        }
    
    def check_voltage_drop(
        self,
        connection: Any,
        source_voltage: float = 24.0
    ) -> Tuple[bool, float]:
        """
        Check voltage drop for a device connection.
        
        Args:
            connection: DeviceConnection object with CalculatedLength and CableType
            source_voltage: Source voltage (24V for fire alarm, 48V for CCTV)
            
        Returns:
            Tuple of (passes_check, voltage_drop_percent)
        """
        if not self._standards_loaded:
            self.load_standards_from_db()
        
        # Get cable type resistance (ohms per 1000ft)
        cable_resistance = {
            'CCTVCable': 0.075,  # 18 AWG
            'FireAlarmCable': 0.065,  # 16 AWG
            'DataCable': 0.1,  # Cat5e
            'ControlCable': 0.05,  # 14 AWG
            'PowerCable': 0.03,  # 12 AWG
        }.get(connection.CableType, 0.05)
        
        # Calculate voltage drop: V_drop = I * R * Length
        # Assume 0.5A per device for fire alarm, 0.25A for CCTV
        current = 0.5 if connection.CableType == 'FireAlarmCable' else 0.25
        length_km = (connection.CalculatedLength or 0) / 1000  # Convert m to km
        
        voltage_drop = current * cable_resistance * length_km
        voltage_drop_percent = (voltage_drop / source_voltage) * 100
        
        passes = voltage_drop_percent <= self.max_voltage_drop_percent
        
        logger.info(f"Voltage drop check: {voltage_drop_percent:.2f}% (max: {self.max_voltage_drop_percent}%)")
        
        return passes, voltage_drop_percent
    
    def check_loop_length(
        self,
        loop_devices: List[Any]
    ) -> Tuple[bool, float]:
        """
        Check total loop length against max allowed.
        
        Args:
            loop_devices: List of DeviceConnection objects in the loop
            
        Returns:
            Tuple of (passes_check, total_length_meters)
        """
        if not self._standards_loaded:
            self.load_standards_from_db()
        
        total_length = sum(
            (conn.CalculatedLength or 0)
            for conn in loop_devices
        )
        
        passes = total_length <= self.max_loop_length
        
        logger.info(f"Loop length check: {total_length:.1f}m (max: {self.max_loop_length}m)")
        
        return passes, total_length
    
    def check_device_count_per_loop(
        self,
        loop_id: str,
        all_connections: List[Any]
    ) -> Tuple[bool, int]:
        """
        Check number of devices per loop.
        
        Args:
            loop_id: Loop ID to check
            all_connections: All connection records
            
        Returns:
            Tuple of (passes_check, device_count)
        """
        if not self._standards_loaded:
            self.load_standards_from_db()
        
        device_count = sum(
            1 for conn in all_connections
            if conn.LoopID == loop_id
        )
        
        passes = device_count <= self.max_devices_per_loop
        
        logger.info(f"Device count check: {device_count} (max: {self.max_devices_per_loop})")
        
        return passes, device_count
    
    def validate_connection(
        self,
        connection: Any,
        source_voltage: float = 24.0,
        loop_devices: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Run full validation on a connection.
        
        Args:
            connection: DeviceConnection to validate
            source_voltage: Source voltage
            loop_devices: List of devices in same loop
            
        Returns:
            Dict with validation results
        """
        results = {
            'connection_id': connection.ConnectionID,
            'passed': True,
            'issues': []
        }
        
        # Check voltage drop
        passes_vd, vd_percent = self.check_voltage_drop(connection, source_voltage)
        results['voltage_drop'] = {
            'passed': passes_vd,
            'percent': vd_percent
        }
        if not passes_vd:
            results['passed'] = False
            results['issues'].append(f'Voltage drop {vd_percent:.1f}% exceeds limit')
        
        # Check loop length if loop_devices provided
        if loop_devices:
            passes_len, length = self.check_loop_length(loop_devices)
            results['loop_length'] = {
                'passed': passes_len,
                'meters': length
            }
            if not passes_len:
                results['passed'] = False
                results['issues'].append(f'Loop length {length:.1f}m exceeds limit')
        
        return results


# =============================================================================
# Helper Functions
# =============================================================================

def validate_routing_compliance(
    session: Session,
    domain: str = 'FireAlarm'
) -> Dict[str, Any]:
    """
    Validate all routing for a domain against standards.
    
    Args:
        session: Database session
        domain: Engineering domain
        
    Returns:
        Dict with validation results
    """
    validator = RoutingValidator(session)
    validator.load_standards_from_db()
    
    results = {
        'domain': domain,
        'settings': validator.get_settings(),
        'validations': [],
        'passed': True
    }
    
    try:
        from ai_design_integration import DeviceConnection
        
        connections = session.query(DeviceConnection).all()
        
        for conn in connections:
            val_result = validator.validate_connection(conn)
            results['validations'].append(val_result)
            if not val_result['passed']:
                results['passed'] = False
                
    except Exception as e:
        logger.error(f"Validation error: {e}")
        results['error'] = str(e)
    
    return results