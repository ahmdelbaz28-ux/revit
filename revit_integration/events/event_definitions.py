"""
ETAP-AI-WORK Revit Integration Event Definitions
===============================================

Event types and definitions for Revit integration.

Principal Software Architect: Eng. Ahmed Elbaz
"""
from enum import Enum
from typing import Dict, Any, List


class RevitEventType(Enum):
    """Enumeration of all Revit integration event types."""
    
    # Model events
    REVIT_MODEL_IMPORTED = "RevitModelImported"
    REVIT_MODEL_SYNC_STARTED = "RevitSyncStarted"
    REVIT_MODEL_SYNC_COMPLETED = "RevitSyncCompleted"
    REVIT_INCREMENTAL_SYNC_COMPLETED = "RevitIncrementalSyncCompleted"
    REVIT_SYNC_FAILED = "RevitSyncFailed"
    REVIT_SYNC_CANCELLED = "RevitSyncCancelled"
    
    # Element events
    REVIT_ELEMENT_IMPORTED = "RevitElementImported"
    REVIT_ELEMENT_UPDATED = "RevitElementUpdated"
    REVIT_ELEMENT_PROCESSED = "RevitElementProcessed"
    
    # Topology events
    REVIT_TOPOLOGY_CHANGED = "RevitTopologyChanged"
    
    # Asset events
    ELECTRICAL_ASSET_SYNCED = "ElectricalAssetSynced"
    
    # System events
    REVIT_CONNECTION_ESTABLISHED = "RevitConnectionEstablished"
    REVIT_CONNECTION_LOST = "RevitConnectionLost"
    REVIT_ADDIN_LOADED = "RevitAddinLoaded"
    REVIT_ADDIN_UNLOADED = "RevitAddinUnloaded"
    
    # APS events
    APS_UPLOAD_STARTED = "APSUploadStarted"
    APS_UPLOAD_COMPLETED = "APSUploadCompleted"
    APS_DOWNLOAD_STARTED = "APSDownloadStarted"
    APS_DOWNLOAD_COMPLETED = "APSDownloadCompleted"
    APS_DERIVATIVE_JOB_STARTED = "APSModelDerivativeJobStarted"
    APS_DERIVATIVE_JOB_COMPLETED = "APSModelDerivativeJobCompleted"


# Define the event schema for each event type
EVENT_SCHEMAS: Dict[RevitEventType, Dict[str, Any]] = {
    RevitEventType.REVIT_MODEL_IMPORTED: {
        "required": ["model_id", "project_id", "element_count", "timestamp"],
        "optional": ["file_path", "user_id", "client_ip"]
    },
    RevitEventType.REVIT_MODEL_SYNC_STARTED: {
        "required": ["sync_id", "project_id", "timestamp"],
        "optional": ["user_id", "client_ip"]
    },
    RevitEventType.REVIT_MODEL_SYNC_COMPLETED: {
        "required": ["sync_id", "project_id", "successful_elements", "failed_elements", "total_elements", "duration", "timestamp"],
        "optional": ["user_id", "client_ip"]
    },
    RevitEventType.REVIT_INCREMENTAL_SYNC_COMPLETED: {
        "required": ["sync_id", "project_id", "successful_elements", "failed_elements", "timestamp"],
        "optional": ["user_id", "client_ip"]
    },
    RevitEventType.REVIT_SYNC_FAILED: {
        "required": ["sync_id", "project_id", "error", "timestamp"],
        "optional": ["user_id", "client_ip"]
    },
    RevitEventType.REVIT_SYNC_CANCELLED: {
        "required": ["sync_id", "timestamp"],
        "optional": ["user_id", "client_ip"]
    },
    RevitEventType.REVIT_ELEMENT_IMPORTED: {
        "required": ["element_id", "category", "target_model", "timestamp"],
        "optional": ["project_id", "user_id", "client_ip"]
    },
    RevitEventType.REVIT_ELEMENT_UPDATED: {
        "required": ["element_id", "status", "timestamp"],
        "optional": ["project_id", "user_id", "client_ip", "changes"]
    },
    RevitEventType.REVIT_ELEMENT_PROCESSED: {
        "required": ["sync_id", "element_id", "status", "timestamp"],
        "optional": ["project_id", "user_id", "client_ip"]
    },
    RevitEventType.REVIT_TOPOLOGY_CHANGED: {
        "required": ["element_id", "model_type", "change_type", "timestamp"],
        "optional": ["project_id", "user_id", "client_ip"]
    },
    RevitEventType.ELECTRICAL_ASSET_SYNCED: {
        "required": ["element_id", "asset_type", "name", "timestamp"],
        "optional": ["project_id", "user_id", "client_ip"]
    },
    RevitEventType.REVIT_CONNECTION_ESTABLISHED: {
        "required": ["connection_id", "timestamp"],
        "optional": ["revit_version", "user_id", "client_ip"]
    },
    RevitEventType.REVIT_CONNECTION_LOST: {
        "required": ["connection_id", "timestamp"],
        "optional": ["reason", "user_id", "client_ip"]
    },
    RevitEventType.REVIT_ADDIN_LOADED: {
        "required": ["addin_id", "version", "timestamp"],
        "optional": ["revit_version", "user_id", "client_ip"]
    },
    RevitEventType.APS_UPLOAD_STARTED: {
        "required": ["upload_id", "project_id", "file_path", "timestamp"],
        "optional": ["user_id", "client_ip"]
    },
    RevitEventType.APS_UPLOAD_COMPLETED: {
        "required": ["upload_id", "project_id", "file_path", "status", "timestamp"],
        "optional": ["duration", "user_id", "client_ip"]
    },
    RevitEventType.APS_DERIVATIVE_JOB_STARTED: {
        "required": ["job_id", "urn", "timestamp"],
        "optional": ["formats", "project_id", "user_id", "client_ip"]
    },
    RevitEventType.APS_DERIVATIVE_JOB_COMPLETED: {
        "required": ["job_id", "urn", "status", "timestamp"],
        "optional": ["progress", "outputs", "project_id", "user_id", "client_ip"]
    }
}


