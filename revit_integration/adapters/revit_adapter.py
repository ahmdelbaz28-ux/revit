"""
ETAP-AI-WORK Revit Integration Adapters
=======================================

Adapters for translating between Revit and ETAP data structures.

Principal Software Architect: Eng. Ahmed Elbaz
"""
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod
import logging

from ..dto.revit_dto import RevitElementDTO, ElectricalAssetDTO


class IRevitAdapter(ABC):
    """Interface for Revit adapters."""
    
    @abstractmethod
    def convert_to_dto(self, revit_element: Any) -> RevitElementDTO:
        """Convert Revit element to DTO."""
        pass
    
    @abstractmethod
    def extract_electrical_asset(self, revit_element: Any) -> Optional[ElectricalAssetDTO]:
        """Extract electrical asset information from Revit element."""
        pass


class RevitElementAdapter(IRevitAdapter):
    """
    Adapter for converting Revit elements to DTOs.
    Translates Revit API objects to standardized DTOs.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def convert_to_dto(self, revit_element: Any) -> RevitElementDTO:
        """
        Convert a Revit element to RevitElementDTO.
        
        Args:
            revit_element: Raw Revit element object
            
        Returns:
            RevitElementDTO: Standardized element representation
        """
        try:
            # Extract basic properties
            element_id = str(getattr(revit_element, 'Id', ''))
            name = getattr(revit_element, 'Name', '') or getattr(revit_element, 'FamilyName', '')
            
            # Extract category
            category = getattr(getattr(revit_element, 'Category', None), 'Name', 'Unknown')
            
            # Extract family and type info
            family = getattr(getattr(revirt_element, 'Family', None), 'Name', '') if hasattr(revit_element, 'Family') else ''
            element_type = getattr(getattr(revit_element, 'Symbol', None), 'FamilyName', '') if hasattr(revit_element, 'Symbol') else ''
            
            # Extract parameters
            parameters = self._extract_parameters(revit_element)
            
            # Extract location
            location = self._extract_location(revit_element)
            
            # Extract geometry
            geometry = self._extract_geometry(revit_element)
            
            # Extract level and workset
            level = getattr(revit_element, 'Level', None)
            workset = getattr(revit_element, 'WorksetId', None)
            
            return RevitElementDTO(
                id=element_id,
                name=name or f"Element_{element_id}",
                category=category,
                family=family,
                type=element_type,
                parameters=parameters,
                location=location,
                geometry=geometry,
                level=str(level) if level else None,
                workset=str(workset) if workset else None
            )
            
        except Exception as e:
            self.logger.error(f"Error converting Revit element to DTO: {e}")
            # Return minimal DTO on error
            return RevitElementDTO(
                id=str(getattr(revit_element, 'Id', 'unknown')),
                name=f"Element_{getattr(revit_element, 'Id', 'unknown')}",
                category='Unknown'
            )
    
    def extract_electrical_asset(self, revit_element: Any) -> Optional[ElectricalAssetDTO]:
        """
        Extract electrical asset information from a Revit element.
        
        Args:
            revit_element: Raw Revit element object
            
        Returns:
            ElectricalAssetDTO: Electrical asset representation, or None if not applicable
        """
        try:
            # Check if element is electrical equipment
            category = getattr(getattr(revit_element, 'Category', None), 'Name', '')
            if 'electrical' not in category.lower() and 'panel' not in category.lower():
                return None
            
            element_id = str(getattr(revit_element, 'Id', ''))
            name = getattr(revit_element, 'Name', '') or getattr(revit_element, 'FamilyName', '')
            
            # Determine asset type based on category
            if 'panel' in category.lower():
                asset_type = 'ElectricalPanel'
            elif 'transformer' in category.lower():
                asset_type = 'Transformer'
            elif 'switchboard' in category.lower():
                asset_type = 'Switchboard'
            else:
                asset_type = 'ElectricalEquipment'
            
            # Extract electrical parameters
            parameters = self._extract_parameters(revit_element)
            electrical_params = self._extract_electrical_parameters(parameters)
            
            # Extract location coordinates
            location = self._extract_location(revit_element)
            
            return ElectricalAssetDTO(
                element_id=element_id,
                asset_type=asset_type,
                name=name or f"Asset_{element_id}",
                voltage_rating=electrical_params.get('voltage'),
                power_rating=electrical_params.get('power'),
                manufacturer=parameters.get('Manufacturer', ''),
                model=parameters.get('Model', ''),
                serial_number=parameters.get('SerialNumber', ''),
                capacity=electrical_params.get('capacity'),
                connections=[],  # Will be populated during sync
                location_coordinates=location,
                electrical_parameters=electrical_params
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting electrical asset from Revit element: {e}")
            return None
    
    def _extract_parameters(self, revit_element: Any) -> Dict[str, Any]:
        """Extract parameters from Revit element."""
        parameters = {}
        try:
            if hasattr(revit_element, 'Parameters'):
                for param in revit_element.Parameters:
                    try:
                        param_name = param.Definition.Name if hasattr(param, 'Definition') else 'Unknown'
                        param_value = self._get_parameter_value(param)
                        if param_name and param_value is not None:
                            parameters[param_name] = param_value
                    except:
                        continue
        except:
            pass
        return parameters
    
    def _get_parameter_value(self, parameter):
        """Get value from Revit parameter."""
        try:
            if parameter.HasValue:
                if parameter.StorageType == 'String':
                    return parameter.AsString()
                elif parameter.StorageType == 'Integer':
                    return parameter.AsInteger()
                elif parameter.StorageType == 'Double':
                    return parameter.AsDouble()
                elif parameter.StorageType == 'ElementId':
                    return str(parameter.AsElementId())
                else:
                    return str(parameter.AsValueString())
        except:
            return None
    
    def _extract_location(self, revit_element: Any) -> Optional[Dict[str, float]]:
        """Extract location from Revit element."""
        try:
            location = getattr(revit_element, 'Location', None)
            if location and hasattr(location, 'Point'):
                point = location.Point
                return {
                    'x': float(point.X),
                    'y': float(point.Y),
                    'z': float(point.Z)
                }
        except:
            pass
        return None
    
    def _extract_geometry(self, revit_element: Any) -> Optional[Dict[str, Any]]:
        """Extract geometry information from Revit element."""
        try:
            # This is a simplified geometry extraction
            # In a real implementation, this would extract detailed geometry
            geometry_info = {
                'has_geometry': True,
                'geometry_type': 'Unknown'  # Would be determined based on element type
            }
            return geometry_info
        except:
            return None
    
    def _extract_electrical_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Extract electrical-specific parameters."""
        electrical_params = {}
        
        # Look for common electrical parameter names
        for key, value in parameters.items():
            if 'voltage' in key.lower():
                electrical_params['voltage'] = value
            elif 'power' in key.lower() or 'watt' in key.lower():
                electrical_params['power'] = value
            elif 'capacity' in key.lower() or 'rating' in key.lower():
                electrical_params['capacity'] = value
            elif 'amperage' in key.lower() or 'current' in key.lower():
                electrical_params['current'] = value
            elif 'frequency' in key.lower():
                electrical_params['frequency'] = value
        
        return electrical_params


