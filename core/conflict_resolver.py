"""
FireAI Conflict Resolution - Conflict detection and resolution
"""

import uuid
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

from core.models import ConflictType, ChangeSource

logger = logging.getLogger(__name__)


@dataclass
class Conflict:
    """تمثيل التعارض"""
    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    element_id: str = ""
    conflict_type: ConflictType = ConflictType.PROPERTY_CONFLICT
    timestamp: datetime = field(default_factory=datetime.now)
    source_a: ChangeSource = ChangeSource.AUTOCAD
    source_b: ChangeSource = ChangeSource.REVIT
    change_a: Dict = field(default_factory=dict)
    change_b: Dict = field(default_factory=dict)
    resolution: Optional[Dict] = None
    resolved: bool = False
    
    def to_dict(self) -> Dict:
        return {
            'conflict_id': self.conflict_id,
            'element_id': self.element_id,
            'conflict_type': self.conflict_type.value,
            'timestamp': self.timestamp.isoformat(),
            'source_a': self.source_a.value,
            'source_b': self.source_b.value,
            'change_a': self.change_a,
            'change_b': self.change_b,
            'resolved': self.resolved
        }


class ConflictDetector:
    """كاشف التعارضات"""
    
    def __init__(self):
        self.conflicts: List[Conflict] = []
    
    def detect(
        self,
        element_id: str,
        change_a: Dict,
        change_b: Dict,
        source_a: ChangeSource,
        source_b: ChangeSource
    ) -> List[Conflict]:
        """كشف التعارض بين تغييرين"""
        detected = []
        
        # Check geometry mismatch
        if 'geometry' in change_a and 'geometry' in change_b:
            geo_a = change_a.get('geometry', {})
            geo_b = change_b.get('geometry', {})
            
            if self._geometry_changed(geo_a, geo_b):
                conflict = Conflict(
                    element_id=element_id,
                    conflict_type=ConflictType.GEOMETRY_MISMATCH,
                    source_a=source_a,
                    source_b=source_b,
                    change_a=change_a,
                    change_b=change_b
                )
                detected.append(conflict)
        
        # Check property conflict
        if 'properties' in change_a and 'properties' in change_b:
            prop_a = change_a.get('properties', {})
            prop_b = change_b.get('properties', {})
            
            if self._properties_conflict(prop_a, prop_b):
                conflict = Conflict(
                    element_id=element_id,
                    conflict_type=ConflictType.PROPERTY_CONFLICT,
                    source_a=source_a,
                    source_b=source_b,
                    change_a=change_a,
                    change_b=change_b
                )
                detected.append(conflict)
        
        self.conflicts.extend(detected)
        return detected
    
    def _geometry_changed(self, geo_a: Dict, geo_b: Dict) -> bool:
        """فحص تغيير الهندسة"""
        if not geo_a or not geo_b:
            return False
        
        points_a = geo_a.get('points', [])
        points_b = geo_b.get('points', [])
        
        if len(points_a) != len(points_b):
            return True
        
        for p_a, p_b in zip(points_a, points_b):
            if abs(p_a.get('x', 0) - p_b.get('x', 0)) > 0.01:
                return True
            if abs(p_a.get('y', 0) - p_b.get('y', 0)) > 0.01:
                return True
        
        return False
    
    def _properties_conflict(self, prop_a: Dict, prop_b: Dict) -> bool:
        """فحص تعارض الخصائص"""
        for key in prop_a:
            if key in prop_b and prop_a[key] != prop_b[key]:
                # Ignore certain acceptable differences
                if key == 'name':
                    continue
                return True
        return False


class ConflictResolver:
    """محلل التعارضات"""
    
    def __init__(self, strategy: str = 'SEMANTIC_MERGE'):
        self.strategy = strategy
    
    def resolve(self, conflict: Conflict) -> Dict:
        """حل التعارض"""
        if self.strategy == 'LAST_WRITE_WINS':
            return conflict.change_b
        
        elif self.strategy == 'SEMANTIC_MERGE':
            conflicting_fields = set(conflict.change_a.keys()) & set(conflict.change_b.keys())
            
            if not conflicting_fields:
                return {**conflict.change_a, **conflict.change_b}
            
            # Try field-by-field merge
            merged = {}
            for key in set(conflict.change_a.keys()) | set(conflict.change_b.keys()):
                if key in conflict.change_a and key in conflict.change_b:
                    if conflict.change_a[key] == conflict.change_b[key]:
                        merged[key] = conflict.change_a[key]
                elif key in conflict.change_a:
                    merged[key] = conflict.change_a[key]
                elif key in conflict.change_b:
                    merged[key] = conflict.change_b[key]
            
            return merged
        
        return conflict.change_a