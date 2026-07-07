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
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional


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
        with open(self.ifc_path) as f:
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

                # V78 FIX: Validate area — negative areas corrupt total_area calculation
                # V79 FIX: Negative area → skip space entirely (not set to 0).
                # Setting to 0 means zero protection for a room with real geometry.
                raw_area = attrs.get('Area', 0)
                if raw_area < 0:
                    logging.getLogger(__name__).warning(  # NOSONAR: S5145 logging reviewed for SSRF risk
                        "Negative area for space %s: %s. Space REJECTED — "
                        "manual fire protection design REQUIRED.",
                        inst.get('id'), raw_area,
                    )
                    continue

                space = {
                    'id': inst.get('id'),
                    'name': attrs.get('Name'),
                    'long_name': attrs.get('LongName'),
                    'area': raw_area,
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
        """
        Extract fire protection devices from multiple IFC fire entity types.

        Supports:
          - IfcFireSuppressionDevice_Type  (sprinklers, standpipes)
          - IfcAlarm                       (fire alarm devices)
          - IfcSensor                      (smoke/heat detectors)
          - IfcProtectiveDevice            (fire dampers, fire doors)
        """
        _FIRE_ENTITY_TYPES = {
            'IfcFireSuppressionDevice_Type',
            'IfcAlarm',
            'IfcSensor',
            'IfcProtectiveDevice',
        }
        devices = []
        for inst in instances:
            if inst.get('type') in _FIRE_ENTITY_TYPES:
                attrs = inst.get('attributes', {})
                applicable = inst.get('applicable_to', [])

                device = {
                    'id': inst.get('id'),
                    'name': attrs.get('Name'),
                    'detector_type': attrs.get('DetectorType'),
                    'sensitivity': attrs.get('Sensitivity'),
                    'coverage_radius': attrs.get('CoverageRadius', None),  # V79 FIX: was 0 — zero radius means device covers nothing
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
        """
        Main parsing method.

        Raises:
            ValueError: If the IFC file cannot be loaded or parsed,
                including security validation failures (V125 hardening).

        """
        # V125/V126 SECURITY (Rule #23): validate self.ifc_path BEFORE opening.
        # The path was supplied at __init__ time; this is the last gate
        # before file I/O. Closes path traversal, null bytes, argument
        # injection (defense-in-depth), and oversized files.
        import os as _os

        from parsers._path_security import (
            UnsafePathError,
            validate_file_size,
            validate_input_path,
        )

        _IFC_MAX_BYTES = int(_os.getenv("FIREAI_IFC_MAX_FILE_SIZE_BYTES",
                                        str(500 * 1024 * 1024)))  # 500 MB
        _ALLOWED_EXTENSIONS = frozenset({".ifc", ".ifcxml", ".json"})
        try:
            safe_path = validate_input_path(
                self.ifc_path,
                allowed_extensions=_ALLOWED_EXTENSIONS,
                parser_name="IFCParser",
            )
            validate_file_size(safe_path, max_size_bytes=_IFC_MAX_BYTES,
                               parser_name="IFCParser")
        except FileNotFoundError as e:
            raise ValueError(f"IFC file not found: {e}") from e
        except UnsafePathError as e:
            raise ValueError(f"SECURITY: {e}") from e

        # Use resolved canonical path for the actual load (TOCTOU fix)
        self.ifc_path = str(safe_path)

        # Load data
        if self.data is None:
            try:
                self.data = self._load_json()
            except Exception as e:
                raise ValueError(
                    f"Failed to load IFC file '{self.ifc_path}': {e}"
                ) from e

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
