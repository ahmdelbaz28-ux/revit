"""
FireAI AutoCAD Adapter - AutoCAD integration
"""

import logging
from typing import Optional, Dict

from core.models import (
    UniversalElement, ElementType, Point3D, Geometry,
    ChangeSource
)
from core.database import UniversalDataModel
from core.sync_engine import LiveSyncEngine
from parsers.dwg_parser import DWGParser

logger = logging.getLogger(__name__)


class AutoCADAdapter:
    """
    Adapter لربط AutoCAD مع FireAI Digital Twin
    """
    
    def __init__(self, db=None, sync=None, use_mock: bool = True, db_path: str = "fireai_universal.db"):
        if db is None:
            self.universal_model = UniversalDataModel(db_path)
        else:
            self.universal_model = db
        self.dwg_parser = DWGParser()
        self.live_sync = sync
        self.is_monitoring = False
        self.use_mock = use_mock
        self._is_monitoring = False
        self._mock_entities = {}
        self.autocad = None
        self.dwg_file_path = None
        self.element_id_map: Dict[str, str] = {}
        
        logger.info("AutoCAD Adapter initialized")
    
    def connect_to_autocad(self):
        """الاتصال بـ AutoCAD"""
        try:
            from pyautocad import Autocad
            self.autocad = Autocad()
            self.dwg_file_path = self.autocad.doc.Name
            logger.info(f"Connected to AutoCAD. File: {self.dwg_file_path}")
            return True
        except ImportError:
            logger.error("pyautocad not installed. Install with: pip install pyautocad")
            return False
        except Exception as e:
            logger.error(f"Error connecting to AutoCAD: {e}")
            return False
    
    def start_monitoring(self):
        """بدء مراقبة التغييرات"""
        if self.use_mock:
            self._is_monitoring = True
            self.is_monitoring = True
            logger.info("AutoCAD MOCK monitoring started")
            return True
        
        if not self.connect_to_autocad():
            return False
        
        self.is_monitoring = True
        logger.info("Started monitoring AutoCAD changes")
        
        # Initial import
        self._import_current_drawing()
        
        # Start live sync
        self.live_sync.start_sync()
        
        return True
    
    def import_current_drawing(self):
        """Import from current AutoCAD drawing"""
        if not self._is_monitoring:
            return []
        
        if self.use_mock:
            if not self._mock_entities:
                self._mock_entities = {
                    "1": {"id": "1", "type": "LINE", "data": {"layer": "A-WALL"}},
                    "2": {"id": "2", "type": "CIRCLE", "data": {"layer": "A-FURN"}},
                    "3": {"id": "3", "type": "POLYLINE", "data": {"layer": "A-WALL"}}}
            return list(self._mock_entities.values())
        
        return []
    
    def on_entity_added(self, entity):
        """Callback عند إضافة كائن جديد في AutoCAD"""
        if self.use_mock:
            try:
                entity_id = entity.get("id")
                if entity_id:
                    self._mock_entities[entity_id] = entity
            except (AttributeError, TypeError):
                pass
            return True
        
        try:
            logger.debug(f"Entity added: {entity.ObjectName}")
            
            universal_element = self.dwg_parser._convert_entity_to_universal(entity, self.dwg_file_path)
            
            if universal_element:
                self.universal_model.add_element(universal_element)
                
                if hasattr(entity, 'Handle'):
                    self.element_id_map[entity.Handle] = universal_element.element_id
                
                logger.info(f"Added element to Universal Model: {universal_element.element_id}")
        
        except Exception as e:
            logger.error(f"Error handling entity added: {e}")
        
        return True
    
    def on_entity_modified(self, entity_id, new_data=None):
        """Callback عند تعديل كائن في AutoCAD"""
        if self.use_mock:
            if entity_id in self._mock_entities:
                if new_data:
                    self._mock_entities[entity_id].update(new_data)
                return True
            return False
        
        try:
            logger.debug(f"Entity modified: {entity_id}")
            
            # Find corresponding Universal Element
            if entity_id not in self.element_id_map:
                logger.warning(f"Modified entity not found in mapping: {entity_id}")
                return
            
            element_id = self.element_id_map[entity_id]
            
            # Update Universal Model
            updates = self._extract_entity_properties(entity_id)
            self.universal_model.update_element(
                element_id,
                updates,
                source=ChangeSource.AUTOCAD,
                reason="Entity modified in AutoCAD"
            )
            
            logger.info(f"Updated element {element_id} from AutoCAD")
        
        except Exception as e:
            logger.error(f"Error handling entity modified: {e}")
    
    def on_entity_deleted(self, entity_id):
        """Callback عند حذف كائن في AutoCAD"""
        if self.use_mock:
            if entity_id in self._mock_entities:
                del self._mock_entities[entity_id]
                return True
            return False
        
        try:
            logger.debug(f"Entity deleted: {entity_id}")
            
            if entity_id not in self.element_id_map:
                logger.warning(f"Deleted entity not found in mapping: {entity_id}")
                return
            
            element_id = self.element_id_map[entity_id]
            
            self.universal_model.delete_element(
                element_id,
                source=ChangeSource.AUTOCAD,
                reason="Entity deleted in AutoCAD"
            )
            
            del self.element_id_map[entity_id]
            
            logger.info(f"Deleted element {element_id}")
        except Exception as e:
            logger.error(f"Error handling entity deleted: {e}")
    
    def stop_monitoring(self):
        """إيقاف المراقبة"""
        self.is_monitoring = False
        self._is_monitoring = False
        if self.live_sync:
            self.live_sync.stop_sync()
        logger.info("Stopped monitoring AutoCAD changes")
    
    def _import_current_drawing(self):
        """استيراد الرسم الحالي إلى Universal Model"""
        try:
            logger.info("Importing current AutoCAD drawing...")
            
            # استخدم DWG parser
            elements = self.dwg_parser.parse_dwg(self.dwg_file_path)
            
            for element in elements:
                self.universal_model.add_element(element)
                
                # Store mapping for later updates
                if element.autocad_handle:
                    self.element_id_map[element.autocad_handle] = element.element_id
            
            logger.info(f"Imported {len(elements)} elements from {self.dwg_file_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error importing drawing: {e}")
            return False
    
    def _extract_entity_properties(self, entity) -> dict:
        """استخراج الخصائص من كائن AutoCAD"""
        properties = {}
        
        try:
            # Get layer name
            layer = getattr(entity, 'Layer', None)
            if layer:
                properties['layer'] = layer
                
                # Infer element type from layer
                if 'WALL' in layer.upper():
                    properties['element_type'] = ElementType.WALL.value
                elif 'ROOM' in layer.upper():
                    properties['element_type'] = ElementType.ROOM.value
            
            # Get geometry
            if hasattr(entity, 'Coordinates'):
                points = [Point3D(x, y, 0) for x, y in entity.Coordinates]
                geometry = Geometry(points=points)
                geometry.calculate_area()
                geometry.calculate_perimeter()
                properties['geometry'] = geometry.to_dict()
            
            # Get other properties
            if hasattr(entity, 'TextString'):
                properties['name'] = entity.TextString
        
        except Exception as e:
            logger.warning(f"Error extracting entity properties: {e}")
        
        return properties
    
    def apply_pending_changes_from_revit(self):
        """تطبيق التغييرات القادمة من Revit على AutoCAD"""
        try:
            pending = self.universal_model.get_pending_changes(ChangeSource.REVIT)
            
            if not pending:
                return
            
            logger.info(f"Applying {len(pending)} changes from Revit to AutoCAD...")
            
            for element in pending:
                if element.is_deleted:
                    self._delete_entity_in_autocad(element)
                else:
                    if element.autocad_handle:
                        self._update_entity_in_autocad(element)
                    else:
                        self._create_entity_in_autocad(element)
            
            # Clear pending
            self.universal_model.clear_pending_changes(ChangeSource.REVIT)
            logger.info("Changes from Revit applied to AutoCAD")
        
        except Exception as e:
            logger.error(f"Error applying Revit changes: {e}")
    
    def _create_entity_in_autocad(self, element: UniversalElement):
        """إنشاء كائن جديد في AutoCAD"""
        if not self.autocad or not element.geometry:
            return
        
        try:
            msp = self.autocad.doc.ModelSpace
            
            if element.properties.element_type == ElementType.WALL:
                points = [(p.x, p.y) for p in element.geometry.points]
                entity = msp.AddLightweightPolyline(points)
                entity.Closed = True
                entity.Layer = element.properties.layer or "FA_WALLS"
            
            elif element.properties.element_type == ElementType.DOOR:
                if element.geometry.points:
                    p = element.geometry.points[0]
                    entity = msp.AddCircle(0, (p.x, p.y, p.z), 0.5)
                    entity.Layer = element.properties.layer or "FA_DOORS"
            
            if hasattr(entity, 'Handle'):
                self.element_id_map[entity.Handle] = element.element_id
            
            logger.info(f"Created entity in AutoCAD for {element.element_id}")
        
        except Exception as e:
            logger.error(f"Error creating entity in AutoCAD: {e}")
    
    def _update_entity_in_autocad(self, element: UniversalElement):
        """تحديث كائن موجود في AutoCAD"""
        if not self.autocad or not element.autocad_handle:
            return
        
        try:
            doc = self.autocad.doc
            entity = doc.HandleToObject(element.autocad_handle)
            
            if hasattr(entity, 'Layer'):
                entity.Layer = element.properties.layer or "FA_WALLS"
            
            logger.info(f"Updated entity in AutoCAD for {element.element_id}")
        
        except Exception as e:
            logger.error(f"Error updating entity in AutoCAD: {e}")
    
    def _delete_entity_in_autocad(self, element: UniversalElement):
        """حذف كائن من AutoCAD"""
        if not self.autocad or not element.autocad_handle:
            return
        
        try:
            doc = self.autocad.doc
            entity = doc.HandleToObject(element.autocad_handle)
            entity.Delete()
            
            if element.autocad_handle in self.element_id_map:
                del self.element_id_map[element.autocad_handle]
            
            logger.info(f"Deleted entity in AutoCAD for {element.element_id}")
        
        except Exception as e:
            logger.error(f"Error deleting entity in AutoCAD: {e}")
    
    def get_status(self) -> dict:
        """الحصول على حالة الـ adapter"""
        return {
            'monitoring': self.is_monitoring,
            'autocad_connected': self.autocad is not None,
            'elements_count': len(self.universal_model.elements),
            'sync_count': self.live_sync.sync_count
        }


