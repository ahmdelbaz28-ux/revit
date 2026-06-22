"""
ETAP-AI-WORK Revit Integration Asset Extraction Service
====================================================

Service for extracting electrical and other assets from Revit models.

Principal Software Architect: Eng. Ahmed Elbaz
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime


class AssetExtractionService:
    """
    Service for extracting electrical and other assets from Revit models.
    Identifies and extracts equipment, devices, and components for downstream processing.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def extract_electrical_assets(self, model_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract electrical assets from model elements.
        
        Args:
            model_elements: List of model elements to extract assets from
            
        Returns:
            List[Dict]: Extracted electrical assets
        """
        electrical_assets = []
        
        for element in model_elements:
            category = element.get('category', '').lower()
            
            # Identify electrical equipment
            if any(keyword in category for keyword in ['electrical', 'panel', 'transformer', 'switch', 'circuit']):
                asset = {
                    'element_id': element.get('id'),
                    'name': element.get('name', ''),
                    'asset_type': self._classify_electrical_asset_type(element),
                    'category': element.get('category'),
                    'parameters': element.get('parameters', {}),
                    'location': element.get('location'),
                    'connections': [],  # Will be populated with connected elements
                    'created_at': datetime.utcnow().isoformat()
                }
                electrical_assets.append(asset)
        
        self.logger.info(f"Extracted {len(electrical_assets)} electrical assets")
        return electrical_assets
    
    async def extract_mechanical_assets(self, model_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract mechanical assets from model elements.
        
        Args:
            model_elements: List of model elements to extract assets from
            
        Returns:
            List[Dict]: Extracted mechanical assets
        """
        mechanical_assets = []
        
        for element in model_elements:
            category = element.get('category', '').lower()
            
            # Identify mechanical equipment
            if any(keyword in category for keyword in ['mechanical', 'hvac', 'duct', 'pipe', 'equipment']):
                asset = {
                    'element_id': element.get('id'),
                    'name': element.get('name', ''),
                    'asset_type': self._classify_mechanical_asset_type(element),
                    'category': element.get('category'),
                    'parameters': element.get('parameters', {}),
                    'location': element.get('location'),
                    'created_at': datetime.utcnow().isoformat()
                }
                mechanical_assets.append(asset)
        
        self.logger.info(f"Extracted {len(mechanical_assets)} mechanical assets")
        return mechanical_assets
    
    async def extract_structural_assets(self, model_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract structural assets from model elements.
        
        Args:
            model_elements: List of model elements to extract assets from
            
        Returns:
            List[Dict]: Extracted structural assets
        """
        structural_assets = []
        
        for element in model_elements:
            category = element.get('category', '').lower()
            
            # Identify structural elements
            if any(keyword in category for keyword in ['structural', 'column', 'beam', 'foundation', 'member']):
                asset = {
                    'element_id': element.get('id'),
                    'name': element.get('name', ''),
                    'asset_type': self._classify_structural_asset_type(element),
                    'category': element.get('category'),
                    'parameters': element.get('parameters', {}),
                    'location': element.get('location'),
                    'created_at': datetime.utcnow().isoformat()
                }
                structural_assets.append(asset)
        
        self.logger.info(f"Extracted {len(structural_assets)} structural assets")
        return structural_assets
    
    async def extract_spatial_elements(self, model_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract spatial elements (rooms, spaces, areas) from model.
        
        Args:
            model_elements: List of model elements to extract from
            
        Returns:
            List[Dict]: Extracted spatial elements
        """
        spatial_elements = []
        
        for element in model_elements:
            category = element.get('category', '').lower()
            
            # Identify spatial elements
            if any(keyword in category for keyword in ['room', 'space', 'area']):
                spatial_element = {
                    'element_id': element.get('id'),
                    'name': element.get('name', ''),
                    'element_type': 'spatial',
                    'category': element.get('category'),
                    'parameters': element.get('parameters', {}),
                    'location': element.get('location'),
                    'geometry': element.get('geometry'),
                    'created_at': datetime.utcnow().isoformat()
                }
                spatial_elements.append(spatial_element)
        
        self.logger.info(f"Extracted {len(spatial_elements)} spatial elements")
        return spatial_elements
    
    def _classify_electrical_asset_type(self, element: Dict[str, Any]) -> str:
        """Classify the type of electrical asset."""
        category = element.get('category', '').lower()
        name = element.get('name', '').lower()
        
        if 'transformer' in category or 'transformer' in name:
            return 'Transformer'
        elif 'panel' in category or 'panel' in name:
            return 'Panelboard'
        elif 'switch' in category or 'switch' in name:
            return 'Switchgear'
        elif 'motor' in category or 'motor' in name:
            return 'Motor'
        elif 'generator' in category or 'generator' in name:
            return 'Generator'
        else:
            return 'ElectricalEquipment'
    
    def _classify_mechanical_asset_type(self, element: Dict[str, Any]) -> str:
        """Classify the type of mechanical asset."""
        category = element.get('category', '').lower()
        name = element.get('name', '').lower()
        
        if 'hvac' in category or 'air' in category:
            return 'HVACEquipment'
        elif 'duct' in category:
            return 'DuctWork'
        elif 'pipe' in category:
            return 'Piping'
        else:
            return 'MechanicalEquipment'
    
    def _classify_structural_asset_type(self, element: Dict[str, Any]) -> str:
        """Classify the type of structural asset."""
        category = element.get('category', '').lower()
        name = element.get('name', '').lower()
        
        if 'column' in category or 'column' in name:
            return 'StructuralColumn'
        elif 'beam' in category or 'beam' in name:
            return 'StructuralBeam'
        elif 'foundation' in category or 'footing' in name:
            return 'Foundation'
        else:
            return 'StructuralMember'
    
    async def get_asset_connections(self, model_elements: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Identify connections between assets.
        
        Args:
            model_elements: List of model elements to analyze
            
        Returns:
            Dict: Mapping of element_id to connected element_ids
        """
        connections = {}
        
        # In a real implementation, this would analyze geometric relationships,
        # electrical circuits, piping networks, etc.
        # For now, we'll simulate simple connections
        
        for i, element in enumerate(model_elements):
            element_id = element.get('id')
            # Connect to next element if it exists and is electrical
            if i < len(model_elements) - 1 and 'electrical' in element.get('category', '').lower():
                connections[element_id] = [model_elements[i + 1].get('id')]
        
        return connections