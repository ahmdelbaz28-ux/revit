"""
Compliance Service
==================
Application service for comprehensive compliance checking.

This service orchestrates all compliance checks across standards
and provides unified violation reporting.
"""

from typing import List, Dict, Any, Optional
from ..domain.models import Room, Device, Violation, ViolationSeverity, DesignProject
from ..domain.standards import NFPA72, BS5839, get_standard
from .coverage_service import CoverageService
from .wall_distance_service import WallDistanceService


class ComplianceService:
    """
    Service for comprehensive compliance checking.
    
    Responsibilities:
    - Orchestrate all compliance checks for a room/project
    - Aggregate violations from multiple standards
    - Provide compliance summary and scoring
    - Generate compliance reports
    """
    
    def __init__(self, standard_names: List[str] = None):
        """
        Initialize with one or more standards to check against.
        
        Args:
            standard_names: List of standard names (e.g., ['NFPA72', 'BS5839'])
        """
        if standard_names is None:
            standard_names = ['NFPA72']
        
        self.standards = []
        self.services = {}
        
        for std_name in standard_names:
            std = get_standard(std_name)
            if std:
                self.standards.append(std)
                self.services[std_name] = {
                    'coverage': CoverageService(),  # No beams needed for basic check
                    'wall_distance': WallDistanceService(std_name),
                }
    
    def check_room_compliance(self, room: Room, devices: List[Device]) -> List[Violation]:
        """
        Check full compliance for a room with its devices.
        
        Args:
            room: Room to check
            devices: Devices in the room
            
        Returns:
            List of all violations found
        """
        all_violations = []
        
        # Check each standard
        for std_name, services in self.services.items():
            # Coverage checks
            coverage_violations = services['coverage'].check_room_coverage(room, devices)
            all_violations.extend(coverage_violations)
            
            # Spacing checks
            spacing_violations = services['coverage'].check_device_spacing(room, devices)
            all_violations.extend(spacing_violations)
            
            # Wall distance checks
            wall_violations = services['wall_distance'].check_all_devices(room, devices)
            all_violations.extend(wall_violations)
        
        # Check room-specific requirements (e.g., kitchen heat detectors)
        for std in self.standards:
            if isinstance(std, NFPA72):
                room_violations = std.validate_room_requirements(room, devices)
                all_violations.extend(room_violations)
        
        return all_violations
    
    def check_project_compliance(self, project: DesignProject) -> Dict[str, Any]:
        """
        Check compliance for an entire design project.
        
        Args:
            project: Design project to check
            
        Returns:
            Dictionary with compliance summary and detailed violations
        """
        all_violations = []
        rooms_checked = 0
        devices_checked = 0
        
        for room in project.rooms:
            room_devices = [d for d in project.devices if d.room_id == room.room_id]
            violations = self.check_room_compliance(room, room_devices)
            all_violations.extend(violations)
            rooms_checked += 1
            devices_checked += len(room_devices)
        
        # Calculate compliance score
        total_checks = rooms_checked * 3  # Coverage, spacing, wall distance
        violations_count = len(all_violations)
        critical_count = sum(1 for v in all_violations if v.severity == ViolationSeverity.CRITICAL)
        major_count = sum(1 for v in all_violations if v.severity == ViolationSeverity.MAJOR)
        
        # Score: 100% - penalties for violations
        penalty = (critical_count * 20) + (major_count * 10) + ((violations_count - critical_count - major_count) * 5)
        compliance_score = max(0, 100 - penalty)
        
        return {
            'compliance_score': compliance_score,
            'total_violations': violations_count,
            'critical_violations': critical_count,
            'major_violations': major_count,
            'minor_violations': violations_count - critical_count - major_count,
            'rooms_checked': rooms_checked,
            'devices_checked': devices_checked,
            'violations': [v.to_dict() for v in all_violations],
            'is_compliant': compliance_score >= 80 and critical_count == 0,
            'standards_checked': [std.__class__.__name__ for std in self.standards]
        }
    
    def get_compliance_summary(self, violations: List[Violation]) -> Dict[str, Any]:
        """
        Get a summary of violations grouped by type and severity.
        
        Args:
            violations: List of violations to summarize
            
        Returns:
            Summary dictionary
        """
        summary = {
            'total': len(violations),
            'by_severity': {},
            'by_standard': {},
            'by_code': {},
            'critical_codes': [],
            'recommendations': []
        }
        
        # Group by severity
        for severity in ViolationSeverity:
            count = sum(1 for v in violations if v.severity == severity)
            if count > 0:
                summary['by_severity'][severity.value] = count
        
        # Group by standard
        standards_count = {}
        for v in violations:
            std_name = v.standard_name
            standards_count[std_name] = standards_count.get(std_name, 0) + 1
        summary['by_standard'] = standards_count
        
        # Group by violation code
        code_count = {}
        for v in violations:
            code = v.violation_code
            code_count[code] = code_count.get(code, 0) + 1
        summary['by_code'] = code_count
        
        # Identify critical codes
        summary['critical_codes'] = list(set(
            v.violation_code for v in violations 
            if v.severity == ViolationSeverity.CRITICAL
        ))
        
        # Generate recommendations
        summary['recommendations'] = self._generate_recommendations(violations)
        
        return summary
    
    def _generate_recommendations(self, violations: List[Violation]) -> List[str]:
        """Generate actionable recommendations based on violations"""
        recommendations = []
        
        code_counts = {}
        for v in violations:
            code = v.violation_code
            code_counts[code] = code_counts.get(code, 0) + 1
        
        if 'NFPA72_EXCEEDS_MAX_WALL_DISTANCE' in code_counts:
            count = code_counts['NFPA72_EXCEEDS_MAX_WALL_DISTANCE']
            recommendations.append(
                f"Relocate {count} device(s) that exceed maximum wall distance. "
                "Move devices closer to room center or add additional devices."
            )
        
        if 'NFPA72_KITCHEN_REQUIRES_HEAT_DETECTOR' in code_counts:
            recommendations.append(
                "Replace smoke detectors with heat detectors in kitchen areas "
                "to prevent false alarms from cooking activities."
            )
        
        if 'COVERAGE_NO_DEVICES' in code_counts:
            recommendations.append(
                "Install fire detection devices in rooms with no coverage. "
                "All occupied spaces require at least one detection device."
            )
        
        if 'COVERAGE_INSUFFICIENT_TOTAL' in code_counts:
            recommendations.append(
                "Add more devices to rooms with insufficient coverage. "
                "Ensure overlapping coverage circles eliminate gaps."
            )
        
        if not recommendations:
            recommendations.append("No critical issues found. Design appears compliant.")
        
        return recommendations