class ETAPDataAdapter:
    """
    Adapter for converting DTOs to ETAP-compatible formats.
    Transforms standardized DTOs to ETAP-specific data structures.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def convert_to_etap_format(self, dto: RevitElementDTO) -> Dict[str, Any]:
        """
        Convert RevitElementDTO to ETAP-compatible format.
        
        Args:
            dto: Standardized element DTO
            
        Returns:
            Dict: ETAP-compatible data structure
        """
        etap_format = {
            'id': dto.id,
            'name': dto.name,
            'category': dto.category,
            'family': dto.family,
            'type': dto.type,
            'parameters': dto.parameters,
            'location': dto.location,
            'geometry': dto.geometry,
            'level': dto.level,
            'workset': dto.workset,
            'etap_specific': {
                'mapped_category': self._map_category_to_etap(dto.category),
                'is_electrical': self._is_electrical_equipment(dto.category)
            }
        }
        return etap_format
    
    def _map_category_to_etap(self, category: str) -> str:
        """Map Revit category to ETAP category."""
        mapping = {
            'Electrical Equipment': 'ElectricalAsset',
            'Electrical Fixtures': 'ElectricalFixture',
            'Data Devices': 'CommunicationsDevice',
            'Fire Alarm Devices': 'SafetyDevice',
            'Lighting Fixtures': 'LightingEquipment',
            'Mechanical Equipment': 'MechanicalAsset',
            'Plumbing Fixtures': 'PlumbingAsset',
            'Structural Framing': 'StructuralMember',
            'Doors': 'ArchitecturalOpening',
            'Windows': 'ArchitecturalOpening',
            'Rooms': 'SpatialElement',
            'Spaces': 'SpatialElement',
            'Cable Tray': 'CableManagement',
            'Conduit': 'CableManagement'
        }
        return mapping.get(category, category)
    
    def _is_electrical_equipment(self, category: str) -> bool:
        """Check if category represents electrical equipment."""
        electrical_keywords = [
            'electrical', 'panel', 'transformer', 'switch', 
            'breaker', 'circuit', 'lighting', 'power'
        ]
        cat_lower = category.lower()
        return any(keyword in cat_lower for keyword in electrical_keywords)


class IFCAdapter:
    """
    Adapter for IFC fallback workflow.
    Converts between IFC format and DTOs when direct Revit API is unavailable.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def import_from_ifc(self, ifc_file_path: str) -> List[RevitElementDTO]:
        """
        Import elements from IFC file to DTOs.
        
        Args:
            ifc_file_path: Path to IFC file
            
        Returns:
            List[RevitElementDTO]: Imported elements as DTOs
        """
        # Placeholder implementation
        # In a real implementation, this would parse IFC files
        # using an IFC parsing library like ifcopenshell
        self.logger.warning("IFC import is not yet implemented")
        return []
    
    def export_to_ifc(self, elements: List[RevitElementDTO], ifc_file_path: str) -> bool:
        """
        Export DTOs to IFC file.
        
        Args:
            elements: Elements to export
            ifc_file_path: Output IFC file path
            
        Returns:
            bool: True if successful
        """
        # Placeholder implementation
        self.logger.warning("IFC export is not yet implemented")
        return False


class GeoJSONAdapter:
    """
    Adapter for GeoJSON export workflow.
    Converts Revit geometry to GeoJSON format for GIS integration.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def convert_to_geojson(self, elements: List[RevitElementDTO]) -> Dict[str, Any]:
        """
        Convert Revit elements to GeoJSON format.
        
        Args:
            elements: List of Revit elements to convert
            
        Returns:
            Dict: GeoJSON feature collection
        """
        features = []
        
        for element in elements:
            if element.location and element.geometry:
                feature = {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [element.location['x'], element.location['y']]
                    },
                    'properties': {
                        'id': element.id,
                        'name': element.name,
                        'category': element.category,
                        'family': element.family,
                        'type': element.type
                    }
                }
                features.append(feature)
        
        geojson = {
            'type': 'FeatureCollection',
            'features': features
        }
        
        return geojson