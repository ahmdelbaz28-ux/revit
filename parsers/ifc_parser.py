"""
IFC Parser - Industry Foundation Classes
===================================

Parse IFC (Industry Foundation Classes) files for fire alarm analysis.
IFC is a standardized format for BIM (Building Information Modeling).

Supports:
- IFC2X3
- IFC4
- JSON-based IFC export

Extracted data:
- Spaces (rooms) with dimensions
- Fire suppression devices
- Building structure
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class IFCAnalysis:
    """Analysis result from IFC file."""
    building_name: str
    floors: int
    spaces: List[Dict]
    devices: List[Dict]
    total_area: float


class IFCParser:
    """Parse IFC format files."""
    
    def __init__(self, ifc_path: str):
        self.ifc_path = ifc_path
        self.data = None
        
    def _load_json(self) -> Dict:
        """Load IFC JSON file."""
        with open(self.ifc_path, 'r') as f:
            return json.load(f)
    
    def _parse_instances(self, data: Dict) -> List[Dict]:
        """Parse instances from IFC data."""
        return data.get('instances', [])
    
    def _extract_spaces(self, instances: List[Dict]) -> List[Dict]:
        """Extract IfcSpace instances."""
        spaces = []
        for inst in instances:
            if inst.get('type') == 'IfcSpace':
                attrs = inst.get('attributes', {})
                geom = inst.get('geometry', {})
                
                bounds = geom.get('bounds', {})
                origin = bounds.get('origin', {})
                dims = bounds.get('dimensions', {})
                
                space = {
                    'id': inst.get('id'),
                    'name': attrs.get('Name'),
                    'long_name': attrs.get('LongName'),
                    'area': attrs.get('Area', 0),
                    'elevation': attrs.get('Elevation', 0),
                    'bounds': {
                        'x': origin.get('x', 0),
                        'y': origin.get('y', 0),
                        'z': origin.get('z', 0),
                        'width': dims.get('width', 0),
                        'length': dims.get('length', 0),
                        'height': dims.get('height', 0),
                    }
                }
                spaces.append(space)
        
        return spaces
    
    def _extract_devices(self, instances: List[Dict]) -> List[Dict]:
        """Extract fire suppression devices."""
        devices = []
        for inst in instances:
            if inst.get('type') == 'IfcFireSuppressionDevice_Type':
                attrs = inst.get('attributes', {})
                applicable = inst.get('applicable_to', [])
                
                device = {
                    'id': inst.get('id'),
                    'name': attrs.get('Name'),
                    'detector_type': attrs.get('DetectorType'),
                    'sensitivity': attrs.get('Sensitivity'),
                    'coverage_radius': attrs.get('CoverageRadius', 0),
                    'mounting_height': attrs.get('MountingHeight', 0),
                    'applicable_spaces': applicable,
                }
                devices.append(device)
        
        return devices
    
    def _extract_building(self, instances: List[Dict]) -> Dict:
        """Extract building info."""
        for inst in instances:
            if inst.get('type') == 'IfcBuilding':
                attrs = inst.get('attributes', {})
                return {
                    'name': attrs.get('Name'),
                    'long_name': attrs.get('LongName'),
                }
        return {'name': 'Unknown'}
    
    def _count_floors(self, instances: List[Dict]) -> int:
        """Count building stories."""
        floors = set()
        for inst in instances:
            if inst.get('type') == 'IfcBuildingStorey':
                floors.add(inst.get('id'))
        return len(floors)
    
    def parse(self) -> IFCAnalysis:
        """Main parsing method."""
        # Load data
        if self.data is None:
            try:
                self.data = self._load_json()
            except Exception as e:
                return None
        
        instances = self._parse_instances(self.data)
        
        # Extract data
        building = self._extract_building(instances)
        spaces = self._extract_spaces(instances)
        devices = self._extract_devices(instances)
        floors = self._count_floors(instances)
        
        # Calculate total area
        total_area = sum(s.get('area', 0) for s in spaces)
        
        return IFCAnalysis(
            building_name=building.get('name', 'Unknown'),
            floors=floors,
            spaces=spaces,
            devices=devices,
            total_area=total_area,
        )
    
    def to_standard_format(self, ifc_analysis: IFCAnalysis) -> Dict:
        """Convert IFC analysis to standard format."""
        # Extract walls from space bounds (simplified)
        walls = []
        for space in ifc_analysis.spaces:
            bounds = space.get('bounds', {})
            x, y = bounds.get('x', 0), bounds.get('y', 0)
            w, l = bounds.get('width', 0), bounds.get('length', 0)
            
            if w > 0 and l > 0:
                walls.append({
                    'x1': x, 'y1': y,
                    'x2': x + w, 'y2': y + l,
                })
        
        return {
            'building_name': ifc_analysis.building_name,
            'floors': ifc_analysis.floors,
            'walls': walls,
            'rooms': [
                {
                    'id': s['id'],
                    'name': s['name'],
                    'area': s.get('area', 0),
                    'bounds': s.get('bounds', {}),
                }
                for s in ifc_analysis.spaces
            ],
            'devices': [
                {
                    'id': d['id'],
                    'name': d['name'],
                    'type': d.get('detector_type'),
                    'coverage_radius': d.get('coverage_radius', 0),
                }
                for d in ifc_analysis.devices
            ],
            'total_area': ifc_analysis.total_area,
        }


def parse_ifc(ifc_path: str) -> Optional[IFCAnalysis]:
    """Convenience function."""
    parser = IFCParser(ifc_path)
    return parser.parse()