# AutoCAD Commands
def start_fireai_sync():
    """AutoCAD command: FIREAI_START"""
    from adapters.autocad_adapter import AutoCADAdapter
    adapter = AutoCADAdapter()
    if adapter.start_monitoring():
        print("✓ FireAI Sync started!")
    else:
        print("✗ Failed to start FireAI Sync")


def stop_fireai_sync():
    """AutoCAD command: FIREAI_STOP"""
    from adapters.autocad_adapter import AutoCADAdapter
    adapter = AutoCADAdapter()
    adapter.stop_monitoring()
    print("✓ FireAI Sync stopped!")


def show_fireai_status():
    """AutoCAD command: FIREAI_STATUS"""
    from adapters.autocad_adapter import AutoCADAdapter
    adapter = AutoCADAdapter()
    status = adapter.get_status()
    
    print("\n" + "="*60)
    print("FireAI Digital Twin Status")
    print("="*60)
    print(f"Monitoring: {'ON' if status['monitoring'] else 'OFF'}")
    print(f"AutoCAD Connected: {'YES' if status['autocad_connected'] else 'NO'}")
    print(f"Elements: {status['elements_count']}")
    print(f"Sync Cycles: {status['sync_count']}")
    print("="*60 + "\n")


def export_fireai_data():
    """AutoCAD command: FIREAI_EXPORT"""
    print("Use backend API for export")