"""
FireAI Universal Data Model - Database Layer
"""

import sqlite3
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from core.models import (
    UniversalElement, SemanticProperties, Geometry, 
    Relationship, ChangeSource, ConflictType, Conflict
)

logger = logging.getLogger(__name__)


class ConflictResolutionError(Exception):
    """خطأ في حل التعارضات"""
    pass


class UniversalDataModel:
    """
    قاعدة البيانات الموحدة: مركز الحقيقة الوحيدة
    """
    
    def __init__(self, db_path: str = "fireai_universal.db"):
        self.db_path = db_path
        self.elements: Dict[str, UniversalElement] = {}
        self.relationships: List[Relationship] = []
        self.conflicts: Dict[str, Conflict] = {}
        
        # Metadata
        self.version = 0
        self.last_sync_timestamp = None
        self.pending_changes: Dict[str, List[str]] = {
            'autocad': [],
            'revit': []
        }
        
        # Track previous state for conflict detection
        self.element_snapshots: Dict[str, Dict] = {}
        
        # Initialize database
        self._init_database()
        
        logger.info(f"Universal Data Model initialized at {db_path}")
    
    def _init_database(self):
        """إنشاء قاعدة البيانات"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS elements (
                element_id TEXT PRIMARY KEY,
                data JSON,
                version INTEGER,
                content_hash TEXT,
                created_timestamp TIMESTAMP,
                last_modified_timestamp TIMESTAMP,
                last_modified_by TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS change_log (
                log_id TEXT PRIMARY KEY,
                element_id TEXT,
                timestamp TIMESTAMP,
                source TEXT,
                change_type TEXT,
                old_value JSON,
                new_value JSON,
                reason TEXT,
                FOREIGN KEY (element_id) REFERENCES elements(element_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conflicts (
                conflict_id TEXT PRIMARY KEY,
                element_id TEXT,
                conflict_type TEXT,
                timestamp TIMESTAMP,
                source_a TEXT,
                source_b TEXT,
                change_a JSON,
                change_b JSON,
                resolved BOOLEAN,
                resolution JSON,
                FOREIGN KEY (element_id) REFERENCES elements(element_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS relationships (
                relationship_id TEXT PRIMARY KEY,
                from_element_id TEXT,
                to_element_id TEXT,
                relationship_type TEXT,
                is_parametric BOOLEAN,
                metadata JSON,
                FOREIGN KEY (from_element_id) REFERENCES elements(element_id),
                FOREIGN KEY (to_element_id) REFERENCES elements(element_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_element(self, element: UniversalElement) -> bool:
        """إضافة عنصر جديد"""
        try:
            # Validate
            is_valid, errors = element.validate_semantic_consistency()
            if not is_valid:
                logger.warning(f"Element validation failed: {errors}")
            
            # Calculate geometry
            if element.geometry:
                element.geometry.calculate_area()
                element.geometry.calculate_perimeter()
            
            # Store
            self.elements[element.element_id] = element
            self.element_snapshots[element.element_id] = element.to_dict()
            
            # Log change
            element.add_change_log_entry(
                change_type='create',
                source=element.last_modified_by and ChangeSource(element.last_modified_by) or ChangeSource.SYSTEM,
                new_value=element.to_dict()
            )
            
            # Persist
            self._persist_element(element)
            
            self.version += 1
            logger.info(f"Added element {element.element_id} ({element.properties.element_type.value})")
            return True
        
        except Exception as e:
            logger.error(f"Error adding element: {e}")
            return False
    
    def update_element(
        self,
        element_id: str,
        updates: Dict[str, Any],
        source: ChangeSource = ChangeSource.SYSTEM,
        reason: Optional[str] = None
    ) -> bool:
        """تحديث عنصر موجود"""
        try:
            if element_id not in self.elements:
                logger.error(f"Element {element_id} not found")
                return False
            
            element = self.elements[element_id]
            old_value = element.to_dict()
            
            # Apply updates
            for key, value in updates.items():
                if key == 'properties' and isinstance(value, dict):
                    # Update existing properties or create new
                    if element.properties is None:
                        element.properties = SemanticProperties.from_dict(value)
                    else:
                        # Update individual property fields
                        for prop_key, prop_value in value.items():
                            if hasattr(element.properties, prop_key):
                                setattr(element.properties, prop_key, prop_value)
                elif key == 'geometry' and isinstance(value, dict):
                    element.geometry = Geometry.from_dict(value)
                elif hasattr(element, key):
                    setattr(element, key, value)
            
            # Validate
            is_valid, errors = element.validate_semantic_consistency()
            if not is_valid:
                logger.warning(f"Updated element validation failed: {errors}")
            
            # Recalculate geometry
            if element.geometry:
                element.geometry.calculate_area()
                element.geometry.calculate_perimeter()
            
            # Log change
            new_value = element.to_dict()
            element.add_change_log_entry(
                change_type='update',
                source=source,
                old_value=old_value,
                new_value=new_value,
                reason=reason
            )
            
            # Track for sync
            if source == ChangeSource.AUTOCAD:
                if element_id not in self.pending_changes['revit']:
                    self.pending_changes['revit'].append(element_id)
            elif source == ChangeSource.REVIT:
                if element_id not in self.pending_changes['autocad']:
                    self.pending_changes['autocad'].append(element_id)
            
            # Persist
            self._persist_element(element)
            
            # Increment element version
            element.version += 1
            
            self.version += 1
            logger.info(f"Updated element {element_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error updating element {element_id}: {e}")
            return False
    
    def delete_element(
        self,
        element_id: str,
        source: ChangeSource = ChangeSource.SYSTEM,
        reason: Optional[str] = None
    ) -> bool:
        """حذف عنصر (soft delete)"""
        try:
            if element_id not in self.elements:
                logger.error(f"Element {element_id} not found")
                return False
            
            element = self.elements[element_id]
            old_value = element.to_dict()
            
            element.is_deleted = True
            element.add_change_log_entry(
                change_type='delete',
                source=source,
                old_value=old_value,
                reason=reason
            )
            
            # Track for sync
            if source == ChangeSource.AUTOCAD:
                if element_id not in self.pending_changes['revit']:
                    self.pending_changes['revit'].append(element_id)
            elif source == ChangeSource.REVIT:
                if element_id not in self.pending_changes['autocad']:
                    self.pending_changes['autocad'].append(element_id)
            
            # Persist
            self._persist_element(element)
            
            self.version += 1
            logger.info(f"Deleted element {element_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error deleting element {element_id}: {e}")
            return False
    
    def detect_conflicts(self) -> List[Conflict]:
        """كشف التعارضات"""
        detected_conflicts = []
        
        # Compare snapshots with current state
        for element_id, element in self.elements.items():
            if element_id not in self.element_snapshots:
                continue
            
            previous_state = self.element_snapshots[element_id]
            current_state = element.to_dict()
            
            # Check if changed from multiple sources in short time
            if len(element.change_log) >= 2:
                last_change = element.change_log[-1]
                prev_change = element.change_log[-2]
                
                time_diff = (last_change.timestamp - prev_change.timestamp).total_seconds()
                
                if time_diff < 5.0 and last_change.source != prev_change.source:
                    # Potential conflict
                    conflict = Conflict(
                        element_id=element_id,
                        conflict_type=ConflictType.TIMING_CONFLICT,
                        source_a=prev_change.source,
                        source_b=last_change.source,
                        change_a=prev_change.new_value or {},
                        change_b=last_change.new_value or {}
                    )
                    detected_conflicts.append(conflict)
                    logger.warning(f"Detected timing conflict in element {element_id}")
        
        return detected_conflicts
    
    def resolve_conflict(
        self,
        conflict: Conflict,
        strategy: str = 'SEMANTIC_MERGE'
    ) -> bool:
        """حل التعارض"""
        try:
            if strategy == 'LAST_WRITE_WINS':
                conflict.resolution = conflict.change_b
                conflict.resolved = True
                logger.info(f"Resolved conflict {conflict.conflict_id} using LAST_WRITE_WINS")
            
            elif strategy == 'SEMANTIC_MERGE':
                conflicting_fields = set(conflict.change_a.keys()) & set(conflict.change_b.keys())
                
                if not conflicting_fields:
                    merged = {**conflict.change_a, **conflict.change_b}
                    conflict.resolution = merged
                    conflict.resolved = True
                    logger.info(f"Auto-resolved conflict {conflict.conflict_id} using semantic merge")
                else:
                    raise ConflictResolutionError(
                        f"Cannot auto-resolve: conflicting fields {conflicting_fields}"
                    )
            
            else:
                raise ValueError(f"Unknown resolution strategy: {strategy}")
            
            self.conflicts[conflict.conflict_id] = conflict
            return True
        
        except ConflictResolutionError:
            logger.error(f"Manual review required for conflict {conflict.conflict_id}")
            return False
        except Exception as e:
            logger.error(f"Error resolving conflict {conflict.conflict_id}: {e}")
            return False
    
    def _persist_element(self, element: UniversalElement):
        """حفظ العنصر في قاعدة البيانات"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO elements
                (element_id, data, version, content_hash, created_timestamp, 
                 last_modified_timestamp, last_modified_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                element.element_id,
                json.dumps(element.to_dict(), default=str),
                element.version,
                element.content_hash,
                element.created_timestamp.isoformat(),
                element.last_modified_timestamp.isoformat(),
                element.last_modified_by
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error persisting element {element.element_id}: {e}")
    
    def load_from_database(self) -> bool:
        """تحميل جميع العناصر من قاعدة البيانات"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT data FROM elements WHERE 1=1')
            rows = cursor.fetchall()
            
            for row in rows:
                data = json.loads(row[0])
                element = UniversalElement.from_dict(data)
                self.elements[element.element_id] = element
            
            conn.close()
            logger.info(f"Loaded {len(self.elements)} elements from database")
            return True
        except Exception as e:
            logger.error(f"Error loading from database: {e}")
            return False
    
    def get_pending_changes(self, source: ChangeSource) -> List[UniversalElement]:
        """الحصول على التغييرات المعلقة"""
        if source == ChangeSource.AUTOCAD:
            pending_ids = self.pending_changes['revit']
        elif source == ChangeSource.REVIT:
            pending_ids = self.pending_changes['autocad']
        else:
            return []
        
        return [self.elements[eid] for eid in pending_ids if eid in self.elements]
    
    def clear_pending_changes(self, source: ChangeSource):
        """مسح التغييرات المعلقة بعد المزامنة"""
        if source == ChangeSource.AUTOCAD:
            self.pending_changes['revit'] = []
        elif source == ChangeSource.REVIT:
            self.pending_changes['autocad'] = []
        
        self.last_sync_timestamp = datetime.now()