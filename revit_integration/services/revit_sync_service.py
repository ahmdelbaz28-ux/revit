"""
ETAP-AI-WORK Revit Integration Sync Service
==========================================

Service for synchronizing Revit models with the Digital Twin.

Principal Software Architect: Eng. Ahmed Elbaz
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import json
import os
from pathlib import Path

from ..dto.revit_dto import (
    RevitElementDTO, ElectricalAssetDTO, SyncStatusDTO, 
    ModelMetadataDTO, RevitProjectDTO, RevitSyncLogDTO
)
from ..adapters.revit_adapter import RevitElementAdapter
from ..mappings.category_mapper import CategoryMapper
from ..aps.data_exchange import APSDataExchange
from ..events.event_publisher import RevitEventPublisher


class RevitSyncService:
    """
    Service for synchronizing Revit models with the ETAP Digital Twin.
    Handles incremental sync, delta detection, and error recovery.
    """
    
    def __init__(self, aps_data_exchange: APSDataExchange = None):
        self.logger = logging.getLogger(__name__)
        self.element_adapter = RevitElementAdapter()
        self.category_mapper = CategoryMapper()
        self.aps_data_exchange = aps_data_exchange
        self.event_publisher = RevitEventPublisher()
        
        # Track ongoing sync operations
        self.active_syncs = {}
        
        # Cache for performance
        self.element_cache = {}
        self.sync_cache = {}
    
    async def sync_project(self, project_dto: RevitProjectDTO) -> SyncStatusDTO:
        """
        Synchronize a Revit project with the Digital Twin.
        
        Args:
            project_dto: Project information
            
        Returns:
            SyncStatusDTO: Status of the synchronization
        """
        sync_id = f"sync_{project_dto.project_id}_{int(datetime.utcnow().timestamp())}"
        
        # Create initial sync status
        sync_status = SyncStatusDTO(
            sync_id=sync_id,
            project_id=project_dto.project_id,
            status="in_progress",
            start_time=datetime.utcnow()
        )
        
        # Add to active syncs
        self.active_syncs[sync_id] = sync_status
        
        try:
            # Publish sync started event
            await self.event_publisher.publish_event("RevitSyncStarted", {
                "sync_id": sync_id,
                "project_id": project_dto.project_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Get model metadata
            if project_dto.revit_file_path:
                model_metadata = await self._get_model_metadata(project_dto.revit_file_path)
                sync_status.total_elements = model_metadata.total_elements
            else:
                # If no local file, try to get from APS
                if self.aps_data_exchange and project_dto.aps_project_id:
                    # This would involve downloading from APS
                    pass
            
            # Perform the actual sync
            processed_count = 0
            successful_count = 0
            failed_count = 0
            
            # Simulate processing elements
            # In a real implementation, this would connect to Revit API
            elements = await self._extract_elements_from_revit(project_dto)
            
            for i, element in enumerate(elements):
                try:
                    # Process element
                    processed_successfully = await self._process_element(element, project_dto)
                    
                    if processed_successfully:
                        successful_count += 1
                    else:
                        failed_count += 1
                    
                    processed_count += 1
                    
                    # Update progress
                    sync_status.processed_elements = processed_count
                    sync_status.successful_elements = successful_count
                    sync_status.failed_elements = failed_count
                    sync_status.progress = (processed_count / len(elements)) * 100.0 if elements else 0.0
                    
                    # Publish element processed event
                    await self.event_publisher.publish_event("RevitElementProcessed", {
                        "sync_id": sync_id,
                        "element_id": element.id,
                        "status": "success" if processed_successfully else "failed",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                    # Small delay to allow other operations
                    await asyncio.sleep(0.01)
                    
                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"Error processing element {i}: {e}")
            
            # Update final sync status
            sync_status.processed_elements = processed_count
            sync_status.successful_elements = successful_count
            sync_status.failed_elements = failed_count
            sync_status.progress = 100.0
            sync_status.end_time = datetime.utcnow()
            sync_status.status = "completed" if failed_count == 0 else "completed_with_errors"
            
            # Publish sync completed event
            await self.event_publisher.publish_event("RevitSyncCompleted", {
                "sync_id": sync_id,
                "project_id": project_dto.project_id,
                "successful_elements": successful_count,
                "failed_elements": failed_count,
                "total_elements": processed_count,
                "duration": (sync_status.end_time - sync_status.start_time).total_seconds(),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Update project last sync time
            project_dto.last_sync = datetime.utcnow()
            
            return sync_status
            
        except Exception as e:
            self.logger.error(f"Error during project sync: {e}")
            sync_status.status = "failed"
            sync_status.end_time = datetime.utcnow()
            sync_status.error_details = {"error": str(e)}
            
            # Publish sync failed event
            await self.event_publisher.publish_event("RevitSyncFailed", {
                "sync_id": sync_id,
                "project_id": project_dto.project_id,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return sync_status
        
        finally:
            # Remove from active syncs
            if sync_id in self.active_syncs:
                del self.active_syncs[sync_id]
    
    async def incremental_sync(self, project_id: str, changed_elements: List[RevitElementDTO]) -> SyncStatusDTO:
        """
        Perform an incremental sync of changed elements.
        
        Args:
            project_id: ID of the project
            changed_elements: List of elements that have changed
            
        Returns:
            SyncStatusDTO: Status of the incremental sync
        """
        sync_id = f"incremental_{project_id}_{int(datetime.utcnow().timestamp())}"
        
        sync_status = SyncStatusDTO(
            sync_id=sync_id,
            project_id=project_id,
            status="in_progress",
            total_elements=len(changed_elements),
            start_time=datetime.utcnow()
        )
        
        try:
            successful_count = 0
            failed_count = 0
            
            for i, element in enumerate(changed_elements):
                try:
                    # Process the changed element
                    processed_successfully = await self._process_element(element, None)
                    
                    if processed_successfully:
                        successful_count += 1
                    else:
                        failed_count += 1
                    
                    # Update progress
                    sync_status.processed_elements = i + 1
                    sync_status.successful_elements = successful_count
                    sync_status.failed_elements = failed_count
                    sync_status.progress = ((i + 1) / len(changed_elements)) * 100.0 if changed_elements else 0.0
                    
                    # Publish element updated event
                    await self.event_publisher.publish_event("RevitElementUpdated", {
                        "sync_id": sync_id,
                        "element_id": element.id,
                        "status": "success" if processed_successfully else "failed",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"Error processing changed element {element.id}: {e}")
            
            sync_status.successful_elements = successful_count
            sync_status.failed_elements = failed_count
            sync_status.end_time = datetime.utcnow()
            sync_status.status = "completed" if failed_count == 0 else "completed_with_errors"
            
            # Publish incremental sync completed event
            await self.event_publisher.publish_event("RevitIncrementalSyncCompleted", {
                "sync_id": sync_id,
                "project_id": project_id,
                "successful_elements": successful_count,
                "failed_elements": failed_count,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return sync_status
            
        except Exception as e:
            self.logger.error(f"Error during incremental sync: {e}")
            sync_status.status = "failed"
            sync_status.end_time = datetime.utcnow()
            sync_status.error_details = {"error": str(e)}
            return sync_status
    
    async def _extract_elements_from_revit(self, project_dto: RevitProjectDTO) -> List[RevitElementDTO]:
        """
        Extract elements from Revit model.
        In a real implementation, this would connect to the Revit API.
        
        Args:
            project_dto: Project information
            
        Returns:
            List[RevitElementDTO]: Extracted elements
        """
        # This is a simulation - in a real implementation, this would:
        # 1. Connect to Revit via the Revit API
        # 2. Extract elements from the model
        # 3. Convert them to DTOs
        
        elements = []
        
        if project_dto.revit_file_path and os.path.exists(project_dto.revit_file_path):
            # Simulate extracting elements from a Revit file
            # This would be replaced with actual Revit API calls
            simulated_elements = [
                RevitElementDTO(
                    id=f"ele_{i}",
                    name=f"Element_{i}",
                    category="Electrical Equipment" if i % 3 == 0 else "Rooms" if i % 3 == 1 else "Cable Tray",
                    family="Generic",
                    type="Default",
                    parameters={"Power": 100 + i, "Voltage": 480},
                    location={"x": float(i), "y": float(i*2), "z": 0.0} if i % 2 == 0 else None
                )
                for i in range(min(50, 1000))  # Simulate up to 50 elements
            ]
            elements.extend(simulated_elements)
        
        return elements
    
    async def _process_element(self, element_dto: RevitElementDTO, project_dto: Optional[RevitProjectDTO]) -> bool:
        """
        Process a single Revit element for synchronization.
        
        Args:
            element_dto: Element to process
            project_dto: Associated project (optional)
            
        Returns:
            bool: True if processing was successful
        """
        try:
            # Validate the element
            validation_result = self.category_mapper.validate_mapping({
                'id': element_dto.id,
                'name': element_dto.name,
                'category': element_dto.category,
                'parameters': element_dto.parameters
            })
            
            if not validation_result['valid']:
                self.logger.warning(f"Invalid element {element_dto.id}: {validation_result['issues']}")
                return False
            
            # Transform element to ETAP format
            etap_element = self.category_mapper.transform_for_etap({
                'id': element_dto.id,
                'name': element_dto.name,
                'category': element_dto.category,
                'parameters': element_dto.parameters,
                'location': element_dto.location,
                'geometry': element_dto.geometry,
                'level': element_dto.level,
                'workset': element_dto.workset,
                'created_at': element_dto.created_at,
                'updated_at': element_dto.updated_at
            })
            
            # Determine target model based on category
            target_model = self.category_mapper.get_target_model(element_dto.category)
            
            if target_model:
                # In a real implementation, this would sync to the appropriate ETAP model
                # For now, we'll simulate the sync process
                await self._sync_to_etap_model(etap_element, target_model.value)
            
            # Extract electrical asset if applicable
            if element_dto.category and 'electrical' in element_dto.category.lower():
                electrical_asset = self.element_adapter.extract_electrical_asset(MockRevitElement(element_dto))
                if electrical_asset:
                    await self._sync_electrical_asset(electrical_asset)
            
            # Publish element imported event
            await self.event_publisher.publish_event("RevitElementImported", {
                "element_id": element_dto.id,
                "category": element_dto.category,
                "target_model": target_model.value if target_model else "Unknown",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing element {element_dto.id}: {e}")
            return False
    
    async def _sync_to_etap_model(self, etap_element: Dict[str, Any], model_type: str) -> bool:
        """
        Sync element to appropriate ETAP model.
        
        Args:
            etap_element: Element in ETAP format
            model_type: Target model type
            
        Returns:
            bool: True if sync was successful
        """
        # In a real implementation, this would sync to the actual ETAP model
        # For now, we'll just log the sync operation
        self.logger.debug(f"Syncing element {etap_element['id']} to {model_type} model")
        
        # Publish topology changed event if it's an electrical element
        if model_type == "ElectricalModel":
            await self.event_publisher.publish_event("RevitTopologyChanged", {
                "element_id": etap_element['id'],
                "model_type": model_type,
                "change_type": "element_added",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        return True
    
    async def _sync_electrical_asset(self, electrical_asset: ElectricalAssetDTO) -> bool:
        """
        Sync electrical asset to electrical model.
        
        Args:
            electrical_asset: Electrical asset to sync
            
        Returns:
            bool: True if sync was successful
        """
        # In a real implementation, this would sync to the electrical model
        # For now, we'll just log the operation
        self.logger.debug(f"Syncing electrical asset {electrical_asset.element_id} to electrical model")
        
        # Publish electrical asset event
        await self.event_publisher.publish_event("ElectricalAssetSynced", {
            "element_id": electrical_asset.element_id,
            "asset_type": electrical_asset.asset_type,
            "name": electrical_asset.name,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return True
    
    async def _get_model_metadata(self, file_path: str) -> ModelMetadataDTO:
        """
        Get metadata from Revit model file.
        
        Args:
            file_path: Path to Revit file
            
        Returns:
            ModelMetadataDTO: Model metadata
        """
        # In a real implementation, this would read metadata from the Revit file
        # For now, we'll create a simulated metadata object
        return ModelMetadataDTO(
            model_id=os.path.basename(file_path),
            project_name=os.path.splitext(os.path.basename(file_path))[0],
            revit_version="2024",
            model_units="Imperial",
            total_elements=100,
            electrical_elements=30,
            geometry_elements=70,
            file_size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            created_date=datetime.now(),
            modified_date=datetime.now(),
            author="Simulated Author",
            organization="Simulated Organization",
            description="Simulated Revit Model"
        )
    
    async def get_active_syncs(self) -> List[SyncStatusDTO]:
        """Get list of currently active sync operations."""
        return list(self.active_syncs.values())
    
    async def cancel_sync(self, sync_id: str) -> bool:
        """
        Cancel an active sync operation.
        
        Args:
            sync_id: ID of sync to cancel
            
        Returns:
            bool: True if sync was cancelled
        """
        if sync_id in self.active_syncs:
            sync_status = self.active_syncs[sync_id]
            sync_status.status = "cancelled"
            sync_status.end_time = datetime.utcnow()
            
            # Publish sync cancelled event
            await self.event_publisher.publish_event("RevitSyncCancelled", {
                "sync_id": sync_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            del self.active_syncs[sync_id]
            return True
        
        return False


class MockRevitElement:
    """
    Mock class to simulate Revit element for adapter testing.
    In a real implementation, this would be a real Revit API element.
    """
    
    def __init__(self, element_dto: RevitElementDTO):
        self.Id = element_dto.id
        self.Name = element_dto.name
        self.Category = MockCategory(element_dto.category)
        self.Parameters = MockParameters(element_dto.parameters)
        self.Location = MockLocation(element_dto.location)
        self.Level = element_dto.level
        self.WorksetId = element_dto.workset


class MockCategory:
    def __init__(self, name: str):
        self.Name = name


class MockParameters:
    def __init__(self, params: Dict[str, Any]):
        self.params = params
        # Create mock parameter objects
        self.mock_params = []
        for name, value in params.items():
            param = MockParameter(name, value)
            self.mock_params.append(param)
    
    def __iter__(self):
        return iter(self.mock_params)


class MockParameter:
    def __init__(self, name: str, value: Any):
        self.Definition = MockParameterDef(name)
        self.HasValue = value is not None
        self.StorageType = 'String' if isinstance(value, str) else 'Double' if isinstance(value, (int, float)) else 'String'
        self._value = value
    
    def AsString(self):
        return str(self._value) if self._value is not None else ""
    
    def AsInteger(self):
        return int(self._value) if self._value is not None else 0
    
    def AsDouble(self):
        return float(self._value) if self._value is not None else 0.0
    
    def AsElementId(self):
        return str(self._value) if self._value is not None else "0"
    
    def AsValueString(self):
        return str(self._value) if self._value is not None else ""


class MockLocation:
    def __init__(self, location_data: Optional[Dict[str, float]]):
        if location_data:
            from collections import namedtuple
            Point = namedtuple('Point', ['X', 'Y', 'Z'])
            self.Point = Point(
                X=location_data.get('x', 0.0),
                Y=location_data.get('y', 0.0),
                Z=location_data.get('z', 0.0)
            )
        else:
            self.Point = None