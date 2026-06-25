"""
RevitJSON Parser - Autodesk Revit Project Export
===========================================

Parse Revit project exports (JSON format).

Supports:
- Revit 2024+ JSON export
- Multi-level buildings
- Fire alarm device families
- Spatial data (rooms/spaces)
- Parameters and settings
"""

import json
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class RevitProject:
    """Parsed Revit project."""
    name: str
    version: str
    units: str
    levels: List[Dict]
    categories: List[str]
    families: Dict[str, List[str]]
    parameters: Dict


class RevitJSONParser:
    """Parse Revit JSON exports."""

    def __init__(self, json_path: str):
        self.json_path = json_path
        self.data = None

    def _load_json(self) -> Dict:
        """Load JSON file."""
        with open(self.json_path, 'r') as f:
            return json.load(f)

    def parse(self) -> Optional[RevitProject]:
        """Parse Revit JSON."""
        try:
            if self.data is None:
                self.data = self._load_json()
        except Exception:
            return None

        info = self.data.get('project_info', {})

        return RevitProject(
            name=info.get('name', 'Unknown'),
            version=info.get('version', 'Unknown'),
            units=info.get('units', 'metric'),
            levels=self.data.get('levels', []),
            categories=self.data.get('categories', []),
            families=self.data.get('families', {}),
            parameters=self.data.get('parameters', {}),
        )

    def get_level_count(self) -> int:
        """Get number of levels."""
        if self.data:
            return len(self.data.get('levels', []))
        return 0

    def get_fire_alarm_families(self) -> List[str]:
        """Get fire alarm device families."""
        if self.data:
            families = self.data.get('families', {})
            fa_families = []
            for device_type, variants in families.items():
                if device_type in ['SmokeDetector', 'HeatDetector', 'PullStation', 'HornStrobe']:
                    fa_families.extend(variants)
            return fa_families
        return []

    def get_parameters(self) -> Dict:
        """Get project parameters."""
        if self.data:
            return self.data.get('parameters', {})
        return {}


def parse_revit_json(json_path: str) -> Optional[RevitProject]:
    """Convenience function."""
    parser = RevitJSONParser(json_path)
    return parser.parse()
