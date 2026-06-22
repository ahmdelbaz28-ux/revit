"""
ETAP-AI-WORK Revit Integration Category Mapper
=============================================

Maps Revit categories to ETAP models and systems.

Principal Software Architect: Eng. Ahmed Elbaz
"""
from typing import Dict, List, Optional, Any
import logging
from enum import Enum


class ETAPModelType(Enum):
    """Types of ETAP models that Revit elements map to."""
    ELECTRICAL = "ElectricalModel"
    GIS = "GISModel"
    SCADA = "SCADAModel"
    STRUCTURAL = "StructuralModel"
    MECHANICAL = "MechanicalModel"
    SAFETY = "SafetyModel"


class CategoryMapper:
    """
    Maps Revit categories to ETAP models and systems.
    Provides category-specific transformation logic.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Mapping from Revit categories to ETAP models
        self.category_to_model_map = {
            # Electrical Equipment
            'Electrical Equipment': ETAPModelType.ELECTRICAL,
            'Electrical Fixtures': ETAPModelType.ELECTRICAL,
            'Data Devices': ETAPModelType.SAFETY,
            'Fire Alarm Devices': ETAPModelType.SAFETY,
            'Security Devices': ETAPModelType.SAFETY,
            'Nurse Call Devices': ETAPModelType.SAFETY,
            
            # Power Systems
            'Electrical Circuits': ETAPModelType.ELECTRICAL,
            'Power Circuits': ETAPModelType.ELECTRICAL,
            'Electrical Panel': ETAPModelType.ELECTRICAL,
            'Switch Systems': ETAPModelType.ELECTRICAL,
            
            # Infrastructure
            'Cable Tray': ETAPModelType.ELECTRICAL,
            'Conduit': ETAPModelType.ELECTRICAL,
            'Wire': ETAPModelType.ELECTRICAL,
            'Flex Duct': ETAPModelType.MECHANICAL,
            'Flex Pipe': ETAPModelType.MECHANICAL,
            
            # Spatial
            'Rooms': ETAPModelType.GIS,
            'Spaces': ETAPModelType.GIS,
            'Areas': ETAPModelType.GIS,
            
            # Structural
            'Structural Columns': ETAPModelType.STRUCTURAL,
            'Structural Framing': ETAPModelType.STRUCTURAL,
            'Structural Foundations': ETAPModelType.STRUCTURAL,
            
            # Architectural
            'Doors': ETAPModelType.GIS,
            'Windows': ETAPModelType.GIS,
            'Walls': ETAPModelType.GIS,
            'Floors': ETAPModelType.GIS,
            'Roofs': ETAPModelType.GIS,
        }
        
        # Detailed mapping for specific equipment types
        self.equipment_type_map = {
            # Transformers
            'Transformer': 'Transformer',
            'Power Transformer': 'Transformer',
            'Distribution Transformer': 'Transformer',
            
            # Switchgear
            'Switchgear': 'Switchgear',
            'Switchboard': 'Switchboard',
            'Panelboard': 'Panelboard',
            'Circuit Breaker Panel': 'Panelboard',
            
            # Motor Control Centers
            'Motor Control Center': 'MotorControlCenter',
            'MCC': 'MotorControlCenter',
            
            # Power Distribution Units
            'Power Distribution Unit': 'PowerDistributionUnit',
            'PDU': 'PowerDistributionUnit',
            
            # UPS Systems
            'UPS': 'UninterruptiblePowerSupply',
            'Uninterruptible Power Supply': 'UninterruptiblePowerSupply',
            
            # Generators
            'Generator': 'Generator',
            'Emergency Generator': 'Generator',
            'Backup Generator': 'Generator',
        }
    
    def get_target_model(self, revit_category: str) -> Optional[ETAPModelType]:
        """
        Get the target ETAP model for a Revit category.
        
        Args:
            revit_category: Name of the Revit category
            
        Returns:
            ETAPModelType: Target model type or None if not mapped
        """
        return self.category_to_model_map.get(revit_category)
    
    def map_category_to_attributes(self, revit_category: str) -> Dict[str, Any]:
        """
        Map a Revit category to ETAP attributes.
        
        Args:
            revit_category: Name of the Revit category
            
        Returns:
            Dict: Mapped attributes for ETAP
        """
        attributes = {
            'etap_model_type': self.get_target_model(revit_category),
            'is_electrical': 'electrical' in revit_category.lower() or 
                           any(equip in revit_category.lower() for equip in ['panel', 'transformer', 'switch']),
            'is_spatial': revit_category.lower() in ['rooms', 'spaces', 'areas'],
            'requires_gis': revit_category.lower() in ['rooms', 'spaces', 'areas', 'doors', 'windows', 'walls'],
            'is_infrastructure': revit_category.lower() in ['cable tray', 'conduit', 'wire'],
            'priority': self._get_priority(revit_category)
        }
        
        return attributes
    
    def _get_priority(self, category: str) -> int:
        """Get processing priority for category."""
        priority_map = {
            'Electrical Equipment': 1,
            'Electrical Panel': 1,
            'Power Circuits': 2,
            'Cable Tray': 3,
            'Conduit': 3,
            'Rooms': 4,
            'Spaces': 4,
            'Electrical Circuits': 5,
        }
        return priority_map.get(category, 10)  # Default low priority
    
    def classify_equipment_type(self, equipment_name: str, category: str) -> str:
        """
        Classify equipment type based on name and category.
        
        Args:
            equipment_name: Name of the equipment
            category: Revit category
            
        Returns:
            str: Classified equipment type
        """
        # First try to match against specific equipment types
        for key, value in self.equipment_type_map.items():
            if key.lower() in equipment_name.lower() or key.lower() in category.lower():
                return value
        
        # If no specific match, use category-based classification
        if 'electrical' in category.lower():
            if 'panel' in category.lower():
                return 'Panelboard'
            elif 'transformer' in category.lower():
                return 'Transformer'
            else:
                return 'ElectricalEquipment'
        elif 'room' in category.lower() or 'space' in category.lower():
            return 'SpatialElement'
        else:
            return 'GeneralEquipment'
    
    def get_required_parameters(self, equipment_type: str) -> List[str]:
        """
        Get required parameters for specific equipment type.
        
        Args:
            equipment_type: Type of equipment
            
        Returns:
            List[str]: Required parameter names
        """
        required_params = {
            'Transformer': ['VoltageRating', 'PowerRating', 'Efficiency', 'Impedance'],
            'Panelboard': ['VoltageRating', 'CurrentRating', 'PoleCount', 'InterruptingRating'],
            'Switchgear': ['VoltageRating', 'CurrentRating', 'ShortCircuitRating'],
            'MotorControlCenter': ['VoltageRating', 'CurrentRating', 'MotorCount'],
            'Generator': ['PowerRating', 'VoltageRating', 'Frequency', 'FuelType'],
            'UninterruptiblePowerSupply': ['PowerRating', 'Runtime', 'Efficiency'],
            'PowerDistributionUnit': ['VoltageRating', 'OutletCount', 'CurrentRating'],
            'ElectricalEquipment': ['Voltage', 'Power', 'ModelNumber'],
            'SpatialElement': ['Area', 'Volume', 'Perimeter', 'Level'],
            'GeneralEquipment': ['ModelNumber', 'Manufacturer', 'SerialNumber']
        }
        
        return required_params.get(equipment_type, ['ModelNumber', 'Manufacturer'])
    
    def validate_mapping(self, revit_element_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that Revit element data can be properly mapped to ETAP.
        
        Args:
            revit_element_data: Raw Revit element data
            
        Returns:
            Dict: Validation results
        """
        validation_result = {
            'valid': True,
            'issues': [],
            'recommended_action': 'process',
            'mapped_attributes': {}
        }
        
        category = revit_element_data.get('category', 'Unknown')
        name = revit_element_data.get('name', 'Unknown')
        
        # Check if category is supported
        if category not in self.category_to_model_map:
            validation_result['valid'] = False
            validation_result['issues'].append(f"Unsupported category: {category}")
            validation_result['recommended_action'] = 'skip'
        
        # Check if required parameters are present
        equipment_type = self.classify_equipment_type(name, category)
        required_params = self.get_required_parameters(equipment_type)
        
        parameters = revit_element_data.get('parameters', {})
        missing_params = []
        
        for param in required_params:
            if param not in parameters:
                missing_params.append(param)
        
        if missing_params:
            validation_result['issues'].append(f"Missing required parameters: {missing_params}")
            if equipment_type in ['Transformer', 'Panelboard', 'Switchgear']:
                validation_result['recommended_action'] = 'flag_for_review'
        
        # Get mapped attributes
        validation_result['mapped_attributes'] = self.map_category_to_attributes(category)
        
        return validation_result
    
    def transform_for_etap(self, revit_element_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Revit element data to ETAP-compatible format.
        
        Args:
            revit_element_data: Raw Revit element data
            
        Returns:
            Dict: ETAP-compatible element data
        """
        category = revit_element_data.get('category', 'Unknown')
        name = revit_element_data.get('name', 'Unknown')
        
        # Get equipment type
        equipment_type = self.classify_equipment_type(name, category)
        
        # Map category to attributes
        etap_attributes = self.map_category_to_attributes(category)
        
        # Transform parameters
        transformed_params = self._transform_parameters(
            revit_element_data.get('parameters', {}),
            equipment_type
        )
        
        # Create ETAP-compatible element
        etap_element = {
            'id': revit_element_data.get('id', ''),
            'name': name,
            'equipment_type': equipment_type,
            'category': category,
            'etap_model_type': etap_attributes['etap_model_type'].value if etap_attributes['etap_model_type'] else 'Unknown',
            'parameters': transformed_params,
            'location': revit_element_data.get('location'),
            'geometry': revit_element_data.get('geometry'),
            'level': revit_element_data.get('level'),
            'workset': revit_element_data.get('workset'),
            'is_electrical': etap_attributes['is_electrical'],
            'requires_gis': etap_attributes['requires_gis'],
            'priority': etap_attributes['priority'],
            'created_at': revit_element_data.get('created_at'),
            'updated_at': revit_element_data.get('updated_at')
        }
        
        return etap_element
    
    def _transform_parameters(self, parameters: Dict[str, Any], equipment_type: str) -> Dict[str, Any]:
        """
        Transform Revit parameters to ETAP-compatible parameters.
        
        Args:
            parameters: Original Revit parameters
            equipment_type: Type of equipment
            
        Returns:
            Dict: Transformed parameters
        """
        transformed = {}
        
        # Common parameter transformations
        parameter_transformations = {
            # Voltage parameters
            'Voltage': 'VoltageRating',
            'Nominal Voltage': 'VoltageRating',
            'Primary Voltage': 'PrimaryVoltage',
            'Secondary Voltage': 'SecondaryVoltage',
            
            # Power parameters
            'Power': 'PowerRating',
            'Rated Power': 'PowerRating',
            'Capacity': 'PowerRating',
            'KW': 'PowerRating_kW',
            'KVA': 'PowerRating_kVA',
            
            # Current parameters
            'Current': 'CurrentRating',
            'Amps': 'CurrentRating_A',
            'Amperage': 'CurrentRating_A',
            
            # Physical parameters
            'Height': 'Height_mm',
            'Width': 'Width_mm',
            'Depth': 'Depth_mm',
            'Weight': 'Weight_kg',
            
            # Manufacturer info
            'Manufacturer': 'Manufacturer',
            'Model': 'ModelNumber',
            'Model Number': 'ModelNumber',
            'Serial Number': 'SerialNumber',
            'SerialNumber': 'SerialNumber',
            
            # Electrical characteristics
            'Efficiency': 'Efficiency_Percent',
            'Power Factor': 'PowerFactor',
            'Frequency': 'Frequency_Hz',
            'Poles': 'PoleCount',
            'Phases': 'PhaseCount',
        }
        
        for revit_param, etap_param in parameter_transformations.items():
            if revit_param in parameters:
                transformed[etap_param] = parameters[revit_param]
        
        # Add any remaining parameters that don't have specific mappings
        for param_name, param_value in parameters.items():
            if param_name not in parameter_transformations and param_name not in transformed:
                transformed[f"revit_{param_name}"] = param_value
        
        return transformed