# Map of event types for easy reference
REVIT_EVENT_TYPES = {
    "RevitModelImported": RevitEventType.REVIT_MODEL_IMPORTED,
    "RevitSyncStarted": RevitEventType.REVIT_MODEL_SYNC_STARTED,
    "RevitSyncCompleted": RevitEventType.REVIT_MODEL_SYNC_COMPLETED,
    "RevitIncrementalSyncCompleted": RevitEventType.REVIT_INCREMENTAL_SYNC_COMPLETED,
    "RevitSyncFailed": RevitEventType.REVIT_SYNC_FAILED,
    "RevitSyncCancelled": RevitEventType.REVIT_SYNC_CANCELLED,
    "RevitElementImported": RevitEventType.REVIT_ELEMENT_IMPORTED,
    "RevitElementUpdated": RevitEventType.REVIT_ELEMENT_UPDATED,
    "RevitElementProcessed": RevitEventType.REVIT_ELEMENT_PROCESSED,
    "RevitTopologyChanged": RevitEventType.REVIT_TOPOLOGY_CHANGED,
    "ElectricalAssetSynced": RevitEventType.ELECTRICAL_ASSET_SYNCED,
    "RevitConnectionEstablished": RevitEventType.REVIT_CONNECTION_ESTABLISHED,
    "RevitConnectionLost": RevitEventType.REVIT_CONNECTION_LOST,
    "RevitAddinLoaded": RevitEventType.REVIT_ADDIN_LOADED,
    "APSUploadStarted": RevitEventType.APS_UPLOAD_STARTED,
    "APSUploadCompleted": RevitEventType.APS_UPLOAD_COMPLETED,
    "APSModelDerivativeJobStarted": RevitEventType.APS_DERIVATIVE_JOB_STARTED,
    "APSModelDerivativeJobCompleted": RevitEventType.APS_DERIVATIVE_JOB_COMPLETED,
}


# Event priorities (higher number = higher priority)
EVENT_PRIORITIES = {
    RevitEventType.REVIT_SYNC_FAILED: 100,
    RevitEventType.REVIT_CONNECTION_LOST: 95,
    RevitEventType.REVIT_TOPOLOGY_CHANGED: 80,
    RevitEventType.ELECTRICAL_ASSET_SYNCED: 70,
    RevitEventType.REVIT_MODEL_SYNC_COMPLETED: 60,
    RevitEventType.REVIT_ELEMENT_UPDATED: 50,
    RevitEventType.REVIT_ELEMENT_IMPORTED: 40,
    RevitEventType.REVIT_MODEL_IMPORTED: 30,
    RevitEventType.REVIT_MODEL_SYNC_STARTED: 20,
    RevitEventType.REVIT_CONNECTION_ESTABLISHED: 10,
    RevitEventType.REVIT_ADDIN_LOADED: 5,
}


# Event categories for grouping
EVENT_CATEGORIES = {
    "sync": [
        RevitEventType.REVIT_MODEL_SYNC_STARTED,
        RevitEventType.REVIT_MODEL_SYNC_COMPLETED,
        RevitEventType.REVIT_INCREMENTAL_SYNC_COMPLETED,
        RevitEventType.REVIT_SYNC_FAILED,
        RevitEventType.REVIT_SYNC_CANCELLED,
    ],
    "element": [
        RevitEventType.REVIT_ELEMENT_IMPORTED,
        RevitEventType.REVIT_ELEMENT_UPDATED,
        RevitEventType.REVIT_ELEMENT_PROCESSED,
    ],
    "topology": [
        RevitEventType.REVIT_TOPOLOGY_CHANGED,
    ],
    "asset": [
        RevitEventType.ELECTRICAL_ASSET_SYNCED,
    ],
    "connection": [
        RevitEventType.REVIT_CONNECTION_ESTABLISHED,
        RevitEventType.REVIT_CONNECTION_LOST,
        RevitEventType.REVIT_ADDIN_LOADED,
        RevitEventType.REVIT_ADDIN_UNLOADED,
    ],
    "aps": [
        RevitEventType.APS_UPLOAD_STARTED,
        RevitEventType.APS_UPLOAD_COMPLETED,
        RevitEventType.APS_DOWNLOAD_STARTED,
        RevitEventType.APS_DOWNLOAD_COMPLETED,
        RevitEventType.APS_DERIVATIVE_JOB_STARTED,
        RevitEventType.APS_DERIVATIVE_JOB_COMPLETED,
    ]
}


def validate_event_payload(event_type: RevitEventType, payload: Dict[str, Any]) -> List[str]:
    """
    Validate that an event payload contains required fields.
    
    Args:
        event_type: Type of event
        payload: Event payload to validate
        
    Returns:
        List[str]: List of validation errors
    """
    errors = []
    
    if event_type not in EVENT_SCHEMAS:
        errors.append(f"Unknown event type: {event_type}")
        return errors
    
    schema = EVENT_SCHEMAS[event_type]
    
    # Check required fields
    for field in schema["required"]:
        if field not in payload:
            errors.append(f"Missing required field: {field}")
    
    return errors